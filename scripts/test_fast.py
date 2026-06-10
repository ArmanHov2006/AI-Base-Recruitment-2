import asyncio
import uuid

from app.database import async_session_factory
from app.parser.service import parse_and_validate


async def test_fast():
    print("Starting test_fast...")
    from app.config import settings
    # ...
    settings.ollama_model = "llama3.2:1b"
    settings.llm_timeout_seconds = 300
    print(f"Using model: {settings.ollama_model}")
    
    file_id = "c195cfd8-370e-4a2d-8f26-6d94762120e0"
    job_id = uuid.UUID("cdf2aa70-56a6-4b84-94ab-569a9e7e0e66")

    async with async_session_factory() as db:
        try:
            result = await parse_and_validate(file_id, db, job_id=job_id)
            print("Successfully parsed!")
            print(result.model_dump_json(indent=2))
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_fast())
