"""Unit tests for interview rubric math and video upload validation.

These tests are pure-Python — no database, no LLM, no ffmpeg, no MinIO needed.
"""

from __future__ import annotations

import pytest

from app.llm.rubric import (
    INTERVIEW_WEIGHTS,
    TIER_POINTS,
    aggregate_interview,
    interview_tiers_to_points,
)
from app.storage.validator import FileValidationError, validate_video_upload

# ---------------------------------------------------------------------------
# T2: Rubric pure-unit tests
# ---------------------------------------------------------------------------


class TestInterviewWeights:
    def test_weights_sum_to_one(self) -> None:
        total = sum(INTERVIEW_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, f"INTERVIEW_WEIGHTS sum = {total}, expected 1.0"

    def test_all_four_dimensions_present(self) -> None:
        expected = {"technical_accuracy", "answer_relevance", "problem_structure", "communication"}
        assert set(INTERVIEW_WEIGHTS.keys()) == expected


class TestInterviewTiersToPoints:
    def test_all_excellent(self) -> None:
        tiers = {
            "technical_accuracy": "excellent",
            "answer_relevance": "excellent",
            "problem_structure": "excellent",
            "communication": "excellent",
        }
        points = interview_tiers_to_points(tiers)
        assert all(v == TIER_POINTS["excellent"] for v in points.values())

    def test_all_none(self) -> None:
        tiers = {
            "technical_accuracy": "none",
            "answer_relevance": "none",
            "problem_structure": "none",
            "communication": "none",
        }
        points = interview_tiers_to_points(tiers)
        assert all(v == TIER_POINTS["none"] for v in points.values())

    def test_missing_dimension_raises(self) -> None:
        with pytest.raises(ValueError, match="missing interview dimension"):
            interview_tiers_to_points({"technical_accuracy": "strong"})

    def test_unknown_tier_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown score tier"):
            interview_tiers_to_points(
                {
                    "technical_accuracy": "great",  # invalid tier
                    "answer_relevance": "strong",
                    "problem_structure": "partial",
                    "communication": "weak",
                }
            )

    def test_case_insensitive_tier(self) -> None:
        """normalize_tier lowercases, so 'STRONG' → 'strong'."""
        tiers = {
            "technical_accuracy": "STRONG",
            "answer_relevance": "Partial",
            "problem_structure": "WEAK",
            "communication": "none",
        }
        points = interview_tiers_to_points(tiers)
        assert points["technical_accuracy"] == TIER_POINTS["strong"]
        assert points["answer_relevance"] == TIER_POINTS["partial"]


class TestAggregateInterview:
    def test_exact_weighted_score_mixed(self) -> None:
        """Hand-computed reference:
        technical_accuracy = strong  → 78 pts, weight 0.45 → 35.10
        answer_relevance   = partial → 53 pts, weight 0.25 → 13.25
        problem_structure  = weak    → 28 pts, weight 0.18 →  5.04
        communication      = none    → 12 pts, weight 0.12 →  1.44
        total = 54.83 → round → 55
        """
        tiers = {
            "technical_accuracy": "strong",
            "answer_relevance": "partial",
            "problem_structure": "weak",
            "communication": "none",
        }
        points = interview_tiers_to_points(tiers)
        score = aggregate_interview(points)
        # Hand-verified computation
        expected = int(round(78 * 0.45 + 53 * 0.25 + 28 * 0.18 + 12 * 0.12))
        assert score == expected, f"Got {score}, expected {expected}"

    def test_exact_weighted_score_all_excellent(self) -> None:
        """All excellent: 95 * (0.45 + 0.25 + 0.18 + 0.12) = 95 * 1.0 = 95."""
        tiers = {d: "excellent" for d in INTERVIEW_WEIGHTS}
        points = interview_tiers_to_points(tiers)
        assert aggregate_interview(points) == 95

    def test_exact_weighted_score_all_none(self) -> None:
        """All none: 12 * 1.0 = 12."""
        tiers = {d: "none" for d in INTERVIEW_WEIGHTS}
        points = interview_tiers_to_points(tiers)
        assert aggregate_interview(points) == 12

    def test_score_in_valid_range(self) -> None:
        """Any combination must yield 0-100."""
        tiers = {
            "technical_accuracy": "excellent",
            "answer_relevance": "none",
            "problem_structure": "strong",
            "communication": "partial",
        }
        points = interview_tiers_to_points(tiers)
        score = aggregate_interview(points)
        assert 0 <= score <= 100


# ---------------------------------------------------------------------------
# T8: validate_video_upload — pure-Python, no disk, no MinIO
# ---------------------------------------------------------------------------

# Magic byte constants
_WEBM_MAGIC = b"\x1a\x45\xdf\xa3"
_MP4_FTYP = b"\x00\x00\x00\x18ftypisom"  # bytes 0-3 = size, 4-7 = "ftyp"

_150MB = 150 * 1024 * 1024
_1KB = 1024


def _make_webm(extra: int = 64) -> bytes:
    return _WEBM_MAGIC + b"\x00" * extra


def _make_mp4(extra: int = 64) -> bytes:
    # MP4 ftyp box: 4 bytes size + b"ftyp" starting at offset 4
    header = b"\x00\x00\x00\x18" + b"ftyp" + b"isom" + b"\x00" * 4
    return header + b"\x00" * extra


class TestValidateVideoUpload:
    def test_webm_magic_accepted(self) -> None:
        content = _make_webm()
        validate_video_upload("recording.webm", content, _150MB)  # should not raise

    def test_mp4_ftyp_accepted(self) -> None:
        content = _make_mp4()
        validate_video_upload("recording.mp4", content, _150MB)  # should not raise

    def test_txt_extension_rejected(self) -> None:
        with pytest.raises(FileValidationError, match="not allowed"):
            validate_video_upload("file.txt", b"hello world", _150MB)

    def test_pdf_extension_rejected(self) -> None:
        with pytest.raises(FileValidationError, match="not allowed"):
            validate_video_upload("resume.pdf", b"%PDF-1.4 fake", _150MB)

    def test_over_cap_rejected(self) -> None:
        # Create a content reference that is "too large" — we pass bytes here
        # but use a tiny cap so it fails immediately
        content = _make_webm()
        with pytest.raises(FileValidationError, match="exceeds"):
            validate_video_upload("recording.webm", content, 4)  # cap = 4 bytes

    def test_webm_extension_with_mp4_magic_rejected(self) -> None:
        content = _make_mp4()
        with pytest.raises(FileValidationError, match=".webm.*magic"):
            validate_video_upload("recording.webm", content, _150MB)

    def test_mp4_extension_with_webm_magic_rejected(self) -> None:
        content = _make_webm()
        with pytest.raises(FileValidationError, match=".mp4.*magic"):
            validate_video_upload("recording.mp4", content, _150MB)

    def test_no_extension_rejected(self) -> None:
        with pytest.raises(FileValidationError, match="not allowed"):
            validate_video_upload("recording", _make_webm(), _150MB)

    def test_garbage_bytes_rejected(self) -> None:
        with pytest.raises(FileValidationError):
            validate_video_upload("recording.webm", b"\x00\x01\x02\x03" * 10, _150MB)

    def test_file_path_variant_webm(self, tmp_path) -> None:
        """validate_video_upload also accepts a file path (for worker use)."""
        p = tmp_path / "clip.webm"
        p.write_bytes(_make_webm(extra=512))
        validate_video_upload("clip.webm", str(p), _150MB)  # should not raise

    def test_file_path_variant_over_cap(self, tmp_path) -> None:
        p = tmp_path / "clip.webm"
        data = _make_webm(extra=512)
        p.write_bytes(data)
        with pytest.raises(FileValidationError, match="exceeds"):
            validate_video_upload("clip.webm", str(p), 4)
