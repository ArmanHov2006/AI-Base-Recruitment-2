# AI-Based Recruitment Platform

AI-powered candidate management for AI_Based_recruitment. Upload resumes → LLM parses → rank candidates per job → track through hiring pipeline.

**Stack:** Python 3.12 · FastAPI · PostgreSQL 16 + pgvector · MinIO · Celery + Redis · React 18 · Ant Design · Vite · Docker

## Local Dev (5 commands)

```powershell
cp .env.example .env          # fill in values
docker compose up -d          # postgres + minio + redis + mailpit
uv run alembic upgrade head   # run all 30 migrations
uv run uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev    # :3000
# Celery worker (separate terminal):
uv run celery -A app.worker.celery_app worker -l info
```

Create first admin: `uv run python scripts/create_admin.py`

## Production Deploy

```bash
cp .env.prod.example .env.prod   # fill APP_DOMAIN, secrets, LLM vars
docker compose -f docker-compose.prod.yml up -d --build
```

Traefik auto-provisions TLS via Let's Encrypt. App at `https://$APP_DOMAIN`.

## Key Features

| Feature | Where |
|---------|-------|
| Resume upload + LLM parse | `POST /files/upload` → `POST /parse` |
| AI scoring per job | Celery `score_candidates_for_job_task` |
| Candidate comparison + verdict | `POST /jobs/{id}/comparisons` |
| Kanban pipeline | `frontend/src/pages/Pipeline.tsx` |
| Notifications + @mentions | `app/notifications/` |
| RBAC (admin/recruiter/hr_manager/viewer) | `app/users/models.py` → `UserRole` |
| GDPR data export | `GET /gdpr/candidates/{id}/export` |
| Audit log | `GET /audit/logs` + `GET /audit/business-events` |

## Architecture

Modular monolith. One FastAPI process, one Celery worker, PostgreSQL + MinIO + Redis.
See Obsidian `02 - Architecture.md` for full system diagram.

## Migrations

Chain: `0001 → … → 0030` (30 migrations). Current head: `0030_candidate_photo_url`.
Run: `uv run alembic upgrade head`

## Tests

```
uv run pytest                   # all 212 tests
uv run pytest tests/test_auth.py -v
```

Golden-set eval (interview-scoring tier drift, needs live Ollama/OpenAI, opt-in):

```
RUN_GOLDEN_EVAL=1 uv run pytest tests/test_interview_scoring_golden.py -v
```
