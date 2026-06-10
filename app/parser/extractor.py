import asyncio
import io
import re
import zipfile

import filetype
import pypdf
from docx import Document

from app.config import settings
from app.storage.client import minio_client


def _is_docx(content: bytes) -> bool:
    """Detect DOCX by ZIP signature + presence of word/document.xml.

    Mirrors app.storage.validator._is_valid_docx — see the rationale there.
    """
    if not content.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            return "word/document.xml" in zf.namelist()
    except zipfile.BadZipFile:
        return False


def _get_bytes(file_id: str) -> bytes:
    response = minio_client.get_object(settings.minio_bucket, file_id)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def _remove(file_id: str) -> None:
    minio_client.remove_object(settings.minio_bucket, file_id)


async def fetch_file_bytes(file_id: str) -> bytes:
    return await asyncio.to_thread(_get_bytes, file_id)


async def delete_file(file_id: str) -> None:
    await asyncio.to_thread(_remove, file_id)


def _ocr_pdf(content: bytes) -> str:
    """OCR fallback for image-only PDFs. Requires pytesseract + pdf2image.

    Tesseract language packs used: hye (Armenian), rus (Russian), eng (English).
    Installs required on the system: tesseract-ocr-hye tesseract-ocr-rus tesseract-ocr-eng.
    """
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
    except ImportError:
        return ""
    try:
        images = convert_from_bytes(content, dpi=300)
        return "\n".join(
            pytesseract.image_to_string(img, lang="hye+rus+eng") for img in images
        )
    except Exception:
        return ""


def extract_text(content: bytes) -> str:
    kind = filetype.guess(content)
    mime = kind.mime if kind else None
    is_docx = _is_docx(content)

    if mime == "application/pdf":
        reader = pypdf.PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        # Fall back to OCR when pypdf yields no meaningful text (scanned PDF)
        if len(text.strip()) < 50:
            ocr_text = _ocr_pdf(content)
            if ocr_text.strip():
                return ocr_text
        return text

    if is_docx:
        doc = Document(io.BytesIO(content))
        return "\n".join(para.text for para in doc.paragraphs)

    return content.decode("utf-8", errors="replace")


_LINKEDIN_RE = re.compile(r"https?://(?:www\.)?linkedin\.com/in/[\w\-\.]+/?", re.IGNORECASE)
_GITHUB_RE = re.compile(r"https?://(?:www\.)?github\.com/[\w\-]+/?", re.IGNORECASE)


def extract_linkedin_url(text: str) -> str | None:
    m = _LINKEDIN_RE.search(text)
    return m.group(0).rstrip("/") if m else None


def extract_github_url(text: str) -> str | None:
    m = _GITHUB_RE.search(text)
    return m.group(0).rstrip("/") if m else None
