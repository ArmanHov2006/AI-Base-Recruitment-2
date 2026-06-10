from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import build_system_prompt
from app.ai.schemas import ChatRequest
from app.auth import require_write
from app.candidates.models import Candidate
from app.database import get_db
from app.jobs.models import Job
from app.limiter import limiter
from app.llm import get_llm_client
from app.users.models import User

router = APIRouter(prefix="/ai", tags=["ai"])
_llm_client = get_llm_client()

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("/chat")
@limiter.limit("15/minute")
async def chat(
    request: Request,
    body: ChatRequest,
    db: DbDep,
    current_user: Annotated[User, Depends(require_write)],
) -> StreamingResponse:
    candidate = (
        await db.execute(
            select(Candidate).where(
                Candidate.id == body.candidate_id,
                Candidate.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    job: Job | None = None
    if body.job_id is not None:
        job = (
            await db.execute(
                select(Job).where(Job.id == body.job_id, Job.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    # Build the prompt while the DB session is still open; the stream below
    # touches no DB state so it survives the session closing after return.
    system_prompt = build_system_prompt(candidate, job)

    async def token_stream() -> AsyncGenerator[bytes, None]:
        async for piece in _llm_client.chat_stream(system_prompt, body.message):
            yield piece.encode("utf-8")

    return StreamingResponse(token_stream(), media_type="text/plain; charset=utf-8")
