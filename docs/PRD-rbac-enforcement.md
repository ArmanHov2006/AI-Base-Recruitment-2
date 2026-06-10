# PRD — RBAC Enforcement Across API Routers

**Status:** Ready to execute
**Owner:** Security / Platform
**Branch:** `security/rbac-enforcement` (cut from `main`, NOT from `redesign/design-system-overhaul`)
**Type:** Authorization hardening — close the gap between the documented RBAC matrix and what the code actually enforces.
**Audience:** An orchestrator Claude agent that may fan out to parallel sub-agents (one per router file) and a test sub-agent.

---

## 1. Context

A security audit found the API enforces only "is the caller authenticated" (`get_current_user`) on many sensitive endpoints, with no role differentiation, plus the inverse mistake on notes. The result violates the product's own RBAC matrix in **both** directions and is missing **ownership scoping** for Hiring Managers.

Auth primitives already exist in `app/auth.py`:
- `get_current_user` — any authenticated, active, non-deleted user. Sets `request.state.user`.
- `require_role(*roles)` — factory returning a dependency that 403s unless `user.role in roles`.
- `require_write = require_role(ADMIN, RECRUITER, HR_MANAGER)` — i.e. **everyone except VIEWER**.
- `require_admin = require_role(ADMIN)`.

Enum (`app/users/models.py:12`):
```python
class UserRole(str, enum.Enum):
    ADMIN = "admin"
    RECRUITER = "recruiter"
    HR_MANAGER = "hr_manager"
    VIEWER = "viewer"      # <-- this is the matrix's "Interviewer"
```
> **CRITICAL:** the matrix term "Interviewer" maps to `UserRole.VIEWER`. There is no `INTERVIEWER` member. Use `VIEWER` everywhere.

Jobs ownership field (`app/jobs/models.py:27`): `creator_id: Mapped[uuid.UUID | None]` — **nullable**. Legacy jobs may have `creator_id = None`.

---

## 2. Canonical RBAC matrix (source of truth)

| Role | Allowed |
|---|---|
| **Admin** | Full system control; user management; LLM provider swap; audit logs; GDPR export; everything below. |
| **Recruiter** | Bulk upload/parse; Jobs CRUD (all jobs); candidate CRUD; LLM evaluation triggers; exports. |
| **Hiring Manager** (`HR_MANAGER`) | Manage **owned** jobs only (`creator_id == self`); view candidate leaderboards; LLM triggers on owned jobs; exports. |
| **Interviewer** (`VIEWER`) | **Read-only** candidate details; **leave feedback notes**. **Off-limits:** job creation, LLM evaluation triggers, exports, raw resume download. |

---

## 3. Decided defaults (was "open product decisions" — now locked so agents are unblocked)

| ID | Decision | Locked default | Override note |
|---|---|---|---|
| C1 | Analytics visibility for VIEWER | **Restrict** `/analytics/overview`, `/funnel`, `/sources` to `require_write` (VIEWER 403) | If VIEWER should see aggregate analytics, leave these as `get_current_user` and drop WP-G's C1 portion. |
| C2 | HM scoping on job LLM/mutation ops | **Owner-scoped** — HM may mutate/trigger only owned jobs | If HM may operate any viewable job, use `require_write` instead of the ownership dep in WP-H. |
| C3 | VIEWER raw resume download | **Blocked** — `/files/{id}/download-url` → `require_write` | If VIEWER must view raw resumes of candidates they can see, keep `get_current_user` and drop that one row. |

---

## 4. Scope

**In scope:** authorization guards on existing endpoints; one new ownership dependency; a role×endpoint regression test.

**Out of scope (do NOT touch in this PRD):** audit-logging of reads, prompt-injection defenses, PDF escaping, worker hardening, MinIO scoped creds, SSO. Tracked separately. Adding row-level *visibility* scoping to candidate reads is also out of scope — only job *ownership* for mutations is in scope.

---

## 5. The work — by endpoint

Legend for "Action": **TIGHTEN** = make stricter; **LOOSEN** = grant VIEWER; **OWNER** = ownership dependency.

### Group A1 — VIEWER must not trigger the LLM (TIGHTEN → `require_write`)
| File | Endpoint | Current guard | Change |
|---|---|---|---|
| `app/ai/router.py:25` | `POST /ai/chat` | param `current_user: Depends(get_current_user)` | → `Depends(require_write)` (keep the `current_user` param; it's used) |
| `app/candidates/router.py:305` | `GET /candidates/semantic-search` | `dependencies=[Depends(get_current_user)]` | → `[Depends(require_write)]` |
| `app/evaluations/router.py:398` | `GET /evaluations/candidates/{candidate_id}/interview-questions` | param `_: Depends(get_current_user)` | → `Depends(require_write)` |
| `app/parser/router.py:24` | `POST /parse` | `dependencies=[Depends(get_current_user)]` | → `[Depends(require_write)]` |

### Group A2 — VIEWER must not export / download raw files (TIGHTEN → `require_write`)
| File | Endpoint | Current guard | Change |
|---|---|---|---|
| `app/storage/router.py:80` | `GET /files/{file_id}/download-url` | `dependencies=[Depends(get_current_user)]` | → `[Depends(require_write)]` *(C3)* |
| `app/candidates/router.py:375` | `GET /candidates/export.csv` | `[Depends(get_current_user)]` | → `[Depends(require_write)]` |
| `app/candidates/router.py:447` | `GET /candidates/export.xlsx` | `[Depends(get_current_user)]` | → `[Depends(require_write)]` |
| `app/candidates/router.py:601` | `GET /candidates/{candidate_id}/export.pdf` | `[Depends(get_current_user)]` | → `[Depends(require_write)]` |
| `app/analytics/router.py:319` | `GET /analytics/export.pdf` | `[Depends(get_current_user)]` | → `[Depends(require_write)]` |
| `app/jobs/router.py:444` | `GET /jobs/{job_id}/qualified-candidates.pdf` | `[Depends(get_current_user)]` | → `[Depends(require_write)]` |

### Group A3 — VIEWER MUST be able to leave notes (LOOSEN → `get_current_user`)
| File | Endpoint | Current guard | Change |
|---|---|---|---|
| `app/notes/router.py:67` | `POST /candidates/{candidate_id}/notes` | param `current_user: Depends(require_write)` | → `Depends(get_current_user)` |
| `app/notes/router.py:143` | `PATCH /candidates/{candidate_id}/notes/{note_id}` | param `Depends(require_write)` | → `Depends(get_current_user)` (existing author check at `:154` stays) |
| `app/notes/router.py:178` | `DELETE …/notes/{note_id}` | param `Depends(require_write)` | → `Depends(get_current_user)` (existing author/admin check at `:188` stays) |

### Group C1 — Restrict analytics from VIEWER (TIGHTEN → `require_write`)
| File | Endpoint | Change |
|---|---|---|
| `app/analytics/router.py:47` | `GET /analytics/overview` | → `require_write` |
| `app/analytics/router.py:142` | `GET /analytics/funnel` | → `require_write` |
| `app/analytics/router.py:288` | `GET /analytics/sources` | → `require_write` |
> `/analytics/time-to-hire` (`:177`) is already `require_admin` — leave it.

### Group A4 — Hiring Manager owns-job scoping (OWNER dependency)
New dependency `require_job_owner_or_elevated` (defined in WP0). Apply to these `{job_id}` mutation/trigger endpoints, replacing `require_write`:
| File | Endpoint | Current guard | Change |
|---|---|---|---|
| `app/jobs/router.py:156` | `PATCH /jobs/{job_id}` | param `Depends(require_write)` | → `Depends(require_job_owner_or_elevated)` |
| `app/jobs/router.py:311` | `DELETE /jobs/{job_id}` | param `Depends(require_write)` | → `Depends(require_job_owner_or_elevated)` |
| `app/jobs/router.py:286` | `POST /jobs/{job_id}/auto-split-skills` | `dependencies=[Depends(require_write)]` | → `[Depends(require_job_owner_or_elevated)]` |
| `app/jobs/router.py:642` | `POST /jobs/{job_id}/tiebreaker` | param `Depends(require_write)` | → `Depends(require_job_owner_or_elevated)` *(C2)* |

> Leave job **reads** open: `GET /jobs`, `/jobs/{id}`, `/jobs/{id}/leaderboard`, `/jobs/{id}/shortlist`, `/jobs/{id}/analytics-summary` stay `get_current_user`. `POST /jobs` (create, `:65`) stays `require_write` — HM may create (then owns).

### Already correct — DO NOT CHANGE
`/users/*`, `/audit*`, GDPR export, `/analytics/time-to-hire` (admin). `require_write`: candidate create/update/delete, avatar, applications apply/bulk/interview/stage, evaluations create/update/delete, comparisons create/analyze, file upload, `/jobs/generate-description` (`require_role` R/HM/A), `/jobs/auto-split-preview`. Candidate/job reads for VIEWER. `/auth/*`.

---

## 6. WP0 — foundational change (BLOCKING, do first)

**File:** `app/auth.py` only. Add the ownership dependency. Use a **local import** of `Job` inside the function to avoid a circular import (`app.jobs.models` ↔ `app.auth`).

```python
async def require_job_owner_or_elevated(
    job_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: DbDep,
) -> User:
    """Admin/Recruiter may manage any job; HR_MANAGER only jobs they created."""
    from app.jobs.models import Job  # local import avoids circular dependency
    if user.role not in (UserRole.ADMIN, UserRole.RECRUITER, UserRole.HR_MANAGER):
        raise _FORBIDDEN
    if user.role == UserRole.HR_MANAGER:
        job = await db.get(Job, job_id)
        if job is None or job.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        if job.creator_id != user.id:
            raise _FORBIDDEN
        request_state_user = user  # ensure request.state.user already set by get_current_user
    return user
```
Notes for the implementer:
- `uuid`, `Annotated`, `status`, `HTTPException`, `User`, `UserRole`, `DbDep`, `_FORBIDDEN`, `get_current_user` are all already imported/defined in `app/auth.py` (verify; add `import uuid` if missing).
- The path-parameter name **must** be exactly `job_id` to bind to `/jobs/{job_id}`.
- Nullable `creator_id`: a legacy job with `creator_id is None` will (correctly) 403 for HR_MANAGER since `None != user.id`. That is intended — only Admin/Recruiter can manage owner-less jobs.
- Do **not** change `require_write`, `require_admin`, or `get_current_user`.

---

## 7. Work packages & parallelization

One package per file ⇒ no two agents edit the same file ⇒ zero merge conflicts. Only WP-H depends on WP0.

| WP | File | Groups | Depends on |
|---|---|---|---|
| **WP0** | `app/auth.py` | new ownership dep | — |
| WP-B | `app/ai/router.py` | A1 | — |
| WP-C | `app/candidates/router.py` | A1 + A2 | — |
| WP-D | `app/evaluations/router.py` | A1 | — |
| WP-E | `app/parser/router.py` | A1 | — |
| WP-F | `app/storage/router.py` | A2 (C3) | — |
| WP-G | `app/analytics/router.py` | A2 + C1 | — |
| WP-I | `app/notes/router.py` | A3 | — |
| WP-H | `app/jobs/router.py` | A2 + A4 | **WP0** |
| WP-T | `tests/test_rbac_matrix.py` (new) | regression test | all |

**Recommended waves (orchestrator may choose otherwise):**
- **Wave 1 (parallel, ~8 agents):** WP0, WP-B, WP-C, WP-D, WP-E, WP-F, WP-G, WP-I. These never touch the same file; the swap WPs don't import the new dep, so they don't actually need WP0 to finish — but keep WP0 in this wave so it's ready.
- **Wave 2:** WP-H (imports `require_job_owner_or_elevated` from WP0; add `from app.auth import require_job_owner_or_elevated`).
- **Wave 3:** WP-T, then run the full suite + lint + types.

Each WP = one atomic commit. Commit message convention:
```
fix(rbac): <endpoint group> — <role> gate

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

## 8. Per-WP acceptance (each sub-agent self-checks before committing)

- Only its own file changed (`git diff --name-only` shows one path).
- Imports resolve: the WP added any needed import (`require_write` already exported from `app.auth`; WP-H adds `require_job_owner_or_elevated`).
- No endpoint left half-converted; the `current_user`/`_` param is preserved where the handler body references it.
- `ruff check <file>` and `mypy <file>` clean.

---

## 9. WP-T — regression test (the real gate)

Create `tests/test_rbac_matrix.py`. **First inspect `tests/conftest.py`** for existing fixtures (app client, db, user/token factories) and reuse them — do not invent a new harness. Create one active user per role (`admin`, `recruiter`, `hr_manager`, `viewer`) and obtain a bearer token for each.

Parametrize `(role, method, path) -> expected_status`. Use `403` for forbidden, any `2xx`/`404`/`422` (i.e. "passed authz") for allowed — assert **authz outcome**, not business success. Minimum cases:

| Endpoint | admin | recruiter | hr_manager | viewer |
|---|---|---|---|---|
| `POST /ai/chat` | allow | allow | allow | **403** |
| `GET /candidates/semantic-search` | allow | allow | allow | **403** |
| `GET /evaluations/candidates/{id}/interview-questions` | allow | allow | allow | **403** |
| `POST /parse` | allow | allow | allow | **403** |
| `GET /files/{id}/download-url` | allow | allow | allow | **403** |
| `GET /candidates/export.csv` | allow | allow | allow | **403** |
| `GET /candidates/export.xlsx` | allow | allow | allow | **403** |
| `GET /candidates/{id}/export.pdf` | allow | allow | allow | **403** |
| `GET /analytics/export.pdf` | allow | allow | allow | **403** |
| `GET /analytics/overview` | allow | allow | allow | **403** |
| `POST /candidates/{id}/notes` | allow | allow | allow | **allow (2xx)** |
| `GET /candidates/{id}` | allow | allow | allow | allow |
| `GET /jobs/{id}/leaderboard` | allow | allow | allow | allow |
| `PATCH /jobs/{job_id}` (job owned by a *different* HM) | allow | allow | **403** | 403 |
| `PATCH /jobs/{job_id}` (job owned by *this* HM) | allow | allow | **allow** | 403 |

The two job-ownership rows are the only ones needing seeded data: create a job with `creator_id = hr_manager_A.id`, then assert `hr_manager_B` gets 403 and `hr_manager_A` gets 2xx.

---

## 10. Global acceptance criteria (orchestrator verifies at the end)

1. Every row in §5 reflected in code; §5 "do not change" list untouched (`git diff` review).
2. `tests/test_rbac_matrix.py` passes.
3. Full suite green: `uv run pytest` — **no regressions** vs `main`.
4. `uv run ruff check app tests` clean.
5. `uv run mypy app` clean (or no new errors vs baseline).
6. One atomic commit per WP; branch is `security/rbac-enforcement` off `main`.
7. PR opened to `main`, body summarizing the matrix gaps closed (link this PRD).

### Verification commands
```bash
git checkout main && git pull && git checkout -b security/rbac-enforcement
# ... WPs land ...
uv run pytest tests/test_rbac_matrix.py -q
uv run pytest -q
uv run ruff check app tests
uv run mypy app
```

---

## 11. Risks & rollback

- **VIEWER lockout regression:** if A3 (notes LOOSEN) is skipped, real interviewers can't do their job. A3 is mandatory, not optional.
- **HM ownership over-block:** legacy jobs with `creator_id IS NULL` become unmanageable by HMs by design — confirm this matches ops expectations; if a backfill of `creator_id` is needed it's a separate task.
- **Circular import in WP0:** if `from app.jobs.models import Job` at module top causes an import cycle, keep it function-local (as written). Verify `uv run python -c "import app.main"` still imports cleanly.
- **Rollback:** pure guard changes; revert the branch. No schema/data migration involved.

---

## 12. Out-of-scope follow-ups (do not start here — note for backlog)
Audit-logging of reads/exports; resume prompt-injection defenses; ReportLab markup escaping; worker decompression-bomb limits; rate-limit key behind proxy + account lockout; scoped MinIO credentials + startup public-bucket assert; LLM-provider PII guard; SSO `aud`/`iss`/`nonce` (latent — fix before enabling SSO).
