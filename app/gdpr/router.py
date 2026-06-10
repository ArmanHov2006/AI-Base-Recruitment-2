"""GDPR right-of-access export.

Bundles every record referencing a candidate into a single downloadable JSON.
Admin-only. The export itself is recorded as a business event (accessing PII is
auditable). Soft-deleted records are intentionally included — the data subject's
right of access applies regardless of soft-delete state.
"""
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applications.models import JobApplication
from app.audit.actions import BusinessEventAction
from app.audit.events import BusinessEvent, record
from app.audit.models import AuditLog
from app.audit.snapshots import (
    _s,
    snapshot_application,
    snapshot_candidate,
    snapshot_evaluation,
    snapshot_note,
)
from app.auth import require_admin
from app.candidates.models import Candidate
from app.database import get_db
from app.evaluations.models import CandidateEvaluation
from app.notes.models import CandidateNote
from app.users.models import User

router = APIRouter(prefix="/candidates/{candidate_id}/gdpr-export", tags=["gdpr"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


def _serialize_business_event(e: BusinessEvent) -> dict[str, object]:
    return {
        "id": _s(e.id),
        "actor_id": _s(e.actor_id),
        "action": e.action,
        "resource_type": e.resource_type,
        "resource_id": _s(e.resource_id),
        "request_id": _s(e.request_id),
        "before": e.before,
        "after": e.after,
        "meta": e.meta,
        "created_at": _s(e.created_at),
    }


def _serialize_audit_log(a: AuditLog) -> dict[str, object]:
    return {
        "id": _s(a.id),
        "user_id": _s(a.user_id),
        "method": a.method,
        "path": a.path,
        "status_code": a.status_code,
        "ip": a.ip,
        "user_agent": a.user_agent,
        "request_id": _s(a.request_id),
        "created_at": _s(a.created_at),
    }


@router.get("")
async def gdpr_export(
    request: Request,
    candidate_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[User, Depends(require_admin)],
) -> JSONResponse:
    candidate = (
        await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    ).scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    applications = list(
        (
            await db.execute(
                select(JobApplication)
                .where(JobApplication.candidate_id == candidate_id)
                .order_by(JobApplication.applied_at)
            )
        )
        .scalars()
        .all()
    )
    evaluations = list(
        (
            await db.execute(
                select(CandidateEvaluation)
                .where(CandidateEvaluation.candidate_id == candidate_id)
                .order_by(CandidateEvaluation.created_at)
            )
        )
        .scalars()
        .all()
    )
    notes = list(
        (
            await db.execute(
                select(CandidateNote)
                .where(CandidateNote.candidate_id == candidate_id)
                .order_by(CandidateNote.created_at)
            )
        )
        .scalars()
        .all()
    )

    # Every business event referencing the candidate OR any of its child records.
    related_ids: set[uuid.UUID] = {candidate_id}
    related_ids.update(a.id for a in applications)
    related_ids.update(e.id for e in evaluations)
    related_ids.update(n.id for n in notes)
    business_events = list(
        (
            await db.execute(
                select(BusinessEvent)
                .where(BusinessEvent.resource_id.in_(related_ids))
                .order_by(BusinessEvent.created_at)
            )
        )
        .scalars()
        .all()
    )

    # HTTP audit entries whose path references this candidate's UUID.
    audit_entries = list(
        (
            await db.execute(
                select(AuditLog)
                .where(AuditLog.path.contains(str(candidate_id)))
                .order_by(AuditLog.created_at)
            )
        )
        .scalars()
        .all()
    )

    record_counts = {
        "applications": len(applications),
        "evaluations": len(evaluations),
        "notes": len(notes),
        "business_events": len(business_events),
        "http_audit_log": len(audit_entries),
    }

    bundle: dict[str, object] = {
        "export_metadata": {
            "candidate_id": str(candidate_id),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_by": str(current_user.id),
            "record_counts": record_counts,
        },
        "candidate": snapshot_candidate(candidate),
        "applications": [snapshot_application(a) for a in applications],
        "evaluations": [snapshot_evaluation(e) for e in evaluations],
        "notes": [snapshot_note(n) for n in notes],
        "business_events": [_serialize_business_event(e) for e in business_events],
        "http_audit_log": [_serialize_audit_log(a) for a in audit_entries],
    }

    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.CANDIDATE_GDPR_EXPORTED,
        resource_type="candidate",
        resource_id=candidate_id,
        request_id=getattr(request.state, "request_id", None),
        meta={"record_counts": record_counts},
    )
    await db.commit()

    filename = f"gdpr-export-{candidate_id}.json"
    return JSONResponse(
        content=jsonable_encoder(bundle),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
