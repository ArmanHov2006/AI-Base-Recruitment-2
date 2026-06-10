"""
Azure AD OIDC SSO router — F2.

Routes are disabled (404) when Azure config vars are not set.
Password login endpoints are untouched.

Flow: PKCE Authorization Code
  GET /auth/sso/login      → redirect to Azure /authorize
  GET /auth/sso/callback   → exchange code, verify id_token, map email → user, mint JWT
"""
import hashlib
import logging
import secrets
import uuid
from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import BusinessEventAction
from app.audit.events import record
from app.config import settings
from app.database import get_db
from app.security import create_access_token
from app.users.models import User

logger = logging.getLogger(__name__)
log = structlog.get_logger()

router = APIRouter(prefix="/auth/sso", tags=["sso"])

DbDep = Annotated[AsyncSession, Depends(get_db)]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SSO_DISABLED = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="SSO is not configured on this server",
)


def _sso_configured() -> bool:
    """Return True only when all four Azure config vars are non-empty."""
    return bool(
        settings.azure_tenant_id
        and settings.azure_client_id
        and settings.azure_client_secret
        and settings.azure_redirect_uri
    )


def _authorization_endpoint() -> str:
    return (
        f"https://login.microsoftonline.com/{settings.azure_tenant_id}"
        "/oauth2/v2.0/authorize"
    )


def _token_endpoint() -> str:
    return (
        f"https://login.microsoftonline.com/{settings.azure_tenant_id}"
        "/oauth2/v2.0/token"
    )


def _jwks_uri() -> str:
    return (
        f"https://login.microsoftonline.com/{settings.azure_tenant_id}"
        "/discovery/v2.0/keys"
    )


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _generate_code_verifier() -> str:
    """Generate a cryptographically random PKCE code_verifier (43–128 chars)."""
    return secrets.token_urlsafe(64)


def _derive_code_challenge(verifier: str) -> str:
    """Derive S256 code_challenge from verifier."""
    digest = hashlib.sha256(verifier.encode()).digest()
    import base64
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/login")
async def sso_login(request: Request) -> RedirectResponse:
    """Redirect the browser to the Azure AD authorization endpoint (PKCE)."""
    if not _sso_configured():
        raise _SSO_DISABLED

    state = secrets.token_urlsafe(32)
    verifier = _generate_code_verifier()
    challenge = _derive_code_challenge(verifier)

    # Store state + verifier in the session-like server-side store (in-process
    # for simplicity; production can swap to Redis-backed store).
    _pending[state] = verifier

    params = {
        "client_id": settings.azure_client_id,
        "response_type": "code",
        "redirect_uri": settings.azure_redirect_uri,
        "response_mode": "query",
        "scope": "openid profile email",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url=f"{_authorization_endpoint()}?{query}", status_code=302)


@router.get("/callback")
async def sso_callback(
    request: Request,
    db: DbDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> dict:
    """
    Handle the Azure OIDC callback.
    - Exchange code for tokens.
    - Verify the id_token and extract the email claim.
    - Map email to an existing active user.
    - Mint and return an app JWT (same format as password login).
    """
    if not _sso_configured():
        raise _SSO_DISABLED

    # --- Azure returned an error ---
    if error:
        log.warning("sso_callback.azure_error", error=error, description=error_description)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Azure AD error: {error}",
        )

    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing code or state parameter",
        )

    # --- Validate state + retrieve PKCE verifier ---
    verifier = _pending.pop(state, None)
    if verifier is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired SSO state",
        )

    # --- Exchange code for tokens ---
    token_data = await _exchange_code(code, verifier)

    # --- Verify id_token and extract email ---
    email = await _verify_id_token_and_get_email(token_data["id_token"])

    # --- Look up user by email ---
    result = await db.execute(
        select(User).where(
            User.email == email,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()

    request_id: uuid.UUID | None = getattr(request.state, "request_id", None)

    if user is None or not user.is_active:
        # Emit denied event (best-effort — no real user_id to link to)
        log.warning("sso_callback.user_not_found_or_inactive", email=email)
        # We cannot record a business event without a valid user row; just raise.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active account found for this identity. Contact your administrator.",
        )

    # --- Emit business event ---
    await record(
        db,
        actor_id=user.id,
        action=BusinessEventAction.USER_SSO_LOGIN,
        resource_type="user",
        resource_id=user.id,
        request_id=request_id,
        after={"email": user.email, "role": user.role.value},
        meta={"provider": "azure_ad", "oid_email": email},
    )
    await db.commit()

    # --- Mint app JWT ---
    access_token = create_access_token(str(user.id), user.email, user.role.value)
    log.info("sso_callback.success", user_id=str(user.id), email=email)
    return {"access_token": access_token, "token_type": "bearer"}


# ---------------------------------------------------------------------------
# In-process PKCE state store (state → code_verifier)
# Suitable for a single-process dev/test server.
# Production: replace with a short-TTL Redis key.
# ---------------------------------------------------------------------------
_pending: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Token exchange + id_token verification
# ---------------------------------------------------------------------------

async def _exchange_code(code: str, verifier: str) -> dict:
    """POST to Azure token endpoint; return the JSON body."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _token_endpoint(),
            data={
                "client_id": settings.azure_client_id,
                "client_secret": settings.azure_client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.azure_redirect_uri,
                "code_verifier": verifier,
            },
        )
    if resp.status_code != 200:
        logger.error("Token exchange failed: %s %s", resp.status_code, resp.text[:200])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Token exchange with Azure failed",
        )
    return resp.json()


async def _verify_id_token_and_get_email(id_token: str) -> str:
    """
    Verify the Azure id_token JWT signature using JWKS, then return the email claim.

    Uses authlib's JsonWebToken for signature verification.
    """
    from authlib.jose import JsonWebKey, JsonWebToken
    from authlib.jose.errors import JoseError

    # Fetch JWKS from Azure
    async with httpx.AsyncClient(timeout=10) as client:
        jwks_resp = await client.get(_jwks_uri())
    if jwks_resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch Azure JWKS",
        )
    jwks_data = jwks_resp.json()

    try:
        key_set = JsonWebKey.import_key_set(jwks_data)
        claims = JsonWebToken(["RS256"]).decode(id_token, key_set)
        claims.validate()
    except JoseError as exc:
        logger.warning("id_token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Azure id_token",
        ) from exc

    email: str | None = claims.get("email") or claims.get("preferred_username")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Azure token does not contain an email claim",
        )
    return email.lower().strip()
