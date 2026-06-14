# PRD — Next Stage: Production Hardening & Backlog

**Status:** Draft for review
**Date:** 2026-06-11
**Owner:** Arman
**Repo:** https://github.com/ArmanHov2006/AI-Base-Recruitment-2 (`main` @ `b9da276`)

---

## 1. Context — where we are

Full live test pass completed 2026-06-11 against real infra (Postgres+pgvector, MinIO,
Redis, Elasticsearch, Mailpit) and real data (3 users, 50 candidates, 9 jobs).

**Verified working end-to-end** (Playwright, zero console/API errors except a benign
pre-login `401 /auth/refresh`):
- Auth/login, RBAC (self-row controls locked)
- Candidates list (filters, pagination), Jobs, Pipeline Kanban with AI scores
- Audit log (1309 entries, filters), Analytics dashboard, Candidate detail (parsed
  skills/experience/education)
- **AI chat** — live OpenAI streaming, grounded answers
- Global candidate search

**Static checks** (Sonnet agents, isolated worktrees):
- `pytest` 417 passed / 1 skipped · `ruff check` clean · `mypy` clean (103 files)
- frontend `tsc` clean · `npm run build` clean

**Shipped this session:** `Ardshinbank` → `AI_Based_recruitment` rebrand (17 files,
committed `b9da276`, pushed to `origin/main`).

The product is functional. This PRD covers what stands between "works on my machine with
real infra" and "deployable, maintainable, and feature-complete for handoff."

---

## 2. Goals / Non-Goals

**Goals**
- Make the app safely deployable to production (Traefik prod stack) with a documented runbook.
- Close security/secrets-hygiene gaps surfaced during testing.
- Add CI so `main` stays green automatically on the new GitHub repo.
- Re-validate and fix the frontend UX bug list (much of `SHIP_TODO.md` may already be fixed —
  needs a fresh QA pass, not a blind re-fix).
- Sequence the deferred feature backlog (`docs/dev/TODOS.md`).

**Non-Goals (this stage)**
- New product surfaces beyond the documented backlog.
- Multi-tenant / multi-org. This is a single internal tool.
- Replacing the scoring rubric or LLM provider architecture.

---

## 3. Workstreams (prioritized)

### WS-1 — Secrets & security hygiene  · **P0**
Surfaced during testing: the local `.env` (gitignored, not committed) contains **live
secrets in plaintext**: OpenAI API key, Gmail SMTP app-password, Slack webhook.

- **S-1 (P0):** Rotate the exposed credentials (OpenAI key, Gmail app-password, Slack webhook)
  — they have been visible in plaintext on disk. Move to a secrets manager / `.env.prod`
  injected at deploy, never committed.
- **S-2 (P1):** Enforce the dev-LLM PII guardrail in code, not just docs. `.env.example`
  states the OpenAI/dev path must only process **synthetic** resumes. Today nothing prevents
  feeding real candidate PII to OpenAI. Add a config gate (e.g. refuse OpenAI provider unless
  `ALLOW_REAL_PII=false` is explicitly understood, or hard-block in prod where provider=ollama).
- **S-3 (P1):** TODO-005 — GDPR / automated-decision compliance for `CandidateJobScore.reasoning`:
  role-restrict reasoning text (admin/HR only), log `CANDIDATE_REASONING_VIEWED` business event.
  Files: `app/comparisons/schemas.py`, `app/jobs/router.py`.
- **S-4 (P2):** Restore the `git push*` deny rule in `.claude/settings.local.json` if the
  guardrail is still wanted (removed this session to allow the push).

### WS-2 — Production deploy readiness  · **P0**
`docker-compose.prod.yml` is now largely correct (pgvector, redis w/ password, worker,
elasticsearch w/ auth, ollama, health-gated `depends_on`, `COOKIE_SECURE=true`). Remaining:

- **P-1 (P0):** Verify `frontend/nginx.conf` proxies **all** API route prefixes —
  `evaluations`, `notes`, `gdpr`, `ai`, `applications`, `resumes` (SHIP_TODO N-1). Missing
  prefixes 404 in prod even though they work in dev.
- **P-2 (P1):** nginx SSE for `/ai` chat — `proxy_buffering off; add_header X-Accel-Buffering no;`
  and `proxy_read_timeout` ≥ `LLM_TIMEOUT_SECONDS` (N-2/N-3). Without it the live chat
  (verified working in dev) streams as one dump in prod.
- **P-3 (P1):** `Dockerfile` runs as root — add non-root `appuser` (SHIP_TODO I-7).
- **P-4 (P1):** Confirm `.env.prod.example` has `LLM_PROVIDER=ollama` + Ollama vars and all
  required keys; confirm backend reachability through Traefik→frontend(nginx)→backend is the
  intended path (backend has no Traefik labels — document as intentional or add).
- **P-5 (P0):** Write `docs/DEPLOY.md` runbook: clone → `.env.prod` → `docker compose -f
  docker-compose.prod.yml up -d` → `alembic upgrade head` → `scripts/create_admin.py` →
  pull Ollama model. First-deploy is currently undocumented.
- **P-6 (P2):** First prod smoke test on a staging host (the e2e/SSO paths can't be exercised
  locally without Azure creds + a domain).

### WS-3 — CI / CD  · **P1**
No CI today. The new repo should gate `main`.

- **C-1 (P1):** GitHub Actions workflow: `ruff check`, `ruff format --check`, `mypy`,
  `pytest` (mocked suite) on push/PR; frontend `tsc` + `build`.
- **C-2 (P1):** Land the **`ruff format`** 90-file pre-existing style drift as a single
  isolated commit, then turn on `ruff format --check` in CI so it stays clean. (Deliberately
  not mixed into the rebrand commit.)
- **C-3 (P2):** A job that spins up infra (services in Actions) to run the infra-dependent
  tests (`test_e2e_pipeline`, Elasticsearch) that the mocked suite skips.
- **C-4 (P3):** `pip-audit` / `npm audit` gate (currently only `pip`-self vuln PYSEC-2026-196,
  fixed by bumping pip; 2 moderate npm advisories informational).

### WS-4 — Frontend UX bug-fix pass  · **P1**
`SHIP_TODO.md` lists UX bugs (notifications click-through NF-1/2, stage-filter pills CF-1,
dead nav links SN-1/2, "New role" button HR-1). Some appear already fixed (Pipeline nav now
routes to `/pipeline` and renders). **Do not blind-fix** — run a fresh QA pass to confirm
which remain, then fix only the live ones.

- **U-1 (P1):** Run `/qa` (standard tier) across the app; produce a current bug list with
  before/after evidence.
- **U-2 (P1):** Fix confirmed: notification click → mark-read + navigate; stage-filter pills
  actually filter; "New role" opens create form; remove/relabel any disabled nav items.
- **U-3 (P2):** React `<ErrorBoundary>` in `App.tsx` (FT-2) so API errors don't white-screen.

### WS-5 — Feature backlog  · **P2–P3**
From `docs/dev/TODOS.md`, sequence after deploy is solid and after recruiter feedback:

- **F-1 (P2):** TODO-001 — proactive background scoring on new application (`app/applications/service.py`
  post-create hook → enqueue scoring). Removes leaderboard cold-start.
- **F-2 (P2):** TODO-002 — admin "Re-score" action (force fresh LLM score).
- **F-3 (P2):** TODO-003 — cross-role pipeline-health dashboard (`GET /analytics/role-health`
  + `RoleHealthDashboard.tsx`).
- **F-4 (P3):** TODO-004 — recruiter "score feels off" flags → `score_flags` table for
  calibration loop.

### WS-6 — Housekeeping  · **P3**
- **H-1:** Delete throwaway admin `qa.playwright@airecruitment.com` (created for live testing).
- **H-2:** Remove leftover git worktree `agent-a9483543b84630c8e` once the push branch isn't needed.
- **H-3:** `app/llm/factory.py` — singleton LLM client (SHIP_TODO B-1); `notifications/service.py`
  commit-vs-flush in transaction (B-3).

---

## 4. Success criteria
- `docker compose -f docker-compose.prod.yml up` on a clean host yields a working app reachable
  over HTTPS, following `DEPLOY.md`, with no 404s on any API prefix and working AI chat stream.
- No live secrets in any tracked or working-tree file; provider guardrail enforced in code.
- CI green on `main`: ruff (check+format), mypy, pytest, frontend build.
- `/qa` standard pass reports no 🔴/🟠 issues.

## 5. Suggested sequencing
1. **Milestone A (deploy-safe):** WS-1 S-1, WS-2 P-1/P-5, WS-3 C-1/C-2. → can deploy.
2. **Milestone B (hardened):** WS-1 S-2/S-3, WS-2 P-2/P-3/P-4, WS-4 U-1/U-2.
3. **Milestone C (features):** WS-5, remaining WS-3/WS-4/WS-6.

## 6. Open questions
- Production hosting target + domain? (needed for Traefik TLS, Azure SSO redirect URI, e2e smoke)
- Prod LLM: Ollama on a GPU host (per `.env.example` intent) or stay OpenAI? Drives S-2 + P-4.
- Is Azure AD SSO in scope for first prod, or password-login only at launch?
- Who is the recruiter validating the leaderboard before WS-5 features get built?
