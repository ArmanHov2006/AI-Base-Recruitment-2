from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import get_current_user, require_write
from app.main import app
from app.storage.validator import FileValidationError, validate_file
from app.users.models import UserRole
from tests.conftest import make_user

AUTH = {"Authorization": "Bearer test-stub"}  # bypassed by dependency override
BAD_AUTH = {"Authorization": "Bearer definitely-wrong-token"}
PDF_BYTES = b"%PDF-1.4\n%%EOF"
_MAX = 10 * 1024 * 1024


@pytest.fixture
async def client() -> AsyncClient:
    fake = make_user(UserRole.RECRUITER)
    app.dependency_overrides[get_current_user] = lambda: fake
    app.dependency_overrides[require_write] = lambda: fake
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


# ── Healthcheck ───────────────────────────────────────────────────────────────

async def test_healthz(client: AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# Auth gating covered by tests/test_rbac.py.


# ── 400 negative cases ────────────────────────────────────────────────────────

async def test_upload_bad_extension_returns_400(client: AsyncClient) -> None:
    r = await client.post(
        "/files/upload",
        headers=AUTH,
        files={"file": ("malware.exe", b"\x4d\x5a\x90\x00", "application/octet-stream")},
    )
    assert r.status_code == 400


async def test_upload_no_extension_returns_400(client: AsyncClient) -> None:
    r = await client.post(
        "/files/upload",
        headers=AUTH,
        files={"file": ("resume", b"some content", "application/octet-stream")},
    )
    assert r.status_code == 400


async def test_upload_pdf_extension_wrong_content_returns_400(client: AsyncClient) -> None:
    r = await client.post(
        "/files/upload",
        headers=AUTH,
        files={"file": ("resume.pdf", b"this is not a pdf", "application/pdf")},
    )
    assert r.status_code == 400


async def test_upload_docx_extension_wrong_content_returns_400(client: AsyncClient) -> None:
    r = await client.post(
        "/files/upload",
        headers=AUTH,
        files={"file": ("resume.docx", PDF_BYTES, "application/pdf")},
    )
    assert r.status_code == 400


async def test_upload_txt_non_utf8_returns_400(client: AsyncClient) -> None:
    r = await client.post(
        "/files/upload",
        headers=AUTH,
        files={"file": ("resume.txt", b"\xff\xfe\xfd", "text/plain")},
    )
    assert r.status_code == 400


async def test_upload_oversized_file_returns_400(client: AsyncClient) -> None:
    r = await client.post(
        "/files/upload",
        headers=AUTH,
        files={"file": ("resume.pdf", b"x" * (11 * 1024 * 1024), "application/pdf")},
    )
    assert r.status_code == 400


# ── 200 happy paths ───────────────────────────────────────────────────────────

async def test_upload_valid_pdf_returns_file_id(client: AsyncClient) -> None:
    with patch("app.storage.router._put_object"):
        r = await client.post(
            "/files/upload",
            headers=AUTH,
            files={"file": ("resume.pdf", PDF_BYTES, "application/pdf")},
        )
    assert r.status_code == 200
    data = r.json()
    assert "file_id" in data
    assert len(data["file_id"]) == 36  # UUID4


async def test_upload_valid_txt_returns_file_id(client: AsyncClient) -> None:
    with patch("app.storage.router._put_object"):
        r = await client.post(
            "/files/upload",
            headers=AUTH,
            files={"file": ("resume.txt", b"Jane Doe\nPython Developer", "text/plain")},
        )
    assert r.status_code == 200
    assert "file_id" in r.json()


async def test_upload_valid_docx_returns_file_id(client: AsyncClient) -> None:
    with (
        patch("app.storage.validator._is_valid_docx", return_value=True),
        patch("app.storage.router._put_object"),
    ):
        r = await client.post(
            "/files/upload",
            headers=AUTH,
            files={"file": ("resume.docx", b"PK\x03\x04", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
    assert r.status_code == 200
    assert "file_id" in r.json()


# ── validate_file unit tests ──────────────────────────────────────────────────

def test_validator_rejects_disallowed_extension() -> None:
    with pytest.raises(FileValidationError, match="not allowed"):
        validate_file("virus.exe", b"\x4d\x5a\x90\x00", _MAX)


def test_validator_rejects_no_extension() -> None:
    with pytest.raises(FileValidationError, match="not allowed"):
        validate_file("resume", b"content", _MAX)


def test_validator_rejects_oversized_file() -> None:
    with pytest.raises(FileValidationError, match="exceeds"):
        validate_file("big.pdf", b"x" * (11 * 1024 * 1024), _MAX)


def test_validator_rejects_pdf_magic_mismatch() -> None:
    with pytest.raises(FileValidationError, match="content does not match"):
        validate_file("resume.pdf", b"not-a-pdf", _MAX)


def test_validator_rejects_docx_magic_mismatch() -> None:
    with pytest.raises(FileValidationError, match="content does not match"):
        validate_file("resume.docx", PDF_BYTES, _MAX)


def test_validator_rejects_txt_non_utf8() -> None:
    with pytest.raises(FileValidationError, match="non-UTF-8"):
        validate_file("resume.txt", b"\xff\xfe\xfd", _MAX)


def test_validator_accepts_valid_txt() -> None:
    validate_file("resume.txt", b"Jane Doe\nPython developer", _MAX)


def test_validator_accepts_valid_pdf() -> None:
    validate_file("resume.pdf", PDF_BYTES, _MAX)


# ── Phase 1 expansion: edge cases ─────────────────────────────────────────────

def test_validator_rejects_empty_file() -> None:
    with pytest.raises(FileValidationError, match="content does not match"):
        validate_file("resume.pdf", b"", _MAX)


def test_validator_rejects_double_extension_exe() -> None:
    with pytest.raises(FileValidationError, match="not allowed"):
        validate_file("resume.pdf.exe", b"\x4d\x5a", _MAX)


def test_validator_rejects_oversized_boundary() -> None:
    with pytest.raises(FileValidationError, match="exceeds"):
        validate_file("big.pdf", b"x" * (_MAX + 1), _MAX)


def test_validator_accepts_at_max_size() -> None:
    # Use the smallest valid PDF, then pad up — content must still pass magic check.
    # Easier: drive the size check directly with a buffer of size _MAX containing %PDF prefix.
    payload = b"%PDF-1.4\n" + b"\x00" * (_MAX - len(b"%PDF-1.4\n") - len(b"\n%%EOF")) + b"\n%%EOF"
    assert len(payload) == _MAX
    validate_file("resume.pdf", payload, _MAX)


def test_validator_rejects_zip_without_word_xml() -> None:
    """Plain ZIP (no word/document.xml) with .docx extension must be rejected."""
    import io as _io
    import zipfile as _zf

    buf = _io.BytesIO()
    with _zf.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "not a docx")
    with pytest.raises(FileValidationError, match="content does not match"):
        validate_file("resume.docx", buf.getvalue(), _MAX)
