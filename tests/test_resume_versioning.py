"""Tests for B4: resume versioning table and model."""
import uuid
from datetime import datetime, timezone

from app.resumes.models import CandidateResume


def test_candidate_resume_model_has_version_field() -> None:
    resume = CandidateResume(
        id=uuid.uuid4(),
        candidate_id=uuid.uuid4(),
        file_id="test-file-id",
        version=1,
        parsed_at=datetime.now(timezone.utc),
    )
    assert resume.version == 1
    assert resume.file_id == "test-file-id"


def test_candidate_resume_model_tablename() -> None:
    assert CandidateResume.__tablename__ == "candidate_resumes"


def test_candidate_model_has_current_resume_version() -> None:
    from app.candidates.models import Candidate
    assert hasattr(Candidate, "current_resume_version")


def test_candidate_model_has_photo_url() -> None:
    from app.candidates.models import Candidate
    assert hasattr(Candidate, "photo_url")
