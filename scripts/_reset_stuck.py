import asyncio
import sys

sys.path.insert(0, '.')
from datetime import datetime, timezone

from sqlalchemy import text

from app.config import settings
from app.database import async_session_factory
from app.storage.client import minio_client

STUCK_IDS = [
    '32836156-91de-43b6-8b23-5b056e2fc0ff',
    '3d494bcc-770c-4876-bbf8-ef11bd2ebd93',
    '19ef98aa-e0f7-4d7b-8f6e-7988c302ffce',
    '32e48840-ed84-4ebc-b4e9-a4edb84c38ab',
]
FILE_IDS = [
    '4fec6d0b-d119-446c-b05f-e29a6552c662',
    'e07bac19-3620-43c7-9958-24851a5f59fa',
    'ab3a2260-4fea-48b5-b807-d73ba71727b1',
    '5ff4f06a-46cd-4267-9444-45fe9001610f',
]

async def main():
    # Check if files still in MinIO
    print('=== MinIO file status ===')
    for fid in FILE_IDS:
        try:
            minio_client.stat_object(settings.minio_bucket, fid)
            print(f'  {fid[:8]}: EXISTS')
        except Exception:
            print(f'  {fid[:8]}: MISSING')

    async with async_session_factory() as db:
        now = datetime.now(timezone.utc)
        for app_id in STUCK_IDS:
            await db.execute(text(
                "UPDATE job_applications SET status='parse_failed', error_message='Stuck: manually reset', updated_at=:now WHERE id=CAST(:id AS uuid) AND status='parsing'"
            ), {'now': now, 'id': app_id})
        await db.commit()
        print(f'\nMarked {len(STUCK_IDS)} stuck applications as parse_failed.')

asyncio.run(main())
