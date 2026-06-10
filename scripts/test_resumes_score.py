"""Quick test: parse + score all resumes in a directory against a job."""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.database import async_session_factory
from app.jobs.models import Job
from app.llm.ollama import OllamaClient
from app.parser.extractor import extract_text


async def fetch_job(job_id: str | None, job_title: str | None) -> Job:
    async with async_session_factory() as session:
        q = select(Job).where(Job.deleted_at.is_(None))
        if job_id:
            import uuid
            q = q.where(Job.id == uuid.UUID(job_id))
        elif job_title:
            q = q.where(Job.title.ilike(f"%{job_title}%"))
        q = q.limit(1)
        row = await session.execute(q)
        job = row.scalar_one_or_none()
        if job is None:
            raise RuntimeError("No matching active job found in DB")
        return job


async def process(llm: OllamaClient, path: Path, job: Job) -> dict:
    content = path.read_bytes()
    raw_text = extract_text(content)
    if len(raw_text) > 4000:
        print(f"[WARN] {path.name}: text truncated {len(raw_text)} → 4000 chars")
    text = raw_text[:4000]
    candidate = await llm.extract(text)
    result = await llm.score_candidate(
        candidate=candidate,
        job_title=job.title,
        job_description=job.description,
        required_skills=list(job.required_skills or []),
        required_technical_skills=list(job.required_technical_skills or []),
        required_soft_skills=list(job.required_soft_skills or []),
        required_seniority=job.required_seniority,
    )
    return {
        "file": path.name,
        "name": candidate.name or "?",
        "seniority": candidate.seniority or "?",
        "years_exp": candidate.years_experience,
        "skills": candidate.skills[:6],
        "overall": result.overall_score,
        "dims": result.dimension_scores,
        "reasoning": result.reasoning,
    }


async def main(resume_dir: Path, job_id: str | None, job_title: str | None) -> None:
    job = await fetch_job(job_id, job_title)

    files = sorted(resume_dir.glob("*.*"))
    if not files:
        print(f"No files in {resume_dir}")
        return

    llm = OllamaClient()
    print(f"\nScoring {len(files)} resumes -> {job.title} ({job.required_seniority})\n")
    print("=" * 80)

    results = []
    for path in files:
        print(f"\n[{path.name}]")
        try:
            r = await process(llm, path, job)
            results.append(r)
            print(f"  Name:        {r['name']}")
            print(f"  Seniority:   {r['seniority']}  |  Years: {r['years_exp']}")
            print(f"  Skills:      {', '.join(r['skills'])}")
            print(f"  OVERALL:     {r['overall']:>3}/100")
            dims = r["dims"]
            print(f"  skills_match={dims.get('skills_match','?'):>3}  "
                  f"experience={dims.get('experience_level','?'):>3}  "
                  f"seniority={dims.get('seniority_fit','?'):>3}  "
                  f"education={dims.get('education','?'):>3}")
            print(f"  Reasoning:   {r['reasoning']}")
        except Exception as exc:
            print(f"  ERROR: {exc}")

    if results:
        print("\n" + "=" * 80)
        print("RANKING")
        print("=" * 80)
        ranked = sorted(results, key=lambda x: x["overall"], reverse=True)
        for i, r in enumerate(ranked, 1):
            print(f"  {i}. {r['name']:<30} {r['overall']:>3}/100  ({r['file']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Score resumes against a job")
    parser.add_argument("--resume-dir", required=True, type=Path, help="Directory containing resume files")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--job-id", help="UUID of the job to score against")
    group.add_argument("--job-title", help="Title substring to match the job (case-insensitive)")
    args = parser.parse_args()
    asyncio.run(main(args.resume_dir, args.job_id, args.job_title))
