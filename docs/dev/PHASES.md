# AI Recruitment — Remaining Core Phases

> Phase 3 (Search) is done. Phases 4–6 below are independent enough to run in separate worktrees.
> Each phase lists exact files to touch and the DB migration number to use next.

---

## Phase 4 — Evaluation & Status Workflow

**Goal:** Recruiters can rate candidates, leave interview feedback, and move candidates through a hiring pipeline.

### New model: `CandidateEvaluation`

File: `app/evaluations/models.py`

```python
class CandidateEvaluation(Base):
    __tablename__ = "candidate_evaluations"

    id: UUID PK
    candidate_id: UUID FK → candidates.id  (indexed)
    job_id: UUID FK → jobs.id              (indexed)
    evaluator_id: UUID FK → users.id       (indexed)

    stage: String(30)          # reviewing | shortlisted | interview | offer | hired | rejected
    overall_rating: Integer    # 1–5, nullable
    technical_score: Integer   # 1–5, nullable
    communication_score: Integer
    leadership_score: Integer
    cultural_fit_score: Integer
    english_score: Integer
    domain_score: Integer

    feedback: Text             # interview notes / general comment
    ai_suggested_rating: Integer  # nullable, filled by AI if requested

    created_at: DateTime(tz)
    updated_at: DateTime(tz)
    deleted_at: DateTime(tz)   # soft delete
```

### Application status workflow

`JobApplication.status` valid transitions (add CHECK constraint in migration):

```
applied → reviewing → shortlisted → interview → offer → hired
                                              ↘ rejected
        ↘ rejected (at any stage)
```

Add endpoint `PATCH /jobs/{job_id}/applications/{app_id}/stage` — body: `{ "stage": "interview", "reason": "..." }`.
Guard invalid transitions (e.g. hired → reviewing) with 409.

### Endpoints

- `POST /candidates/{id}/evaluations` — create evaluation (require_write)
- `GET  /candidates/{id}/evaluations` — list all evaluations for candidate (get_current_user)
- `GET  /candidates/{id}/evaluations?job_id=` — filter by job (get_current_user)
- `PATCH /candidates/{id}/evaluations/{eval_id}` — update scores/feedback (require_write)
- `DELETE /candidates/{id}/evaluations/{eval_id}` — soft delete (require_write)
- `PATCH /jobs/{job_id}/applications/{app_id}/stage` — transition status (require_write)

### Schemas

File: `app/evaluations/schemas.py`

- `CreateEvaluationRequest` — all score fields optional, stage required
- `UpdateEvaluationRequest` — all fields optional
- `EvaluationResponse` — full model + evaluator name denormalized
- `StageTransitionRequest` — `stage: Literal[...]`, `reason: str | None`

### Migration: `0017_candidate_evaluations.py`

- Create `candidate_evaluations` table
- Add CHECK constraint to `job_applications.status` expanding valid values to full workflow set
- Index `(candidate_id, job_id)` on evaluations

### Wire up

- Add `app/evaluations/__init__.py`, `router.py`, `models.py`, `schemas.py`
- Register router in `app/main.py`: `app.include_router(evaluations_router)`

---

## Phase 5 — Notes & Candidate Profile Enhancements

**Goal:** Recruiters leave internal notes on candidates. Candidate profiles gain missing fields (certifications, languages, LinkedIn/GitHub, salary).

### New model: `CandidateNote`

File: `app/notes/models.py`

```python
class CandidateNote(Base):
    __tablename__ = "candidate_notes"

    id: UUID PK
    candidate_id: UUID FK → candidates.id  (indexed)
    author_id: UUID FK → users.id          (indexed)
    text: Text  (not nullable)
    created_at: DateTime(tz)
    updated_at: DateTime(tz)
    deleted_at: DateTime(tz)
```

### Endpoints

- `GET    /candidates/{id}/notes` — list active notes (get_current_user)
- `POST   /candidates/{id}/notes` — create note (require_write)
- `PATCH  /candidates/{id}/notes/{note_id}` — edit own note (require_write + author check)
- `DELETE /candidates/{id}/notes/{note_id}` — soft delete (require_write + author or admin)

### Candidate model additions

File: `app/candidates/models.py` — add columns:

```python
certifications: list[str]   JSONB default []
languages: list[str]        JSONB default []
linkedin_url: Text nullable
github_url: Text nullable
desired_salary: Integer nullable   # in USD/year
```

Update `CreateCandidateRequest`, `UpdateCandidateRequest`, `CandidateResponse` in `app/candidates/schemas.py`.

Also update `app/parser/schemas.py` `CandidateData` to include these fields so the LLM extractor can populate them.
Update `app/parser/extractor.py` to extract certifications, languages, linkedin_url, github_url from resume text.

### Migration: `0018_notes_and_candidate_fields.py`

- Create `candidate_notes` table
- `ALTER TABLE candidates ADD COLUMN certifications JSONB NOT NULL DEFAULT '[]'`
- `ALTER TABLE candidates ADD COLUMN languages JSONB NOT NULL DEFAULT '[]'`
- `ALTER TABLE candidates ADD COLUMN linkedin_url TEXT`
- `ALTER TABLE candidates ADD COLUMN github_url TEXT`
- `ALTER TABLE candidates ADD COLUMN desired_salary INTEGER`

### Wire up

- Add `app/notes/__init__.py`, `router.py`, `models.py`, `schemas.py`
- Register router in `app/main.py`: `app.include_router(notes_router)`

---

## Phase 6 — Analytics & Export

**Goal:** Dashboard-level metrics for stakeholders. CSV export for candidates.

### Endpoints

All read-only, `Depends(get_current_user)`.

#### `GET /analytics/overview`

Response:
```json
{
  "total_candidates": 1024,
  "total_jobs": 38,
  "total_applications": 312,
  "applications_by_status": { "applied": 120, "interview": 45, ... },
  "top_skills": [{ "skill": "Python", "count": 200 }, ...]
}
```

Implementation:
- `SELECT COUNT(*) FROM candidates WHERE deleted_at IS NULL`
- `SELECT status, COUNT(*) FROM job_applications GROUP BY status`
- Top skills: `SELECT jsonb_array_elements_text(skills) AS skill, COUNT(*) GROUP BY skill ORDER BY count DESC LIMIT 10`

#### `GET /analytics/funnel`

Response: stages with candidate counts, conversion rates stage→stage.

Query `job_applications` grouped by `status`, optionally filtered by `?job_id=`.

#### `GET /analytics/recruiter-activity`

Response: per-user evaluation count, avg rating given, last active.

Query `candidate_evaluations` grouped by `evaluator_id`, join `users` for name.
Admin-only (`Depends(require_admin)`).

#### `GET /candidates/export.csv`

- Same filter params as `/candidates/search` (q, skills, seniority, location, years_min, years_max)
- Returns `StreamingResponse` with `text/csv` content type
- Columns: id, name, email, phone, location, seniority, years_experience, skills (pipe-separated), desired_position, created_at
- Cap at 10 000 rows

Implementation uses `csv.writer` over `io.StringIO` → `StreamingResponse`.

### New files

- `app/analytics/__init__.py`
- `app/analytics/router.py` — all 3 analytics endpoints
- `app/analytics/schemas.py` — response models

Add export endpoint directly to `app/candidates/router.py` (same prefix, no new module needed).

### Migration: `0019_analytics_indexes.py`

- `CREATE INDEX IF NOT EXISTS ix_job_applications_status ON job_applications (status)`
- `CREATE INDEX IF NOT EXISTS ix_candidate_evaluations_evaluator ON candidate_evaluations (evaluator_id)` ← only needed after Phase 4
- No schema changes

### Wire up

- Register router in `app/main.py`: `app.include_router(analytics_router)`

---

## Dependency order

```
Phase 4  (evaluations)  — no deps on 5 or 6
Phase 5  (notes)        — no deps on 4 or 6; migration 0018 depends on 0017 existing, so run after 4
Phase 6  (analytics)    — recruiter-activity query needs evaluations table from Phase 4
```

Safe parallel worktree order: **4 and 5 in parallel**, then **6 after 4 merges**.
