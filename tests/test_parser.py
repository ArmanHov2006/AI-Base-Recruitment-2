from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from minio.error import S3Error

from app.auth import get_current_user, require_write
from app.llm.base import LLMParseError, LLMTimeoutError
from app.parser.router import router as parser_router
from app.parser.schemas import CandidateData
from app.users.models import UserRole
from tests.conftest import make_user

AUTH = {"Authorization": "Bearer test-stub"}  # bypassed by dependency override
BAD_AUTH = {"Authorization": "Bearer definitely-wrong-token"}

_FAKE_CANDIDATE = CandidateData(
    name="Jane Doe",
    email="jane@example.com",
    skills=["Python", "FastAPI"],
    years_experience=5.0,
    seniority="senior",
)

PDF_BYTES = b"%PDF-1.4\n%%EOF"
_VALID_UUID4 = "550e8400-e29b-41d4-a716-446655440000"
_S3_ERR = S3Error("NoSuchKey", "The key does not exist.", "/", "reqid", "hostid", None)


@pytest.fixture
async def client() -> AsyncClient:
    # Build a minimal test app so tests are independent of main.py router state.
    _app = FastAPI()
    _app.include_router(parser_router)
    fake = make_user(UserRole.RECRUITER)
    _app.dependency_overrides[get_current_user] = lambda: fake
    _app.dependency_overrides[require_write] = lambda: fake
    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as c:
        yield c


# Auth gating covered by tests/test_rbac.py.


# ── 400 / 422 bad input ───────────────────────────────────────────────────────

async def test_parse_url_as_file_id_returns_400(client: AsyncClient) -> None:
    r = await client.post(
        "/parse",
        headers=AUTH,
        json={"file_id": "http://internal-service/secret"},
    )
    assert r.status_code == 400


async def test_parse_random_string_file_id_returns_400(client: AsyncClient) -> None:
    r = await client.post("/parse", headers=AUTH, json={"file_id": "not-a-uuid"})
    assert r.status_code == 400


async def test_parse_empty_file_id_returns_400(client: AsyncClient) -> None:
    r = await client.post("/parse", headers=AUTH, json={"file_id": ""})
    assert r.status_code == 400


async def test_parse_uuid_v1_returns_400(client: AsyncClient) -> None:
    uuid_v1 = "550e8400-e29b-11d4-a716-446655440000"  # version byte is 1, not 4
    r = await client.post("/parse", headers=AUTH, json={"file_id": uuid_v1})
    assert r.status_code == 400


async def test_parse_missing_file_id_field_returns_422(client: AsyncClient) -> None:
    r = await client.post("/parse", headers=AUTH, json={})
    assert r.status_code == 422


# ── Upstream errors ───────────────────────────────────────────────────────────

async def test_parse_file_not_found_returns_404(client: AsyncClient) -> None:
    with patch("app.parser.service.fetch_file_bytes", new=AsyncMock(side_effect=_S3_ERR)):
        r = await client.post("/parse", headers=AUTH, json={"file_id": _VALID_UUID4})
    assert r.status_code == 404


async def test_parse_llm_timeout_returns_504(client: AsyncClient) -> None:
    with (
        patch("app.parser.service.fetch_file_bytes", new=AsyncMock(return_value=PDF_BYTES)),
        patch("app.parser.service.extract_text", new=MagicMock(return_value="some resume text")),
        patch("app.parser.service._llm.extract", new=AsyncMock(side_effect=LLMTimeoutError("timed out"))),
    ):
        r = await client.post("/parse", headers=AUTH, json={"file_id": _VALID_UUID4})

    assert r.status_code == 504


async def test_parse_llm_parse_error_returns_502(client: AsyncClient) -> None:
    delete_mock = AsyncMock()
    with (
        patch("app.parser.service.fetch_file_bytes", new=AsyncMock(return_value=PDF_BYTES)),
        patch("app.parser.service.extract_text", new=MagicMock(return_value="some resume text")),
        patch("app.parser.service._llm.extract", new=AsyncMock(side_effect=LLMParseError("bad json"))),
        patch("app.parser.service.delete_file", new=delete_mock),
    ):
        r = await client.post("/parse", headers=AUTH, json={"file_id": _VALID_UUID4})

    assert r.status_code == 502
    delete_mock.assert_called_once_with(_VALID_UUID4)


# ── Happy path ────────────────────────────────────────────────────────────────

async def test_parse_valid_file_id_returns_candidate_data(client: AsyncClient) -> None:
    with (
        patch("app.parser.service.fetch_file_bytes", new=AsyncMock(return_value=PDF_BYTES)),
        patch("app.parser.service.extract_text", new=MagicMock(return_value="Jane Doe resume text")),
        patch("app.parser.service._llm.extract", new=AsyncMock(return_value=_FAKE_CANDIDATE)),
    ):
        r = await client.post("/parse", headers=AUTH, json={"file_id": _VALID_UUID4})

    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "Jane Doe"
    assert "python" in data["skills"]  # skills are normalised to lowercase
