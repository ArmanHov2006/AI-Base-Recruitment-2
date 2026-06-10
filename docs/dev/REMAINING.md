# Remaining Work

Phases 1–7 complete + most of Phase 8 (AI rating, interview questions, audit hardening,
admin/invites UI, Excel export). Verified against code on 2026-05-29 — this file was
significantly stale before; corrected below.

This file tracks everything **not yet built**, ordered by effort.
For an actionable, step-by-step checklist see [`WORK_TODO.md`](WORK_TODO.md).

---

## ✅ Already shipped (previously listed here as remaining)

These were marked TODO in older revisions but are **done in code** — do not rebuild:

- **Real SMTP** — `app/users/email.py` uses `aiosmtplib`, gated on `settings.smtp_host`. `aiosmtplib>=3.0` in deps.
- **`is_active` enforcement** — `app/auth.py:49` blocks inactive users; `app/users/service.py` too.
- **Audit log query endpoint** — `GET /audit` + `GET /audit/events` (admin), `app/audit/router.py`.
- **Salary & certification search filters** — present in `app/candidates/router.py:search_candidates`.
- **Similar candidates** — `GET /candidates/{id}/similar`, pgvector backed.
- **AI-suggested rating** — wired via Celery `generate_ai_suggested_rating_task` (`app/worker/tasks.py`).
- **AI-suggested interview questions** — `GET /candidates/{id}/interview-questions`.
- **Excel export** — `GET /candidates/export.xlsx`, `openpyxl>=3.1` in deps.
- **Admin user management** — backend `app/users/admin_router.py` (`/users`, role/active toggle, invites) + frontend `pages/AdminUsers.tsx`.
- **pgvector ANN index** — IVFFlat index exists (migration 0020).

---

## Priority 1 — Quick Wins (< 1 day each)

### 1. Frontend profile field surfacing
- Backend has `linkedin_url`, `github_url`, `certifications`, `languages`, `desired_salary` (migration 0018) but `frontend/src/types/index.ts` + `CandidateDetail.tsx` don't render them all.
- Add fields to TS types and the candidate detail view.

### 2. Time-to-hire analytics
- New metric on `GET /analytics/overview` (or new `/analytics/time-to-hire`).
- Query `MIN(applied_at)` → first evaluation/application with `stage='hired'` timestamp; data already exists.
- File: `app/analytics/router.py`.

### 3. Candidate source tracking
- Add `source` column to `job_applications` (e.g. "manual", "linkedin", "referral").
- Surface as filter + column. New migration.

### 4. Slack / MS Teams webhook (optional)
- `SLACK_WEBHOOK_URL` env var; fire on stage change inside `app/notifications/service.py`.

---

## Priority 2 — Medium Effort (1–3 days each)

### 5. Bulk upload
- `POST /jobs/{id}/applications/bulk` — multipart, multiple files.
- Dispatch one Celery `apply_pipeline_task` per file.
- Frontend: multi-file drop zone in `StepUpload.tsx` (currently single-file).

### 6. Duplicate detection
- On application create: compute MD5 of extracted resume text **or** vector similarity (`embedding <=> new_embedding < 0.05`).
- Return `409` with `similar_candidate_id` if match.
- File: `app/applications/service.py`.

### 7. AI Chat Assistant
- `POST /ai/chat` — stateless; system prompt = candidate JSON + job requirements.
- Ollama streaming (existing `OllamaClient`).
- Frontend: chat panel in `CandidateDetail.tsx`. New `app/ai/` module.

### 8. GDPR data export
- `GET /candidates/{id}/gdpr-export` (admin only).
- Returns candidate + applications + evaluations + notes + audit/business-event entries as JSON.
- Satisfies data subject access request.

### 9. @mentions in notes
- Parse `@username` in `candidate_notes.text`, fire existing notification to mentioned user.
- Files: `app/notes/router.py` + `app/notifications/service.py`.

---

## Priority 3 — Larger Effort (3+ days each)

### 10. PDF Export
- `GET /candidates/{id}/export.pdf` — candidate profile as formatted PDF.
- `GET /analytics/export.pdf` — dashboard summary.
- Library: `weasyprint` or `reportlab` (NOT yet in deps).

### 11. Resume Versioning
- New table: `candidate_resumes (id, candidate_id, file_id, version, parsed_at)`.
- `candidates.current_resume_id` FK.
- New upload → new version row, update `current_resume_id`; candidate row not duplicated.

### 12. Photo / avatar
- MinIO `avatars/` bucket, `photo_url` column on `Candidate`, upload endpoint + UI.

### 13. OCR for scanned PDFs
- `pytesseract` + `pdf2image` fallback before `pypdf`; currently text-layer only.

---

## Priority 4 — Future / Optional

| Feature | Notes |
|---|---|
| AI chat with candidate-search ("show similar to John with banking exp") | Tool-calling over existing semantic search |
| Attach documents to notes | MinIO `note-attachments/` + join table |
| Synonym / skill-normalization dictionary | Improve search recall beyond pg_trgm fuzzy |
| Multi-tenant | `tenant_id` UUID on all tables + tenant middleware; no tables have it |
| HA / 99.9% uptime | Nginx LB, PostgreSQL replica, MinIO replication |
| Backup & DR | Not configured |

---

## Test Coverage Gaps

| Module | Test file | Status |
|---|---|---|
| `app/evaluations/` | — | No tests |
| `app/notes/` | — | No tests |
| `app/analytics/` | — | No tests |
| `app/notifications/` | — | No tests |

No E2E integration test exists: upload PDF → parse → apply → Celery → check leaderboard.

**Pre-existing broken tests (patch-path / mock issues) — should be FIXED, not ignored:**
- `tests/test_parser.py` — patch path targets `app.parser.router`, functions live in `app.parser.service`.
- `tests/test_candidates.py` — `MagicMock` invalid for Pydantic `str` fields.
- `tests/test_storage.py::test_upload_valid_docx_returns_file_id` — DOCX returns `400` unexpectedly.

---

## Migration Hygiene (NEW — found 2026-05-29)

⚠️ **Duplicate revision id `0024`** — two migration files both declare `revision = "0024"` with
`down_revision = "0023"`:
- `0024_business_events_request_id.py`
- `0024_user_invites.py`

Alembic revision ids must be unique. This is a branched/colliding head. Verify `alembic heads`
resolves cleanly; if not, renumber one to `0024b`/`0025` and re-thread `down_revision`.
0025 → down_revision `0024` is ambiguous until this is resolved.

---

## NFR / Infrastructure Gaps

| Gap | Detail |
|---|---|
| App-level encryption at rest | OS-level disk encryption only |
| GDPR consent management | No consent timestamps or cookie consent tracking (export covered by Priority 2 #8) |
| Backup & DR | Not configured for PostgreSQL or MinIO |
| Multi-tenant | No `tenant_id` on any table |
| Horizontal scale to 1M+ | Modular monolith scales vertically; microservice split not built (likely YAGNI) |
