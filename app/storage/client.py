import asyncio
from datetime import datetime, timedelta

from minio import Minio
from minio.datatypes import PostPolicy

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


def _presigned_video_post_sync(key: str, max_bytes: int, ttl_seconds: int) -> tuple[str, dict[str, str]]:
    policy = PostPolicy(settings.minio_bucket, datetime.utcnow() + timedelta(seconds=ttl_seconds))
    policy.add_equals_condition("key", key)
    policy.add_content_length_range_condition(1, max_bytes)
    form_data = minio_client.presigned_post_policy(policy)
    url = f"{settings.minio_public_url}/{settings.minio_bucket}"
    return url, form_data


async def presigned_video_post(key: str, max_bytes: int, ttl_seconds: int) -> tuple[str, dict[str, str]]:
    """Return (upload_url, form_fields) for a single-use presigned POST policy."""
    return await asyncio.to_thread(_presigned_video_post_sync, key, max_bytes, ttl_seconds)
