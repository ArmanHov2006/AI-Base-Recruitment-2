import re
from typing import Any

from pydantic import BaseModel, field_validator, model_validator


def _normalize_skill(s: str) -> str:
    """Strip trailing proficiency annotations like '(proficient)' and lowercase."""
    return re.sub(r'\s*\(.*?\)\s*$', '', s).strip().lower()


_MONTH_MAP = {
    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
    'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
    'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12',
}
_ONGOING = {'present', 'current', 'now', 'ongoing', 'till date', 'to date', 'today'}
_RANGE_SEPS = [' – ', ' - ', '–', ' to ']


def _parse_date(text: str) -> str | None:
    """Normalize a freeform date string to YYYY-MM, or None if ongoing/unparseable."""
    t = text.strip()
    if not t or t.lower() in _ONGOING:
        return None
    if re.match(r'^\d{4}-(0[1-9]|1[0-2])$', t):
        return t
    # "Mon YYYY" or "Month YYYY"
    m = re.match(r'^([a-zA-Z]{3,9})\.?\s+(\d{4})$', t)
    if m:
        mn = _MONTH_MAP.get(m.group(1)[:3].lower())
        if mn:
            return f"{m.group(2)}-{mn}"
    # "YYYY Mon"
    m = re.match(r'^(\d{4})\s+([a-zA-Z]{3,9})$', t)
    if m:
        mn = _MONTH_MAP.get(m.group(2)[:3].lower())
        if mn:
            return f"{m.group(1)}-{mn}"
    # Year only
    m = re.match(r'^(\d{4})$', t)
    if m:
        return f"{m.group(1)}-01"
    # MM/YYYY or M-YYYY
    m = re.match(r'^(\d{1,2})[/\-](\d{4})$', t)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    return None


class Education(BaseModel):
    institution: str | None = None
    degree: str | None = None
    year: int | None = None


class WorkExperience(BaseModel):
    company: str | None = None
    role: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    achievements: list[str] = []
    description: str | None = None

    @field_validator('achievements', mode='before')
    @classmethod
    def _coerce_achievements(cls, v: Any) -> Any:
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        return v

    @model_validator(mode='before')
    @classmethod
    def _normalize_dates(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        start_raw = str(data.get('start_date') or '')
        end_raw = str(data.get('end_date') or '')
        # Model sometimes puts the full range in start_date, e.g. "Dec 2022 - Present"
        for sep in _RANGE_SEPS:
            if sep in start_raw:
                parts = start_raw.split(sep, 1)
                data['start_date'] = _parse_date(parts[0])
                if not end_raw:
                    data['end_date'] = _parse_date(parts[1])
                return data
        data['start_date'] = _parse_date(start_raw) if start_raw else None
        if end_raw:
            data['end_date'] = _parse_date(end_raw)
        return data


class CandidateData(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    skills: list[str] = []
    years_experience: float | None = None
    education: list[Education] = []
    work_experiences: list[WorkExperience] = []
    location: str | None = None
    seniority: str | None = None  # junior | mid | senior | lead
    summary: str | None = None
    desired_position: str | None = None
    certifications: list[str] = []
    languages: list[str] = []
    linkedin_url: str | None = None
    github_url: str | None = None
    # F5 — populated by parse_and_validate; not extracted by the LLM.
    # ISO 639-1 code: "hy" | "ru" | "en" | "unknown" | None
    resume_language: str | None = None

    @field_validator('skills', 'education', 'work_experiences', 'certifications', 'languages', mode='before')
    @classmethod
    def _null_lists(cls, v: Any) -> Any:
        return [] if v is None else v

    @field_validator('skills', mode='after')
    @classmethod
    def _normalize_skills(cls, v: list[str]) -> list[str]:
        seen: dict[str, None] = {}
        for s in v:
            if not isinstance(s, str):
                continue
            ns = _normalize_skill(s)
            if ns:
                seen.setdefault(ns, None)
        return list(seen)

    @field_validator('years_experience', mode='before')
    @classmethod
    def _coerce_years(cls, v: Any) -> Any:
        if v is None or isinstance(v, (int, float)):
            return v
        if isinstance(v, str):
            m = re.search(r'\d+(?:\.\d+)?', v)
            return float(m.group()) if m else None
        return v
