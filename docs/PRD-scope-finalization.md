# PRD — AI Recruitment Platform: Scope Finalization (Build Spec)

**Status:** Approved, ready to build
**Date:** 2026-06-03
**Owner:** Arman (Ardshinbank)
**Audience:** A fresh build session. This document is self-contained — read it top to bottom, then execute the build order in §8. Do not relitigate the decisions in §3; they are locked.

---

## 1. Context

Internal AI-powered recruitment platform for **Ardshinbank** (Armenia). Recruiters upload candidate resumes, the system parses them with an LLM, scores candidates against jobs, and supports search, comparison, evaluation, and a hiring pipeline.

**This is an internal bank tool.** Not SaaS, not consumer-facing, not 1M+ scale. Finite candidate pool (hundreds–thousands). These constraints already drove the decisions below — honor them.

## 2. Current architecture (what already exists — do not rebuild)

- **Backend:** FastAPI **modular monolith** (not microservices — deliberate). Python, `uv` for deps, `pyproject.toml`.
- **DB:** PostgreSQL via SQLAlchemy async + Alembic. Migration head is **`0030_add_photo_url`**; the next migration is **`0031`**.
- **Async:** Celery + Redis. Worker at `app/worker/`, beat schedule in `app/worker/celery_app.py` (already has `audit-purge-daily`).
- **Storage:** MinIO (S3-compatible) via `app/storage/`.
- **LLM:** Factory-switched between Ollama (local) and OpenAI — `app/llm/factory.py`, `app/llm/ollama.py`, `app/llm/openai_client.py`, base in `app/llm/base.py`. Hybrid scoring rubric in `app/llm/rubric.py`.
- **Search:** Postgres-native today — `pg_trgm` fuzzy (migration 0016) + `pgvector` semantic (migration 0020). Endpoints in `app/candidates/router.py`: `/candidates/search`, `/candidates/semantic-search`, `/candidates/{id}/similar`.
- **Auth:** Own JWT + bcrypt(12 rounds). `app/auth.py`, `app/users/`, `app/security.py`. RBAC via `UserRole` + `require_role()`. Roles: ADMIN, RECRUITER, HR_MANAGER, VIEWER. Rate limiting via slowapi (`app/limiter.py`).
- **Observability:** `audit_log` (HTTP middleware) + `business_events` (semantic) — `app/audit/`. GDPR export in `app/gdpr/`.
- **Notifications:** in-app (`notifications` table) + email + Slack/Teams webhook + SSE real-time. `app/notifications/` — note `create_notification(db, user_id, type_, payload)` in `service.py`.
- **Frontend:** React + TypeScript + Ant Design (dark theme), Vite. In `frontend/`.

Modules registered in `app/main.py`: auth, users-admin, storage, parser, candidates, jobs, applications, comparisons, evaluations, notes, notifications, analytics, audit, ai, gdpr.

**Already built and working** (do NOT re-implement): resume upload (PDF/DOCX/TXT + OCR), bulk upload, duplicate detection (embedding cosine), resume versioning (`candidate_resumes`), AI extraction, hybrid scoring (`candidate_job_scores`), comparison + S/A/B/F tiering + leaderboard, evaluations, notes + @mentions, analytics (overview/funnel/recruiter-activity/time-to-hire + PDF), CSV/XLSX/PDF export, candidate status workflow with CHECK constraint, AI chat assistant (`/ai/chat`), AI interview questions.

## 3. Locked decisions (do not reopen)

| # | Decision |
|---|---|
| D1 | Interview scheduling: lightweight, on `job_applications`, with full change history to `business_events`. |
| D2 | Multi-tenancy: **skipped**. Single tenant. Do not add `tenant_id`. |
| D3 | Auth: add **Azure AD OIDC**, keep password auth as break-glass. |
| D4 | AI provider: **OpenAI in dev** (no GPU), **Ollama in prod**. Factory already supports this — config only. |
| D5 | Search: **add Elasticsearch** for text; keep pgvector for semantic. |
| D6 | Analytics: add **candidate-sources** endpoint; defer AI-match-accuracy. |
| D7 | Pull to core: **multi-language resumes (Armenian + Russian + English)** and **auto job descriptions**. Defer all other §8 future items. |

---

## 4. Feature specs

### F1 — Interview scheduling + reminders (D1)

**Goal:** Schedule an interview datetime/location per application; remind interviewer + recruiter before it; keep full reschedule history.

**Data model** — migration `0031`:
- Add to `job_applications` (`app/applications/models.py`):
  - `interview_scheduled_at TIMESTAMPTZ NULL`
  - `interview_location VARCHAR(500) NULL` (room name or video link)
- **No new table.** Reschedule history is reconstructed from `business_events`.

**Behavior:**
- New endpoint to set/update interview: `PATCH /jobs/{job_id}/applications/{app_id}/interview` (RECRUITER/HR_MANAGER/ADMIN). Body: `{ scheduled_at, location }`.
- On every set/change/clear, emit a `business_events` row (action like `interview.scheduled` / `interview.rescheduled` / `interview.cleared`) capturing old + new value, actor, request_id. Follow the existing `app/audit/events.py` `record()` pattern.
- Setting an interview also creates an in-app notification (`create_notification`) + email to the assigned recruiter.
- **Reminder:** add a Celery beat task (in `app/worker/`, register in `celery_app.py` `beat_schedule`) that runs every 15 min, finds applications with `interview_scheduled_at` in the next 24h (and again ~1h before) not yet reminded, and fires notification + email. Track "reminded" state idempotently (e.g. a `business_events` marker or a dedup key) so reminders don't double-fire.

**Acceptance:**
- Can set, change, and clear an interview time; each action lands in `business_events`.
- Rescheduling does not lose prior times (reconstructable from events).
- A reminder fires once ~24h before and once ~1h before; never duplicates.
- Frontend: interview datetime visible on the application/pipeline card; a simple date-time picker to set it.

### F2 — Azure AD OIDC SSO (D3)

**Goal:** Recruiters sign in with Ardshinbank Microsoft accounts (Entra ID). Password login remains for break-glass admin, dev, and CI.

**Approach:**
- Add OIDC Authorization Code flow (with PKCE) against Azure AD. Use a standard lib (e.g. `authlib`).
- New routes (e.g. `/auth/sso/login` → redirect to Azure, `/auth/sso/callback` → exchange code, map the verified email to an existing `users` row, mint your **existing** app JWT). Reuse current JWT issuance — SSO is a new identity source, not a new token system.
- **User mapping:** match on verified email claim. If no matching active user, deny (provisioning stays invite-based via existing admin flow) — do NOT auto-create users from SSO unless explicitly enabled by a config flag.
- **Config:** `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_REDIRECT_URI` in `app/config.py` (all optional; SSO routes 404/disabled if unset).
- **MFA:** enforced on the Azure side, not in app code.
- **Keep** all existing password endpoints untouched.

**Build note:** Bank IT must provide real Azure app-registration credentials for production. For the build, develop and test against a **free personal Azure AD / Entra tenant**; production is a credentials swap. Do not block other features on this.

**Acceptance:**
- With Azure creds set, `/auth/sso/login` completes a full round-trip and yields a valid app JWT for a pre-existing user.
- With creds unset, SSO routes are disabled and password login works unchanged.
- Unknown SSO email → access denied (no silent user creation).
- Password login still works (break-glass).

### F3 — AI provider config split (D4)

**Goal:** OpenAI in dev, Ollama in prod, via the existing factory. This is **mostly configuration**, not new code.

**Tasks:**
- Confirm `app/llm/factory.py` selects provider from a single setting (e.g. `LLM_PROVIDER=openai|ollama`). If not already, make it do so.
- Document `.env` examples: dev uses `openai`, prod uses `ollama`.
- **Guardrail (must enforce in docs + reviewer note):** dev/OpenAI path must only ever see **synthetic** resumes (`scripts/generate_*_resumes.py`), never real candidate PII, until a DPA exists.
- Prod infra dependency (flag, not code): a GPU host to run Ollama.

**Acceptance:** Switching `LLM_PROVIDER` swaps the client with no code change. Both paths pass existing LLM tests.

### F4 — Elasticsearch search (D5)

**Goal:** Add Elasticsearch for **text** search — fuzzy, **synonyms** (e.g. JS↔JavaScript, k8s↔Kubernetes), **facets/aggregations** (counts per skill/location/seniority), **BM25 ranking**. Keep **pgvector** for semantic + `/similar` (do not duplicate vectors in ES).

**Ownership split:**
- `GET /candidates/search` → re-implement against Elasticsearch (text, fuzzy, synonyms, facets, BM25).
- `GET /candidates/semantic-search` and `/candidates/{id}/similar` → **stay on pgvector**. Untouched.

**Sync strategy — Celery outbox (mandatory, do not dual-write inline):**
- On candidate create / update / soft-delete, enqueue a Celery task that (re)indexes or removes that candidate document in ES. Reuse the existing worker. Tasks must be **idempotent and retryable** so ES downtime never breaks uploads and never drifts permanently.
- Add a **backfill task** to index all existing candidates (mirror the pattern in `scripts/reparse_candidates.py`).

**Index design:**
- One `candidates` index. Per-field analyzers chosen for the languages in F5 (Armenian + Russian + English) — see F5; pick analyzers/tokenizers that handle Armenian and Cyrillic, not just Latin.
- Synonyms via an ES synonym filter (seed a starter skill-synonym list; make it editable).
- Facets via ES aggregations returned alongside results.

**Infra:** add Elasticsearch service to `docker-compose.yml` (and `docker-compose.prod.yml`), secured. New settings in `app/config.py` (`ELASTICSEARCH_URL`, auth).

**Acceptance:**
- `/candidates/search` returns fuzzy + synonym-expanded + BM25-ranked results with facet counts.
- Creating/updating/deleting a candidate is reflected in ES within one worker cycle; ES outage degrades gracefully (writes still succeed, index catches up on retry).
- Backfill indexes the full existing corpus.
- `semantic-search` and `similar` behavior unchanged (still pgvector).

### F5 — Multi-language resume support: Armenian + Russian + English (D7)

**Goal:** Resumes arriving in **Armenian, Russian, or English** are parsed, extracted, scored, and searched correctly. This is a **correctness** requirement for the Armenian market, not a nice-to-have.

**Touch points:**
1. **OCR** (`app/parser/extractor.py`, `_ocr_pdf`): ensure OCR language packs cover `hye` (Armenian), `rus` (Russian), `eng`. Configure Tesseract (or equivalent) with all three.
2. **LLM extraction prompts** (`app/llm/` + `app/ai/prompts.py`): prompts must instruct the model to extract correctly from non-English text and **normalize output** (e.g. skills, seniority) to a consistent canonical form regardless of source language. Decide and document the canonical output language (recommend English for tags/skills to keep search/scoring uniform; preserve original text for the summary/raw fields).
3. **Search analyzers** (F4 ES index): Armenian + Cyrillic-aware analyzers so tokenization/stemming works; pg_trgm already handles raw substrings but ES is the primary text path.
4. **Detection:** detect resume language (cheap heuristic or library) and store it on the candidate for filtering/debugging.

**Acceptance:**
- An Armenian-script resume and a Russian-script resume both produce correctly populated structured fields (name, skills, experience).
- Such candidates are findable via search using both their original-language terms and canonical English skill terms.
- No crash/garbling on non-Latin input anywhere in upload → parse → index → search.

### F6 — Candidate sources analytics (D6)

**Goal:** Report where candidates come from. The `source` column already exists on `job_applications` (`models.py:39`, migration 0028) — just aggregate it.

**Tasks:**
- New endpoint `GET /analytics/sources` (auth required, follow `app/analytics/router.py` conventions): `GROUP BY source` → `[{ source, count }]`, NULL bucketed as "unknown".
- Add a schema in `app/analytics/schemas.py`.
- Optionally surface on the analytics dashboard + include in the analytics PDF (`app/pdf/builders.py`) — match existing sections.

**Acceptance:** Endpoint returns per-source counts; frontend shows a sources breakdown.

### F7 — Auto job descriptions (D7)

**Goal:** Generate a draft job description from minimal input (title + key skills + seniority) using the existing LLM client.

**Tasks:**
- New endpoint (e.g. `POST /jobs/generate-description`, RECRUITER/HR_MANAGER/ADMIN, rate-limited per `app/limiter.py` conventions). Input: title, seniority, required skills, optional notes. Output: structured draft (summary, responsibilities, requirements) the recruiter can edit before saving.
- Use the existing LLM factory client and a new prompt in `app/ai/prompts.py`. Do **not** auto-save a job — return a draft only.
- Frontend: a "Generate" button on the job-create form that fills the fields.

**Acceptance:** Given a title + skills, returns an editable draft description; recruiter edits then saves through the normal job-create flow.

## 5. Explicitly OUT of scope (deferred — do not build)

- Multi-tenancy / `tenant_id` / RLS (D2).
- AI-match-accuracy analytics (D6) — defer until real hire volume.
- Microservice split / API gateway / horizontal scaling (not 1M+).
- §8 future items: video interview analysis, AI interview summaries, voice analysis, LinkedIn integration, ATS integration, AI hiring recommendations.
- Public social login (Google/LinkedIn). SSO is corporate Azure AD only.

## 6. Non-functional / conventions

- Match existing code style and module layout. Each feature: `models.py` / `schemas.py` / `router.py` (+ `service.py` if logic-heavy), mirroring existing modules.
- Every new migration: sequential id after `0030`, with a runtime-vs-migration test where a CHECK/enum is touched (see existing `tests/` patterns for status constraints).
- Every write action that matters: emit a `business_events` record (`app/audit/events.py`).
- Tests: add unit tests per new endpoint following existing `tests/` structure (mock DB pattern already established). Keep the existing test suite green.
- Security: never log secrets/PII; respect existing rate-limit decorators; keep password auth intact.
- After code changes: run `graphify update .` (per CLAUDE.md) and update the Obsidian KB if the daily-sync rule applies.

## 7. External blockers (parallel, not code)

1. Bank IT → Azure AD app registration (client id/secret/tenant) for F2 prod.
2. Bank IT → GPU host to run Ollama for F3 prod.
3. Legal → OpenAI DPA decision (only if cloud LLM on real PII is ever wanted; current plan avoids it — dev uses synthetic data).

## 8. Build order (dependency-sorted)

1. **F1** Interview scheduling — small, self-contained, immediate value.
2. **F6** Candidate-sources analytics — trivial, fast win.
3. **F5** Multi-language (hy/ru/en) — must precede ES so analyzers are chosen with real languages in mind.
4. **F4** Elasticsearch — biggest lift; depends on F5 language decisions for index analyzers.
5. **F7** Auto job descriptions — cheap LLM feature, slot anytime.
6. **F2** Azure AD SSO — start on throwaway tenant now, finish when IT delivers creds.
7. **F3** AI provider config — mostly config; verify and document anytime.

Build incrementally: one feature, migration if needed, tests green, atomic commit, then next.

## 9. Execution strategy — ONE WORKTREE PER FEATURE (mandatory)

Each feature is built in its **own git worktree on its own branch**, in a **separate build chat**. Rationale: isolated context per chat (no accumulation of unrelated feature history), clean diffs, parallelizable independents, and no migration-number collisions from features stepping on each other.

**Rules:**
- One worktree = one feature = one branch = one PR. Never build two features in the same worktree.
- Each build chat opens its worktree, reads this PRD, builds only its assigned feature, keeps tests green, commits atomically, opens a PR. It does **not** touch other features.
- **Migration numbering:** only features that need a migration claim a number, and they must be **merged in claim order** to avoid duplicate ids. Pre-assign: **F1 → `0031`**. F4, F5 may need migrations (ES is mostly external; F5 may add a `resume_language` column) — whichever merges first after F1 takes `0032`, next `0033`, etc. A feature that branches while another's migration is unmerged must rebase and renumber before merge.

**Dependency waves** (a worktree in a later wave branches from `main` *after* the prior wave merged):

- **Wave 1 — parallel, fully independent** (branch all from current `main`): **F1**, **F6**, **F7**, **F2**, **F3**.
- **Wave 2 — F5** (multi-language). Can start in parallel, but **merge before F4**.
- **Wave 3 — F4** (Elasticsearch). Branch from `main` **after F5 is merged**, so ES analyzers are built against the finalized language support.

**Branch naming:** `feat/f1-interview-scheduling`, `feat/f2-azure-sso`, `feat/f3-llm-provider-config`, `feat/f4-elasticsearch`, `feat/f5-multilang-resumes`, `feat/f6-source-analytics`, `feat/f7-auto-job-descriptions`.

**Worktree setup (run from the main repo root):**
```bash
git worktree add ../recruit-f1 -b feat/f1-interview-scheduling
git worktree add ../recruit-f6 -b feat/f6-source-analytics
git worktree add ../recruit-f7 -b feat/f7-auto-job-descriptions
git worktree add ../recruit-f2 -b feat/f2-azure-sso
git worktree add ../recruit-f3 -b feat/f3-llm-provider-config
git worktree add ../recruit-f5 -b feat/f5-multilang-resumes
# F4 only AFTER f5 merges to main:
# git worktree add ../recruit-f4 -b feat/f4-elasticsearch
```
Clean up after merge: `git worktree remove ../recruit-fX`.

**Per-feature build-chat kickoff prompt** (paste into a fresh chat, opened in that worktree's directory):
> Read `docs/PRD-scope-finalization.md`. Build **only feature F&lt;N&gt;** per §4 and the conventions in §6. You are in the `feat/f&lt;N&gt;-...` worktree — stay in scope, do not touch other features. Keep the existing test suite green, add tests for your feature, commit atomically, then open a PR. If you need a migration, use the number assigned in §9.

