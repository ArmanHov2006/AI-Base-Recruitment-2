
from app.config import settings

print(f"MINIO_INTERNAL_URL: {settings.minio_internal_url}")
print(f"MINIO_BUCKET: {settings.minio_bucket}")
print(f"LLM_TIMEOUT_SECONDS: {settings.llm_timeout_seconds}")
