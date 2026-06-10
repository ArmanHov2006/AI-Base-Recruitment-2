# Build TODO — Actionable Checklist

Verified against code on **2026-05-29**. Each task lists: files to touch, steps, acceptance
criteria, and effort (solo dev + AI assist, calendar days). Work top-down; tiers are ordered
by user-visible value. See [`REMAINING.md`](REMAINING.md) for the full gap rationale.

**Estimated total to spec-complete (excluding Tier E):** ~13–18 working days.

---

## Tier A — Functional gaps recruiters hit daily  (~4–6 d)

### ☐ A0. Fix duplicate migration `0024`  (0.5 d) — DO FIRST
Two files declare `revision = "0024"`. Alembic ids must be unique.
- [ ] Run `uv run alembic heads` — confirm single head or see the collision.
- [ ] Renumber `0024_user_invites.py` → `revision = "0024b"` (or `0025` + re-thread chain).
- [ ] Fix `down_revision` of the next migration to point at the renamed one.
- [ ] `uv run alembic upgrade head` on a scratch DB succeeds clean.
- **Files:** `alembic/versions/0024_user_invites.py`, `0025_*.py`
- **Accept:** `alembic upgrade head` runs with no "multiple heads" / "duplicate revision" error.

### ☑ A1. Bulk upload  (1.5 d)
- [ ] Backend `POST /jobs/{id}/applications/bulk` — accept multiple files (multipart list).
- [ ] For each file: create `JobApplication(status="parsing")`, enqueue `apply_pipeline_task`.
- [ ] Return `202` with list of created application ids.
- [ ] Frontend: multi-file drop zone in `StepUpload.tsx` (currently single-file).
- **Files:** `app/applications/router.py`, `app/applications/service.py`, `frontend/src/components/UploadModal/StepUpload.tsx`, `frontend/src/api/applications.ts`
- **Accept:** drop 5 PDFs → 5 applications created, all parse independently, leaderboard fills.

### ☐ A2. Duplicate detection  (1 d)
- [ ] On application create, after text extraction: compute MD5 of extracted text OR cosine vs existing embeddings.
- [ ] If match (`embedding <=> new < 0.05` or exact md5): return `409 {similar_candidate_id}`.
- [ ] Allow force-create with `?allow_duplicate=true`.
- **Files:** `app/applications/service.py`, `app/candidates/router.py` (helper query)
- **Accept:** re-uploading same resume returns 409 with the existing candidate id; force flag bypasses.

### ☐ A3. AI Chat Assistant  (1.5 d)
- [ ] New module `app/ai/` — `POST /ai/chat` stateless.
- [ ] System prompt = candidate JSON (+ job requirements if `job_id` given); stream via `OllamaClient`.
- [ ] Rate-limit (reuse `app/limiter.py`).
- [ ] Frontend: chat panel in `CandidateDetail.tsx` + `frontend/src/api/ai.ts`.
- **Files:** `app/ai/router.py`, `app/ai/schemas.py`, `app/main.py` (register), `frontend/src/pages/CandidateDetail.tsx`
- **Accept:** ask "summarize fit for this job" → streamed answer grounded in candidate data.

### ☐ A4. Frontend profile field surfacing  (0.5 d)
- [ ] Add `linkedin_url, github_url, certifications, languages, desired_salary` to `types/index.ts`.
- [ ] Render them in `CandidateDetail.tsx` (links clickable, lists as tags).
- **Files:** `frontend/src/types/index.ts`, `frontend/src/pages/CandidateDetail.tsx`
- **Accept:** candidate detail shows LinkedIn/GitHub links, certs, languages, salary when present.

---

## Tier B — Compliance & reporting  (~4–5 d)

### ☐ B1. GDPR data export  (1 d)
- [ ] `GET /candidates/{id}/gdpr-export` (admin only).
- [ ] Bundle candidate + applications + evaluations + notes + audit_log + business_events as one JSON.
- **Files:** `app/candidates/router.py` (or new `app/gdpr/`), reuse existing queries.
- **Accept:** admin downloads a single JSON containing every record referencing the candidate.

### ☑ B2. Time-to-hire analytics  (0.5 d)
- [x] New `GET /analytics/time-to-hire` (optional `?job_id=`).
- [x] `hired_at` → `min(business_event.created_at)` where `after->>status == 'hired'` (avg + per-job).
      Uses the immutable audit log, not the mutable `applications.updated_at`.
- [x] Frontend: "Time to Hire" card on `Analytics.tsx` (overall avg + per-job) + `getTimeToHire()` API.
- [x] Tests: `tests/test_time_to_hire.py` — aggregation, empty→null, negative-clamp. 3/3 green.
- **Files:** `app/analytics/router.py`, `app/analytics/schemas.py`, `frontend/src/pages/Analytics.tsx`,
  `frontend/src/api/analytics.ts`, `frontend/src/types/index.ts`
- **Accept:** dashboard shows average days-to-hire; matches manual spot check.

### ☐ B3. PDF export  (1.5 d)
- [ ] Add `weasyprint` (or `reportlab`) to `pyproject.toml`.
- [ ] `GET /candidates/{id}/export.pdf` — formatted profile.
- [ ] `GET /analytics/export.pdf` — dashboard summary.
- **Files:** `pyproject.toml`, `app/candidates/router.py`, `app/analytics/router.py`
- **Accept:** both endpoints return a valid `application/pdf` opening in a viewer.

### ☐ B4. Resume versioning  (1.5 d)
- [ ] New migration: `candidate_resumes (id, candidate_id, file_id, version, parsed_at)` + `candidates.current_resume_id` FK.
- [ ] New upload for existing candidate → insert version row, bump `current_resume_id`; don't duplicate candidate.
- **Files:** new `alembic/versions/00XX_resume_versions.py`, `app/candidates/models.py`, `app/applications/service.py`
- **Accept:** re-uploading for a candidate creates version 2; profile shows current + history.

---

## Tier C — Polish / optional  (~3–4 d)

### ☐ C1. @mentions in notes  (1 d)
- [ ] Parse `@username` in note text → resolve user → fire notification.
- **Files:** `app/notes/router.py`, `app/notifications/service.py`
- **Accept:** mentioning a user creates a notification for them.

### ☐ C2. Photo / avatar  (1 d)
- [ ] MinIO `avatars/` bucket, `photo_url` column on `Candidate`, upload endpoint + UI render.
- **Files:** new migration, `app/candidates/models.py`, `app/storage/`, `CandidateDetail.tsx`
- **Accept:** upload avatar → shows on profile + list.

### ☐ C3. Slack / MS Teams webhook  (0.5 d)
- [ ] `SLACK_WEBHOOK_URL` env var; POST on stage change.
- **Files:** `app/config.py`, `app/notifications/service.py`
- **Accept:** stage change posts a message to the configured channel.

### ☐ C4. Candidate source tracking  (0.5 d)
- [ ] `source` column on `job_applications`; filter + column in UI.
- **Files:** new migration, `app/applications/models.py`, `app/applications/router.py`, frontend list
- **Accept:** can set + filter by source.

### ☐ C5. OCR for scanned PDFs  (1 d)
- [ ] `pytesseract` + `pdf2image` fallback when `pypdf` yields no text layer.
- **Files:** `pyproject.toml`, `app/parser/extractor.py`
- **Accept:** a scanned (image-only) PDF parses to non-empty text.

---

## Tier D — Test debt  (~2–3 d, do alongside Tiers A–B)

### ☐ D1. Fix the 3 broken test files  (0.5 d)
- [ ] `tests/test_parser.py` — repoint patch path `app.parser.router` → `app.parser.service`.
- [ ] `tests/test_candidates.py` — replace `MagicMock` with real values for Pydantic `str` fields.
- [ ] `tests/test_storage.py::test_upload_valid_docx_returns_file_id` — fix DOCX → 400.
- **Accept:** `uv run pytest` green for these files.

### ☐ D2. Add missing module tests  (1.5 d)
- [ ] `tests/test_evaluations.py`, `test_notes.py`, `test_analytics.py`, `test_notifications.py`.
- **Accept:** each module has happy-path + auth-gate + soft-delete coverage.

### ☐ D3. E2E integration test  (1 d)
- [ ] upload PDF → parse → apply → Celery (eager) → assert candidate + score + leaderboard.
- **Files:** `tests/test_e2e_pipeline.py`
- **Accept:** one test exercises the full async pipeline end to end.

---

## Tier E — Heavy NFR (DEFER — needs a deployment decision first)

- ☐ Multi-tenant: `tenant_id` on all tables + tenant middleware.
- ☐ App-level encryption at rest.
- ☐ Backup & DR for PostgreSQL + MinIO.
- ☐ HA / 99.9% uptime: Nginx LB, PG replica, MinIO replication.

> Do not build Tier E until a real multi-customer deployment requires it.

---

## Suggested order

```
Week 1:  A0 → A1 → A2 → A4            (migration safety + upload story)   + D1 alongside
Week 2:  A3 → B1 → B2                 (AI chat + compliance + metric)     + D2 alongside
Week 3:  B3 → B4 → D3                 (reporting + versioning + E2E)
Then:    Tier C opportunistically.    Tier E only on deployment trigger.
```
