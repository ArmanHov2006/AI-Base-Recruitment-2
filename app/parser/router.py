import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_write
from app.database import get_db
from app.limiter import limiter
from app.parser.schemas import CandidateData
from app.parser.service import parse_and_validate

router = APIRouter(tags=["parser"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


class ParseRequest(BaseModel):
    file_id: str
    job_id: uuid.UUID | None = None


@router.post(
    "/parse",
    response_model=CandidateData,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_write)],
)
@limiter.limit("20/minute")
async def parse_resume(request: Request, body: ParseRequest, db: DbDep) -> CandidateData:
    return await parse_and_validate(body.file_id, db, job_id=body.job_id)
