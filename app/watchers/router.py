import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_write
from app.candidates.models import Candidate
from app.database import get_db
from app.jobs.models import Job
from app.users.models import User, UserRole
from app.watchers.models import CandidateWatcher, JobWatcher
from app.watchers.schemas import (
    AddCandidateWatcherRequest,
    AddJobWatcherRequest,
    CandidateWatcherResponse,
    JobWatcherResponse,
    UpdateJobWatcherFiltersRequest,
    WatcherUserSummary,
)

router = APIRouter(tags=["watchers"])

DbDep = Annotated[AsyncSession, Depends(get_db)]

_FORBIDDEN = HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


async def _require_watcher_manager(
    job_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: DbDep,
) -> User:
    if current_user.role == UserRole.ADMIN:
        return current_user
    if current_user.role == UserRole.HR_MANAGER:
        job = await db.get(Job, job_id)
        if job is None or job.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        if job.creator_id != current_user.id:
            raise _FORBIDDEN
        return current_user
    raise _FORBIDDEN


async def _load_job(db: AsyncSession, job_id: uuid.UUID) -> Job:
    job = await db.get(Job, job_id)
    if job is None or job.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


async def _load_candidate(db: AsyncSession, candidate_id: uuid.UUID) -> Candidate:
    result = await db.execute(
        select(Candidate).where(Candidate.id == candidate_id, Candidate.deleted_at.is_(None))
    )
    candidate = result.scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return candidate


async def _load_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None), User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _watcher_user_summary(user: User) -> WatcherUserSummary:
    return WatcherUserSummary(id=user.id, email=user.email, full_name=user.full_name)


# ---------------------------------------------------------------------------
# Job watchers
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}/watchers", response_model=list[JobWatcherResponse])
async def list_job_watchers(
    job_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
) -> list[JobWatcherResponse]:
    await _load_job(db, job_id)
    rows = await db.execute(select(JobWatcher).where(JobWatcher.job_id == job_id))
    watchers = rows.scalars().all()
    user_ids = {w.user_id for w in watchers}
    if not user_ids:
        return []
    user_rows = await db.execute(select(User).where(User.id.in_(user_ids)))
    users = {u.id: u for u in user_rows.scalars().all()}
    return [
        JobWatcherResponse(
            user=_watcher_user_summary(users[w.user_id]),
            filters=w.filters,
            created_at=w.created_at,
        )
        for w in watchers
        if w.user_id in users
    ]


@router.post(
    "/jobs/{job_id}/watchers",
    response_model=JobWatcherResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_job_watcher(
    job_id: uuid.UUID,
    body: AddJobWatcherRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(_require_watcher_manager)],
) -> JobWatcherResponse:
    await _load_job(db, job_id)
    target_user = await _load_user(db, body.user_id)

    stmt = (
        pg_insert(JobWatcher)
        .values(id=uuid.uuid4(), job_id=job_id, user_id=body.user_id, filters=body.filters)
        .on_conflict_do_update(
            constraint="uq_job_watcher",
            set_={"filters": body.filters},
        )
        .returning(JobWatcher)
    )
    result = await db.execute(stmt)
    watcher = result.scalar_one()
    await db.commit()
    return JobWatcherResponse(
        user=_watcher_user_summary(target_user),
        filters=watcher.filters,
        created_at=watcher.created_at,
    )


@router.patch(
    "/jobs/{job_id}/watchers/{user_id}/filters",
    response_model=JobWatcherResponse,
)
async def update_job_watcher_filters(
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    body: UpdateJobWatcherFiltersRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(_require_watcher_manager)],
) -> JobWatcherResponse:
    result = await db.execute(
        select(JobWatcher).where(JobWatcher.job_id == job_id, JobWatcher.user_id == user_id)
    )
    watcher = result.scalar_one_or_none()
    if watcher is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watcher not found")
    watcher.filters = body.filters
    await db.commit()
    await db.refresh(watcher)
    target_user = await _load_user(db, user_id)
    return JobWatcherResponse(
        user=_watcher_user_summary(target_user),
        filters=watcher.filters,
        created_at=watcher.created_at,
    )


@router.delete("/jobs/{job_id}/watchers/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_job_watcher(
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[User, Depends(_require_watcher_manager)],
) -> None:
    result = await db.execute(
        select(JobWatcher).where(JobWatcher.job_id == job_id, JobWatcher.user_id == user_id)
    )
    watcher = result.scalar_one_or_none()
    if watcher is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watcher not found")
    await db.delete(watcher)
    await db.commit()


# ---------------------------------------------------------------------------
# Candidate watchers
# ---------------------------------------------------------------------------


@router.get(
    "/candidates/{candidate_id}/watchers",
    response_model=list[CandidateWatcherResponse],
)
async def list_candidate_watchers(
    candidate_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
) -> list[CandidateWatcherResponse]:
    await _load_candidate(db, candidate_id)
    rows = await db.execute(
        select(CandidateWatcher).where(CandidateWatcher.candidate_id == candidate_id)
    )
    watchers = rows.scalars().all()
    user_ids = {w.user_id for w in watchers}
    if not user_ids:
        return []
    user_rows = await db.execute(select(User).where(User.id.in_(user_ids)))
    users = {u.id: u for u in user_rows.scalars().all()}
    return [
        CandidateWatcherResponse(
            user=_watcher_user_summary(users[w.user_id]),
            created_at=w.created_at,
        )
        for w in watchers
        if w.user_id in users
    ]


@router.post(
    "/candidates/{candidate_id}/watchers",
    response_model=CandidateWatcherResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_candidate_watcher(
    candidate_id: uuid.UUID,
    body: AddCandidateWatcherRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
) -> CandidateWatcherResponse:
    await _load_candidate(db, candidate_id)
    target_id = body.user_id if body.user_id is not None else current_user.id
    if target_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise _FORBIDDEN
    target_user = await _load_user(db, target_id)

    stmt = (
        pg_insert(CandidateWatcher)
        .values(id=uuid.uuid4(), candidate_id=candidate_id, user_id=target_id)
        .on_conflict_do_nothing(constraint="uq_candidate_watcher")
        .returning(CandidateWatcher)
    )
    result = await db.execute(stmt)
    watcher = result.scalar_one_or_none()
    if watcher is None:
        existing = await db.execute(
            select(CandidateWatcher).where(
                CandidateWatcher.candidate_id == candidate_id,
                CandidateWatcher.user_id == target_id,
            )
        )
        watcher = existing.scalar_one()
    await db.commit()
    return CandidateWatcherResponse(
        user=_watcher_user_summary(target_user),
        created_at=watcher.created_at,
    )


@router.delete(
    "/candidates/{candidate_id}/watchers/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_candidate_watcher(
    candidate_id: uuid.UUID,
    user_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
) -> None:
    if user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise _FORBIDDEN
    result = await db.execute(
        select(CandidateWatcher).where(
            CandidateWatcher.candidate_id == candidate_id,
            CandidateWatcher.user_id == user_id,
        )
    )
    watcher = result.scalar_one_or_none()
    if watcher is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watcher not found")
    await db.delete(watcher)
    await db.commit()
