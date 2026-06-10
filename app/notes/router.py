import re
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import BusinessEventAction
from app.audit.events import record
from app.audit.snapshots import snapshot_note
from app.auth import get_current_user
from app.candidates.models import Candidate
from app.database import get_db
from app.notes.models import CandidateNote
from app.notes.schemas import CreateNoteRequest, NoteResponse, UpdateNoteRequest
from app.users.models import User, UserRole

router = APIRouter(prefix="/candidates/{candidate_id}/notes", tags=["notes"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _load_candidate(db: AsyncSession, candidate_id: uuid.UUID) -> Candidate:
    result = await db.execute(
        select(Candidate).where(Candidate.id == candidate_id, Candidate.deleted_at.is_(None))
    )
    candidate = result.scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return candidate


async def _load_note(
    db: AsyncSession, candidate_id: uuid.UUID, note_id: uuid.UUID
) -> CandidateNote:
    result = await db.execute(
        select(CandidateNote).where(
            CandidateNote.id == note_id,
            CandidateNote.candidate_id == candidate_id,
            CandidateNote.deleted_at.is_(None),
        )
    )
    note = result.scalar_one_or_none()
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note


@router.get("", response_model=list[NoteResponse])
async def list_notes(
    candidate_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[NoteResponse]:
    await _load_candidate(db, candidate_id)
    result = await db.execute(
        select(CandidateNote).where(
            CandidateNote.candidate_id == candidate_id,
            CandidateNote.deleted_at.is_(None),
        )
    )
    return [NoteResponse.model_validate(n) for n in result.scalars().all()]


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    request: Request,
    candidate_id: uuid.UUID,
    body: CreateNoteRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(get_current_user)],
) -> NoteResponse:
    await _load_candidate(db, candidate_id)
    note = CandidateNote(
        candidate_id=candidate_id,
        author_id=current_user.id,
        text=body.text,
    )
    db.add(note)
    await db.flush()
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.NOTE_CREATED,
        resource_type="note",
        resource_id=note.id,
        request_id=getattr(request.state, "request_id", None),
        after=snapshot_note(note),
    )
    await db.commit()
    await db.refresh(note)

    await _dispatch_mention_notifications(db, body.text, current_user.id, note.id, candidate_id)

    return NoteResponse.model_validate(note)


_MENTION_RE = re.compile(r"@([\w.+-]+)")


_TEAM_HANDLES: dict[str, UserRole] = {
    "recruiters": UserRole.RECRUITER,
    "hr-team": UserRole.HR_MANAGER,
    "hr_team": UserRole.HR_MANAGER,
    "hr_managers": UserRole.HR_MANAGER,
    "admins": UserRole.ADMIN,
}


async def _dispatch_mention_notifications(
    db: AsyncSession,
    text: str,
    author_id: uuid.UUID,
    note_id: uuid.UUID,
    candidate_id: uuid.UUID,
) -> None:
    handles = _MENTION_RE.findall(text)
    if not handles:
        return
    from app.notifications.service import create_notification

    seen: set[uuid.UUID] = set()

    all_users_result = await db.execute(
        select(User).where(User.deleted_at.is_(None), User.is_active.is_(True))
    )
    all_users = all_users_result.scalars().all()

    async def _notify(user: User) -> None:
        if user.id == author_id or user.id in seen:
            return
        seen.add(user.id)
        try:
            await create_notification(
                db,
                user_id=user.id,
                type_="mention",
                payload={
                    "note_id": str(note_id),
                    "candidate_id": str(candidate_id),
                    "author_id": str(author_id),
                },
            )
        except Exception:
            pass

    for handle in handles:
        handle_lower = handle.lower()
        team_role = _TEAM_HANDLES.get(handle_lower)
        if team_role is not None:
            for user in all_users:
                if user.role == team_role:
                    await _notify(user)
        else:
            for user in all_users:
                name_match = handle_lower in (user.full_name or "").lower()
                email_match = handle_lower in user.email.lower()
                if name_match or email_match:
                    await _notify(user)


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    request: Request,
    candidate_id: uuid.UUID,
    note_id: uuid.UUID,
    body: UpdateNoteRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(get_current_user)],
) -> NoteResponse:
    note = await _load_note(db, candidate_id, note_id)

    if note.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can edit this note",
        )

    _before = snapshot_note(note)
    note.text = body.text
    note.updated_at = datetime.now(timezone.utc)
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.NOTE_UPDATED,
        resource_type="note",
        resource_id=note_id,
        request_id=getattr(request.state, "request_id", None),
        before=_before,
        after=snapshot_note(note),
    )
    await db.commit()
    await db.refresh(note)
    return NoteResponse.model_validate(note)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    request: Request,
    candidate_id: uuid.UUID,
    note_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    note = await _load_note(db, candidate_id, note_id)

    if note.author_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author or an admin can delete this note",
        )

    _before = snapshot_note(note)
    note.deleted_at = datetime.now(timezone.utc)
    await record(
        db,
        actor_id=current_user.id,
        action=BusinessEventAction.NOTE_DELETED,
        resource_type="note",
        resource_id=note_id,
        request_id=getattr(request.state, "request_id", None),
        before=_before,
    )
    await db.commit()
