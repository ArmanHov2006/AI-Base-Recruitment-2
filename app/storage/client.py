import asyncio

from minio import Minio

from app.config import settings

minio_client: Minio = Minio(
    settings.minio_internal_url.split("://", 1)[1],
    access_key=settings.minio_root_user,
    secret_key=settings.minio_root_password,
    secure=settings.minio_internal_url.startswith("https://"),
)


def _ensure_bucket_sync() -> None:
    if not minio_client.bucket_exists(settings.minio_bucket):
        minio_client.make_bucket(settings.minio_bucket)


async def ensure_bucket() -> None:
    await asyncio.to_thread(_ensure_bucket_sync)
