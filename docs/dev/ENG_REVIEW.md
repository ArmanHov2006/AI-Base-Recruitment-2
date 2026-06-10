# Engineering Review — Score Memory, Leaderboard, and Comparison History

Date: 2026-05-22  
Reviewer: /plan-eng-review (gstack)  
Branch: main  
Feature: Score Memory, Leaderboard, and Comparison History  
Design doc: ~/.gstack/projects/ArmanHov2006-AI_Based_Recruitment/Arman-main-design-20260522-130346.md

---

## Decisions Made

### Section 1 — Architecture

**D1 — Hash must not include `decision_tags` or `required_seniority`**  
`_score_one` does not pass these fields to `score_candidate()`. The hash must equal the exact LLM payload or it will produce cache misses for identical LLM calls.  
Hash inputs: `job.title`, `job.description`, `job.required_skills`, `job.required_technical_skills`, `job.required_soft_skills`, `candidate.skills`, `candidate.years_experience`, `candidate.education`, `candidate.work_experiences`, `candidate.seniority`, `candidate.summary`, plus `model_tag` from `settings.ollama_model`.

**D2 — Deterministic serialization spec**  
All list fields must be sorted before hashing: `sorted(field or [])`. Final payload serialized with `json.dumps(payload, sort_keys=True)`. SHA-256 of the UTF-8 encoded string. This prevents hash divergence when the LLM call is identical but list fields arrive in different order.

**D3 — Add `limit` param to `list_comparisons`**  
Current endpoint (`app/comparisons/router.py:110`) has no LIMIT clause — will fetch every comparison ever created. Add `limit: int = 50` query param. History panel frontend uses `limit=20`.

**D4 — Extract hash function to `app/comparisons/utils.py`**  
`compute_score_input_hash(candidate: Candidate, job: Job, model_tag: str) -> str` lives in its own module. Imported by `router.py` and by test suite. Testable in isolation without DB or LLM.

### Section 2 — Code Quality

**D5 — Alembic DESC index with `postgresql_ops`**  
Alembic migration for `CandidateJobScore` must specify:
```python
sa.Index(
    "ix_candidate_job_scores_job_score",
    "job_id",
    sa.text("overall_score DESC NULLS LAST"),
    postgresql_ops={"overall_score": "DESC NULLS LAST"},
)
```
Plain `Index("...", "job_id", "overall_score")` creates an ASC index and does not satisfy `ORDER BY overall_score DESC` efficiently.

**D6 — Cache logic in wrapper `_score_with_cache`, not in `_score_one`**  
`_score_one(candidate, job)` remains a pure LLM call (no DB dependency). New wrapper:
```python
async def _score_with_cache(
    candidate: Candidate,
    job: Job,
    db: AsyncSession,
    model_tag: str,
) -> tuple[uuid.UUID, int, dict, str, dict | None]:
```
Wrapper: compute hash → SELECT from `CandidateJobScore` → if hit return cached row → if miss call `_score_one` → UPSERT result with hash. `create_comparison` calls `_score_with_cache`.

### Section 3 — Tests

**D7 — Full test suite required (7 tests)**  
`tests/test_comparisons.py` must cover:

| # | Test | What it guards |
|---|------|----------------|
| 1 | `test_hash_stability_sorted_inputs` | `sorted()` normalizes list order; same logical payload → same hash |
| 2 | `test_hash_changes_on_model_tag` | Different `model_tag` → different hash → cache miss |
| 3 | `test_score_cache_hit` | Cache hit path returns stored score; LLM not called |
| 4 | `test_score_cache_miss_upserts` | Cache miss calls LLM; result written to `CandidateJobScore` |
| 5 | `test_leaderboard_ordered_desc` | `/jobs/{id}/leaderboard` returns candidates sorted by score descending |
| 6 | `test_leaderboard_applicants_only` | Non-applicant candidates excluded even if their score exists |
| 7 | `test_list_comparisons_limit` | `GET /comparisons?limit=20` returns at most 20 rows |

Pattern: `AsyncMock(spec=AsyncSession)` + FastAPI `dependency_overrides[get_db]` (matches `test_candidates.py`).

### Section 4 — Performance

**D8 — Leaderboard uses single JOIN query**  
`GET /jobs/{id}/leaderboard` must not load all scores then filter in Python. Single SQLAlchemy query:

```python
select(CandidateJobScore, Candidate)
.join(Candidate, CandidateJobScore.candidate_id == Candidate.id)
.where(
    CandidateJobScore.job_id == job_id,
    CandidateJobScore.candidate_id.in_(
        select(Application.candidate_id).where(Application.job_id == job_id)
    ),
)
.order_by(CandidateJobScore.overall_score.desc())
.limit(limit)
```

Uses the `(job_id, overall_score DESC)` index from D5.

---

## Acknowledged Risks (no action required for v1)

- **Concurrent UPSERT race**: two simultaneous cache misses for the same `(job_id, candidate_id)` will call the LLM twice and the second UPSERT will overwrite the first. Acceptable for v1 — Ollama is local, not billed per call, and the result is deterministic (same hash → same LLM response).

---

## Implementation Tasks

Derived from the 8 findings above. Each task is self-contained and sequenced by dependency.

- [ ] **E1 (P1, human: ~20min / CC: ~5min)** — Create `app/comparisons/utils.py` with `compute_score_input_hash()`
  - Contract: `sorted()` all list fields, `json.dumps(sort_keys=True)`, SHA-256, return hex string
  - Files: new `app/comparisons/utils.py`
  - Verify: `test_hash_stability_sorted_inputs` and `test_hash_changes_on_model_tag` pass

- [ ] **E2 (P1, human: ~30min / CC: ~10min)** — Add `CandidateJobScore` SQLAlchemy model
  - Fields: `id`, `job_id` (FK), `candidate_id` (FK), `overall_score`, `dimension_scores` (JSONB), `skill_breakdown` (JSONB), `reasoning`, `model_tag`, `score_input_hash`, `created_at`, `updated_at`
  - Constraint: `UniqueConstraint("job_id", "candidate_id")`
  - Files: `app/comparisons/models.py`
  - Verify: model importable, `Base.metadata.tables` contains `candidate_job_scores`

- [ ] **E3 (P1, human: ~20min / CC: ~5min)** — Alembic migration for `candidate_job_scores`
  - Include: DESC index per D5 with `postgresql_ops`
  - Files: new `alembic/versions/0011_candidate_job_scores.py`
  - Verify: `alembic upgrade head` runs clean; `alembic downgrade -1` reverts cleanly

- [ ] **E4 (P1, human: ~45min / CC: ~15min)** — Add `_score_with_cache` wrapper + wire into `create_comparison`
  - Import `compute_score_input_hash` from utils; read `settings.ollama_model` for model_tag
  - UPSERT via `INSERT ... ON CONFLICT (job_id, candidate_id) DO UPDATE`
  - Replace `asyncio.gather(*[_score_one(...)])` with `asyncio.gather(*[_score_with_cache(...)])`
  - Files: `app/comparisons/router.py`
  - Verify: `test_score_cache_hit` (no LLM call) and `test_score_cache_miss_upserts` pass

- [ ] **E5 (P2, human: ~20min / CC: ~5min)** — Add `limit` param to `list_comparisons`
  - `limit: int = Query(default=50, ge=1, le=500)`
  - Files: `app/comparisons/router.py`
  - Verify: `test_list_comparisons_limit` passes; existing callers unaffected (default 50)

- [ ] **E6 (P1, human: ~45min / CC: ~15min)** — Add `GET /jobs/{id}/leaderboard` endpoint
  - Single JOIN query per D8; response schema `LeaderboardEntry` (candidate_id, name, overall_score, rank)
  - Files: `app/jobs/router.py` (or new `app/comparisons/router.py` endpoint), `app/comparisons/schemas.py`
  - Verify: `test_leaderboard_ordered_desc` and `test_leaderboard_applicants_only` pass

- [ ] **E7 (P1, human: ~2h / CC: ~20min)** — Create `tests/test_comparisons.py` with all 7 tests
  - Pattern: `AsyncMock(spec=AsyncSession)` + dependency override (same as `test_candidates.py`)
  - Files: new `tests/test_comparisons.py`
  - Verify: `pytest tests/test_comparisons.py` — all 7 pass, no LLM or DB required

---

## GSTACK ENG REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| Eng Review | `/plan-eng-review` | Architecture & tests | 1 | DECISIONS_RESOLVED | score: 8 decisions, 7 impl tasks |

**UNRESOLVED:** 0 (all 8 decisions resolved by user)  
**VERDICT:** Eng review complete. 7 implementation tasks ready to execute. No blocking issues.
