import json

from app.candidates.models import Candidate
from app.jobs.models import Job


def _candidate_dict(c: Candidate) -> dict[str, object]:
    return {
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "location": c.location,
        "seniority": c.seniority,
        "years_experience": c.years_experience,
        "summary": c.summary,
        "desired_position": c.desired_position,
        "desired_salary": c.desired_salary,
        "skills": c.skills,
        "certifications": c.certifications,
        "languages": c.languages,
        "education": c.education,
        "work_experiences": c.work_experiences,
        "linkedin_url": c.linkedin_url,
        "github_url": c.github_url,
    }


def _job_dict(j: Job) -> dict[str, object]:
    return {
        "title": j.title,
        "description": j.description,
        "required_skills": j.required_skills,
        "required_technical_skills": j.required_technical_skills,
        "required_soft_skills": j.required_soft_skills,
        "required_seniority": j.required_seniority,
        "location": j.location,
    }


def generate_job_description_prompt(
    title: str,
    seniority: str,
    skills: list[str],
    notes: str | None,
) -> str:
    """Build a prompt that asks the LLM to generate a structured job description draft.

    Returns a prompt whose response is valid JSON matching the shape:
    {
      "summary": "<2-3 sentence role overview>",
      "responsibilities": ["<item>", ...],
      "requirements": ["<item>", ...]
    }
    """
    skills_line = ", ".join(skills) if skills else "not specified"
    notes_line = notes if notes else "none"
    return (
        "You are an expert HR copywriter at a bank. "
        "Generate a professional job description draft for an internal recruitment platform. "
        "Return ONLY valid JSON — no markdown, no extra text.\n\n"
        "Return this exact JSON structure:\n"
        "{\n"
        '  "summary": "<2-3 sentence overview of the role and its purpose>",\n'
        '  "responsibilities": [\n'
        '    "<concrete responsibility 1>",\n'
        '    "<concrete responsibility 2>",\n'
        '    "... (4-6 items total)"\n'
        '  ],\n'
        '  "requirements": [\n'
        '    "<concrete requirement 1>",\n'
        '    "<concrete requirement 2>",\n'
        '    "... (4-6 items total)"\n'
        '  ]\n'
        "}\n\n"
        "Rules:\n"
        "- Write in clear, professional English suitable for an Armenian bank\n"
        "- responsibilities: day-to-day tasks and ownership areas (4-6 items)\n"
        "- requirements: skills, qualifications, and experience required (4-6 items)\n"
        "- Tailor requirements to the seniority level provided\n"
        "- Do NOT fabricate requirements not implied by the title/skills/notes\n"
        "- Do NOT add salary or benefits information\n\n"
        f"--- INPUT ---\n"
        f"Job title: {title}\n"
        f"Seniority: {seniority}\n"
        f"Required skills: {skills_line}\n"
        f"Additional notes: {notes_line}\n"
    )


def build_system_prompt(candidate: Candidate, job: Job | None) -> str:
    """Ground the assistant strictly in the candidate (and optional job) data."""
    parts = [
        "You are a recruitment assistant helping a recruiter evaluate a single candidate.",
        "Answer ONLY from the candidate data below. If the data does not contain the "
        "answer, say you don't have that information — never invent facts.",
        "Be concise and specific: reference concrete skills, roles, companies, and years.",
        # F5 — multi-language: the candidate data may originate from an Armenian or Russian
        # resume. Structured fields (skills, seniority, titles) are already normalised to
        # English. The summary/description fields may contain the original language text —
        # always respond to the recruiter in English regardless of the source language.
        "The candidate's resume may have been written in Armenian or Russian. "
        "Structured fields are normalised to English. "
        "Always respond in English.",
        "",
        "--- CANDIDATE (JSON) ---",
        json.dumps(_candidate_dict(candidate), ensure_ascii=False, indent=2),
    ]
    if job is not None:
        parts += [
            "",
            "--- JOB REQUIREMENTS (JSON) ---",
            json.dumps(_job_dict(job), ensure_ascii=False, indent=2),
            "",
            "When asked about fit, judge the candidate against these job requirements.",
        ]
    return "\n".join(parts)
