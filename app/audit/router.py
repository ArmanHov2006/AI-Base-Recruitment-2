import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.events import BusinessEvent
from app.audit.models import AuditLog
from app.auth import require_admin
from app.database import get_db
from app.users.models import User

router = APIRouter(prefix="/audit", tags=["audit"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("", dependencies=[Depends(require_admin)])
async def list_audit_logs(
    response: Response,
    db: DbDep,
    user_id: uuid.UUID | None = Query(default=None),
    method: str | None = Query(default=None, description="HTTP method filter: POST, PATCH, etc."),
    path_contains: str | None = Query(default=None, description="Substring match on request path"),
    from_dt: datetime | None = Query(default=None),
    to_dt: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    base = select(AuditLog)
    if user_id:
        base = base.where(AuditLog.user_id == user_id)
    if method:
        base = base.where(AuditLog.method == method.upper())
    if path_contains:
        escaped = path_contains.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        base = base.where(AuditLog.path.ilike(f"%{escaped}%", escape="\\"))
    if from_dt:
        base = base.where(AuditLog.created_at >= from_dt)
    if to_dt:
        base = base.where(AuditLog.created_at <= to_dt)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    response.headers["X-Total-Count"] = str(total)

    stmt = base.order_by(desc(AuditLog.created_at)).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()

    user_ids = {r.user_id for r in rows if r.user_id}
    user_map: dict[uuid.UUID, User] = {}
    if user_ids:
        users = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        user_map = {u.id: u for u in users}

    return [
        {
            "id": str(r.id),
            "user_id": str(r.user_id) if r.user_id else None,
            "user_email": user_map[r.user_id].email if r.user_id and r.user_id in user_map else None,
            "user_full_name": user_map[r.user_id].full_name if r.user_id and r.user_id in user_map else None,
            "method": r.method,
            "path": r.path,
            "status_code": r.status_code,
            "ip": r.ip,
            "user_agent": r.user_agent,
            "request_id": str(r.request_id),
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/events", dependencies=[Depends(require_admin)])
async def list_business_events(
    response: Response,
    db: DbDep,
    actor_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None, description="e.g. job.created, application.status_changed"),
    resource_type: str | None = Query(default=None, description="e.g. job, candidate, application"),
    resource_id: uuid.UUID | None = Query(default=None),
    request_id: uuid.UUID | None = Query(default=None),
    from_dt: datetime | None = Query(default=None),
    to_dt: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    base = select(BusinessEvent)
    if actor_id:
        base = base.where(BusinessEvent.actor_id == actor_id)
    if action:
        base = base.where(BusinessEvent.action == action)
    if resource_type:
        base = base.where(BusinessEvent.resource_type == resource_type)
    if resource_id:
        base = base.where(BusinessEvent.resource_id == resource_id)
    if request_id:
        base = base.where(BusinessEvent.request_id == request_id)
    if from_dt:
        base = base.where(BusinessEvent.created_at >= from_dt)
    if to_dt:
        base = base.where(BusinessEvent.created_at <= to_dt)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    response.headers["X-Total-Count"] = str(total)

    stmt = base.order_by(desc(BusinessEvent.created_at)).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()

    actor_ids = {r.actor_id for r in rows if r.actor_id}
    actor_map: dict[uuid.UUID, User] = {}
    if actor_ids:
        actors = (await db.execute(select(User).where(User.id.in_(actor_ids)))).scalars().all()
        actor_map = {u.id: u for u in actors}

    return [
        {
            "id": str(r.id),
            "actor_id": str(r.actor_id) if r.actor_id else None,
            "actor_email": actor_map[r.actor_id].email if r.actor_id and r.actor_id in actor_map else None,
            "actor_full_name": actor_map[r.actor_id].full_name if r.actor_id and r.actor_id in actor_map else None,
            "action": r.action,
            "resource_type": r.resource_type,
            "resource_id": str(r.resource_id),
            "request_id": str(r.request_id) if r.request_id else None,
            "before": r.before,
            "after": r.after,
            "meta": r.meta,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
