"""OpenAI API client — same public surface as OllamaClient."""

from collections.abc import AsyncGenerator

from openai import APITimeoutError, AsyncOpenAI
from openai import RateLimitError as OpenAIRateLimitError

from app.config import settings
from app.llm.base import LLMParseError, LLMTimeoutError
from app.llm.ollama import OllamaClient

_EMBED_DIMENSIONS = 768  # matches candidates.embedding vector(768) / nomic-embed-text


class OpenAIClient:
    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is required when LLM_PROVIDER=openai. Set it in .env or switch LLM_PROVIDER=ollama."
            )
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=float(settings.llm_timeout_seconds),
        )

    async def warmup(self) -> None:
        """Lightweight ping so the first user request is not the only cold call."""
        try:
            await self._client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": "ok"}],
                max_tokens=1,
                temperature=0,
            )
        except APITimeoutError as exc:
            raise LLMTimeoutError(f"LLM timed out after {settings.llm_timeout_seconds}s") from exc

    async def embed(self, text: str) -> list[float]:
        kwargs: dict = {"model": settings.openai_embed_model, "input": text}
        if settings.openai_embed_model.startswith("text-embedding-3"):
            kwargs["dimensions"] = _EMBED_DIMENSIONS
        try:
            response = await self._client.embeddings.create(**kwargs)
        except APITimeoutError as exc:
            raise LLMTimeoutError(f"Embedding request timed out after {settings.llm_timeout_seconds}s") from exc
        except OpenAIRateLimitError as exc:
            raise LLMParseError(f"Embedding rate limited: {exc}") from exc
        except Exception as exc:
            raise LLMParseError(f"Embedding request failed: {exc}") from exc

        if not response.data:
            raise LLMParseError("OpenAI returned no embedding data")
        return list(response.data[0].embedding)

    async def _chat(self, content: str) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": content}],
                response_format={"type": "json_object"},
                temperature=0,
            )
        except APITimeoutError as exc:
            raise LLMTimeoutError(f"LLM timed out after {settings.llm_timeout_seconds}s") from exc

        message = response.choices[0].message.content
        if not message:
            raise LLMParseError("OpenAI returned empty completion")
        return message

    async def _chat_text(self, content: str) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": content}],
                temperature=0,
            )
        except APITimeoutError as exc:
            raise LLMTimeoutError(f"LLM timed out after {settings.llm_timeout_seconds}s") from exc

        message = response.choices[0].message.content
        if not message:
            raise LLMParseError("OpenAI returned empty completion")
        return message

    async def chat_stream(self, system_prompt: str, user_message: str) -> AsyncGenerator[str, None]:
        try:
            stream = await self._client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.3,
                stream=True,
            )
        except APITimeoutError as exc:
            raise LLMTimeoutError(f"LLM timed out after {settings.llm_timeout_seconds}s") from exc

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# High-level flows call self._chat / self._chat_text — reuse OllamaClient implementations.
OpenAIClient.extract = OllamaClient.extract
OpenAIClient.score_candidate = OllamaClient.score_candidate
OpenAIClient.compare_candidates = OllamaClient.compare_candidates
OpenAIClient.generate_verdict = OllamaClient.generate_verdict
OpenAIClient.compare_candidates_structured = OllamaClient.compare_candidates_structured
OpenAIClient.suggest_skill_split = OllamaClient.suggest_skill_split
OpenAIClient.suggest_interview_questions = OllamaClient.suggest_interview_questions
OpenAIClient.generate_job_description = OllamaClient.generate_job_description
OpenAIClient.tiebreaker_analysis = OllamaClient.tiebreaker_analysis
OpenAIClient.score_interview = OllamaClient.score_interview
