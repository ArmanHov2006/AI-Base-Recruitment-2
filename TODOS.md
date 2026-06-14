# TODOS

## Golden-set eval for AI-interview tier-classification

- **What:** Human-labeled answer set + CI eval asserting LLM dimension tiers match labels within ±1 tier; gates changes to the interview scoring prompt.
- **Why:** `score_interview()` splits into deterministic rubric math (unit-tested) + LLM tier-classification (no quality gate). Prompt edits would silently move real candidate scores with nothing catching the drift.
- **Pros:** Regression guard on scoring quality; defensible "AI suggests, human decides" posture for EU/Art. 22; catches prompt drift before it reaches candidates.
- **Cons:** Needs a curated, human-labeled fixture (~5–10 answers/dimension); ~3h human / ~40min CC.
- **Context:** Deferred from `/plan-eng-review` (decision T-EVAL, 2026-06-14). Slice 1 unit-tests the pure rubric math only; LLM tier quality eyeballed during the spike. This TODO formalizes the CI gate once the scoring prompt stabilizes post-slice.
- **Depends on / blocked by:** `score_interview()` prompt stable (after the STT+scoring mini-slice, Lane B). **Blocks:** scoring real candidates in production.

## Candidate recorder i18n (consent + UI chrome + error states)

- **What:** Localize the public candidate recorder UI — consent gate text, recorder chrome, permission/error/empty states — into the role language (hy/ru/en), matching the question language the PRD already localizes.
- **Why:** Consent shown in a language the candidate doesn't read is a weak legal record; non-English candidates hitting English-only error/permission screens get confused and abandon. Matters for EU/CIS GTM.
- **Pros:** Legally sound consent; higher completion for non-English candidates; consistent with role-language questions.
- **Cons:** ~half-day; needs role-language plumbing through to the public page.
- **Context:** Surfaced by `/plan-design-review` (2026-06-14). PRD §7 localizes only the questions, not the wrapper UI. Slice is English-first (eng decision A2), so this is deliberately deferred.
- **Depends on / blocked by:** candidate page built (T6/T12); role-language available on the public token payload. **Blocks:** non-English candidate rollout.

