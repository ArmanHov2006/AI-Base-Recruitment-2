"""F3 — AI provider config split.

Verifies that get_llm_client() returns the correct client type based on the
LLM_PROVIDER setting, with no code change required to swap providers.
"""

from unittest.mock import patch

import pytest

from app.llm.ollama import OllamaClient
from app.llm.openai_client import OpenAIClient


@pytest.mark.parametrize(
    "provider,expected_type",
    [
        ("ollama", OllamaClient),
        ("openai", OpenAIClient),
    ],
)
def test_get_llm_client_returns_correct_type(provider: str, expected_type: type) -> None:
    """Switching LLM_PROVIDER swaps the client with no code change."""
    with (
        patch("app.llm.factory.settings") as mock_factory_settings,
        patch("app.llm.openai_client.settings") as mock_oc_settings,
    ):
        mock_factory_settings.llm_provider = provider
        mock_oc_settings.openai_api_key = "test-key"
        mock_oc_settings.llm_timeout_seconds = 30
        import app.llm.factory
        from app.llm.factory import get_llm_client

        # Reset the module-level singleton cache so this test case doesn't inherit
        # the cached client from a previous parametrized iteration.
        app.llm.factory._client = None

        client = get_llm_client()
        assert isinstance(client, expected_type), (
            f"Expected {expected_type.__name__} for LLM_PROVIDER={provider!r}, "
            f"got {type(client).__name__}"
        )


def test_default_provider_is_ollama() -> None:
    """Prod default must be ollama (on-prem, no PII to cloud)."""
    from app.config import Settings

    # Instantiate with only the required fields; llm_provider should default to "ollama".
    default = Settings.model_fields["llm_provider"].default
    assert default == "ollama", (
        "Default LLM_PROVIDER must be 'ollama' (prod-safe default). "
        "Set LLM_PROVIDER=openai explicitly in dev .env."
    )


def test_llm_provider_rejects_unknown_value() -> None:
    """Config must reject an unrecognised provider string at startup."""
    import pydantic

    with pytest.raises((pydantic.ValidationError, ValueError)):
        from app.config import Settings

        Settings(
            jwt_secret="a" * 32,
            postgres_db="x",
            postgres_user="x",
            postgres_password="x",
            minio_root_user="x",
            minio_root_password="x",
            minio_bucket="x",
            minio_internal_url="http://localhost:9000",
            minio_public_url="http://localhost:9000",
            llm_provider="anthropic",  # type: ignore[arg-type]  # not a valid literal
        )
