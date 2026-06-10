
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts._auth import login

CONCURRENT_UPLOADS = 10   # parallel uploads per batch
BULK_CHUNK_SIZE = 100     # max file_ids per /bulk call
BASE_URL = "http://localhost:8000"


async def _upload_one(
    client: httpx.AsyncClient,
    headers: dict,
    file_path: Path,
    sem: asyncio.Semaphore,
    index: int,
    total: int,
) -> str | None:
    async with sem:
        print(f"  [{index}/{total}] Uploading {file_path.name} …")
        try:
            content = file_path.read_bytes()
            resp = await client.post(
                f"{BASE_URL}/files/upload",
                headers=headers,
                files={"file": (file_path.name, content, "application/octet-stream")},
                timeout=60.0,
            )
            if resp.status_code not in (200, 201):
                print(f"  [{index}/{total}] FAILED {file_path.name}: {resp.status_code} {resp.text[:120]}")
                return None
            data = resp.json()
            if "file_id" not in data:
                print(f"  [{index}/{total}] FAILED {file_path.name}: no file_id in response")
                return None
            return data["file_id"]
        except Exception as exc:
            print(f"  [{index}/{total}] ERROR {file_path.name}: {exc}")
            return None


async def bulk_upload(directory: str, job_id: str) -> None:
    # Auth
    try:
        headers = login(BASE_URL)
    except SystemExit:
        print("ADMIN_EMAIL/PASSWORD not set, trying default test admin…")
        async with httpx.AsyncClient() as c:
            resp = await c.post(
                f"{BASE_URL}/auth/login",
                json={"email": "admin@test.local", "password": "Admin1234"},
                timeout=10.0,
            )
        if resp.status_code != 200:
            print(f"Login failed ({resp.status_code}): {resp.text}")
            return
        headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    dir_path = Path(directory)
    if not dir_path.exists():
        print(f"Directory not found: {directory}")
        return

    extensions = {".pdf", ".docx", ".txt"}
    files_to_upload = [
        f for f in sorted(dir_path.iterdir())
        if f.is_file() and f.suffix.lower() in extensions
    ]
    if not files_to_upload:
        print(f"No .pdf/.docx/.txt files in {directory}")
        return

    total = len(files_to_upload)
    print(f"Found {total} files. Uploading {CONCURRENT_UPLOADS} at a time…\n")

    sem = asyncio.Semaphore(CONCURRENT_UPLOADS)
    async with httpx.AsyncClient() as client:
        tasks = [
            _upload_one(client, headers, fp, sem, i + 1, total)
            for i, fp in enumerate(files_to_upload)
        ]
        results = await asyncio.gather(*tasks)

    file_ids = [fid for fid in results if fid is not None]
    failed = total - len(file_ids)
    print(f"\nUploaded {len(file_ids)}/{total} files ({failed} failed).")

    if not file_ids:
        print("Nothing to submit.")
        return

    # Submit in chunks of BULK_CHUNK_SIZE
    print(f"\nCreating applications for job {job_id}…")
    all_app_ids: list[str] = []
    async with httpx.AsyncClient() as client:
        for start in range(0, len(file_ids), BULK_CHUNK_SIZE):
            chunk = file_ids[start: start + BULK_CHUNK_SIZE]
            resp = await client.post(
                f"{BASE_URL}/jobs/{job_id}/applications/bulk",
                headers=headers,
                json={"file_ids": chunk, "source": "bulk_upload"},
                timeout=60.0,
            )
            if resp.status_code not in (200, 201, 202):
                print(f"Bulk create failed (chunk {start}–{start + len(chunk)}): {resp.status_code} {resp.text[:200]}")
                continue
            data = resp.json()
            if "application_ids" not in data:
                print(f"  Bulk create missing application_ids in response: {str(data)[:200]}")
                continue
            ids = data["application_ids"]
            all_app_ids.extend(ids)
            print(f"  Submitted chunk {start + 1}–{start + len(chunk)}: {len(ids)} applications queued")

    print(f"\nDone. {len(all_app_ids)} applications queued for parsing.")
    print("Candidates appear in the app as the worker processes each resume.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/bulk_upload_candidates.py <directory> <job_id>")
        print("Example: python scripts/bulk_upload_candidates.py C:\\resumes\\batch1 <uuid>")
        sys.exit(1)
    asyncio.run(bulk_upload(sys.argv[1], sys.argv[2]))
