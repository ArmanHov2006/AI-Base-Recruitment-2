# TODOS

## ~~Golden-set eval for AI-interview tier-classification~~ — DONE 2026-07-15

Implemented: `tests/golden/fixtures.py` (6 hand-anchored transcripts spanning
the tier ladder) + `tests/test_interview_scoring_golden.py` (asserts each
dimension lands within ±1 tier via `app/llm/rubric.py::tier_distance`).
Opt-in like the existing `TEST_DATABASE_URL` integration test — needs a live
LLM, so it's skipped by default:

```
RUN_GOLDEN_EVAL=1 uv run pytest tests/test_interview_scoring_golden.py -v
```

**Not yet done:** wiring this into an actual CI pipeline — this repo has no
`.github/workflows/` at all yet, so "gates changes to the scoring prompt" is
still a manual step (run the command above before merging prompt/rubric
changes). Also: fixture labels are Claude-authored anchors, not
recruiter-reviewed — read the provenance note at the top of `fixtures.py`
before trusting them as ground truth. Hasn't been run against a live LLM yet
either (no local Ollama running at time of writing) — run it once before
relying on it.

## Candidate recorder i18n (consent + UI chrome + error states)

- **What:** Localize the public candidate recorder UI — consent gate text, recorder chrome, permission/error/empty states — into the role language (hy/ru/en), matching the question language the PRD already localizes.
- **Why:** Consent shown in a language the candidate doesn't read is a weak legal record; non-English candidates hitting English-only error/permission screens get confused and abandon. Matters for EU/CIS GTM.
- **Pros:** Legally sound consent; higher completion for non-English candidates; consistent with role-language questions.
- **Cons:** ~half-day; needs role-language plumbing through to the public page.
- **Context:** Surfaced by `/plan-design-review` (2026-06-14). PRD §7 localizes only the questions, not the wrapper UI. Slice is English-first (eng decision A2), so this is deliberately deferred.
- **Depends on / blocked by:** candidate page built (T6/T12); role-language available on the public token payload. **Blocks:** non-English candidate rollout.
- **Re-verified 2026-07-15 — still genuinely blocked, not just stale:** confirmed via code search, no "language"/role-language concept exists anywhere (no column on `Job` or `InterviewSession`, nothing in `interviews/schemas.py`). Bigger than i18n now: `frontend/src/pages/InterviewSession.tsx:120` already calls `GET /interviews/public/{sessionId}/info`, but that endpoint doesn't exist in `app/interviews/router.py` — the router only has `/public/upload-url` and `/public/{session_id}/answers/{idx}/start`. There is also no session-creation endpoint anywhere (`InterviewSession(...)` is never instantiated outside `models.py`/tests) — Lane B (access-token-gated creation) is still unbuilt, matching the `router.py` module docstring's own admission. Doing this TODO for real means first: (1) add the missing public `GET /info` endpoint, (2) add a `language` column to `InterviewSession` + migration, sourced from `candidate.resume_language` (already captured, hy/ru/en/unknown) at session-creation time — there's no session-creation endpoint to hang that on yet either, so that has to be built too, (3) only then localize the UI chrome against it. That's a session-creation + auth-token design decision (public unauthenticated endpoint surface), not a translation task — flagging for a scoping call rather than guessing at the token/security design solo.

