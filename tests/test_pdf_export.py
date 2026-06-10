"""Tests for B3: PDF export endpoints."""
from unittest.mock import MagicMock


def test_build_candidate_pdf_returns_bytes() -> None:
    from app.export.pdf import build_candidate_pdf

    candidate = MagicMock()
    candidate.name = "Jane Doe"
    candidate.email = "jane@example.com"
    candidate.phone = None
    candidate.location = "Yerevan"
    candidate.seniority = "senior"
    candidate.years_experience = 5.0
    candidate.desired_position = "Backend Engineer"
    candidate.desired_salary = None
    candidate.linkedin_url = None
    candidate.github_url = None
    candidate.summary = "Experienced Python developer."
    candidate.skills = ["Python", "FastAPI"]
    candidate.certifications = ["AWS Certified"]
    candidate.languages = ["English", "Armenian"]
    candidate.work_experiences = [
        {
            "title": "Engineer",
            "company": "Acme",
            "start_date": "2020-01",
            "end_date": "present",
            "description": "Built APIs.",
        }
    ]
    candidate.education = [
        {"degree": "BSc CS", "institution": "YSU", "year": 2019}
    ]

    result = build_candidate_pdf(candidate)
    assert isinstance(result, bytes)
    assert len(result) > 100
    assert result[:4] == b"%PDF"


def test_build_analytics_pdf_returns_bytes() -> None:
    from app.export.pdf import build_analytics_pdf

    overview = MagicMock()
    overview.total_candidates = 10
    overview.total_jobs = 3
    overview.total_applications = 15
    overview.applications_by_status = {"applied": 10, "hired": 2}

    result = build_analytics_pdf(overview, None, None)
    assert isinstance(result, bytes)
    assert result[:4] == b"%PDF"
