from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.comparisons.utils import to_ten_scale


@dataclass
class TierAssignment:
    mode: Literal["tiered", "qualified_only"]
    cut_rating: float | None
    # (row, tier) pairs in descending-score stable order
    entries: list[tuple[Any, Literal["S", "A", "B", "F"] | None]] = field(
        default_factory=list
    )


def assign_tiers(
    rows: list[Any],
    target: int | None,
    threshold: float,
) -> TierAssignment:
    """Assign S/A/B/F tiers to scored rows.

    rows    objects with .overall_score (int), .updated_at (datetime), .candidate_id (uuid)
    target  recruiter seat count; None → qualified_only mode
    threshold  minimum precise score (0–10) to qualify; below → F
    """
    ordered = sorted(
        rows,
        key=lambda r: (
            -r.overall_score,
            -r.updated_at.timestamp(),
            str(r.candidate_id),
        ),
    )

    def precise(r: Any) -> float:
        return r.overall_score / 10

    def rating(r: Any) -> float:
        return to_ten_scale(r.overall_score)  # type: ignore[return-value]

    f_rows = [r for r in ordered if precise(r) < threshold]
    qualified = [r for r in ordered if precise(r) >= threshold]

    if target is None:
        return TierAssignment(
            mode="qualified_only",
            cut_rating=None,
            entries=[(r, None) for r in qualified] + [(r, "F") for r in f_rows],
        )

    if target >= len(qualified):
        return TierAssignment(
            mode="tiered",
            cut_rating=None,
            entries=[(r, "S") for r in qualified] + [(r, "F") for r in f_rows],
        )

    cut = rating(qualified[target - 1])
    tier_entries: list[tuple[Any, Literal["S", "A", "B", "F"] | None]] = []
    for r in qualified:
        r_rating = rating(r)
        t: Literal["S", "A", "B", "F"] = (
            "S" if r_rating > cut else ("A" if r_rating == cut else "B")
        )
        tier_entries.append((r, t))
    tier_entries.extend((r, "F") for r in f_rows)
    return TierAssignment(mode="tiered", cut_rating=cut, entries=tier_entries)
