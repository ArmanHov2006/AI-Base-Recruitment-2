from typing import Literal

from app.config import settings
from app.llm.ollama import OllamaClient
from app.llm.openai_client import OpenAIClient

LLMClient = OllamaClient | OpenAIClient

_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        provider: Literal["ollama", "openai"] = settings.llm_provider  # type: ignore[assignment]
        _client = OpenAIClient() if provider == "openai" else OllamaClient()
    return _client
