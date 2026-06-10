"""One-shot script: list resumes in MinIO, parse each with Ollama, print results.

Uses the project's OllamaClient so prompt stays in sync with the API.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.llm.ollama import OllamaClient
from app.parser.extractor import extract_text
from app.storage.client import minio_client


async def parse_one(llm: OllamaClient, file_id: str, content: bytes) -> dict:
    text = extract_text(content)
    print(f"\n  Extracted {len(text)} chars of text")
    result = await llm.extract(text)
    return result.model_dump()


async def main() -> None:
    llm = OllamaClient()

    objects = list(minio_client.list_objects(settings.minio_bucket))
    if not objects:
        print("No objects found in bucket.")
        return

    print(f"Found {len(objects)} file(s) in bucket '{settings.minio_bucket}':")
    for obj in objects:
        print(f"  - {obj.object_name}  ({obj.size} bytes)")

    for obj in objects:
        file_id = obj.object_name
        print(f"\n{'='*60}")
        print(f"Parsing: {file_id}")

        resp = minio_client.get_object(settings.minio_bucket, file_id)
        try:
            content = resp.read()
        finally:
            resp.close()
            resp.release_conn()

        try:
            result = await parse_one(llm, file_id, content)
            print(f"\nResult for {file_id}:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        except Exception as exc:
            print(f"ERROR: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
