import asyncio
import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import BusinessEventAction
from app.audit.events import record
from app.audit.snapshots import snapshot_candidate
from app.auth import get_current_user, require_write
from app.candidates.models import Candidate
from app.candidates.schemas import (
    CandidateListResponse,
    CandidateResponse,
    CreateCandidateRequest,
    UpdateCandidateRequest,
)
from app.database import get_db
from app.users.models import User

_DUPLICATE_THRESHOLD = 0.015


try:
    from app.worker.tasks import es_index_candidate_task
    from app.worker.tasks import es_remove_candidate_task as _es_remove_task

    def _enqueue_es_index(candidate_id: str) -> None:
        """Fire-and-forget: enqueue ES indexing task."""
        try:
            es_index_candidate_task.delay(candidate_id)
        except Exception:  # noqa: BLE001
            pass

    def _enqueue_es_remove(candidate_id: str) -> None:
        """Fire-and-forget: enqueue ES removal task."""
        try:
            _es_remove_task.delay(candidate_id)
        except Exception:  # noqa: BLE001
            pass

except Exception:  # noqa: BLE001  — Celery unavailable (e.g. test environment without broker)
    def _enqueue_es_index(candidate_id: str) -> None:  # type: ignore[misc]
        pass

    def _enqueue_es_remove(candidate_id: str) -> None:  # type: ignore[misc]
        pass


async def find_similar_candidate(
    db: AsyncSession, vec: list[float], threshold: float = _DUPLICATE_THRESHOLD
) -> Candidate | None:
    vec_str = "[" + ",".join(map(str, vec)) + "]"
    await db.execute(text("SET LOCAL ivfflat.probes = 100"))
    result = await db.execute(
        select(Candidate)
        .where(
            Candidate.embedding.is_not(None),
            Candidate.deleted_at.is_(None),
            text("embedding <=> CAST(:vec AS vector) < :threshold"),
        )
        .order_by(text("embedding <=> CAST(:vec AS vector)"))
        .limit(1)
        .params(vec=vec_str, threshold=threshold)
    )
    return result.scalar_one_or_none()

router = APIRouter(prefix="/candidates", tags=["candidates"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


def _skill_ilike_clauses(skills: list[str]) -> list:
    """Return OR-able clauses: any element in candidates.skills ILIKE %skill%."""
    clauses = []
    for i, s in enumerate(skills):
        param = f"_sk{i}"
        clauses.append(
            text(
                f"EXISTS (SELECT 1 FROM jsonb_array_elements_text(candidates.skills) _e"
                f" WHERE lower(_e) LIKE :{param})"
            ).bindparams(**{param: f"%{s.strip().lower()}%"})
        )
    return clauses


@router.post(
    "",
    response_model=CandidateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_candidate(
    request: Request,
    body: CreateCandidateRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
) -> Candidate:
    if body.email:
        existing = await db.execute(
            select(Candidate).where(
                Candidate.email == body.email,
                Candidate.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Active candidate with email '{body.email}' already exists",
            )
    candidate = Candidate(
        file_id=body.file_id,
        name=body.name,
        email=body.email,
        phone=body.phone,
        skills=body.skills,
        years_experience=body.years_experience,
        education=[e.model_dump() for e in body.education],
        work_experiences=[e.model_dump() for e in body.work_experiences],
        location=body.location,
        seniority=body.seniority,
        summary=body.summary,
        desired_position=body.desired_position,
        certifications=body.certifications,
        languages=body.languages,
        linkedin_url=body.linkedin_url,
        github_url=body.github_url,
        desired_salary=body.desired_salary,
    )
    db.add(candidate)
    await db.flush()
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.CANDIDATE_CREATED,
        resource_type="candidate",
        resource_id=candidate.id,
        request_id=getattr(request.state, "request_id", None),
        after=snapshot_candidate(candidate),
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Active candidate with email '{body.email}' already exists",
        )
    _enqueue_es_index(str(candidate.id))
    return candidate


@router.get(
    "",
    response_model=list[CandidateResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user)],
)
async def list_candidates(db: DbDep) -> list[Candidate]:
    result = await db.execute(
        select(Candidate)
        .where(Candidate.deleted_at.is_(None))
        .order_by(Candidate.created_at.desc())
    )
    return list(result.scalars().all())


@router.get(
    "/search",
    response_model=CandidateListResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user)],
)
async def search_candidates(
    db: DbDep,
    q: str | None = Query(
        default=None,
        description="Full-text search: name, position, skills, summary (BM25 + synonyms via ES; ILIKE fallback)",
    ),
    skills: list[str] = Query(default=[], description="Any-of skill filter (synonym-expanded)"),
    seniority: str | None = Query(default=None),
    status: str | None = Query(default=None, description="Filter by candidate status (active, hired, archived)"),
    location: str | None = Query(default=None, description="Location filter"),
    years_min: float | None = Query(default=None, ge=0),
    years_max: float | None = Query(default=None, ge=0),
    desired_salary_min: int | None = Query(default=None, ge=0),
    desired_salary_max: int | None = Query(default=None, ge=0),
    certification: str | None = Query(default=None, description="Certification filter"),
    resume_language: str | None = Query(default=None, description="Filter by resume language (en, ru, hy)"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> CandidateListResponse:
    """Search candidates via Elasticsearch (BM25, synonyms, facets).

    Falls back to Postgres ILIKE search when Elasticsearch is not configured.
    """
    from app.search.service import search_candidates as _es_search

    es_result = await _es_search(
        q=q,
        skills=skills or None,
        seniority=seniority,
        location=location,
        years_min=years_min,
        years_max=years_max,
        desired_salary_min=desired_salary_min,
        desired_salary_max=desired_salary_max,
        certification=certification,
        status=status,
        resume_language=resume_language,
        page=page,
        size=size,
    )

    _has_search_criteria = any([
        q,
        skills,
        seniority,
        status,
        location,
        years_min is not None,
        years_max is not None,
        desired_salary_min is not None,
        desired_salary_max is not None,
        certification,
        resume_language,
    ])

    # Use ES results unless the index is empty for an unfiltered list view.
    # An empty index must never silently blank the candidates list (which also
    # feeds the dashboard and command palette), so fall through to the Postgres
    # path when ES returns nothing and no search criteria were supplied. A real
    # query that legitimately matches nothing still returns empty via the ES path.
    if es_result is not None and not (
        es_result["total"] == 0 and not _has_search_criteria
    ):
        # ES path: fetch ordered candidates from Postgres by the returned IDs
        candidate_ids_str = es_result["candidate_ids"]
        total: int = es_result["total"]
        facets = es_result["facets"]

        if not candidate_ids_str:
            return CandidateListResponse.build(
                items=[], total=total, page=page, size=size, facets=facets
            )

        import uuid as _uuid
        candidate_ids = [_uuid.UUID(cid) for cid in candidate_ids_str]

        # Fetch in the ES-ranked order using CASE WHEN for ordering
        from sqlalchemy import case

        order_map = case(
            {cid: idx for idx, cid in enumerate(candidate_ids)},
            value=Candidate.id,
        )
        rows = await db.execute(
            select(Candidate)
            .where(Candidate.id.in_(candidate_ids))
            .order_by(order_map)
        )
        candidates_map = {c.id: c for c in rows.scalars().all()}
        # Preserve ES rank order
        items = [
            CandidateResponse.model_validate(candidates_map[cid])
            for cid in candidate_ids
            if cid in candidates_map
        ]
        return CandidateListResponse.build(
            items=items, total=total, page=page, size=size, facets=facets
        )

    # ── Postgres fallback (ES not configured, or empty index on a list view) ──
    base = select(Candidate).where(Candidate.deleted_at.is_(None))

    if q:
        term = f"%{q}%"
        base = base.where(
            or_(
                Candidate.name.ilike(term),
                Candidate.email.ilike(term),
                Candidate.location.ilike(term),
                Candidate.desired_position.ilike(term),
                *_skill_ilike_clauses([q]),
            )
        )
    if skills:
        base = base.where(or_(*_skill_ilike_clauses(skills)))
    if seniority:
        base = base.where(Candidate.seniority == seniority)
    if status:
        base = base.where(Candidate.status == status)
    if location:
        base = base.where(Candidate.location.ilike(f"%{location}%"))
    if years_min is not None:
        base = base.where(Candidate.years_experience >= years_min)
    if years_max is not None:
        base = base.where(Candidate.years_experience <= years_max)
    if desired_salary_min is not None:
        base = base.where(Candidate.desired_salary >= desired_salary_min)
    if desired_salary_max is not None:
        base = base.where(Candidate.desired_salary <= desired_salary_max)
    if certification:
        base = base.where(
            text(
                "EXISTS (SELECT 1 FROM jsonb_array_elements_text(candidates.certifications) _c"
                " WHERE lower(_c) LIKE :cert_pat)"
            ).bindparams(cert_pat=f"%{certification.strip().lower()}%")
        )
    if resume_language:
        base = base.where(Candidate.resume_language == resume_language)

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar_one()

    rows_pg = await db.execute(
        base.order_by(Candidate.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    items = [CandidateResponse.model_validate(c) for c in rows_pg.scalars().all()]

    return CandidateListResponse.build(items=items, total=total, page=page, size=size)


@router.get(
    "/semantic-search",
    response_model=CandidateListResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_write)],
)
async def semantic_search_candidates(
    db: DbDep,
    q: str = Query(..., description="Natural language query, e.g. 'Java architect with banking experience'"),
    limit: int = Query(default=20, ge=1, le=100),
) -> CandidateListResponse:
    from sqlalchemy import text

    from app.llm import get_llm_client

    llm = get_llm_client()
    q_vec = await llm.embed(q)
    vec_str = "[" + ",".join(map(str, q_vec)) + "]"

    # IVFFlat default probes=1 misses most rows on small datasets.
    # SET (session-level) is safe because get_current_user already began the transaction.
    await db.execute(text("SET ivfflat.probes = 100"))
    result = await db.execute(
        select(Candidate)
        .where(Candidate.embedding.is_not(None), Candidate.deleted_at.is_(None))
        .order_by(text("embedding <=> CAST(:vec AS vector)"))
        .params(vec=vec_str)
        .limit(limit)
    )
    items = [CandidateResponse.model_validate(c) for c in result.scalars().all()]
    return CandidateListResponse.build(items=items, total=len(items), page=1, size=limit)


@router.get(
    "/{candidate_id}/similar",
    response_model=CandidateListResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user)],
)
async def similar_candidates(
    candidate_id: uuid.UUID,
    db: DbDep,
    limit: int = Query(default=10, ge=1, le=50),
) -> CandidateListResponse:
    target = await db.get(Candidate, candidate_id)
    if not target or target.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    if target.embedding is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Candidate has no embedding yet")

    vec_str = "[" + ",".join(map(str, list(target.embedding))) + "]"
    await db.execute(text("SET ivfflat.probes = 100"))
    result = await db.execute(
        select(Candidate)
        .where(
            Candidate.embedding.is_not(None),
            Candidate.deleted_at.is_(None),
            Candidate.id != candidate_id,
        )
        .order_by(text("embedding <=> CAST(:vec AS vector)"))
        .params(vec=vec_str)
        .limit(limit)
    )
    items = [CandidateResponse.model_validate(c) for c in result.scalars().all()]
    return CandidateListResponse.build(items=items, total=len(items), page=1, size=limit)


def _safe_cell(v: object) -> object:
    """Prevent CSV/spreadsheet formula injection by prefixing dangerous strings."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v
    return v


@router.get(
    "/export.csv",
    dependencies=[Depends(require_write)],
    response_class=StreamingResponse,
)
async def export_candidates_csv(
    db: DbDep,
    q: str | None = Query(default=None),
    skills: list[str] = Query(default=[]),
    seniority: str | None = Query(default=None),
    location: str | None = Query(default=None),
    years_min: float | None = Query(default=None, ge=0),
    years_max: float | None = Query(default=None, ge=0),
) -> StreamingResponse:
    base = select(Candidate).where(Candidate.deleted_at.is_(None))

    if q:
        term = f"%{q}%"
        base = base.where(
            or_(
                Candidate.name.ilike(term),
                Candidate.email.ilike(term),
                Candidate.location.ilike(term),
                Candidate.desired_position.ilike(term),
                *_skill_ilike_clauses([q]),
            )
        )
    if skills:
        base = base.where(or_(*_skill_ilike_clauses(skills)))
    if seniority:
        base = base.where(Candidate.seniority == seniority)
    if location:
        base = base.where(Candidate.location.ilike(f"%{location}%"))
    if years_min is not None:
        base = base.where(Candidate.years_experience >= years_min)
    if years_max is not None:
        base = base.where(Candidate.years_experience <= years_max)

    rows = await db.execute(base.order_by(Candidate.created_at.desc()).limit(10_000))
    candidates = rows.scalars().all()

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["id", "name", "email", "phone", "location", "seniority",
             "years_experience", "skills", "desired_position", "created_at"]
        )
        yield buf.getvalue()
        for c in candidates:
            buf.seek(0)
            buf.truncate()
            writer.writerow([
                c.id,
                _safe_cell(c.name),
                _safe_cell(c.email),
                _safe_cell(c.phone),
                _safe_cell(c.location),
                _safe_cell(c.seniority),
                c.years_experience,
                _safe_cell("|".join(c.skills or [])),
                _safe_cell(c.desired_position),
                c.created_at.isoformat(),
            ])
            yield buf.getvalue()

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=candidates.csv"},
    )


@router.get(
    "/export.xlsx",
    dependencies=[Depends(require_write)],
)
async def export_candidates_xlsx(
    db: DbDep,
    q: str | None = Query(default=None),
    skills: list[str] = Query(default=[]),
    seniority: str | None = Query(default=None),
    location: str | None = Query(default=None),
    years_min: float | None = Query(default=None, ge=0),
    years_max: float | None = Query(default=None, ge=0),
) -> Response:
    import openpyxl

    base = select(Candidate).where(Candidate.deleted_at.is_(None))

    if q:
        term = f"%{q}%"
        base = base.where(
            or_(
                Candidate.name.ilike(term),
                Candidate.email.ilike(term),
                Candidate.location.ilike(term),
                Candidate.desired_position.ilike(term),
                *_skill_ilike_clauses([q]),
            )
        )
    if skills:
        base = base.where(or_(*_skill_ilike_clauses(skills)))
    if seniority:
        base = base.where(Candidate.seniority == seniority)
    if location:
        base = base.where(Candidate.location.ilike(f"%{location}%"))
    if years_min is not None:
        base = base.where(Candidate.years_experience >= years_min)
    if years_max is not None:
        base = base.where(Candidate.years_experience <= years_max)

    rows = await db.execute(base.order_by(Candidate.created_at.desc()).limit(10_000))
    candidates = rows.scalars().all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(
        ["id", "name", "email", "phone", "location", "seniority",
         "years_experience", "skills", "desired_position", "created_at"]
    )
    for c in candidates:
        ws.append([
            str(c.id),
            _safe_cell(c.name),
            _safe_cell(c.email),
            _safe_cell(c.phone),
            _safe_cell(c.location),
            _safe_cell(c.seniority),
            c.years_experience,
            _safe_cell("|".join(c.skills or [])),
            _safe_cell(c.desired_position),
            c.created_at.isoformat(),
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=candidates.xlsx"},
    )


@router.patch(
    "/{candidate_id}",
    response_model=CandidateResponse,
    status_code=status.HTTP_200_OK,
)
async def update_candidate(
    request: Request,
    candidate_id: uuid.UUID,
    body: UpdateCandidateRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
) -> Candidate:
    result = await db.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.deleted_at.is_(None),
        )
    )
    candidate = result.scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    if body.email is not None and body.email != candidate.email:
        conflict = await db.execute(
            select(Candidate).where(
                Candidate.email == body.email,
                Candidate.deleted_at.is_(None),
                Candidate.id != candidate_id,
            )
        )
        if conflict.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Active candidate with email '{body.email}' already exists",
            )

    _before = snapshot_candidate(candidate)
    if body.name is not None:
        candidate.name = body.name
    if body.email is not None:
        candidate.email = body.email
    if body.phone is not None:
        candidate.phone = body.phone
    if body.skills is not None:
        candidate.skills = body.skills
    if body.years_experience is not None:
        candidate.years_experience = body.years_experience
    if body.education is not None:
        candidate.education = [e.model_dump() for e in body.education]
    if body.work_experiences is not None:
        candidate.work_experiences = [e.model_dump() for e in body.work_experiences]
    if body.location is not None:
        candidate.location = body.location
    if body.seniority is not None:
        candidate.seniority = body.seniority
    if body.summary is not None:
        candidate.summary = body.summary
    if body.desired_position is not None:
        candidate.desired_position = body.desired_position
    if body.certifications is not None:
        candidate.certifications = body.certifications
    if body.languages is not None:
        candidate.languages = body.languages
    if body.linkedin_url is not None:
        candidate.linkedin_url = body.linkedin_url
    if body.github_url is not None:
        candidate.github_url = body.github_url
    if body.desired_salary is not None:
        candidate.desired_salary = body.desired_salary

    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.CANDIDATE_UPDATED,
        resource_type="candidate",
        resource_id=candidate_id,
        request_id=getattr(request.state, "request_id", None),
        before=_before,
        after=snapshot_candidate(candidate),
    )
    await db.commit()
    _enqueue_es_index(str(candidate_id))
    return candidate


@router.get(
    "/{candidate_id}/export.pdf",
    dependencies=[Depends(require_write)],
)
async def export_candidate_pdf(candidate_id: uuid.UUID, db: DbDep) -> Response:
    from app.export.pdf import build_candidate_pdf

    result = await db.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.deleted_at.is_(None),
        )
    )
    candidate = result.scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    pdf_bytes = await asyncio.to_thread(build_candidate_pdf, candidate)
    filename = f"candidate_{candidate_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get(
    "/{candidate_id}",
    response_model=CandidateResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user)],
)
async def get_candidate(candidate_id: uuid.UUID, db: DbDep) -> Candidate:
    result = await db.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.deleted_at.is_(None),
        )
    )
    candidate = result.scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return candidate


@router.get(
    "/{candidate_id}/applications",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user)],
)
async def get_candidate_applications(candidate_id: uuid.UUID, db: DbDep) -> list[dict]:
    from app.applications.models import JobApplication
    from app.jobs.models import Job

    result = await db.execute(
        select(JobApplication, Job.title)
        .outerjoin(Job, Job.id == JobApplication.job_id)
        .where(
            JobApplication.candidate_id == candidate_id,
            JobApplication.deleted_at.is_(None),
        )
        .order_by(JobApplication.applied_at.desc())
    )
    rows = result.all()
    return [
        {
            "id": str(app.id),
            "job_id": str(app.job_id),
            "job_title": job_title,
            "status": app.status,
            "interview_scheduled_at": app.interview_scheduled_at.isoformat() if app.interview_scheduled_at else None,
            "interview_location": app.interview_location,
            "applied_at": app.applied_at.isoformat(),
        }
        for app, job_title in rows
    ]


@router.delete(
    "/{candidate_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_candidate(
    request: Request,
    candidate_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
) -> None:
    result = await db.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.deleted_at.is_(None),
        )
    )
    candidate = result.scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    _before = snapshot_candidate(candidate)
    candidate.deleted_at = datetime.now(timezone.utc)
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.CANDIDATE_DELETED,
        resource_type="candidate",
        resource_id=candidate_id,
        request_id=getattr(request.state, "request_id", None),
        before=_before,
    )
    await db.commit()
    _enqueue_es_remove(str(candidate_id))


_AVATAR_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_AVATAR_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_AVATARS_PREFIX = "avatars"


def _upload_avatar_sync(file_id: str, content: bytes, content_type: str) -> None:
    import io as _io

    from app.config import settings
    from app.storage.client import minio_client

    bucket = settings.minio_bucket
    if not minio_client.bucket_exists(bucket):
        minio_client.make_bucket(bucket)
    minio_client.put_object(
        bucket,
        f"{_AVATARS_PREFIX}/{file_id}",
        _io.BytesIO(content),
        length=len(content),
        content_type=content_type,
    )


def _get_avatar_url(file_id: str) -> str:
    from app.config import settings
    return f"{settings.minio_public_url}/{settings.minio_bucket}/{_AVATARS_PREFIX}/{file_id}"


@router.post(
    "/{candidate_id}/avatar",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def upload_candidate_avatar(
    candidate_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
    file: UploadFile = File(...),
) -> dict:
    content_type = file.content_type or ""
    if content_type not in _AVATAR_ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported image type. Allowed: {', '.join(_AVATAR_ALLOWED_TYPES)}",
        )

    content = await file.read()
    if len(content) > _AVATAR_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Avatar must be ≤5 MB",
        )

    result = await db.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.deleted_at.is_(None),
        )
    )
    candidate = result.scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    file_id = str(uuid.uuid4())
    await asyncio.to_thread(_upload_avatar_sync, file_id, content, content_type)

    candidate.photo_url = _get_avatar_url(file_id)
    await db.commit()
    return {"photo_url": candidate.photo_url}
