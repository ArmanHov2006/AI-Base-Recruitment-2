"""Tests for the deterministic scoring rubric (tier -> points -> overall)."""
import pytest

from app.comparisons.utils import to_ten_scale
from app.llm.rubric import (
    SCORE_TIERS,
    SCORE_WEIGHTS,
    TIER_POINTS,
    aggregate,
    apply_local_bonus,
    is_local_hire,
    normalize_tier,
    points_to_tier,
    tier_distance,
    tiers_to_dimension_points,
)


def test_weights_sum_to_one() -> None:
    assert abs(sum(SCORE_WEIGHTS.values()) - 1.0) < 1e-9


def test_normalize_tier_is_case_and_space_insensitive() -> None:
    assert normalize_tier("  Excellent ") == "excellent"
    assert normalize_tier("STRONG") == "strong"


def test_normalize_tier_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        normalize_tier("amazing")


def test_normalize_tier_rejects_raw_number() -> None:
    # The whole point: the LLM must not emit numbers anymore.
    with pytest.raises(ValueError):
        normalize_tier(85)


def test_tiers_to_points_maps_every_dimension() -> None:
    tiers = {
        "skills_match": "excellent",
        "experience_level": "strong",
        "seniority_fit": "partial",
        "education": "none",
    }
    points = tiers_to_dimension_points(tiers)
    assert points == {
        "skills_match": TIER_POINTS["excellent"],
        "experience_level": TIER_POINTS["strong"],
        "seniority_fit": TIER_POINTS["partial"],
        "education": TIER_POINTS["none"],
    }


def test_tiers_to_points_requires_all_dimensions() -> None:
    with pytest.raises(ValueError):
        tiers_to_dimension_points({"skills_match": "excellent"})


def test_aggregate_all_excellent_is_95() -> None:
    points = tiers_to_dimension_points(dict.fromkeys(SCORE_WEIGHTS, "excellent"))
    assert aggregate(points) == 95


def test_aggregate_all_none_is_12() -> None:
    points = tiers_to_dimension_points(dict.fromkeys(SCORE_WEIGHTS, "none"))
    assert aggregate(points) == 12


def test_aggregate_skills_dominates() -> None:
    # Excellent skills + none elsewhere should still clear the midpoint,
    # because skills_match carries the majority weight.
    tiers = {
        "skills_match": "excellent",
        "experience_level": "none",
        "seniority_fit": "none",
        "education": "none",
    }
    overall = aggregate(tiers_to_dimension_points(tiers))
    # 95*0.55 + 12*0.45 = 52.25 + 5.4 = 57.65 -> 58
    assert overall == 58


@pytest.mark.parametrize(
    "location,expected",
    [
        ("Yerevan", True),
        ("  YEREVAN  ", True),
        ("Armenia", True),
        ("Yerevan, Armenia", True),
        ("երևան", True),
        ("Ереван", True),
        ("Tbilisi", False),
        ("New York", False),
        (None, False),
        ("", False),
    ],
)
def test_is_local_hire(location: str | None, expected: bool) -> None:
    assert is_local_hire(location) is expected


_BASE_TIERS = {
    "skills_match": "partial",
    "experience_level": "strong",
    "seniority_fit": "excellent",
    "education": "weak",
}


def test_apply_local_bonus_bumps_partial_to_strong_for_local() -> None:
    result = apply_local_bonus(_BASE_TIERS, "Yerevan")
    assert result["skills_match"] == "strong"


def test_apply_local_bonus_no_change_for_non_local() -> None:
    result = apply_local_bonus(_BASE_TIERS, "Tbilisi")
    assert result["skills_match"] == "partial"


def test_apply_local_bonus_does_not_bump_already_strong() -> None:
    tiers = {**_BASE_TIERS, "skills_match": "strong"}
    result = apply_local_bonus(tiers, "Yerevan")
    assert result["skills_match"] == "strong"


def test_apply_local_bonus_does_not_bump_weak() -> None:
    tiers = {**_BASE_TIERS, "skills_match": "weak"}
    result = apply_local_bonus(tiers, "Yerevan")
    assert result["skills_match"] == "weak"


def test_apply_local_bonus_does_not_mutate_input() -> None:
    original = dict(_BASE_TIERS)
    apply_local_bonus(_BASE_TIERS, "Yerevan")
    assert _BASE_TIERS == original


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, None),
        (0, 0.0),
        (100, 10.0),
        (84, 8.5),   # 8.4 -> nearest 0.5
        (82, 8.0),   # 8.2 -> nearest 0.5
        (77, 7.5),   # 7.7*2=15.4 -> round 15 -> 7.5
        (75, 7.5),
        (58, 6.0),   # 5.8 -> 6.0
    ],
)
def test_to_ten_scale(raw: int | None, expected: float | None) -> None:
    assert to_ten_scale(raw) == expected


@pytest.mark.parametrize("tier", SCORE_TIERS)
def test_points_to_tier_round_trips_every_tier(tier: str) -> None:
    assert points_to_tier(TIER_POINTS[tier]) == tier


def test_points_to_tier_rejects_unknown_points() -> None:
    with pytest.raises(ValueError):
        points_to_tier(50)


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("excellent", "excellent", 0),
        ("excellent", "strong", 1),
        ("excellent", "none", 4),
        ("weak", "strong", 2),
        ("STRONG", " weak ", 2),  # normalize_tier handles case/space
    ],
)
def test_tier_distance(a: str, b: str, expected: int) -> None:
    assert tier_distance(a, b) == expected
