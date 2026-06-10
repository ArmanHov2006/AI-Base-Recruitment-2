from typing import Literal

from app.config import settings
from app.llm.ollama import OllamaClient
from app.llm.openai_client import OpenAIClient

LLMClient = OllamaClient | OpenAIClient


def get_llm_client() -> LLMClient:
    provider: Literal["ollama", "openai"] = settings.llm_provider  # type: ignore[assignment]
    if provider == "openai":
        return OpenAIClient()
    return OllamaClient()
