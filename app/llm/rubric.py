"""Deterministic scoring rubric — the formula half of the hybrid scorer.

The LLM judges each dimension into a fixed, anchored *tier* (it is good at
coarse, behaviorally-anchored classification and bad at picking precise numbers
on a 0-100 scale — broad scales trigger central-tendency clustering). This
module owns the deterministic half: mapping tiers to points and aggregating
them with auditable, tunable weights.

This mirrors how production AI ATS systems (e.g. Eightfold) work: an ML/LLM
layer produces explainable signals, a deterministic model aggregates them so
the final number is stable, reproducible, and defensible under bias audits
(NYC Local Law 144 and similar). Retune weights here — never in the prompt.
"""

from __future__ import annotations

# Ordered best→worst. Used to validate LLM output and to drive the prompt enum.
SCORE_TIERS: tuple[str, ...] = ("excellent", "strong", "partial", "weak", "none")

# Tier → representative points (0-100). Band midpoints, anchored to the rubric
# text in the scoring prompt. Coarse on purpose: the LLM only has to pick a
# bucket, not a precise integer.
TIER_POINTS: dict[str, int] = {
    "excellent": 95,  # reserved for standout evidence, not just qualified
    "strong": 78,  # qualified with real project evidence
    "partial": 53,  # partially qualified or skills without evidence
    "weak": 28,  # significant gaps
    "none": 12,  # essentially unqualified
}

# The four scored dimensions and their aggregation weights. MUST sum to 1.0.
# Education intentionally tiny — relevance has fallen for most modern roles.
# Tune these to change scoring policy without touching the LLM prompt.
SCORE_WEIGHTS: dict[str, float] = {
    "skills_match": 0.55,
    "experience_level": 0.30,
    "seniority_fit": 0.12,
    "education": 0.03,
}

assert abs(sum(SCORE_WEIGHTS.values()) - 1.0) < 1e-9, "SCORE_WEIGHTS must sum to 1.0"


# Canonical local-hire location tokens (lowercase). Covers Latin, Armenian script, and Cyrillic.
_LOCAL_HIRE_TOKENS: frozenset[str] = frozenset({"armenia", "yerevan", "երևան", "ереван"})

# Maps tier name → index in SCORE_TIERS (0=best). Used for the one-step bump.
_TIER_INDEX: dict[str, int] = {t: i for i, t in enumerate(SCORE_TIERS)}


def is_local_hire(location: str | None) -> bool:
    """True when the candidate location contains a recognized local-hire token."""
    if not location:
        return False
    normalized = location.lower().strip()
    return any(token in normalized for token in _LOCAL_HIRE_TOKENS)


def apply_local_bonus(tiers: dict[str, str], location: str | None) -> dict[str, str]:
    """Bump skills_match one tier toward 'excellent' when the candidate is a
    local hire AND skills_match is exactly 'partial' (adjacent to 'strong').
    Applying the bonus only at the partial→strong boundary keeps the policy
    narrow, auditable, and consistent with NYC Local Law 144-style defensibility."""
    if not is_local_hire(location):
        return tiers
    tier = normalize_tier(tiers.get("skills_match", "none"))
    if tier != "partial":
        return tiers
    bumped = SCORE_TIERS[_TIER_INDEX[tier] - 1]
    return {**tiers, "skills_match": bumped}


def normalize_tier(value: object) -> str:
    """Coerce an LLM tier label to a canonical tier. Raises on unknown values."""
    tier = str(value).strip().lower()
    if tier not in TIER_POINTS:
        raise ValueError(f"unknown score tier: {value!r} (expected one of {SCORE_TIERS})")
    return tier


def tiers_to_dimension_points(tiers: dict) -> dict[str, int]:
    """Map a {dimension: tier} dict to {dimension: points}. Every weighted
    dimension must be present."""
    points: dict[str, int] = {}
    for dim in SCORE_WEIGHTS:
        if dim not in tiers:
            raise ValueError(f"missing dimension in LLM output: {dim!r}")
        points[dim] = TIER_POINTS[normalize_tier(tiers[dim])]
    return points


def aggregate(dimension_points: dict[str, int]) -> int:
    """Weighted aggregation of dimension points → overall 0-100 integer."""
    overall = sum(dimension_points[dim] * w for dim, w in SCORE_WEIGHTS.items())
    return int(round(overall))


# ---------------------------------------------------------------------------
# Interview scoring — dimensions + weights
# ---------------------------------------------------------------------------

# Interview scoring dimensions + weights. MUST sum to 1.0.
INTERVIEW_WEIGHTS: dict[str, float] = {
    "technical_accuracy": 0.45,
    "answer_relevance": 0.25,
    "problem_structure": 0.18,
    "communication": 0.12,
}

assert abs(sum(INTERVIEW_WEIGHTS.values()) - 1.0) < 1e-9, "INTERVIEW_WEIGHTS must sum to 1.0"


def interview_tiers_to_points(tiers: dict) -> dict[str, int]:
    """Map {dimension: tier} → {dimension: points} for interview dimensions.
    Every weighted dimension must be present. Reuses TIER_POINTS + normalize_tier."""
    points: dict[str, int] = {}
    for dim in INTERVIEW_WEIGHTS:
        if dim not in tiers:
            raise ValueError(f"missing interview dimension in LLM output: {dim!r}")
        points[dim] = TIER_POINTS[normalize_tier(tiers[dim])]
    return points


def aggregate_interview(dimension_points: dict[str, int]) -> int:
    """Weighted aggregation of interview dimension points → 0-100 integer."""
    overall = sum(dimension_points[dim] * w for dim, w in INTERVIEW_WEIGHTS.items())
    return int(round(overall))


# Reverse of TIER_POINTS. Exact — every value in TIER_POINTS is unique, so this
# round-trips losslessly. Used to recover the tier an LLM chose once its
# dimension points have been stored (e.g. golden-set eval, audit trails).
_POINTS_TO_TIER: dict[int, str] = {v: k for k, v in TIER_POINTS.items()}


def points_to_tier(points: int) -> str:
    """Inverse of TIER_POINTS: recover the tier label from its point value."""
    try:
        return _POINTS_TO_TIER[points]
    except KeyError:
        raise ValueError(f"unknown score points: {points!r} (expected one of {list(_POINTS_TO_TIER)})") from None


def tier_distance(a: str, b: str) -> int:
    """Absolute distance between two tiers on the SCORE_TIERS ladder (0 = exact match)."""
    return abs(_TIER_INDEX[normalize_tier(a)] - _TIER_INDEX[normalize_tier(b)])
