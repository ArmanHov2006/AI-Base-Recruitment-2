# PRD — Pipeline Kanban Card Redesign

**Status:** Draft
**Author:** Arman
**Date:** 2026-06-03
**Owner area:** `frontend/src/pages/Pipeline.tsx`, `app/applications/*`
**Related:** Leaderboard S/A/B/F tier design (locked 2026-06-03, `/10` quantized to 0.5, advisory-only)

---

## 1. Problem

The pipeline kanban board (`Pipeline.tsx`) renders candidate cards that are functionally
blind. Three concrete failures, reported from real use:

1. **No rating on the card.** A recruiter cannot rank candidates within a column without
   leaving the board for the leaderboard. The card has no score because `list_applications`
   (`app/applications/router.py:210`) joins only the `Candidate` table — never
   `CandidateJobScore` — and `ApplicationResponse` (`app/applications/schemas.py:101`) has no
   score field. The frontend literally never receives a rating to display.

2. **Names frequently missing.** Cards render `app.candidate?.name || 'Unknown'`
   (`Pipeline.tsx:237`). When the LLM parse succeeds but extracts no `name` (photo-heavy CV,
   bad OCR), the card shows a bare `Unknown`. Multiple such cards stack indistinguishably.

3. **Same-name collisions.** Two candidates named "Aram Petrosyan" produce two visually
   identical cards. The only differentiators currently shown are name (which collides by
   definition) and email. No score, no avatar, no unique anchor.

This matters because the board is the recruiter's primary triage surface, and this is a bank
hiring context where decisions must be defensible.

---

## 2. Goals

- Show a **score** on every scored card, encoded so it is scannable across columns.
- Make every card **uniquely identifiable**, even with missing names or duplicate names.
- Do not regress drag-and-drop, parsing strip, or board performance.
- Respect role-based access — AI scores are sensitive data.

### Non-goals

- Changing the scoring algorithm or the `/10` rescale itself (owned by the leaderboard branch).
- Building per-column filtering/sorting controls (future iteration).
- Touching the leaderboard page.

---

## 3. Decisions (locked via grill session 2026-06-03)

| # | Decision | Rationale | Rejected alternative |
|---|----------|-----------|----------------------|
| D1 | Score reaches the card via **backend LEFT JOIN** into `list_applications`, exposed on `ApplicationResponse`. | One query, no client-side merge drift, server-sortable later. | Client-side second query to leaderboard + merge by `candidate_id` — races, drops unscored candidates, flickers on refetch. |
| D2 | JOIN is **LEFT**, not INNER. Unscored candidates still appear. | Board must show everyone, scored or not. | INNER join silently hides unscored applicants. |
| D3 | Card distinguishes **`0` (scored, bad)** from **`N/A` (not yet scored)**. `N/A` muted/gray, real scores colored. | Conflating them makes a queued strong hire look AI-rejected, and a real 0 look "pending". | Single blank/zero for both. |
| D4 | Tier encoded as **color**, raw score shown as **`X.X/10`**. Not the letter. | Color is pre-attentive — find all "A" cards in one sweep. Number gives drill-down precision. Letter+number is redundant on a tiny card. | Show tier letter; show both. |
| D5 | Tier→color map is a **single shared constant** imported by both pipeline and leaderboard; must pass contrast on dark theme (`#09090e` body, `#5b6af5` indigo base). | Two different greens = two visual languages. | Per-page ad-hoc colors. |
| D6 | Backend exposes **only `overall_score_10`** (computed via `to_ten_scale()` in the mapper) plus `scored_at` and `score_stale` — **not** the raw 0-100 `overall_score` (codex #24/#25). Card renders `overall_score_10` as `X.X/10`. | `/10` is the only value the UI shows; raw 0-100 on the list response is dead weight and extra leak surface. Conversion stays in one server-side function — no client arithmetic. | Expose raw `overall_score`; hard-code `/10` or `/100` in JSX; recompute scale client-side. |
| D7 | Missing-name **fallback ladder**: `name` → `email` → **`#<last 6 of application.id>`**. Plus a "Needs review" flag. Falls back to `application.id`, **not** `candidate_id` (codex #16/#17/#27 — `candidate_id` is nullable; `application.id` always exists). Original-filename fallback **dropped** (F3). | Surface + flag beats hiding; `application.id` is the only id guaranteed present even when candidate is null/soft-deleted. 6 chars over 4 to cut collision odds. | Hide unparsed cards. Use `candidate_id` short-id (null when unparsed). |
| D8 | Same-name disambiguation primary anchor = **email**; visual = photo/initials + tier color; guaranteed fallback = **`#<application.id>` short ref**. | Name is the colliding field. Photo is nullable. Email is near-unique + human-readable. `application.id` never null. | Use name/photo/score as primary discriminators; rely on `candidate_id`. |
| D9 | Score fields (`overall_score_10`, `scored_at`, `score_stale`) **role-gated at the field level** in the mapper, set to `null` for `VIEWER` (codex #4/#7/#29). Route stays open via `get_current_user` (board must be viewable). **Cross-endpoint:** the same redaction must hold on leaderboard / comparison / export endpoints, or VIEWER leaks there (codex #5). | Adding AI scores to an all-roles endpoint is silent scope creep; bank/adverse-action exposure. Field-gate, don't route-gate. | Reuse `require_write` (excludes VIEWER from the whole board — wrong). Strip only some score fields. |
| D10 | **DESCOPED — blocked by F7.** `Job` has no `updated_at` column, so there is no JD-edit timestamp to compare `scored_at` against. Staleness detection is **deferred** until `Job.updated_at` is added (separate migration). This PR ships the AI/provenance marker only (the number is AI-derived), **not** the stale flag. | Can't compute staleness without a JD-edit timestamp. Don't fake it. | Add `Job.updated_at` here (migration scope creep, violates read-only constraint). |

---

## 3.5 Codebase review findings (verified 2026-06-03)

- **F1 — score table shape confirmed.** `CandidateJobScore` (`app/comparisons/models.py:32`):
  `overall_score Integer NOT NULL`, `dimension_scores JSONB NOT NULL`, plus `scored_at` and
  `updated_at` (both `timezone=True`). A row exists **only when scored** (unique on
  `job_id, candidate_id`). → A LEFT JOIN yields `NULL overall_score` for unscored candidates,
  which is exactly the `N/A` case in D3. `scored_at` enables the D10 staleness check
  (`scored_at` vs job `updated_at`).
- **F2 — authz primitives already exist.** `app/auth.py` has `require_role(*roles)`,
  `require_write` (= `ADMIN | RECRUITER | HR_MANAGER`, excludes `VIEWER`), and `require_admin`.
  Field-gating (D9) needs no new infra: inject `get_current_user`, branch on `user.role`,
  strip score fields for `VIEWER`. No route-guard change required (board must stay viewable).
- **F3 — original resume filename is NOT stored.** `resume_file_id` is a **UUID4 MinIO object
  key** (`app/parser/service.py:80` validates UUID4; `extractor.py:29` uses it as the object
  name). No `filename`/`original_name` column anywhere. The D7 filename fallback is therefore
  **not implementable** without capturing the upload filename at ingest — descoped here, logged
  as a future option.
- **F4 — `_to_response` is a manual constructor** (`app/applications/router.py:69`). It builds
  `ApplicationResponse` field-by-field, so adding `overall_score`/`overall_score_10`/`scored_at`
  requires threading them through the `_to_response` signature, not just the query.
- **F5 — the `/10` scale already shipped on branch `feat/hybrid-tier-scoring` (`79d9e80`).**
  Critical reversal of the original sequencing fear: **storage stays 0-100** (high-resolution
  sort key); the 0-10 value is **quantize-on-read**. There is **no migration and no backfill**
  on `candidate_job_scores` → no Alembic dual-head risk. The branch added:
  - `to_ten_scale(score_100) -> float | None` in `app/comparisons/utils.py` — single source of
    truth, `round(score/10*2)/2` (0.5 steps), null-safe.
  - `overall_score_10: float | None` field on `ComparisonResultResponse` and `LeaderboardEntry`
    (`app/comparisons/schemas.py`), populated via `to_ten_scale(...)` at the response edge
    (`app/comparisons/router.py:_build_comparison_response`).
  - Pipeline must **follow the same convention**: expose both `overall_score` (raw) and
    `overall_score_10` on `ApplicationResponse`, computed with the same `to_ten_scale`.
  - **Tier caveat:** `rubric.py` `SCORE_TIERS` (excellent/strong/partial/weak/none) are the
    LLM *classification* tiers feeding the score — **not** the S/A/B/F *display* tiers from the
    locked leaderboard design. The S/A/B/F→color map (D4/D5) is still unbuilt; pipeline color
    coding depends on that map landing, or defines it jointly. Do not conflate the two tier
    systems.
- **F6 — join correctness (codex #1/#2).** The LEFT JOIN must match on **both**
  `CandidateJobScore.job_id == JobApplication.job_id` **and**
  `CandidateJobScore.candidate_id == JobApplication.candidate_id` (same candidate scores
  differently per job). Single-row-per-application is guaranteed today only by
  `UniqueConstraint(job_id, candidate_id)`. If historical/versioned scores are ever added,
  this join starts duplicating application rows — at that point it must target "latest score".
  The PRD depends on that constraint explicitly.
- **F7 — `Job` has no `updated_at` (blocks D10).** `app/jobs/models.py` defines only
  `created_at` and `deleted_at`. No JD-edit timestamp exists, so score staleness
  (`scored_at` vs JD edit) cannot be computed. D10's stale flag is **descoped**; adding
  `Job.updated_at` (with `onupdate=func.now()` + a migration) is a prerequisite follow-up.
  Drop `score_stale` from the response and the frontend type for this PR.

---

## 4. Sequencing / dependencies

> **Dependency (relaxed after F5).** The `/10` scale shipped on `feat/hybrid-tier-scoring`
> (`79d9e80`) as **quantize-on-read** — no migration, no schema change to
> `candidate_job_scores`. The earlier dual-head/backfill fear does **not** apply.
>
> Remaining ordering:
> 1. **`feat/hybrid-tier-scoring` merges to `main` first** (or this branch rebases onto it) so
>    `to_ten_scale` and the `overall_score_10` convention exist to reuse. Pure code dependency,
>    not a data-migration dependency.
> 2. This branch is **read-only on `candidate_job_scores`** (LEFT JOIN only — no columns, no
>    indexes). Keeps migration history linear.
> 3. **S/A/B/F display-tier color map (D4/D5) is the real blocker for color coding** — it is
>    unbuilt and distinct from the rubric's classification tiers (F5). Either it lands first, or
>    this branch defines the shared tier→color constant and the leaderboard adopts it. Until
>    then, ship the raw `X.X/10` number; layer color in when the map exists.

---

## 5. Scope of work

### 5.1 Backend
- `list_applications` (`app/applications/router.py:210`):
  - Add `LEFT JOIN CandidateJobScore` on **both** keys (F6), selecting `overall_score` (used
    only to derive the `/10` value, not returned) and `scored_at`.
  - (D10 staleness descoped — F7; no `score_stale` this PR.)
  - Change the handler to take `user: User = Depends(get_current_user)` as a **parameter**
    (remove the `dependencies=[...]` entry to avoid running the dep twice — codex #28) so the
    mapper can branch on `user.role`.
- `ApplicationResponse` (`app/applications/schemas.py:101`): add nullable
  `overall_score_10: float | None` and `scored_at: datetime | None`.
  **Do not add raw `overall_score`** (D6, codex #24/#25). Compute `overall_score_10` via the
  existing `to_ten_scale()` (`app/comparisons/utils.py`) — do not reimplement.
- `_to_response` (F4): extend signature to `(application, candidate, *, score=None, user=None)`
  (keep new args optional so the other 3 call sites — lines 151/244/300 — keep working) and
  **centralize score redaction here** (codex #11). For `VIEWER`, set the score fields to `null`.
- **Cross-endpoint audit (D9, codex #5):** verify the leaderboard / comparison-result /
  export endpoints don't already hand AI scores to `VIEWER`. If they do, that's a pre-existing
  leak — flag it (may be a separate fix, but note it here).
- Audit consideration: log score reads if compliance requires (confirm with owner).

### 5.2 Frontend
- `JobApplication` type (`frontend/src/types/index.ts`): add `overall_score_10: number | null`,
  `scored_at: string | null`. (No raw `overall_score` — D6. No `score_stale` — F7/D10 descoped.)
- Tier→color map (new `constants/scoring.ts`) for S/A/B/F **display** tiers, imported by both
  pipeline and leaderboard. Denominator is fixed by the backend `overall_score_10` field — no
  client-side `SCORE_MAX` needed (the conversion lives server-side, F5/D6).
- Card redesign (`Pipeline.tsx` card block, ~`235–256`):
  - Score badge: tier color background, render `overall_score_10` as `X.X/10`, `N/A` muted when
    null.
  - Name fallback ladder (D7: name → email → short id) + "Needs review" flag.
  - Disambiguation row: email + photo/initials + short id when name absent.
  - AI/staleness marker (D10).
- Perf (see 5.3).

### 5.3 Performance (re-scoped per codex #20/#21/#22/#23)
**This PR (cheap, safe):**
- Replace 7 per-column `applications.filter()` calls (`Pipeline.tsx:159`) with a single
  `useMemo` reduce into `Record<status, app[]>`.
- Memoize cards and stabilize drag handlers so a single card move doesn't re-render the board.
- **Tame the 2s poll** (`refetchInterval` while any app is `parsing`, `Pipeline.tsx:58`): it
  currently re-renders all columns every 2s. This is the real cost at scale, not the 7 filters.
  Narrow what re-renders, or pause polling during an active drag.
- Per-column scroll container with a defined behavior (board-level horizontal + constrained
  column vertical) — not seven independently-scrolling columns (codex #23).

**Deferred to a separate PR (do NOT bundle):**
- Virtualization (react-window). The board uses **native HTML5 drag** (`draggable` +
  `onDragStart/onDrop`); windowing unmounts offscreen cards and **breaks dragging to/from
  them and offscreen drop targets** (codex #21). Only pursue if a real >400-card job proves the
  un-virtualized board janks after the cheap wins above, and test against the drag impl first.

---

## 6. Edge cases

- Candidate scored `0` vs unscored → distinct rendering (D3).
- Candidate with null name → fallback ladder + flag (D7).
- Two cards, same name, both no email → short id disambiguates (D8).
- PATCH move fails after optimistic update → existing rollback+toast (`Pipeline.tsx:73`) is
  transient; consider a persistent failure signal (out of scope, noted for follow-up).
- Stale score after JD edit → staleness flag (D10).
- `viewer` role → no score fields in payload (D9).

---

## 7. Acceptance criteria

- [ ] Every scored card shows `X.X/10` (from `overall_score_10`); unscored shows muted `N/A`.
- [ ] Score badge carries a subtle AI/provenance marker (the number is AI-derived). Staleness
      flag is **deferred** (F7 — `Job.updated_at` doesn't exist yet).
- [ ] Tier color is **deferred** until the S/A/B/F map exists; this PR ships a neutral score
      badge (codex #9/#10/#26 — no fake parity with an unbuilt leaderboard constant).
- [ ] No card ever shows a bare `Unknown` with no other identifier — ladder ends at
      `#<application.id>`, which is always present (even when `candidate_id` is null).
- [ ] Two same-name candidates are distinguishable at a glance.
- [ ] `VIEWER` receives `null` for `overall_score_10` and `scored_at`; raw `overall_score` is
      never in the response for any role.
- [ ] Score redaction is centralized in `_to_response` (one decision point).
- [ ] Board stays smooth at 400+ apps via memoized groupBy + tamed polling (virtualization
      deferred).
- [ ] `/10` value comes from backend `to_ten_scale`; no client-side scale arithmetic.
- [ ] No new migration head on `candidate_job_scores` (read-only LEFT JOIN on both keys).

---

## 8. Open questions

- Does compliance require audit logging of score reads (D9)?
- **S/A/B/F display-tier thresholds + color values are not yet defined or built** (distinct
  from rubric classification tiers, F5). Who owns the shared `constants/scoring.ts` tier→color
  map — this branch or the leaderboard branch?
- ~~Is original resume filename available for the D7 fallback?~~ **Resolved (F3): not stored.**
  `resume_file_id` is a UUID4 object key. Filename fallback dropped; revisit only if upload-time
  filename capture is added later.
- Should `dimension_scores` also surface on the card (e.g. tooltip), or is the single
  `overall_score_10` enough for triage? (Leaning: overall only on the card; dimensions on the
  candidate detail page. Codex #25 agrees — keep the list payload narrow.)
- **Is `VIEWER` allowed to see candidate email today?** D8 uses email as the disambiguation
  anchor; if email is itself role-restricted, the ladder needs to be role-aware (codex #14).
  Email is already shown on the current card, so this is not a new leak — but confirm intent.
- **Pre-existing leak check (D9/codex #5):** do the leaderboard/comparison/export endpoints
  already return AI scores to `VIEWER`? If yes, that predates this PR and needs its own fix.
