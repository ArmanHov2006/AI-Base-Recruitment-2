"""Worker pipeline: download recording → STT → LLM score → upsert CandidateEvaluation.

Hardening notes:
- Per-loop async engine: asyncpg pool must be bound to the current event loop
  (same pattern as app/worker/scoring.py — create_async_engine inside the function).
- Non-root container: worker Dockerfile already uses USER appuser; ffmpeg runs
  as the same non-root user. subprocess.run timeout=120 prevents runaway transcodes.
- Never buffer video blob in RAM: minio fget_object streams to a NamedTemporaryFile;
  faster-whisper receives the wav path, not bytes.
- Upsert idempotency: keyed on (candidate_id, job_id, evaluator_id=None, stage="ai_interview")
  via the existing UniqueConstraint uq_ce_candidate_job_evaluator_stage.
  Re-running produces exactly one ai_interview row.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import uuid

import structlog
from minio.error import S3Error
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.evaluations.models import CandidateEvaluation
from app.interviews.models import InterviewAnswer, InterviewSession
from app.llm.base import LLMParseError
from app.storage.validator import FileValidationError, validate_video_upload

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Whisper singleton — loaded lazily at module level to avoid paying the
# model-load cost on every task call. Tests mock this before importing.
# ---------------------------------------------------------------------------
_whisper_model = None  # type: ignore[var-annotated]


def _get_whisper():  # type: ignore[return]
    """Lazy-load WhisperModel so the module can be imported without faster-whisper installed.

    Unit tests patch this function or the _whisper_model global directly.
    """
    global _whisper_model  # noqa: PLW0603
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel  # type: ignore[import-not-found]

            model_size = os.getenv("WHISPER_MODEL", "small.en")
            _whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
        except ImportError:
            raise RuntimeError(
                "faster-whisper is not installed. "
                "Add 'faster-whisper' to pyproject.toml dependencies and run 'uv sync'."
            )
    return _whisper_model


def _transcribe_wav(wav_path: str) -> tuple[str, str]:
    """Run faster-whisper on *wav_path* and return (transcript_text, language_code).

    Returns ("", "unknown") when no speech segments are detected.
    """
    model = _get_whisper()
    segments, info = model.transcribe(wav_path, beam_size=5)
    lang = getattr(info, "language", "unknown") or "unknown"
    texts = [seg.text for seg in segments if seg.text]
    return " ".join(texts).strip(), lang


# ---------------------------------------------------------------------------
# Transient vs permanent error classification
# ---------------------------------------------------------------------------
_TRANSIENT = (S3Error, subprocess.TimeoutExpired, OSError)
_PERMANENT = (LLMParseError, FileValidationError, ValueError)


async def transcribe_and_score(session_id: uuid.UUID) -> None:  # noqa: C901 (complexity)
    """Download recordings → STT → LLM score → upsert CandidateEvaluation.

    Called from the Celery task wrapper in tasks.py via asyncio.run().
    """
    # Per-loop engine — asyncpg pool must be bound to the current event loop.
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _run_pipeline(session_factory, session_id)
    finally:
        await engine.dispose()


async def _run_pipeline(
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
    session_id: uuid.UUID,
) -> None:
    """Inner pipeline — separated so engine.dispose() always runs in the outer wrapper."""
    async with session_factory() as db:
        result = await db.execute(
            select(InterviewSession).where(
                InterviewSession.id == session_id,
                InterviewSession.deleted_at.is_(None),
            )
        )
        session = result.scalar_one_or_none()
        if session is None:
            log.warning("interview.pipeline.session_missing", session_id=str(session_id))
            return

        # interview_answers has no soft-delete column (CASCADE-tied to session)
        answers_result = await db.execute(
            select(InterviewAnswer).where(
                InterviewAnswer.session_id == session_id,
            )
        )
        answers = list(answers_result.scalars().all())

        session.status = "transcribing"
        await db.commit()

        # ----------------------------------------------------------------
        # Per-answer: download → validate → transcode → STT
        # ----------------------------------------------------------------
        from app.storage.client import minio_client

        for answer in answers:
            if not answer.recording_file_id:
                continue
            try:
                _process_answer(answer, minio_client)
                await db.commit()
            except _PERMANENT as exc:
                answer.failure_reason = f"permanent: {exc}"[:1000]
                session.status = "failed"
                await db.commit()
                raise
            except Exception as exc:
                answer.failure_reason = f"transient: {exc}"[:1000]
                session.status = "failed"
                await db.commit()
                raise

        # ----------------------------------------------------------------
        # Assemble full Q/A transcript for LLM scoring
        # ----------------------------------------------------------------
        transcript_parts: list[str] = []
        for i, answer in enumerate(answers, 1):
            q = answer.question_text or f"Question {i}"
            a = answer.transcript or ""
            if a:
                transcript_parts.append(f"Q{i}: {q}\nA{i}: {a}")

        full_transcript = "\n\n".join(transcript_parts)
        if not full_transcript.strip():
            msg = "All answers have empty transcripts — cannot score"
            session.status = "failed"
            await db.commit()
            raise LLMParseError(msg)

        # ----------------------------------------------------------------
        # LLM interview scoring
        # ----------------------------------------------------------------
        from app.jobs.models import Job
        from app.llm.factory import get_llm_client
        from app.llm.rubric import INTERVIEW_WEIGHTS

        job_result = await db.execute(select(Job).where(Job.id == session.job_id))
        job = job_result.scalar_one_or_none()

        job_title = job.title if job else "Unknown"
        job_description = job.description if job else None
        required_skills: list[str] = list(job.required_skills or []) if job else []

        try:
            llm = get_llm_client()
            scoring_result = await llm.score_interview(
                transcript=full_transcript,
                job_title=job_title,
                job_description=job_description,
                required_skills=required_skills,
            )
        except LLMParseError:
            session.status = "failed"
            await db.commit()
            raise
        except Exception as exc:
            session.status = "failed"
            await db.commit()
            raise LLMParseError(f"LLM scoring failed unexpectedly: {exc}") from exc

        # ----------------------------------------------------------------
        # Upsert CandidateEvaluation — exactly one ai_interview row
        # Keyed on (candidate_id, job_id, evaluator_id=None, stage="ai_interview")
        # which matches the unique constraint uq_ce_candidate_job_evaluator_stage.
        # ----------------------------------------------------------------
        ai_suggested_rating = scoring_result.dimension_scores.get("ai_suggested_rating")
        # Extract dimension points (exclude the ai_suggested_rating sentinel key)
        dim_points = {k: v for k, v in scoring_result.dimension_scores.items() if k in INTERVIEW_WEIGHTS}

        eval_result = await db.execute(
            select(CandidateEvaluation).where(
                CandidateEvaluation.candidate_id == session.candidate_id,
                CandidateEvaluation.job_id == session.job_id,
                CandidateEvaluation.evaluator_id.is_(None),
                CandidateEvaluation.stage == "ai_interview",
            )
        )
        existing_eval = eval_result.scalar_one_or_none()

        if existing_eval is not None:
            # Update in place — idempotent re-run
            evaluation = existing_eval
        else:
            evaluation = CandidateEvaluation(
                id=uuid.uuid4(),
                candidate_id=session.candidate_id,
                job_id=session.job_id,
                evaluator_id=None,
                stage="ai_interview",
            )
            db.add(evaluation)

        evaluation.technical_score = dim_points.get("technical_accuracy")
        evaluation.communication_score = dim_points.get("communication")
        evaluation.ai_suggested_rating = ai_suggested_rating
        evaluation.feedback = scoring_result.reasoning
        evaluation.interview_session_id = session.id  # links eval → interview (Lane C migration 0034)

        session.status = "scored"
        await db.commit()

        log.info(
            "interview.pipeline.scored",
            session_id=str(session_id),
            overall_score=scoring_result.overall_score,
            ai_suggested_rating=ai_suggested_rating,
        )


def _process_answer(answer: InterviewAnswer, minio_client) -> None:  # type: ignore[type-arg]
    """Download → validate → ffmpeg → STT for one InterviewAnswer.

    Mutates answer.transcript and answer.transcript_lang in place.
    Runs synchronously — called from async context but wraps blocking I/O.
    Heavy I/O (download, ffmpeg, whisper) blocks; acceptable for Celery worker.
    """
    bucket = settings.minio_bucket
    key = answer.recording_file_id  # type: ignore[assignment]

    # Derive a filename for extension detection from the object key
    filename = os.path.basename(key)
    if "." not in filename:
        filename = filename + ".webm"  # fallback — assume webm for keyless paths

    # Use NamedTemporaryFile so ffmpeg can read a real path.
    # delete=False so we can os.unlink in finally — never buffer blob in RAM.
    with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1] or ".webm", delete=False) as tmp_src:
        src_path = tmp_src.name

    try:
        # Stream download directly to disk
        minio_client.fget_object(bucket, key, src_path)

        # Gate-0: validate the downloaded file (checks size + magic bytes)
        validate_video_upload(filename, src_path, settings.max_video_upload_bytes)

        # Transcode to 16kHz mono WAV for Whisper
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
            wav_path = tmp_wav.name
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    src_path,
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "-f",
                    "wav",
                    wav_path,
                ],
                timeout=120,
                check=True,
                capture_output=True,
            )

            # STT
            transcript, lang = _transcribe_wav(wav_path)
            answer.transcript = transcript or None
            answer.transcript_lang = lang or None

        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    finally:
        try:
            os.unlink(src_path)
        except OSError:
            pass
