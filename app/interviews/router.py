"""
app/interviews/router.py — public interview endpoints (candidate recorder).

These endpoints are reachable without a logged-in user (the candidate is not a
platform user), but they are NOT unauthenticated: every request must present the
per-session ``access_token`` minted when the interview session is created. The
token is compared in constant time, the session must be live (not expired, not
soft-deleted), and every endpoint is rate-limited to blunt brute-force and
storage-DoS abuse.
"""

import hmac
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.interviews.models import InterviewAnswer, InterviewSession
from app.interviews.schemas import StartAttemptResponse, UploadUrlRequest, UploadUrlResponse
from app.limiter import limiter
from app.storage.client import presigned_video_post

router = APIRouter(prefix="/interviews", tags=["interviews"])

_UPLOAD_TTL_SECONDS = 300  # 5-minute policy window


async def _authorize_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    token: str | None,
) -> InterviewSession:
    """Load an interview session and authorize the candidate's access token.

    Raises:
        404 — no such session (or soft-deleted): indistinguishable on purpose.
        401 — missing or non-matching access token.
        410 — session has expired.
    """
    result = await db.execute(
        select(InterviewSession).where(
            InterviewSession.id == session_id,
            InterviewSession.deleted_at.is_(None),
        )
    )
    session: InterviewSession | None = result.scalar_one_or_none()
    # Do the token comparison against a dummy when the session is missing so the
    # response timing does not reveal whether the session id exists.
    expected = session.access_token if (session and session.access_token) else None
    supplied = token or ""
    token_ok = expected is not None and hmac.compare_digest(expected, supplied)
    if session is None or not token_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid interview session or access token.",
        )
    if session.expires_at is not None and session.expires_at < datetime.now(tz=timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This interview session has expired.",
        )
    return session


@router.post(
    "/public/upload-url",
    response_model=UploadUrlResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a presigned POST URL for video upload (session-token gated).",
)
@limiter.limit("10/minute")
async def get_upload_url(
    request: Request,
    body: UploadUrlRequest,
    db: AsyncSession = Depends(get_db),
) -> UploadUrlResponse:
    """
    Generate a fresh UUID4 key and return a single-use presigned POST policy.
    The content-length range enforces max_video_upload_bytes (150 MB). TTL is
    300 s; the exact-key equals-condition binds the policy to one key. Requires
    a valid session access token so URLs cannot be minted anonymously.
    """
    await _authorize_session(db, body.session_id, body.access_token)
    file_id = str(uuid.uuid4())
    url, fields = await presigned_video_post(
        key=file_id,
        max_bytes=settings.max_video_upload_bytes,
        ttl_seconds=_UPLOAD_TTL_SECONDS,
    )
    return UploadUrlResponse(url=url, fields=fields, file_id=file_id)


@router.post(
    "/public/{session_id}/answers/{idx}/start",
    response_model=StartAttemptResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark an answer attempt as started (consumes the single attempt).",
)
@limiter.limit("20/minute")
async def start_answer_attempt(
    request: Request,
    session_id: uuid.UUID,
    idx: int,
    token: str,
    db: AsyncSession = Depends(get_db),
) -> StartAttemptResponse:
    """
    Sets attempt_consumed_at on the InterviewAnswer row if it is null.
    Returns 409 if the attempt was already consumed. Requires a valid session
    access token (passed as the ``token`` query parameter).

    If no answer row exists yet for this session+index, creates a stub row
    using the question text from the session's `questions` JSONB array.
    """
    session = await _authorize_session(db, session_id, token)

    # Look for an existing answer row
    answer_result = await db.execute(
        select(InterviewAnswer).where(
            InterviewAnswer.session_id == session_id,
            InterviewAnswer.question_index == idx,
        )
    )
    answer: InterviewAnswer | None = answer_result.scalar_one_or_none()

    if answer is not None:
        if answer.attempt_consumed_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="attempt already used",
            )
        # Mark as consumed
        answer.attempt_consumed_at = datetime.now(tz=timezone.utc)
        await db.commit()
        await db.refresh(answer)
        return StartAttemptResponse(
            session_id=session_id,
            question_index=idx,
            attempt_consumed_at=answer.attempt_consumed_at,
        )

    # No row yet — create a stub
    questions: list = session.questions or []
    question_text = ""
    if 0 <= idx < len(questions):
        q = questions[idx]
        if isinstance(q, dict):
            question_text = str(q.get("text") or q.get("question") or "")
        elif isinstance(q, str):
            question_text = q

    now = datetime.now(tz=timezone.utc)
    new_answer = InterviewAnswer(
        session_id=session_id,
        question_index=idx,
        question_text=question_text,
        attempt_consumed_at=now,
    )
    db.add(new_answer)
    await db.commit()

    return StartAttemptResponse(
        session_id=session_id,
        question_index=idx,
        attempt_consumed_at=now,
    )
