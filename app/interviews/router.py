"""
app/interviews/router.py — public interview endpoints (Lane A slice).

These endpoints are intentionally unauthenticated for the thin-slice demo.
Full production flow gates access via session access_token (Lane B).
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.interviews.models import InterviewAnswer, InterviewSession
from app.interviews.schemas import StartAttemptResponse, UploadUrlRequest, UploadUrlResponse
from app.storage.client import presigned_video_post

router = APIRouter(prefix="/interviews", tags=["interviews"])

_UPLOAD_TTL_SECONDS = 300  # 5-minute policy window


@router.post(
    "/public/upload-url",
    response_model=UploadUrlResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a presigned POST URL for video upload (public, no auth).",
)
async def get_upload_url(body: UploadUrlRequest) -> UploadUrlResponse:
    """
    Generate a fresh UUID4 key and return a single-use presigned POST policy.
    The content-length range enforces max_video_upload_bytes (150 MB).
    TTL is 300 s; the exact-key equals-condition binds the policy to one key.
    """
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
async def start_answer_attempt(
    session_id: uuid.UUID,
    idx: int,
    db: AsyncSession = Depends(get_db),
) -> StartAttemptResponse:
    """
    Sets attempt_consumed_at on the InterviewAnswer row if it is null.
    Returns 409 if the attempt was already consumed.

    If no answer row exists yet for this session+index, creates a stub row
    using the question text from the session's `questions` JSONB array.
    """
    # Load the session to retrieve question text
    session_result = await db.execute(select(InterviewSession).where(InterviewSession.id == session_id))
    session: InterviewSession | None = session_result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found.",
        )

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
            question_text = q.get("text", q.get("question", ""))
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
