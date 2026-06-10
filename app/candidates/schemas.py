import math
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.parser.schemas import Education, WorkExperience, _normalize_skill


def _normalize_skills_list(v: list[str] | None) -> list[str] | None:
    if v is None:
        return None
    seen: dict[str, None] = {}
    for s in v:
        ns = _normalize_skill(s)
        if ns:
            seen.setdefault(ns, None)
    return list(seen)


class CreateCandidateRequest(BaseModel):
    file_id: str
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    skills: list[str] = []
    years_experience: float | None = None
    education: list[Education] = []
    work_experiences: list[WorkExperience] = []
    location: str | None = None
    seniority: str | None = None
    summary: str | None = None
    desired_position: str | None = None
    certifications: list[str] = []
    languages: list[str] = []
    linkedin_url: str | None = None
    github_url: str | None = None
    desired_salary: int | None = None

    @field_validator('skills', mode='after')
    @classmethod
    def _norm_skills(cls, v: list[str]) -> list[str]:
        return _normalize_skills_list(v) or []


class UpdateCandidateRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    skills: list[str] | None = None

    @field_validator('skills', mode='after')
    @classmethod
    def _norm_skills(cls, v: list[str] | None) -> list[str] | None:
        return _normalize_skills_list(v)
    years_experience: float | None = None
    education: list[Education] | None = None
    work_experiences: list[WorkExperience] | None = None
    location: str | None = None
    seniority: str | None = None
    summary: str | None = None
    desired_position: str | None = None
    certifications: list[str] | None = None
    languages: list[str] | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    desired_salary: int | None = None


class CandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_id: str
    status: str
    name: str | None
    email: str | None
    phone: str | None
    skills: list[str]
    years_experience: float | None
    education: list[Education]
    work_experiences: list[WorkExperience]
    location: str | None
    seniority: str | None
    summary: str | None
    desired_position: str | None
    certifications: list[str]
    languages: list[str]
    linkedin_url: str | None
    github_url: str | None
    desired_salary: int | None
    photo_url: str | None = None
    current_resume_version: int | None = None
    created_at: datetime
    deleted_at: datetime | None


class FacetBucket(BaseModel):
    """A single aggregation bucket returned by Elasticsearch."""
    value: str
    count: int


class SearchFacets(BaseModel):
    """Facet counts returned alongside ES search results.

    Fields are empty lists when Elasticsearch is not configured (Postgres fallback).
    """
    seniority: list[FacetBucket] = []
    skills: list[FacetBucket] = []
    location: list[FacetBucket] = []
    status: list[FacetBucket] = []
    resume_language: list[FacetBucket] = []


class CandidateListResponse(BaseModel):
    items: list[CandidateResponse]
    total: int
    page: int
    size: int
    pages: int
    facets: SearchFacets = SearchFacets()

    @classmethod
    def build(
        cls,
        items: list[CandidateResponse],
        total: int,
        page: int,
        size: int,
        facets: dict | None = None,
    ) -> "CandidateListResponse":
        parsed_facets = SearchFacets()
        if facets:
            parsed_facets = SearchFacets(
                seniority=[FacetBucket(**b) for b in facets.get("seniority", [])],
                skills=[FacetBucket(**b) for b in facets.get("skills", [])],
                location=[FacetBucket(**b) for b in facets.get("location", [])],
                status=[FacetBucket(**b) for b in facets.get("status", [])],
                resume_language=[FacetBucket(**b) for b in facets.get("resume_language", [])],
            )
        return cls(
            items=items,
            total=total,
            page=page,
            size=size,
            pages=max(1, math.ceil(total / size)),
            facets=parsed_facets,
        )
