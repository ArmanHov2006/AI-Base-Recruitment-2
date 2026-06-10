from dataclasses import dataclass, field
from typing import Protocol

from app.parser.schemas import CandidateData


class ScoringResult:
    def __init__(
        self,
        overall_score: int,
        dimension_scores: dict,
        reasoning: str,
        skill_breakdown: dict | None = None,
    ) -> None:
        self.overall_score = overall_score
        self.dimension_scores = dimension_scores
        self.reasoning = reasoning
        self.skill_breakdown = skill_breakdown


@dataclass
class VerdictResult:
    recommended_candidate_id: str  # name/label of top pick
    decision: str  # strong | moderate | weak
    decision_tags: list  # 3-5 short noun phrases
    hire_verdicts: dict  # {candidate_label: "hire"|"consider"|"reject"}
    summary: str  # 2-3 sentence overall recommendation


@dataclass
class TiebreakerResult:
    # Each item: {name, dimension_ratings: {dim: {rating, notes}}, reasoning}
    # Ordered best-fit first.
    results: list[dict] = field(default_factory=list)
    summary: str = ""


class LLMTimeoutError(Exception): ...


class LLMParseError(Exception): ...


class LLMClient(Protocol):
    async def extract(self, resume_text: str, job_context: str | None = None) -> CandidateData: ...

    async def score_candidate(
        self,
        candidate: CandidateData,
        job_title: str,
        job_description: str | None,
        required_skills: list[str],
        required_seniority: str | None = None,
    ) -> ScoringResult: ...

    async def compare_candidates(
        self,
        candidates: list[tuple[str, CandidateData]],
        job_title: str,
        job_description: str | None,
        required_skills: list[str],
        required_seniority: str | None = None,
    ) -> dict: ...

    async def suggest_interview_questions(
        self,
        candidate: CandidateData,
        job_title: str,
        job_description: str | None,
        required_skills: list[str],
    ) -> list[str]: ...

    async def tiebreaker_analysis(
        self,
        candidates: list[tuple[str, str, CandidateData]],
        job_title: str,
        job_description: str | None,
        required_skills: list[str],
        required_seniority: str | None,
        dimensions: list[str],
        slots_remaining: int,
    ) -> TiebreakerResult: ...
