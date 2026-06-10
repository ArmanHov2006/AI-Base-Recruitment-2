# SHIP_TODO — Deployment Readiness Checklist

**Goal:** 100/100 production-ready in next few days.
**Status:** ~72/100. Core backend solid; several critical infra gaps + UX bugs need fixing before handoff.

---

## Legend
- 🔴 **CRITICAL** — app broken / data lost without fix
- 🟠 **HIGH** — visible broken feature, security hole, or deploy blocker
- 🟡 **MEDIUM** — poor UX, confusing UI, or ops risk
- 🔵 **LOW** — polish, nice-to-have

---

## 1. Docker / Infrastructure  `docker-compose.prod.yml`

| # | Sev | Issue | Fix |
|---|-----|-------|-----|
| I-1 | 🔴 | `postgres:16` in prod compose — **pgvector extension won't load**, semantic search + embedding dedup breaks | Change to `pgvector/pgvector:pg16` |
| I-2 | 🔴 | `redis` service missing — Celery worker can't start | Add `redis:7-alpine` service with healthcheck |
| I-3 | 🔴 | `worker` (Celery) service missing — job applications never get parsed (stuck in `parsing` status forever), AI scoring never runs, audit maintenance never runs | Add `worker` service mirroring `docker-compose.yml` |
| I-4 | 🔴 | `backend` service has no Traefik labels — `/auth`, `/jobs`, etc. only reachable via nginx proxy, which works, but if Traefik ever routes direct to backend none of those routes are labeled | Either add Traefik backend label or confirm nginx-proxy-only is intentional and document it |
| I-5 | 🟠 | `MINIO_BUCKET`, `MINIO_INTERNAL_URL` missing from prod compose `environment` block | Add both — without `MINIO_BUCKET` MinIO bucket creation at startup will use wrong name |
| I-6 | 🟠 | `.env.prod.example` missing `LLM_PROVIDER`, `OPENAI_API_KEY` / `OLLAMA_*` config — app defaults to `openai` provider, will crash on startup if key not set | Add `LLM_PROVIDER=ollama` and corresponding vars to `.env.prod.example` |
| I-7 | 🟡 | `Dockerfile` runs as root — security risk in prod | Add `RUN useradd -r appuser && chown -R appuser /app` + `USER appuser` |
| I-8 | 🟡 | `docker-compose.prod.yml` has no `depends_on` for `minio` / `redis` on `backend` | Add health-conditioned depends_on for all dependencies |

---

## 2. nginx Reverse Proxy  `frontend/nginx.conf`

| # | Sev | Issue | Fix |
|---|-----|-------|-----|
| N-1 | 🔴 | Missing proxy routes — `/evaluations`, `/notes`, `/gdpr`, `/ai`, `/applications`, `/resumes` all 404 through nginx (nginx serves `index.html` instead of proxying) | Add to the location regex: `evaluations\|notes\|gdpr\|ai\|applications\|resumes` |
| N-2 | 🟡 | `/ai` SSE streaming needs `X-Accel-Buffering: no` + `proxy_buffering off` — otherwise AI chat stream appears as one big dump after timeout | Add `proxy_buffering off; add_header X-Accel-Buffering no;` to AI location block |
| N-3 | 🟡 | `proxy_read_timeout 120s` applies globally — long AI comparisons can timeout; increase to `180s` to match `LLM_TIMEOUT_SECONDS` | Change to `180s` |

---

## 3. Notifications (Frontend)

| # | Sev | Issue | Fix |
|---|-----|-------|-----|
| NF-1 | 🟠 | Clicking a notification does nothing — no navigation, no mark-as-read | `onClick` on each `List.Item` should: call `markRead(item.id)`, then navigate based on `item.type` + `item.payload` (e.g. `new_application` → `/jobs/${p.job_id}`, `stage_change` → `/candidates/${p.candidate_id}`, `mention` → `/candidates/${p.candidate_id}`) |
| NF-2 | 🟠 | `mention` notification type falls through to raw `n.type` string in `formatNotifTitle` — shows `"mention"` instead of a human message | Add case: `if (n.type === 'mention') return \`@${p.mentioned_by ?? 'Someone'} mentioned you on ${p.candidate_name ?? 'a candidate'}\`` |
| NF-3 | 🟡 | Notification panel fixed at 10 items max, no way to see all | Add "See all" link at bottom of popover → `/notifications` page (needs new page + route) |
| NF-4 | 🟡 | No visual distinction between notification types (all look identical) | Add type icon: 🔔 new_application, ↕ stage_change, ⭐ rating_update, @ mention |
| NF-5 | 🟡 | Notification panel width not constrained — can overflow on small screens | Add `style={{ width: 340, maxHeight: 400, overflowY: 'auto' }}` on `.notification-panel` |
| NF-6 | 🔵 | No browser Notification API / real-time push — 30s polling is fine for MVP but feels laggy | Consider WebSocket or SSE for real-time; defer if not blocking |

---

## 4. CandidateList — Stage Filter Bug

| # | Sev | Issue | Fix |
|---|-----|-------|-----|
| CF-1 | 🟠 | Stage filter pills (Reviewing / Shortlisted / Interview etc.) update `stageFilter` state but **never pass it to `searchCandidates()`** — clicking a filter does nothing to the data | Map pill labels to API `status` values and include in `structuredFilters`. Backend `GET /candidates/search` supports `status` param. |
| CF-2 | 🟡 | Stage filter has 5 stages that all map to `'active'` value — no per-stage filtering possible from UI | Use the actual `job_applications` statuses for filtering, or remove the granular stage pills and just show Active/Hired/Archived |

---

## 5. Sidebar Nav Dead Links

| # | Sev | Issue | Fix |
|---|-----|-------|-----|
| SN-1 | 🟡 | "AI Screening" nav item is disabled (`is-disabled` class) but still rendered — users click it, nothing happens, no tooltip explaining why | Either remove the item, or add tooltip "Coming soon" and visually mark it disabled |
| SN-2 | 🟡 | "Pipeline" sidebar nav (`/pipeline-nav`) navigates to `/jobs` — user lands on job list, not a pipeline | Decide: remove the nav item (pipeline is per-job, accessed from JobDetail), or navigate to first active job's pipeline |

---

## 6. Header "New Role" Button

| # | Sev | Issue | Fix |
|---|-----|-------|-----|
| HR-1 | 🟡 | "New role" button navigates to `/jobs` (the jobs list) instead of opening a create-job form | Open the CreateJob modal directly, or navigate to `/jobs?create=true` and have `JobList` respond to that param |

---

## 7. README / Documentation

| # | Sev | Issue | Fix |
|---|-----|-------|-----|
| D-1 | 🟠 | README is Sprint-1-level — describes old Java stack, references features that are deferred, doesn't mention current 30+ migrations, Celery, RBAC, notifications, etc. | Full README rewrite: current stack, local dev quickstart, env vars reference, Docker prod deploy steps |
| D-2 | 🟡 | No `DEPLOY.md` — prod deploy steps not documented anywhere accessible | Create `docs/DEPLOY.md` with: clone → `.env.prod` setup → `docker compose -f docker-compose.prod.yml up` → first admin user creation (`uv run python scripts/create_admin.py`) |
| D-3 | 🔵 | `.env.prod.example` references `MINIO_PUBLIC_URL=https://yourdomain.com` but prod MinIO needs to be accessible at a sub-path or subdomain — needs clarification | Add note about MinIO public URL setup |

---

## 8. Backend Minor Issues

| # | Sev | Issue | Fix |
|---|-----|-------|-----|
| B-1 | 🟡 | `app/llm/factory.py` `get_llm_client()` creates a **new** `OpenAIClient`/`OllamaClient` instance on every call — each instance creates a new `AsyncOpenAI` client | Make singleton: module-level `_client` cached on first call |
| B-2 | 🟡 | `app/config.py` `cookie_secure: bool = False` in prod HTTPS setup, sessions use insecure cookies | `.env.prod.example` already has `COOKIE_SECURE=true` but it should be in the prod docker-compose env block too |
| B-3 | 🔵 | `app/notifications/service.py` `create_notification` does `await db.commit()` directly — if called mid-transaction, breaks the outer transaction | Change to `db.flush()` if within a transaction, or use a separate session for notifications |

---

## 9. Frontend API / Type Gaps

| # | Sev | Issue | Fix |
|---|-----|-------|-----|
| FT-1 | 🟡 | `frontend/src/api/notifications.ts` exports `markRead` but `AppLayout.tsx` imports it as `markAllNotificationsRead` — if the name drifts this will silently not call mark-individual | Already aliased correctly; but individual `markRead` is never called on click (see NF-1) |
| FT-2 | 🔵 | No `error boundary` component in React tree — unhandled API errors crash the page with white screen | Add `<ErrorBoundary>` wrapper in `App.tsx` |

---

## 10. AI Chat (Streaming)

| # | Sev | Issue | Fix |
|---|-----|-------|-----|
| AI-1 | 🟠 | `/ai/*` routes not in nginx.conf proxy list (see N-1) — AI chat completely broken in prod | Fix N-1 |
| AI-2 | 🟡 | No SSE buffering disabled in nginx — chat streams in one dump after LLM finishes | Fix N-2 |

---

## Summary by Priority

### Must fix before first demo (🔴 CRITICAL)
- [ ] I-1: pgvector image in prod compose
- [ ] I-2: redis service in prod compose
- [ ] I-3: celery worker service in prod compose
- [ ] N-1: nginx missing proxy routes for evaluations/notes/gdpr/ai/applications/resumes

### Fix this sprint (🟠 HIGH)
- [ ] I-5: MINIO_BUCKET + MINIO_INTERNAL_URL in prod compose
- [ ] I-6: LLM vars in .env.prod.example
- [ ] NF-1: Notification click → navigate + mark read
- [ ] NF-2: mention notification title formatting
- [ ] CF-1: Stage filter pills actually filter candidates
- [ ] D-1: README rewrite

### Fix before handoff (🟡 MEDIUM)
- [ ] I-7: Non-root user in Dockerfile
- [ ] I-8: depends_on in prod compose
- [ ] N-2: SSE headers for AI chat stream
- [ ] N-3: nginx timeout matches LLM timeout
- [ ] NF-3: "See all" link in notification popover
- [ ] NF-4: Notification type icons
- [ ] NF-5: Notification panel width/scroll
- [ ] CF-2: Fix stage filter value mapping
- [ ] SN-1: "AI Screening" disabled item UX
- [ ] SN-2: Pipeline nav behavior
- [ ] HR-1: "New role" button action
- [ ] B-1: LLM client singleton
- [ ] B-2: cookie_secure in prod compose env
- [ ] D-2: DEPLOY.md

### Polish (🔵 LOW)
- [ ] B-3: notification transaction isolation
- [ ] FT-2: React error boundary
- [ ] NF-6: Real-time notifications (WebSocket/SSE)
- [ ] D-3: MinIO URL clarification

---

## Score Estimate

| Area | Current | After fixes |
|------|---------|-------------|
| Backend API | 92 | 95 |
| Frontend UX | 68 | 88 |
| Notifications | 55 | 85 |
| DevOps / Deploy | 50 | 90 |
| Docs | 30 | 80 |
| **Overall** | **~72** | **~90** |
