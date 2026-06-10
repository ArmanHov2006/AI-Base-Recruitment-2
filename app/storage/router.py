import asyncio
import io
import re
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from minio.error import S3Error
from pydantic import BaseModel

from app.auth import require_write
from app.config import settings
from app.limiter import limiter
from app.storage.client import minio_client
from app.storage.validator import FileValidationError, validate_file

router = APIRouter(prefix="/files", tags=["files"])

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _put_object(file_id: str, content: bytes, content_type: str) -> None:
    minio_client.put_object(
        settings.minio_bucket,
        file_id,
        io.BytesIO(content),
        length=len(content),
        content_type=content_type,
    )


def _presigned_get(file_id: str, ttl_seconds: int) -> str:
    return minio_client.presigned_get_object(
        settings.minio_bucket,
        file_id,
        expires=timedelta(seconds=ttl_seconds),
    )


class UploadResponse(BaseModel):
    file_id: str


class PresignedUrlResponse(BaseModel):
    url: str
    expires_in: int


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_write)],
)
@limiter.limit("300/minute")
async def upload_file(request: Request, file: UploadFile) -> UploadResponse:
    content = await file.read()
    try:
        validate_file(file.filename or "", content, settings.max_upload_bytes)
    except FileValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    file_id = str(uuid.uuid4())
    try:
        await asyncio.to_thread(
            _put_object,
            file_id,
            content,
            file.content_type or "application/octet-stream",
        )
    except S3Error as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Storage error: {exc}")

    return UploadResponse(file_id=file_id)


@router.get(
    "/{file_id}/download-url",
    response_model=PresignedUrlResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_write)],
)
async def get_download_url(file_id: str) -> PresignedUrlResponse:
    if not _UUID4_RE.match(file_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="file_id must be a valid UUID4",
        )
    ttl = settings.presigned_url_ttl_seconds
    try:
        url = await asyncio.to_thread(_presigned_get, file_id, ttl)
    except S3Error as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File not found: {exc}")
    return PresignedUrlResponse(url=url, expires_in=ttl)
