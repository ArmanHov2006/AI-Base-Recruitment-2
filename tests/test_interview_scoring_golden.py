"""Golden-set eval: LLM interview-scoring tier classification vs human labels.

Sends each tests/golden/fixtures.py transcript through the *real* LLM client
(whatever LLM_PROVIDER/model is configured — Ollama by default) and asserts
every dimension tier lands within ±1 tier of the label (app/llm/rubric.py
SCORE_TIERS ladder: excellent > strong > partial > weak > none).

This is an eval, not a unit test — it needs a live LLM (Ollama running
locally, or OPENAI_API_KEY + LLM_PROVIDER=openai) and is opt-in, same
convention as the TEST_DATABASE_URL-gated integration test in
tests/test_application_status_constraint.py.

Run it:
    RUN_GOLDEN_EVAL=1 uv run pytest tests/test_interview_scoring_golden.py -v

Gate scoring-prompt changes with it: touch _INTERVIEW_SCORE_PROMPT in
app/llm/ollama.py or the tier/weight tables in app/llm/rubric.py, then run
this before merging to catch drift the pure rubric-math unit tests
(tests/test_interview_scoring.py) can't see.
"""

from __future__ import annotations

import os

import pytest

from app.llm.rubric import INTERVIEW_WEIGHTS, points_to_tier, tier_distance
from tests.golden.fixtures import GOLDEN_CASES

_RUN_GOLDEN_EVAL = os.environ.get("RUN_GOLDEN_EVAL")

pytestmark = pytest.mark.skipif(
    not _RUN_GOLDEN_EVAL,
    reason="RUN_GOLDEN_EVAL not set; golden eval needs a live LLM (Ollama/OpenAI) — opt-in only",
)


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=[c.id for c in GOLDEN_CASES])
async def test_golden_case_dimension_tiers(case) -> None:  # noqa: ANN001
    from app.llm.factory import get_llm_client

    llm = get_llm_client()
    result = await llm.score_interview(
        transcript=case.transcript,
        job_title=case.job_title,
        job_description=case.job_description,
        required_skills=case.required_skills,
    )

    errors = []
    for dim in INTERVIEW_WEIGHTS:
        expected = case.expected_tiers[dim]
        actual = points_to_tier(result.dimension_scores[dim])
        distance = tier_distance(expected, actual)
        if distance > 1:
            errors.append(f"  {dim}: expected={expected!r} actual={actual!r} (distance={distance})")

    assert not errors, (
        f"case {case.id!r} drifted beyond ±1 tier:\n"
        + "\n".join(errors)
        + f"\n\ncase notes: {case.notes}"
        + f"\nllm reasoning: {result.reasoning}"
    )
