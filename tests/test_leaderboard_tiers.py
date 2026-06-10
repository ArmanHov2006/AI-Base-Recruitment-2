"""Tests for S/A/B/F leaderboard tier assignment (PRD §11)."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.comparisons.constants import DEFAULT_THRESHOLD_SCORE
from app.comparisons.tiering import assign_tiers
from app.comparisons.utils import to_ten_scale


def _row(overall_score: int, ts: float = 0.0, cid: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        overall_score=overall_score,
        updated_at=datetime.fromtimestamp(ts, tz=timezone.utc),
        candidate_id=uuid.UUID(cid) if cid else uuid.uuid4(),
    )


# ---------------------------------------------------------------------------
# Tier logic
# ---------------------------------------------------------------------------

def test_4_bodies_at_cut_all_land_in_A() -> None:
    # target=2 — cut is at index 1; rows with same rating overflow into A
    # scores: 90, 80, 80, 80 → qualified all (threshold=7.5)
    # rating(80) = to_ten_scale(80) = 8.0; rating(90) = 9.0
    # cut = rating(qualified[1]) = 8.0
    # rank0: 9.0 > 8.0 → S
    # ranks 1,2,3: 8.0 == 8.0 → A
    rows = [_row(90), _row(80), _row(80), _row(80)]
    a = assign_tiers(rows, target=2, threshold=DEFAULT_THRESHOLD_SCORE)
    assert a.mode == "tiered"
    assert a.cut_rating == 8.0
    # The 90-score row is S
    s_entries = [(r, t) for r, t in a.entries if t == "S"]
    a_entries = [(r, t) for r, t in a.entries if t == "A"]
    assert len(s_entries) == 1
    assert s_entries[0][0].overall_score == 90
    assert len(a_entries) == 3
    assert all(r.overall_score == 80 for r, _ in a_entries)


def test_all_below_threshold_all_F() -> None:
    # threshold=7.5, target=10, all scores 40-60 → precise 4.0-6.0 < 7.5 → all F
    rows = [_row(s) for s in [60, 55, 50, 45, 40]]
    a = assign_tiers(rows, target=10, threshold=7.5)
    assert a.mode == "tiered"
    assert all(t == "F" for _, t in a.entries)
    assert a.cut_rating is None


def test_target_gte_qualified_all_S() -> None:
    rows = [_row(s) for s in [90, 85, 80]]
    a = assign_tiers(rows, target=5, threshold=DEFAULT_THRESHOLD_SCORE)
    assert a.mode == "tiered"
    assert a.cut_rating is None
    assert all(t == "S" for _, t in a.entries)


def test_target_none_qualified_only_mode() -> None:
    rows = [_row(90), _row(80), _row(50)]
    a = assign_tiers(rows, target=None, threshold=DEFAULT_THRESHOLD_SCORE)
    assert a.mode == "qualified_only"
    tiers = [(r.overall_score, t) for r, t in a.entries]
    assert (50, "F") in tiers
    assert (90, None) in tiers
    assert (80, None) in tiers


def test_default_threshold_is_7_5() -> None:
    assert DEFAULT_THRESHOLD_SCORE == 7.5


def test_everyone_at_one_rating_all_A() -> None:
    # All have overall_score=80 → rating 8.0; target=2
    # cut = rating(qualified[1]) = 8.0; all == cut → all A
    rows = [_row(80), _row(80), _row(80), _row(80)]
    a = assign_tiers(rows, target=2, threshold=DEFAULT_THRESHOLD_SCORE)
    assert a.mode == "tiered"
    assert all(t == "A" for _, t in a.entries)
    assert a.cut_rating == 8.0


def test_raw_score_tie_deterministic_order() -> None:
    # Two rows with identical overall_score; one updated later → it ranks first
    cid_a = uuid.UUID("00000000-0000-0000-0000-000000000001")
    cid_b = uuid.UUID("00000000-0000-0000-0000-000000000002")
    row_early = SimpleNamespace(
        overall_score=80,
        updated_at=datetime.fromtimestamp(1000.0, tz=timezone.utc),
        candidate_id=cid_a,
    )
    row_late = SimpleNamespace(
        overall_score=80,
        updated_at=datetime.fromtimestamp(2000.0, tz=timezone.utc),
        candidate_id=cid_b,
    )
    a = assign_tiers([row_early, row_late], target=1, threshold=DEFAULT_THRESHOLD_SCORE)
    # updated_at DESC → row_late comes first
    assert a.entries[0][0].candidate_id == cid_b
    assert a.entries[1][0].candidate_id == cid_a


def test_pdf_api_threshold_consistency() -> None:
    # overall_score=73 → precise = 7.3; threshold=7.5 → NOT qualified → F
    # (same logic used by PDF export endpoint)
    row = _row(73)
    a = assign_tiers([row], target=10, threshold=7.5)
    assert a.entries[0][1] == "F"


def test_empty_board() -> None:
    a = assign_tiers([], target=3, threshold=DEFAULT_THRESHOLD_SCORE)
    assert a.entries == []
    assert a.cut_rating is None


def test_target_exact_qualified_count_all_S() -> None:
    rows = [_row(90), _row(85), _row(80)]
    a = assign_tiers(rows, target=3, threshold=DEFAULT_THRESHOLD_SCORE)
    assert a.mode == "tiered"
    assert all(t == "S" for _, t in a.entries)
    assert a.cut_rating is None


def test_mixed_qualified_and_F() -> None:
    # target=1 → cut = rating(qualified[0]) = to_ten_scale(90) = 9.0
    # 90: 9.0 == cut → A; 75: 7.5 < cut → B; 74: precise 7.4 < 7.5 → F
    rows = [_row(90), _row(75), _row(74)]
    a = assign_tiers(rows, target=1, threshold=7.5)
    tier_by_score = {r.overall_score: t for r, t in a.entries}
    assert tier_by_score[90] == "A"
    assert tier_by_score[75] == "B"
    assert tier_by_score[74] == "F"


def test_to_ten_scale_boundary() -> None:
    # 75 → 7.5 exactly (qualifies at threshold 7.5)
    assert to_ten_scale(75) == 7.5
    # 74 → 7.5? Let's check: 74/10*2 = 14.8 → round(14.8) = 15 → 7.5
    # 73 → 73/10*2 = 14.6 → round(14.6) = 15 → 7.5
    # 70 → 7.0
    assert to_ten_scale(70) == 7.0
    # precise(74) = 7.4 < 7.5 → F, but rating(74) = 7.5
    # This tests the precise vs rating split
    row = _row(74)
    a = assign_tiers([row], target=1, threshold=7.5)
    assert a.entries[0][1] == "F"  # precise 7.4 < 7.5 → F despite display 7.5
