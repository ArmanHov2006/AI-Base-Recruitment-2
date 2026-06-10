"""
Tests for F2 — Azure AD OIDC SSO.

Strategy:
- Fresh mini FastAPI app per test group (no lifespan, dependency_overrides).
- get_db overridden with AsyncMock to avoid Postgres connections.
- Azure HTTP calls (JWKS fetch, token exchange) mocked via unittest.mock.patch.
- authlib JWT decode mocked to return controlled claim sets.
"""
import base64
import hashlib
import secrets
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.auth_sso import _pending
from app.auth_sso import router as sso_router
from app.database import get_db
from app.users.models import UserRole
from tests.conftest import make_mock_db, make_user

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_AZURE_CFG = {
    "azure_tenant_id": "test-tenant-id",
    "azure_client_id": "test-client-id",
    "azure_client_secret": "test-client-secret",
    "azure_redirect_uri": "http://localhost:8000/auth/sso/callback",
}


@pytest.fixture
def sso_app() -> FastAPI:
    """Mini FastAPI app with only the SSO router mounted."""
    _app = FastAPI()
    _app.include_router(sso_router)
    return _app


@pytest.fixture
async def sso_client(sso_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=sso_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        yield c


@pytest.fixture
async def sso_client_with_db(
    sso_app: FastAPI,
) -> AsyncGenerator[tuple[AsyncClient, FastAPI], None]:
    mock_db = make_mock_db()

    async def db_override() -> AsyncGenerator:
        yield mock_db

    sso_app.dependency_overrides[get_db] = db_override

    async with AsyncClient(
        transport=ASGITransport(app=sso_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        yield c, sso_app

    sso_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_db_with_user(user):
    """Return a mock DB that yields `user` from scalar_one_or_none()."""
    mock_db = make_mock_db()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    mock_db.execute = AsyncMock(return_value=result)
    return mock_db


# ---------------------------------------------------------------------------
# SSO disabled (no config)
# ---------------------------------------------------------------------------

class TestSSODisabled:
    """When Azure config vars are unset, both routes must return 404."""

    async def test_login_returns_404_when_unconfigured(
        self, sso_client: AsyncClient
    ) -> None:
        with patch("app.auth_sso.settings") as mock_settings:
            mock_settings.azure_tenant_id = None
            mock_settings.azure_client_id = None
            mock_settings.azure_client_secret = None
            mock_settings.azure_redirect_uri = None
            r = await sso_client.get("/auth/sso/login", follow_redirects=False)
        assert r.status_code == 404, f"Expected 404 when SSO unconfigured, got {r.status_code}"

    async def test_callback_returns_404_when_unconfigured(
        self, sso_client: AsyncClient
    ) -> None:
        with patch("app.auth_sso.settings") as mock_settings:
            mock_settings.azure_tenant_id = None
            mock_settings.azure_client_id = None
            mock_settings.azure_client_secret = None
            mock_settings.azure_redirect_uri = None
            r = await sso_client.get(
                "/auth/sso/callback?code=x&state=y", follow_redirects=False
            )
        assert r.status_code == 404, f"Expected 404 when SSO unconfigured, got {r.status_code}"


# ---------------------------------------------------------------------------
# Login redirect
# ---------------------------------------------------------------------------

class TestSSOLogin:
    """GET /auth/sso/login must redirect to Azure when config is set."""

    async def test_login_redirects_when_configured(
        self, sso_client: AsyncClient
    ) -> None:
        with patch("app.auth_sso.settings") as mock_settings:
            mock_settings.azure_tenant_id = _AZURE_CFG["azure_tenant_id"]
            mock_settings.azure_client_id = _AZURE_CFG["azure_client_id"]
            mock_settings.azure_client_secret = _AZURE_CFG["azure_client_secret"]
            mock_settings.azure_redirect_uri = _AZURE_CFG["azure_redirect_uri"]
            r = await sso_client.get("/auth/sso/login", follow_redirects=False)

        assert r.status_code == 302, f"Expected 302 redirect, got {r.status_code}"
        location = r.headers.get("location", "")
        assert "login.microsoftonline.com" in location
        assert "code_challenge" in location
        assert "openid" in location

    async def test_login_stores_state_in_pending(
        self, sso_client: AsyncClient
    ) -> None:
        """A state key must be stored in _pending after /login."""
        _pending.clear()
        with patch("app.auth_sso.settings") as mock_settings:
            mock_settings.azure_tenant_id = _AZURE_CFG["azure_tenant_id"]
            mock_settings.azure_client_id = _AZURE_CFG["azure_client_id"]
            mock_settings.azure_client_secret = _AZURE_CFG["azure_client_secret"]
            mock_settings.azure_redirect_uri = _AZURE_CFG["azure_redirect_uri"]
            await sso_client.get("/auth/sso/login", follow_redirects=False)

        assert len(_pending) == 1, "Expected exactly one pending state after /login"
        _pending.clear()


# ---------------------------------------------------------------------------
# Callback — error cases
# ---------------------------------------------------------------------------

class TestSSOCallbackErrors:
    """Callback must reject bad/missing parameters gracefully."""

    async def test_callback_missing_code_returns_400(
        self, sso_client_with_db: tuple[AsyncClient, FastAPI]
    ) -> None:
        client, _ = sso_client_with_db
        with patch("app.auth_sso.settings") as mock_settings:
            mock_settings.azure_tenant_id = _AZURE_CFG["azure_tenant_id"]
            mock_settings.azure_client_id = _AZURE_CFG["azure_client_id"]
            mock_settings.azure_client_secret = _AZURE_CFG["azure_client_secret"]
            mock_settings.azure_redirect_uri = _AZURE_CFG["azure_redirect_uri"]
            r = await client.get("/auth/sso/callback?state=somestate")
        assert r.status_code == 400

    async def test_callback_invalid_state_returns_400(
        self, sso_client_with_db: tuple[AsyncClient, FastAPI]
    ) -> None:
        """State not found in _pending → 400."""
        client, _ = sso_client_with_db
        _pending.clear()  # ensure empty
        with patch("app.auth_sso.settings") as mock_settings:
            mock_settings.azure_tenant_id = _AZURE_CFG["azure_tenant_id"]
            mock_settings.azure_client_id = _AZURE_CFG["azure_client_id"]
            mock_settings.azure_client_secret = _AZURE_CFG["azure_client_secret"]
            mock_settings.azure_redirect_uri = _AZURE_CFG["azure_redirect_uri"]
            r = await client.get("/auth/sso/callback?code=somecode&state=nonexistent")
        assert r.status_code == 400

    async def test_callback_azure_error_returns_401(
        self, sso_client_with_db: tuple[AsyncClient, FastAPI]
    ) -> None:
        """Azure sends error param → 401."""
        client, _ = sso_client_with_db
        with patch("app.auth_sso.settings") as mock_settings:
            mock_settings.azure_tenant_id = _AZURE_CFG["azure_tenant_id"]
            mock_settings.azure_client_id = _AZURE_CFG["azure_client_id"]
            mock_settings.azure_client_secret = _AZURE_CFG["azure_client_secret"]
            mock_settings.azure_redirect_uri = _AZURE_CFG["azure_redirect_uri"]
            r = await client.get(
                "/auth/sso/callback?error=access_denied&error_description=User+cancelled"
            )
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Callback — happy path (full mocked OIDC)
# ---------------------------------------------------------------------------

class TestSSOCallbackSuccess:
    """Full round-trip with mocked Azure HTTP calls and authlib verification."""

    async def test_known_active_user_gets_jwt(
        self, sso_app: FastAPI
    ) -> None:
        """Known active user → access_token returned."""
        user = make_user(UserRole.RECRUITER)
        user.email = "alice@ardshinbank.am"
        mock_db = _make_mock_db_with_user(user)

        async def db_override() -> AsyncGenerator:
            yield mock_db

        sso_app.dependency_overrides[get_db] = db_override

        # Plant a state/verifier in _pending
        state_value = "test-state-abc"
        verifier_value = secrets.token_urlsafe(64)
        _pending[state_value] = verifier_value

        fake_token_resp = MagicMock()
        fake_token_resp.status_code = 200
        fake_token_resp.json.return_value = {"id_token": "fake.id.token", "access_token": "at"}

        fake_jwks_resp = MagicMock()
        fake_jwks_resp.status_code = 200
        fake_jwks_resp.json.return_value = {"keys": []}

        async def mock_exchange(code, verifier):
            return {"id_token": "fake.id.token"}

        async def mock_verify(id_token):
            return "alice@ardshinbank.am"

        with (
            patch("app.auth_sso.settings") as mock_settings,
            patch("app.auth_sso._exchange_code", side_effect=mock_exchange),
            patch("app.auth_sso._verify_id_token_and_get_email", side_effect=mock_verify),
        ):
            mock_settings.azure_tenant_id = _AZURE_CFG["azure_tenant_id"]
            mock_settings.azure_client_id = _AZURE_CFG["azure_client_id"]
            mock_settings.azure_client_secret = _AZURE_CFG["azure_client_secret"]
            mock_settings.azure_redirect_uri = _AZURE_CFG["azure_redirect_uri"]

            async with AsyncClient(
                transport=ASGITransport(app=sso_app, raise_app_exceptions=False),
                base_url="http://test",
            ) as client:
                r = await client.get(
                    f"/auth/sso/callback?code=authcode&state={state_value}"
                )

        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        body = r.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

        sso_app.dependency_overrides.clear()

    async def test_unknown_email_returns_403(
        self, sso_app: FastAPI
    ) -> None:
        """SSO email not found in DB → 403 (no auto-create)."""
        mock_db = make_mock_db()  # scalar_one_or_none returns None by default

        async def db_override() -> AsyncGenerator:
            yield mock_db

        sso_app.dependency_overrides[get_db] = db_override

        state_value = "test-state-denied"
        verifier_value = secrets.token_urlsafe(64)
        _pending[state_value] = verifier_value

        async def mock_exchange(code, verifier):
            return {"id_token": "fake.id.token"}

        async def mock_verify(id_token):
            return "unknown@outsider.com"

        with (
            patch("app.auth_sso.settings") as mock_settings,
            patch("app.auth_sso._exchange_code", side_effect=mock_exchange),
            patch("app.auth_sso._verify_id_token_and_get_email", side_effect=mock_verify),
        ):
            mock_settings.azure_tenant_id = _AZURE_CFG["azure_tenant_id"]
            mock_settings.azure_client_id = _AZURE_CFG["azure_client_id"]
            mock_settings.azure_client_secret = _AZURE_CFG["azure_client_secret"]
            mock_settings.azure_redirect_uri = _AZURE_CFG["azure_redirect_uri"]

            async with AsyncClient(
                transport=ASGITransport(app=sso_app, raise_app_exceptions=False),
                base_url="http://test",
            ) as client:
                r = await client.get(
                    f"/auth/sso/callback?code=authcode&state={state_value}"
                )

        assert r.status_code == 403, f"Expected 403 for unknown user, got {r.status_code}"
        sso_app.dependency_overrides.clear()

    async def test_inactive_user_returns_403(
        self, sso_app: FastAPI
    ) -> None:
        """SSO email found but user inactive → 403."""
        user = make_user(UserRole.RECRUITER)
        user.email = "inactive@ardshinbank.am"
        user.is_active = False
        mock_db = _make_mock_db_with_user(user)

        async def db_override() -> AsyncGenerator:
            yield mock_db

        sso_app.dependency_overrides[get_db] = db_override

        state_value = "test-state-inactive"
        verifier_value = secrets.token_urlsafe(64)
        _pending[state_value] = verifier_value

        async def mock_exchange(code, verifier):
            return {"id_token": "fake.id.token"}

        async def mock_verify(id_token):
            return "inactive@ardshinbank.am"

        with (
            patch("app.auth_sso.settings") as mock_settings,
            patch("app.auth_sso._exchange_code", side_effect=mock_exchange),
            patch("app.auth_sso._verify_id_token_and_get_email", side_effect=mock_verify),
        ):
            mock_settings.azure_tenant_id = _AZURE_CFG["azure_tenant_id"]
            mock_settings.azure_client_id = _AZURE_CFG["azure_client_id"]
            mock_settings.azure_client_secret = _AZURE_CFG["azure_client_secret"]
            mock_settings.azure_redirect_uri = _AZURE_CFG["azure_redirect_uri"]

            async with AsyncClient(
                transport=ASGITransport(app=sso_app, raise_app_exceptions=False),
                base_url="http://test",
            ) as client:
                r = await client.get(
                    f"/auth/sso/callback?code=authcode&state={state_value}"
                )

        assert r.status_code == 403, f"Expected 403 for inactive user, got {r.status_code}"
        sso_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# PKCE helpers unit tests
# ---------------------------------------------------------------------------

class TestPKCEHelpers:
    """Verify the PKCE code_challenge derivation is spec-compliant."""

    def test_code_challenge_is_s256_of_verifier(self) -> None:
        from app.auth_sso import _derive_code_challenge, _generate_code_verifier

        verifier = _generate_code_verifier()
        challenge = _derive_code_challenge(verifier)

        # Independently compute expected S256 challenge
        digest = hashlib.sha256(verifier.encode()).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

        assert challenge == expected

    def test_verifier_is_url_safe_and_long_enough(self) -> None:
        from app.auth_sso import _generate_code_verifier

        verifier = _generate_code_verifier()
        # RFC 7636: verifier must be 43–128 chars
        assert 43 <= len(verifier) <= 128, f"Verifier length {len(verifier)} out of RFC range"
        # No padding characters
        assert "=" not in verifier
        assert "+" not in verifier
        assert "/" not in verifier
