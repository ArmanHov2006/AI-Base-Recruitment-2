import asyncio
import sys

sys.path.insert(0, '.')
from sqlalchemy import text

from app.database import async_session_factory


async def check():
    async with async_session_factory() as db:
        uuids = [
            '6647b929-6113-4260-8476-0fc65b086374',
            '30ca2e0d-b5a8-42f0-96b7-d60dda7916cf',
            '086c142c-ffe8-4914-888a-39427613cad3',
        ]
        print('=== Duplicate target candidates ===')
        for u in uuids:
            r = await db.execute(text('SELECT name, email, phone FROM candidates WHERE id = :id'), {'id': u})
            row = r.fetchone()
            print(f'  {u[:8]}: {row}')

        print()
        print('=== All candidates (name / email) ===')
        r = await db.execute(text('SELECT id, name, email FROM candidates ORDER BY name'))
        for row in r.fetchall():
            print(f'  {str(row[0])[:8]}: {row[1]} | {row[2]}')

        print()
        print('=== Stuck parsing applications ===')
        r = await db.execute(text(
            "SELECT id, resume_file_id, error_message FROM job_applications WHERE status = 'parsing'"
        ))
        for row in r.fetchall():
            print(f'  app={str(row[0])[:8]} file={str(row[1])[:8]} err={row[2]}')

        print()
        print('=== All parse_failed errors ===')
        r = await db.execute(text(
            "SELECT error_message, COUNT(*) as cnt FROM job_applications WHERE status = 'parse_failed' GROUP BY error_message ORDER BY cnt DESC"
        ))
        for row in r.fetchall():
            print(f'  [{row[1]}x] {row[0]}')

asyncio.run(check())
