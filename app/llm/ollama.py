import asyncio
import datetime
import json
from collections.abc import AsyncGenerator

import httpx
from ollama import AsyncClient
from pydantic import ValidationError

from app.config import settings
from app.llm.base import LLMParseError, LLMTimeoutError, ScoringResult, TiebreakerResult, VerdictResult
from app.llm.rubric import aggregate, apply_local_bonus, tiers_to_dimension_points
from app.parser.schemas import CandidateData

_EXTRACT_PROMPT = """\
You are a resume parser. The resume text below may be truncated — extract \
what is available and do not fabricate missing information. \
Return ONLY valid JSON — no markdown, no extra text.

Multi-language rules (Armenian / Russian / English):
- The resume may be written in Armenian (Հայերեն), Russian (Русский), English, or a mix.
- Extract ALL fields correctly regardless of the source language.
- Normalize the OUTPUT to English canonical form:
  - skills: always in English (e.g. "Python", "React", "Project Management")
  - seniority: always one of the English labels: junior | mid | senior | lead
  - titles/roles: translate to their standard English equivalent where unambiguous
- Preserve the ORIGINAL language text in the "summary" and each work_experience "description" field.
- Names, locations, company names, and institution names: transliterate to Latin script using standard rules; do NOT translate them.
- If a skill appears in the resume in another language (e.g. Armenian "Ծրագրավորում" = Programming, Russian "Управление проектами" = Project Management), map it to the canonical English skill name.

Return this exact JSON structure (use null for missing scalars, [] for missing arrays):
{{
  "name": "candidate full name or null",
  "email": "email address or null",
  "phone": "phone number or null",
  "location": "city/country or null",
  "summary": "1-2 sentence professional summary or null",
  "seniority": "one of: junior, mid, senior, lead — or null",
  "work_experiences": [
    {{
      "company": "employer name",
      "role": "job title or null",
      "start_date": "YYYY-MM",
      "end_date": "YYYY-MM or null",
      "achievements": ["bullet 1", "bullet 2"],
      "description": "free-form role description or null"
    }}
  ],
  "years_experience": "<float: sum of work durations in years, or best estimate from seniority/role count if dates are unclear — never 0 for candidates with visible work history>",
  "skills": ["SkillName (proficiency_level)", "..."],
  "education": [
    {{"institution": "school name", "degree": "degree title or null", "year": 2020}}
  ],
  "desired_position": "job title or role the candidate is seeking, or null"
}}

Rules for work_experiences:
- ONE entry per paid employment or internship; if the same company appears twice for separate contracts, create two entries
- Universities, schools, bootcamps, and courses belong in `education` ONLY — NEVER in `work_experiences`
- Dates MUST be "YYYY-MM" strings (e.g. "2021-03"). If only a year is shown, use "YYYY-01"
- end_date is null if the role is ongoing/present
- For each role, extract up to 3 key achievements or responsibilities into the `achievements` array as concise strings

Rules for education:
- Include all formal schooling: universities, colleges, bootcamps, certifications

Rules for years_experience:
- COUNT only paid employment and internships in work_experiences; DO NOT COUNT education or training
- For ongoing roles (end_date is null) count up to today ({today})
- SUM duration of all roles in months, divide by 12, round to 1 decimal
- If date information is ambiguous or partially missing (e.g. "? – present", no start year), estimate from seniority level and number of roles: junior≈1, mid≈3, senior≈6, lead≈10 years; never output 0.0 for a candidate who clearly has work history
- If no work experience at all, return 0.0

Rules for seniority (infer from years of experience AND role titles — title takes priority):
- junior: 0-2 years OR entry-level titles (associate, junior, trainee, intern)
- mid: 3-5 years OR titles without senior/lead prefix (developer, analyst, engineer)
- senior: 6-9 years OR titles with "senior", "principal", "specialist"
- lead: 10+ years OR titles with "lead", "head of", "manager", "director", "VP", "architect"

Rules for skills (tag each skill with proficiency depth):
- Format exactly as: "SkillName (level)" where level is one of: familiar | proficient | expert
- familiar: mentioned once, brief exposure, or described as "familiar with" / "basic knowledge of"
- proficient: used across multiple roles or 1-3 years consistent use
- expert: primary skill across 3+ years, or explicitly described as expert/advanced/specialist
- Normalize synonyms to canonical form: JS → JavaScript, k8s → Kubernetes, ML → Machine Learning
- Example output: ["Python (expert)", "Docker (proficient)", "Excel (familiar)", "React (expert)"]
{job_context_block}
<resume>
{text}
</resume>"""

_JOB_CONTEXT_BLOCK = """\

--- ROLE CONTEXT ---
You are extracting this resume for the following position. Pay extra attention to \
skills, achievements, and experience most relevant to this role. Tag role-relevant \
skills at their full depth even if mentioned only in passing.
Role: {title}
Required skills: {skills}
{description_line}
--- END ROLE CONTEXT ---
"""

_SCORE_PROMPT = """\
You are a recruitment specialist evaluating how well a candidate fits a job opening.
Return ONLY valid JSON — no markdown, no extra text.

For each dimension, pick EXACTLY ONE tier label from this set:
"excellent", "strong", "partial", "weak", "none".
Do NOT output numbers. Do NOT output an "overall_score" — a downstream system
computes the final score from your tiers.

Return this exact JSON structure:
{{
  "dimension_scores": {{
    "skills_match": "<tier>",
    "experience_level": "<tier>",
    "seniority_fit": "<tier>",
    "education": "<tier>"
  }},
  "skill_breakdown": {{
    "<required skill name>": {{
      "level": "<expert|proficient|familiar|none>",
      "evidence": "<one sentence: specific project, role, or achievement that proves depth — or 'listed only, no project evidence'>"
    }}
  }},
  "reasoning": "<3-5 sentences: cite specific project evidence for the top signal, name the biggest gap with evidence, give one concrete hire/pass recommendation>"
}}

--- CALIBRATION — READ BEFORE SCORING ---
You are grading on a RELATIVE scale against a competitive senior talent pool.
Most candidates will fall in the 6.0–8.5 range. Reserve "excellent" only for
candidates with clear standout evidence. A candidate who simply lists the right
skills with no depth evidence is "strong" at best — never "excellent".
Critically: do NOT award "excellent" just because a candidate is qualified.
Qualified = "strong". Standout = "excellent". Weak = "partial" or below.

--- TIER RUBRICS (choose the closest tier per dimension) ---

skills_match (most important dimension):
- excellent: ALL required skills present at expert level AND resume demonstrates
  deep project evidence — production deployments, systems built at scale,
  tech lead ownership, or quantified outcomes (e.g. "reduced latency 40%",
  "model serving 10M users"). Skills listed without supporting project context → "strong" at best.
- strong: ≥70% of required skills at proficient+ level with some project evidence;
  clear that candidate has used these skills in real work, not just listed them
- partial: ~50% of required skills OR skills listed without any supporting work evidence
- weak: <50% of required skills; major gaps in core areas
- none: very few or no required skills
- Treat skill depth tags: "expert" > "proficient" > "familiar" when judging quality of match
- Normalize synonyms: JS = JavaScript, k8s = Kubernetes, ML = Machine Learning
- Apply semantic inference: "React (expert)" implies strong JavaScript; "Django (expert)" implies Python
- Do NOT apply any location-based adjustments — a downstream policy layer handles that

experience_level:
- excellent: domain directly matches AND resume shows measurable impact — must have
  AT LEAST 2 of: tech/team lead role, production ML/software system ownership,
  quantified business outcome, published work or patent, 5+ years in directly
  relevant domain. Years of experience alone without evidence → "strong" at best.
- strong: mostly relevant experience, years close to requirement, solid contributions
  visible in work history but no standout signal
- partial: some transferable experience but significant domain gap or shallow descriptions
- weak: experience exists but mostly unrelated, or very junior for the role
- none: no meaningful work experience or entirely unrelated field

seniority_fit:
- excellent: exact seniority match for the role
- strong: overqualified (e.g. senior applying for junior) — NO penalty, treat as strong
- partial: one level under (e.g. mid applying for senior) — do NOT disqualify; check
  work_experiences for strong project impact or leadership that partially compensates
- weak: borderline two levels under but with exceptional output for their level
- none: two or more levels under with no compensating signals

education:
- excellent: degree in a directly relevant field
- strong: related field or strong bootcamp/certification
- partial: unrelated degree but relevant certifications present
- weak: unrelated education, no certifications
- none: no formal education and entirely unrelated field
- Note: education carries the least weight; do not over-think this dimension

--- JOB ---
Title: {job_title}
Required seniority: {required_seniority}
Required skills: {required_skills}
Description: {job_description}

--- CANDIDATE ---
Name: {name}
Seniority: {seniority}
Years of experience: {years_experience}
Location: {location}
Summary: {summary}

Skills:
{skills}

Work experience:
{work_experiences}

Education:
{education}
"""

_VERDICT_PROMPT = """\
You are a hiring manager selecting the best candidate from a pool. Scores and \
dimension breakdowns are pre-computed — use them to differentiate candidates, \
especially when overall scores are close.
Return ONLY valid JSON — no markdown, no extra text.

Return this exact structure:
{{
  "recommended_candidate": "<name of top candidate>",
  "decision_tags": ["<3-5 short noun phrases>"],
  "hire_verdicts": {{
    "<candidate name>": "<one of: hire, consider, reject>"
  }},
  "summary": "<2-4 sentences: name the top pick, cite the specific dimension or skill advantage that separates them, note the #2 and any key risk>"
}}

Rules:
- hire_verdicts[recommended_candidate] MUST always be "hire"
- If multiple candidates share the same overall score, differentiate by: dimension with highest gap, specific required skills present/absent, seniority fit, experience depth
- If only one candidate: recommended_candidate = that candidate; evaluate absolute fit against the job
- decision_tags examples: "Strong skills match", "Senior experience", "Domain expertise", "Leadership potential", "Local Armenia hire", "Education gap", "Overqualified", "Limited relevant experience", "Dimension edge: skills_match", "Tied on score — skills depth wins"

Required seniority for this role: {required_seniority}
Decision tags to consider (if any): {decision_tags_hint}

--- JOB ---
Title: {job_title}
Required skills: {required_skills}

--- CANDIDATES (overall score out of 100, then per-dimension breakdown) ---
{candidates_block}
"""

_TIEBREAKER_PROMPT = """\
You are a senior recruiter performing a TIEBREAKER analysis. These candidates scored identically \
and are competing for {slots_remaining} remaining position slot(s). Do NOT use overall numeric \
scores to differentiate — focus exclusively on qualitative fit: specific skill depth, relevant \
experience, and role chemistry.

Rate each candidate 1-5 on each dimension (5=exceptional match, 3=meets expectations, 1=poor fit). \
Then rank ALL candidates best-fit-first.

Return ONLY valid JSON — no markdown, no extra text:
{{
  "results": [
    {{
      "name": "<exact candidate name as given>",
      "dimension_ratings": {{
        "<dimension name>": {{"rating": <1-5>, "notes": "<specific evidence: skill/role/company/achievement>"}}
      }},
      "reasoning": "<2-3 sentences comparing this candidate to the others by name>"
    }}
  ],
  "summary": "<3-4 sentences: name the top {slots_remaining} recommended picks, cite the specific differentiators that tipped the decision>"
}}

Rules:
- ALL candidates must appear in "results", ordered best-fit first
- "notes" MUST reference concrete evidence — no vague phrases like "strong background"
- "reasoning" MUST name at least one other candidate by name for comparison
- The top {slots_remaining} entries in "results" are your final recommendations
- Be decisive — if close, pick on the dimension most critical to THIS role

--- JOB ---
Title: {job_title}
Required seniority: {required_seniority}
Required skills: {required_skills}
Description: {job_description}

--- EVALUATION DIMENSIONS ---
{dimensions_block}

--- BORDERLINE CANDIDATES ---
{candidates_block}
"""

_COMPARE_PROMPT = """\
You are a senior recruitment specialist performing a structured comparative analysis \
of candidates for a job opening.
Return ONLY valid JSON — no markdown, no extra text.

Return this exact JSON structure:
{{
  "candidates": [
    {{
      "name": "<candidate name>",
      "strengths": ["<specific strength referencing a concrete skill, achievement, or years>", "..."],
      "weaknesses": ["<specific gap referencing a missing required skill or experience>", "..."],
      "vs_others": "<one sentence naming which other candidates this person beats and where they fall short>",
      "verdict": "<one-line overall verdict for this candidate>"
    }}
  ],
  "ranking": ["<best fit name>", "<second>", "..."],
  "ranking_rationale": "<one sentence explaining the ordering based on the role requirements>"
}}

Rules:
- Be specific — reference actual skills, job titles, companies, and years from the candidate profiles
- Do NOT write vague phrases like "strong background" or "good fit" — name the specific skill or achievement
- strengths and weaknesses: 2-4 items each
- vs_others MUST name other candidates by name
- ranking must list ALL candidate names, best fit first

--- JOB ---
Title: {job_title}
Required seniority: {required_seniority}
Required skills: {required_skills}
Description: {job_description}

--- CANDIDATES ---
{candidates_block}
"""


def _format_work_experiences(candidate: CandidateData) -> str:
    if not candidate.work_experiences:
        return "  None listed"
    lines = []
    for exp in candidate.work_experiences:
        end = exp.end_date if exp.end_date else "present"
        start = exp.start_date or "?"
        header = f"  - {exp.role or 'Unknown role'} at {exp.company or 'Unknown'} ({start}–{end})"
        lines.append(header)
        for bullet in exp.achievements:
            lines.append(f"      • {bullet}")
        if exp.description:
            lines.append(f"      {exp.description}")
    return "\n".join(lines)


def _format_education(candidate: CandidateData) -> str:
    if not candidate.education:
        return "  None listed"
    lines = []
    for edu in candidate.education:
        year = f" ({edu.year})" if edu.year else ""
        lines.append(f"  - {edu.degree or 'Degree'} at {edu.institution}{year}")
    return "\n".join(lines)


def _derive_companies(candidate: CandidateData) -> list[str]:
    seen: list[str] = []
    for exp in candidate.work_experiences:
        if exp.company and exp.company not in seen:
            seen.append(exp.company)
    return seen


def _candidate_block(label: str, candidate: CandidateData) -> str:
    companies = _derive_companies(candidate)
    return f"""\
[{label}]
Name: {candidate.name or "Unknown"}
Seniority: {candidate.seniority or "unknown"}
Years of experience: {candidate.years_experience or "unknown"}
Location: {candidate.location or "not specified"}
Summary: {candidate.summary or "not provided"}

Skills: {", ".join(candidate.skills) if candidate.skills else "none listed"}

Work experience:
{_format_work_experiences(candidate)}

Education:
{_format_education(candidate)}

Companies: {", ".join(companies) if companies else "none listed"}
"""


class OllamaClient:
    def __init__(self) -> None:
        self._client = AsyncClient(
            host=settings.ollama_base_url,
            timeout=float(settings.llm_timeout_seconds),
        )

    async def warmup(self) -> None:
        """Preload the model into memory so the first real request isn't cold."""
        await asyncio.wait_for(
            self._client.chat(
                model=settings.ollama_model,
                messages=[{"role": "user", "content": "ok"}],
                options={"temperature": 0, "num_predict": 1},
                keep_alive="30m",
            ),
            timeout=float(settings.llm_timeout_seconds),
        )

    async def embed(self, text: str) -> list[float]:
        url = f"{settings.ollama_base_url}/api/embeddings"
        timeout = httpx.Timeout(float(settings.llm_timeout_seconds))
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    url,
                    json={"model": settings.ollama_embed_model, "prompt": text},
                )
                resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LLMParseError(f"Embedding request failed: {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise LLMTimeoutError(f"Embedding request error: {exc}") from exc
        data = resp.json()
        if "embedding" not in data:
            raise LLMParseError(f"Missing 'embedding' key in response: {list(data.keys())}")
        return data["embedding"]  # type: ignore[no-any-return]

    async def _chat(self, content: str) -> str:
        try:
            response = await asyncio.wait_for(
                self._client.chat(
                    model=settings.ollama_model,
                    messages=[{"role": "user", "content": content}],
                    format="json",
                    options={"temperature": 0},
                    keep_alive="30m",
                ),
                timeout=float(settings.llm_timeout_seconds),
            )
        except asyncio.TimeoutError as exc:
            raise LLMTimeoutError(f"LLM timed out after {settings.llm_timeout_seconds}s") from exc
        return response.message.content or ""

    async def _chat_text(self, content: str) -> str:
        """Chat without forcing JSON format — for free-form narrative responses."""
        try:
            response = await asyncio.wait_for(
                self._client.chat(
                    model=settings.ollama_model,
                    messages=[{"role": "user", "content": content}],
                    options={"temperature": 0},
                    keep_alive="30m",
                ),
                timeout=float(settings.llm_timeout_seconds),
            )
        except asyncio.TimeoutError as exc:
            raise LLMTimeoutError(f"LLM timed out after {settings.llm_timeout_seconds}s") from exc
        return response.message.content or ""

    async def chat_stream(
        self, system_prompt: str, user_message: str
    ) -> AsyncGenerator[str, None]:
        """Stream a free-form chat answer token-by-token (no JSON format)."""
        stream = await self._client.chat(
            model=settings.ollama_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            options={"temperature": 0.3},
            keep_alive="30m",
            stream=True,
        )
        async for chunk in stream:
            content = chunk.message.content
            if content:
                yield content

    async def extract(self, resume_text: str, job_context: str | None = None) -> CandidateData:
        job_context_block = ""
        if job_context:
            job_context_block = f"\n--- ROLE CONTEXT ---\n{job_context}\n--- END ROLE CONTEXT ---\n"

        today = datetime.date.today().strftime("%B %Y")
        prompt = _EXTRACT_PROMPT.format(text=resume_text, job_context_block=job_context_block, today=today)

        try:
            return CandidateData.model_validate_json(await self._chat(prompt))
        except (ValidationError, ValueError) as exc:
            raise LLMParseError(f"LLM returned invalid data: {exc}") from exc

    async def score_candidate(
        self,
        candidate: CandidateData,
        job_title: str,
        job_description: str | None,
        required_skills: list[str],
        required_technical_skills: list[str] | None = None,
        required_soft_skills: list[str] | None = None,
        required_seniority: str | None = None,
    ) -> ScoringResult:
        merged_required = list(required_skills or [])
        for s in (required_technical_skills or []) + (required_soft_skills or []):
            if s and s not in merged_required:
                merged_required.append(s)

        prompt = _SCORE_PROMPT.format(
            job_title=job_title,
            required_seniority=required_seniority or "not specified",
            required_skills=", ".join(merged_required) if merged_required else "not specified",
            job_description=job_description or "not provided",
            name=candidate.name or "Unknown",
            seniority=candidate.seniority or "unknown",
            years_experience=candidate.years_experience or "unknown",
            location=candidate.location or "not specified",
            summary=candidate.summary or "not provided",
            skills="\n".join(f"  - {s}" for s in candidate.skills) if candidate.skills else "  none listed",
            work_experiences=_format_work_experiences(candidate),
            education=_format_education(candidate),
        )

        raw = await self._chat(prompt)
        try:
            data = json.loads(raw)
            tiers = data["dimension_scores"]
            # LLM picks anchored tiers; apply any post-LLM policy adjustments
            # (e.g. local-hire bonus) before the deterministic aggregation so
            # policy lives in Python, not in the prompt.
            tiers = apply_local_bonus(tiers, candidate.location)
            dimension_points = tiers_to_dimension_points(tiers)
            overall_score = aggregate(dimension_points)
            skill_breakdown = data.get("skill_breakdown")
            if not isinstance(skill_breakdown, dict):
                skill_breakdown = None
            return ScoringResult(
                overall_score=overall_score,
                dimension_scores=dimension_points,
                reasoning=str(data["reasoning"]),
                skill_breakdown=skill_breakdown,
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise LLMParseError(f"LLM returned invalid scoring data: {exc}") from exc

    async def compare_candidates(
        self,
        candidates: list[tuple[str, CandidateData]],
        job_title: str,
        job_description: str | None,
        required_skills: list[str],
        required_seniority: str | None = None,
    ) -> dict:
        candidates_block = "\n\n".join(
            _candidate_block(label, data) for label, data in candidates
        )

        prompt = _COMPARE_PROMPT.format(
            job_title=job_title,
            required_seniority=required_seniority or "not specified",
            required_skills=", ".join(required_skills) if required_skills else "not specified",
            job_description=job_description or "not provided",
            candidates_block=candidates_block,
        )

        raw = await self._chat(prompt)
        try:
            return json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise LLMParseError(f"LLM returned invalid comparison data: {exc}") from exc

    async def generate_verdict(
        self,
        candidates: list[tuple[str, CandidateData]],
        scores: dict[str, int],  # {candidate_label: overall_score}
        job_title: str,
        required_skills: list[str],
        required_seniority: str | None = None,
        job_decision_tags: list[str] | None = None,
        dimension_scores: dict[str, dict] | None = None,  # {name: {dim: pts}}
    ) -> VerdictResult:
        def _candidate_line(label: str, data: CandidateData) -> str:
            score = scores.get(label, "?")
            dims = (dimension_scores or {}).get(label)
            if dims:
                dim_str = "  " + " | ".join(
                    f"{k.replace('_', ' ')}: {v}" for k, v in dims.items()
                )
                return f"{label} — overall: {score}\n{dim_str}"
            return f"{label} — overall: {score} | {data.summary or 'no summary'}"

        candidates_block = "\n\n".join(
            _candidate_line(label, data) for label, data in candidates
        )
        prompt = _VERDICT_PROMPT.format(
            job_title=job_title,
            required_seniority=required_seniority or "not specified",
            required_skills=", ".join(required_skills) if required_skills else "not specified",
            decision_tags_hint=", ".join(job_decision_tags) if job_decision_tags else "none",
            candidates_block=candidates_block,
        )
        raw = await self._chat(prompt)
        try:
            data = json.loads(raw)
            decision_tags = data.get("decision_tags", [])
            if not isinstance(decision_tags, list):
                decision_tags = []
            return VerdictResult(
                recommended_candidate_id=str(data["recommended_candidate"]),
                decision="",  # computed deterministically by caller from overall_score
                decision_tags=[str(t) for t in decision_tags],
                hire_verdicts=data.get("hire_verdicts", {}),
                summary=str(data["summary"]),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise LLMParseError(f"LLM returned invalid verdict data: {exc}") from exc

    async def compare_candidates_structured(
        self,
        candidates: list[tuple[str, str, CandidateData]],  # (id, name, data)
        job_title: str,
        job_description: str | None,
        required_skills: list[str],
        job_decision_tags: list[str] | None = None,
        required_seniority: str | None = None,
        scores: dict[str, int] | None = None,  # {name: overall_score}
        dimension_scores: dict[str, dict] | None = None,  # {name: {dim: pts}}
    ) -> VerdictResult:
        labeled = [(name, data) for (_id, name, data) in candidates]
        verdict = await self.generate_verdict(
            candidates=labeled,
            scores=scores or {},
            job_title=job_title,
            required_skills=required_skills,
            required_seniority=required_seniority,
            job_decision_tags=job_decision_tags,
            dimension_scores=dimension_scores,
        )
        # Resolve name → id for recommended_candidate_id
        name_to_id = {name: cid for (cid, name, _data) in candidates}
        resolved = name_to_id.get(verdict.recommended_candidate_id)
        if resolved is None and candidates:
            resolved = candidates[0][0]
        return VerdictResult(
            recommended_candidate_id=resolved or "",
            decision=verdict.decision,  # will be overwritten by router with deterministic value
            decision_tags=verdict.decision_tags,
            hire_verdicts=verdict.hire_verdicts,
            summary=verdict.summary,
        )

    async def tiebreaker_analysis(
        self,
        candidates: list[tuple[str, str, CandidateData]],
        job_title: str,
        job_description: str | None,
        required_skills: list[str],
        required_seniority: str | None,
        dimensions: list[str],
        slots_remaining: int,
    ) -> TiebreakerResult:
        candidates_block = "\n\n".join(
            _candidate_block(name, data) for (_, name, data) in candidates
        )
        dimensions_block = "\n".join(f"- {d}" for d in dimensions)
        prompt = _TIEBREAKER_PROMPT.format(
            slots_remaining=slots_remaining,
            job_title=job_title,
            required_seniority=required_seniority or "not specified",
            required_skills=", ".join(required_skills) if required_skills else "not specified",
            job_description=job_description or "not provided",
            dimensions_block=dimensions_block,
            candidates_block=candidates_block,
        )
        raw = await self._chat(prompt)
        try:
            data = json.loads(raw)
            results = data.get("results", [])
            if not isinstance(results, list):
                results = []
            return TiebreakerResult(
                results=results,
                summary=str(data.get("summary", "")),
            )
        except (ValueError, TypeError) as exc:
            raise LLMParseError(f"LLM returned invalid tiebreaker data: {exc}") from exc

    async def suggest_skill_split(
        self,
        title: str,
        description: str | None,
        existing_skills: list[str],
    ) -> dict:
        prompt = (
            "You are a recruitment assistant. Split the provided skills into 'technical' and 'soft' categories.\n"
            "Return ONLY valid JSON: {\"technical\": [...], \"soft\": [...]}.\n\n"
            "Rules:\n"
            "- Normalize to lowercase and deduplicate (JS and JavaScript → keep one as 'javascript')\n"
            "- technical: programming languages, frameworks, tools, platforms, databases, cloud services, methodologies (e.g. Agile, Scrum)\n"
            "- soft: interpersonal, communication, leadership, and behavioral traits\n"
            "- Ambiguous: 'Project Management' → soft (unless a specific PM tool is named); "
            "'DevOps' → technical; 'Data Analysis' → technical; 'Problem Solving' → soft\n\n"
            "Examples:\n"
            "Skills: Python, React, Communication, Docker, Leadership, SQL, Teamwork\n"
            "Output: {\"technical\": [\"python\", \"react\", \"docker\", \"sql\"], \"soft\": [\"communication\", \"leadership\", \"teamwork\"]}\n\n"
            "Skills: Excel, Agile, Presentation Skills, AWS, Negotiation, Jira\n"
            "Output: {\"technical\": [\"excel\", \"agile\", \"aws\", \"jira\"], \"soft\": [\"presentation skills\", \"negotiation\"]}\n\n"
            f"Title: {title}\n"
            f"Description: {description or 'not provided'}\n"
            f"Skills to split: {', '.join(existing_skills) if existing_skills else 'none — infer from title and description'}\n"
        )
        raw = await self._chat(prompt)
        try:
            data = json.loads(raw)
            tech = data.get("technical", []) if isinstance(data, dict) else []
            soft = data.get("soft", []) if isinstance(data, dict) else []
            return {
                "technical": [str(s) for s in tech if s],
                "soft": [str(s) for s in soft if s],
            }
        except (ValueError, TypeError) as exc:
            raise LLMParseError(f"LLM returned invalid skill split: {exc}") from exc

    async def generate_job_description(
        self,
        title: str,
        seniority: str,
        skills: list[str],
        notes: str | None,
    ) -> dict:
        """Return a structured job description draft as {summary, responsibilities, requirements}."""
        from app.ai.prompts import generate_job_description_prompt

        prompt = generate_job_description_prompt(title, seniority, skills, notes)
        raw = await self._chat(prompt)
        try:
            data = json.loads(raw)
            summary = str(data.get("summary", ""))
            responsibilities = data.get("responsibilities", [])
            requirements = data.get("requirements", [])
            if not isinstance(responsibilities, list):
                responsibilities = []
            if not isinstance(requirements, list):
                requirements = []
            return {
                "summary": summary,
                "responsibilities": [str(r) for r in responsibilities if r],
                "requirements": [str(r) for r in requirements if r],
            }
        except (ValueError, TypeError, KeyError) as exc:
            raise LLMParseError(f"LLM returned invalid job description data: {exc}") from exc

    async def suggest_interview_questions(
        self,
        candidate: CandidateData,
        job_title: str,
        job_description: str | None,
        required_skills: list[str],
    ) -> list[str]:
        prompt = (
            "You are a senior technical recruiter. Given the candidate profile and job requirements below, "
            "suggest 5 targeted interview questions that will reveal fit or gaps.\n"
            "Return ONLY valid JSON: {\"questions\": [\"question 1\", \"question 2\", \"question 3\", \"question 4\", \"question 5\"]}\n\n"
            f"--- JOB ---\n"
            f"Title: {job_title}\n"
            f"Required skills: {', '.join(required_skills) if required_skills else 'not specified'}\n"
            f"Description: {job_description or 'not provided'}\n\n"
            f"--- CANDIDATE ---\n"
            f"Name: {candidate.name or 'Unknown'}\n"
            f"Seniority: {candidate.seniority or 'unknown'}\n"
            f"Years of experience: {candidate.years_experience or 'unknown'}\n"
            f"Skills: {', '.join(candidate.skills) if candidate.skills else 'none'}\n"
            f"Summary: {candidate.summary or 'not provided'}\n"
        )
        raw = await self._chat(prompt)
        try:
            data = json.loads(raw)
            questions = data.get("questions")
            if not isinstance(questions, list) or len(questions) != 5:
                raise LLMParseError("LLM returned invalid interview questions payload")
            cleaned = [str(q).strip() for q in questions if str(q).strip()]
            if len(cleaned) != 5:
                raise LLMParseError("LLM returned invalid interview questions payload")
            return cleaned
        except LLMParseError:
            raise
        except (ValueError, TypeError) as exc:
            raise LLMParseError(f"LLM returned invalid interview questions: {exc}") from exc
