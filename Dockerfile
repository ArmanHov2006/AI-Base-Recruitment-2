FROM python:3.12-slim

WORKDIR /app

# ffmpeg: required by the interview worker to transcode untrusted candidate
# video (webm/mp4) → 16k mono wav before STT (A2). Harmless for the API image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Bake the Whisper model into the image (A2): no runtime download, model is
# present + owned by the non-root user. WHISPER_MODEL is env-swappable (flip to
# multilingual `small` for hy/ru later). HF_HOME lives under /app so the final
# chown covers it. NOTE: revision pinning is a hardening follow-up.
ENV HF_HOME=/app/.hf-cache \
    WHISPER_MODEL=small.en
RUN uv run python -c "from faster_whisper import WhisperModel; WhisperModel('small.en', device='cpu', compute_type='int8')"

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

RUN useradd -r -u 1001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"]
