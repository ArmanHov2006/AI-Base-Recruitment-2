# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)

## Daily Obsidian Knowledge Base Sync

**At the start of every conversation**, read `C:\Users\Arman\Documents\Obsidian\Personal OS\07 - AI Recruitment\00 - Guide\00 - Home.md` front matter. Check `last_updated`. If it is not today's date (YYYY-MM-DD), perform a full Obsidian sync before doing any other work:

### Sync Protocol

1. Run `git log --oneline -10` to see recent commits
2. Check `alembic/versions/` for new migrations
3. Check `app/` for new/changed modules
4. Update these Obsidian files (path: `C:\Users\Arman\Documents\Obsidian\Personal OS\07 - AI Recruitment\`):
   - `00 - Guide/00 - Home.md` — bump `last_updated`, update phase status table and migration chain
   - `02 - Core/02 - Architecture.md` — update module map if new files added
   - `02 - Core/03 - Data Model.md` — add new tables/columns if new migrations exist
   - `04 - Reference/10 - API Cheatsheet.md` — add new endpoints if routers changed
   - `04 - Reference/11 - Troubleshooting.md` — add new known issues if any surfaced
   - Any feature note in `03 - Features/` where the feature changed significantly
5. Set `last_updated: YYYY-MM-DD` in `00 - Guide/00 - Home.md` front matter

### What Makes a Good Note Update

- **Pointers**: always include `app/module/file.py:function` references
- **Why not X**: capture rejected alternatives (e.g. "pgvector over Qdrant — already in Postgres, no extra service")
- **Migration chain**: keep the chain current (0001 → … → current) in both `00 - Home.md` and `03 - Data Model.md`

Announce: "Obsidian synced for YYYY-MM-DD" once done, then handle the user's request.

---

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore

---

## Commands

### Backend

```bash
# Start infra (postgres, minio, redis, mailpit, worker)
docker compose up -d

# Install deps + migrate + run API
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs  
Mailpit (dev email): http://localhost:8025

### Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
npm run build
```

### Tests

```bash
# All tests
uv run pytest

# Single test file
uv run pytest tests/test_candidates.py -v

# Single test
uv run pytest tests/test_rbac.py::test_admin_can_delete_user -v
```

Tests use mocked DB (`make_mock_db()` from `tests/conftest.py`) — no live Postgres needed for most suites. `test_e2e_pipeline.py` and ES tests require running infra.

### Lint / type-check

```bash
uv run ruff check app tests
uv run ruff format app tests
uv run mypy app
uv run pip-audit
```

### Backfill scripts (run after infra is up)

```bash
# Backfill pgvector embeddings + ES index for pre-existing candidates
uv run python scripts/backfill_search.py

# Embeddings only / ES only
uv run python scripts/backfill_search.py --embeddings-only
uv run python scripts/backfill_search.py --es-only
```

---

## Architecture

**Modular monolith** — FastAPI backend (`app/`), React frontend (`frontend/`), Celery workers, all orchestrated via Docker Compose.

### Backend module layout (`app/`)

Each domain module under `app/` follows the same pattern: `models.py` (SQLAlchemy ORM), `schemas.py` (Pydantic), `router.py` (FastAPI endpoints), optional `service.py`.

| Module | Responsibility |
|---|---|
| `main.py` | App factory, lifespan hooks (MinIO bucket, ES index, LLM warmup), middleware/router wiring |
| `config.py` | `pydantic-settings` — reads `.env`; validates `JWT_SECRET` strength at startup |
| `database.py` | Async SQLAlchemy engine, `Base`, `get_db` session dependency |
| `auth.py` | JWT bearer extraction, `get_current_user`, role-check dependencies (`require_admin` etc.) |
| `security.py` | `create_access_token` / `decode_access_token` (python-jose) |
| `auth_sso.py` | OAuth2 / SSO router (Authlib) |
| `llm/` | `LLMClient` factory (swap via `LLM_PROVIDER` env). `OllamaClient` / `OpenAIClient` share base interface. `rubric.py` owns deterministic scoring formula |
| `parser/` | Resume text extraction (pypdf, python-docx) + LLM-based structured parse |
| `storage/` | MinIO upload, presigned URL generation (UUID-only keys) |
| `candidates/` | Candidate CRUD, pgvector embedding, dedup |
| `jobs/` | Job CRUD + `POST /jobs/{id}/score/{candidate_id}` scoring endpoint |
| `applications/` | Hiring pipeline stage transitions |
| `comparisons/` | Head-to-head comparison + leaderboard (`CandidateJobScore` model) |
| `evaluations/` | Structured per-candidate LLM evaluations |
| `search/` | Elasticsearch async client (`client.py`), `service.py` for text search. Falls back silently to Postgres when `ELASTICSEARCH_URL` unset |
| `worker/` | Celery app (`celery_app.py`), async tasks for scoring, embedding, audit |
| `notifications/` | In-app + Slack / MS Teams webhook alerts |
| `audit/` | `AuditLogMiddleware` — records every mutating request with before/after JSONB snapshots |
| `ai/` | Streaming LLM chat endpoint with candidate context |
| `gdpr/` | Data export / hard-delete erasure |
| `watchers/` | SLA digest watchers |

### Scoring pipeline (hybrid LLM + deterministic)

1. `POST /jobs/{id}/score/{candidate_id}` triggers `worker/scoring.py` via Celery.
2. LLM classifies each candidate dimension into a fixed tier (`excellent / strong / partial / weak / none`) defined in `app/llm/rubric.py::SCORE_TIERS`.
3. `rubric.py::TIER_POINTS` + `SCORE_WEIGHTS` produce a deterministic 0–100 score. Weights: skills_match 0.55, experience_level 0.30, seniority_fit 0.12, education 0.03.
4. Local-hire bonus (Armenia/Yerevan tokens) bumps tier one step up before aggregation.
5. Result stored in `CandidateJobScore` (comparisons module). **Tune weights in `rubric.py`, never in the LLM prompt.**

### Search architecture (dual-path)

- **Keyword / multi-language**: Elasticsearch `candidates` index with per-field Armenian / Russian / English analyzers + synonym graph (`app/search/synonyms.py`).
- **Semantic / similar**: pgvector (PostgreSQL extension) — embeddings generated by Ollama `nomic-embed-text` or OpenAI `text-embedding-3-small`.
- ES client is `None` when `ELASTICSEARCH_URL` is unset; callers fall back to Postgres. After dependency changes, verify the index actually creates — see memory note on ES silent fallback.

### Auth / RBAC

- **Roles**: `admin / recruiter / hr_manager / viewer`
- JWT access token (15 min) + refresh token (7 days, HttpOnly cookie).
- Role checks are FastAPI dependencies injected at router level, not middleware.
- SSO via `auth_sso.py` (Authlib). Note: `.local` email domains cannot log in — use real or `@test.example` addresses in dev.

### Frontend (`frontend/src/`)

- React 18 + TypeScript + Ant Design + Vite.
- `api/client.ts` — Axios instance with JWT interceptor and refresh-token retry.
- Per-domain API files mirror backend modules (`candidates.ts`, `jobs.ts`, …).
- Pages under `pages/` map 1-to-1 to routes. Shared components in `components/`.
- Design system: dark theme, single accent indigo `#5b6af5`.

### Infrastructure

- `docker-compose.yml` — local dev: postgres (pgvector/pgvector:pg16), MinIO, Redis, Mailpit, Celery worker.
- `docker-compose.prod.yml` — production: adds Traefik v3 + Let's Encrypt TLS.
- API port 8000 (backend), 3000 (frontend dev). MinIO console: 9001.
- Celery broker: Redis. Worker registered in `app/worker/celery_app.py`.

### Key cross-cutting patterns

- All DB models import from `app.database.Base` — SQLAlchemy 2 async ORM.
- `app/resumes/models.py` must be imported in `main.py` (noqa F401) to register `CandidateResume` with Base before migrations.
- File uploads: magic-byte validation + extension whitelist + 10 MB cap in `storage/` router.
- Rate limiting: `slowapi` per-endpoint, configured in `app/limiter.py`.
- Audit log: `AuditLogMiddleware` in `app/audit/middleware.py` wraps every mutating request.
