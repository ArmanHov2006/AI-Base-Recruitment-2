# AI-Based Recruitment Platform

AI-powered recruitment platform for AI_Based_recruitment. Parses resumes with a local or cloud LLM, scores candidates against job descriptions, tracks hiring pipelines, and supports structured candidate comparison.

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 + FastAPI (modular monolith) |
| Frontend | React 18 + TypeScript + Ant Design + Vite |
| Database | PostgreSQL 16 + pgvector + Alembic + SQLAlchemy 2 (async) |
| File storage | MinIO (S3-compatible) |
| AI / LLM | Ollama (local) or OpenAI — swap via `LLM_PROVIDER` env var |
| Background tasks | Celery + Redis |
| Auth | JWT (access + refresh), RBAC (admin / recruiter / hr_manager / viewer) |
| Prod proxy | Traefik v3 + Let's Encrypt TLS |

## Features

- **Resume ingestion**: upload PDF/DOCX → LLM extracts structured candidate profile + vector embedding
- **Candidate management**: search, filter by skills/stage, soft-delete, GDPR export
- **Job management**: post jobs, attach required skills and description
- **AI scoring**: evaluate each candidate against a job via LLM, store structured scores
- **Comparison engine**: head-to-head candidate comparisons with leaderboard ranking
- **Hiring pipeline**: stage-based funnel (applied → screening → interview → offer → hired/rejected)
- **AI chat**: streaming LLM chat with candidate context
- **Notes & evaluations**: per-candidate recruiter notes and structured evaluations
- **Notifications**: in-app notifications + Slack / MS Teams webhook alerts
- **Analytics**: aggregated pipeline and scoring metrics
- **Audit log**: middleware records every mutating request with before/after snapshots
- **Rate limiting**: per-endpoint limits via slowapi

## Local Development

### Prerequisites

- Docker Desktop, `uv` (`pip install uv`), Node 20+

### Start infrastructure

```bash
cp .env.example .env          # fill in required values
docker compose up -d          # postgres, minio, redis, mailpit, worker
```

### Backend

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev                   # http://localhost:3000
```

### Email (dev)

Mailpit catches all outgoing SMTP at http://localhost:8025.

## Environment Variables

See `.env.example` for the full list. Required variables:

| Variable | Description |
|---|---|
| `JWT_SECRET` | Strong random secret ≥32 chars (`openssl rand -hex 32`) |
| `POSTGRES_*` | Database connection |
| `MINIO_*` | Object storage connection |
| `REDIS_URL` | Celery broker / result backend |
| `LLM_PROVIDER` | `ollama` (default) or `openai` |
| `OPENAI_API_KEY` | Required when `LLM_PROVIDER=openai` |

## Production Deployment

Uses `docker-compose.prod.yml`. Requires a server with Docker and a DNS A record pointing to `APP_DOMAIN`.

```bash
cp .env.example .env.prod     # fill in production values
docker compose -f docker-compose.prod.yml up -d
```

Traefik obtains a Let's Encrypt TLS certificate automatically. For GPU-accelerated Ollama, uncomment the `deploy.resources` block in `docker-compose.prod.yml`.

## Project Structure

```
app/
├── main.py              # FastAPI app, lifespan, middleware, router wiring
├── config.py            # pydantic-settings (reads .env)
├── auth.py              # JWT issue/verify, RBAC dependency
├── llm/                 # LLMClient factory — OllamaClient / OpenAIClient
├── parser/              # Resume text extraction + LLM parse
├── storage/             # MinIO upload, presigned URL generation
├── candidates/          # Candidate CRUD, embedding, dedup
├── jobs/                # Job CRUD + scoring endpoints
├── applications/        # Hiring pipeline stages
├── comparisons/         # Head-to-head comparison + leaderboard
├── evaluations/         # Structured LLM evaluations
├── notes/               # Recruiter notes
├── notifications/       # In-app + webhook notifications
├── analytics/           # Aggregated metrics
├── audit/               # Audit log middleware + query API
├── ai/                  # Streaming LLM chat endpoint
├── gdpr/                # Data export / erasure
└── users/               # User management + invite flow
alembic/                 # DB migrations
frontend/                # React app
```

## Security

- JWT access tokens (15 min) + refresh tokens (7 days, HttpOnly cookie)
- RBAC enforced at dependency level — read vs write roles checked per endpoint
- Magic-byte file validation, 10 MB cap, extension whitelist on upload
- UUID-only MinIO keys — no user-controlled path bytes
- 5-minute presigned URL TTL
- Prompt-injection mitigation: resume content wrapped in `<resume>…</resume>` delimiter
- CORS locked to `allowed_origins` (configurable)
- `Candidate.deleted_at` soft-delete; GDPR hard-delete via dedicated endpoint
- Audit log on every mutating request
- Non-root Docker user (`appuser`) in backend and worker images
