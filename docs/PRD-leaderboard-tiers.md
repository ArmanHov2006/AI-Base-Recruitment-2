# PRD — Leaderboard S/A/B/F Shortlist Tiers

**Status:** Draft · **Date:** 2026-06-03 · **Branch base:** `feat/hybrid-tier-scoring` (79d9e80)
**Author:** design finalized via grill + codex consult (47,986-token review folded in)

---

## 1. Problem

The leaderboard is a flat ranked list. Recruiters still have to eyeball where to draw
the "advance to next stage" line, and ties are invisible. They want the board to do the
triage: given how many candidates they intend to advance, split applicants into
**clear advances**, **contested ties at the cut**, **qualified backups**, and **rejects** —
so the only manual decision left is resolving the contested bucket.

## 2. Goals

- Group scored applicants into 4 tiers **S / A / B / F** off the job's target count + threshold.
- Make ties first-class: candidates sharing the cut rating land in one contested tier (A).
- Let recruiters tweak target/threshold live without editing the job.
- Color-code tiers so the board is readable at a glance.

## 3. Non-goals (v1)

- Range targets (`3–5`). Single integer only. Deferred to v2.
- Auto-advancing candidates' stage on load. Advisory-only; bulk advance is **phase 2**.
- Re-skinning the 5 other surfaces that still show 0–100. Out of scope.
- Changing scoring policy (weights/tiers live in `app/llm/rubric.py`, untouched).

## 4. Background — groundwork already shipped (79d9e80)

The 100→10 / 0.5-step migration is **done**; this feature stacks on it.

| Capability | Location | Status |
|---|---|---|
| Hybrid tier scoring (LLM tiers → `aggregate()` → 0–100 int) | `app/llm/rubric.py`, `app/llm/ollama.py:433` | shipped |
| OpenAI inherits scorer | `app/llm/openai_client.py` (aliases `score_candidate`) | shipped |
| Quantizer 0–100 → 0–10 step 0.5 | `app/comparisons/utils.py:to_ten_scale()` (`round(s/10*2)/2`) | shipped |
| `overall_score_10` on entries | `app/comparisons/schemas.py` / `jobs/router.py:330` | shipped |
| Precise-qualify / quantized-display split | `app/jobs/router.py:425` (PDF export) | shipped |
| `Job.candidates_for_next_stage` (Integer), `Job.threshold_score` (Float 0–10) | `app/jobs/models.py:25-26` | shipped |

**Scoring policy is frozen and owned by `rubric.py`** (`SCORE_WEIGHTS` skills 0.55 / exp 0.30 /
seniority 0.12 / education 0.03; `TIER_POINTS` 95/80/60/38/12). Tiering must NOT duplicate or
relocate these. Changing them silently reshuffles every user's tiers.

## 5. Tier definitions

| Tier | Meaning | Rule |
|---|---|---|
| **S** | For-sure advance | qualified AND `rating > cut` |
| **A** | Contested — tied at the cut (recruiter resolves) | qualified AND `rating == cut` |
| **B** | Qualified backup, below the cut | qualified AND `rating < cut` |
| **F** | Failing — below threshold | `precise < threshold` |

`rating` = `to_ten_scale(overall_score)` (0.5 step) — used for **display + cut-bucket ties**.
`precise` = `overall_score / 10` — used for **qualification only** (PDF-consistent; avoids the
`overall_score=73` → displays `7.5` → false-qualify flip).

**Threshold dominates** (codex fix): F is decided first; S/A/B only ever partition the qualified set.

## 6. Algorithm (final, hardened)

```text
INPUT:
  rows      = ALL scored CandidateJobScore rows for the job (full set, NOT limited)
  target    = job.candidates_for_next_stage  (int | None, query-overridable)
  threshold = job.threshold_score ?? DEFAULT_THRESHOLD_SCORE (7.5), query-overridable

# stable order — raw-score tie inside a 0.5 bucket is not enough
rows.sort(key = overall_score DESC, updated_at DESC, candidate_id ASC)

precise(r) = r.overall_score / 10
rating(r)  = to_ten_scale(r.overall_score)

# 1. threshold dominates — F first
F          = [r for r in rows if precise(r) <  threshold]
qualified  = [r for r in rows if precise(r) >= threshold]

# 2. no target → degrade to Qualified / Out (do NOT fabricate a cut)
if target is None:
    mode = "qualified_only"
    return { qualified: tier=None, F: tier="F" }

# 3. enough seats for everyone qualified → all S, nobody contested
if target >= len(qualified):
    mode = "tiered"; cut = None
    return { qualified: tier="S", F: tier="F" }

# 4. normal cut
mode = "tiered"
cut  = rating(qualified[target - 1])          # rating at the target-th qualified row
for r in qualified:
    r.tier = "S" if rating(r) > cut else "A" if rating(r) == cut else "B"
```

Properties: A is rating-defined and may overflow remaining seats (intended — that IS the
contested set). Cut is computed over the full qualified set, independent of display paging.

## 7. Null / edge handling

| Condition | Behavior |
|---|---|
| `threshold` null | `DEFAULT_THRESHOLD_SCORE = 7.5` (new constant, `app/comparisons/constants.py`) |
| `target` null | `mode="qualified_only"` — 2 groups (Qualified / Out) + UI nudge "Set a target to unlock tiers" |
| `target >= len(qualified)` | all qualified → S, `cut=None`, A empty |
| `len(qualified) == 0` | everyone F |
| no scored rows | empty board, existing empty-state |
| raw-score ties | broken deterministically by `updated_at DESC, candidate_id ASC` |

## 8. API

**New endpoint (non-breaking — `/leaderboard` flat array stays untouched):**

```
GET /jobs/{job_id}/shortlist?target={int}&threshold={float}
  → ShortlistResponse
```

```python
class ShortlistResponse(BaseModel):
    mode: Literal["tiered", "qualified_only"]
    target: int | None
    threshold: float           # effective (after default fallback)
    cut_rating: float | None
    scored_count: int
    applicant_count: int
    latest_scored_at: datetime | None
    entries: list[ShortlistEntry]   # FLAT, each carries `tier`; grouping is a frontend concern
```

`ShortlistEntry` = existing `LeaderboardEntry` fields + `tier: Literal["S","A","B","F"] | None`.
Query params override job fields for live what-if; absent → fall back to job values.

**Two-phase read (codex perf note):** phase 1 scans `id, overall_score` over the full scored
set to compute cut + per-candidate tier; phase 2 fetches display fields (JSONB reasoning /
skill_breakdown) only for returned rows.

**No DB migration.** `rating`/`tier` are pure functions of `overall_score`; quantize-on-read
via the single existing `to_ten_scale()`.

**Suggested index** (separate small PR): `(job_id, overall_score DESC, candidate_id)` for stable
descending scans. Current `ix_cjs_job_score (job_id, overall_score)` is usable meanwhile.

## 9. Frontend

- `frontend/src/pages/Leaderboard.tsx` → consume `/shortlist`; render tier section headers
  (S/A/B/F), group flat entries client-side by `tier`, show `overall_score_10` badge.
- Live `target` + `threshold` inputs at top → refetch with query params (what-if, no job edit).
- `mode="qualified_only"` → render Qualified / Out + "set target" nudge.
- `frontend/src/components/JobLeaderboard.tsx` (embedded preview) stays on flat `/leaderboard`.
- `frontend/src/types/index.ts` → `ShortlistResponse`, `ShortlistEntry`, `tier`.

## 10. Colors (dark theme, body `#09090e`, primary `#5b6af5`)

| Tier | Meaning | Accent | Row tint |
|---|---|---|---|
| **S** | go | emerald `#22c55e` | ~14% |
| **A** | you decide | amber `#fbbf24` | ~14% |
| **B** | hold / backup | indigo `#5b6af5` (brand) | ~12% |
| **F** | out | muted grey `#6b7280` | ~8% (collapsible) |

Gradient go → caution → hold → out. Red avoided (no alarm spam); F reads "parked." Accent on
tier chip + 3px left border + row bg tint.

## 11. Testing (`tests/test_leaderboard_tiers.py`)

- 4-bodies-at-cut → all 4 in A (rating-defined overflow).
- **cut below threshold suppressed** — `threshold=7.5, target=10`, all scores 4.0–6.0 → all F, S/A empty.
- `target >= qualified_count` → all qualified S, A empty, `cut=None`.
- `target` null → `qualified_only` mode.
- `threshold` null → 7.5 applied.
- limit/page smaller than target → tiers still correct (full-set computation).
- everyone bunched at one rating → S empty, all A.
- raw-score tie → deterministic order (`updated_at`, `candidate_id`).
- PDF/API threshold consistency — `overall_score=73`, `threshold=7.5` → NOT qualified in both.
- empty board.

## 12. Phasing

- **Phase 1 (this PRD):** `constants.py` (DEFAULT_THRESHOLD_SCORE) · `tiering.py` (pure `assign_tiers`) ·
  `ShortlistResponse`/`ShortlistEntry` schemas · `GET /shortlist` (two-phase) · frontend tiers + colors · tests.
- **Phase 2 (deferred):** bulk "Advance S → next stage" writing `JobApplication.status` via the
  existing FSM, explicit opt-in only.
- **v2 (maybe):** range targets; stale `score_input_hash` flagging during re-scoring; index PR.

## 13. Risks

- Full-set tier computation per request — bounded by applicants/job (hundreds); two-phase query
  keeps JSONB out of the cut scan. Revisit if a job exceeds ~5k applicants.
- Mixed scoring-policy rows during re-scoring — surface `latest_scored_at` / `scored_count`; stale
  detection deferred to v2.
- `DEFAULT_THRESHOLD_SCORE` lives in `comparisons/constants.py` but PDF export still inlines `7.5` —
  fold PDF onto the constant in phase 1 to keep one source of truth.
