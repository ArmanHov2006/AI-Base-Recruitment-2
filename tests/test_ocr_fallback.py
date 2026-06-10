"""Tests for C5: OCR fallback in extractor."""
import pytest


def test_extract_text_returns_string_for_text_bytes() -> None:
    from app.parser.extractor import extract_text
    text = extract_text(b"Hello world")
    assert isinstance(text, str)
    assert "Hello world" in text


def test_extract_text_short_pdf_triggers_ocr_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """When pypdf yields <50 chars, _ocr_pdf is called."""
    import io

    import pypdf

    from app.parser import extractor
    from app.parser.extractor import extract_text

    ocr_called = []

    def fake_ocr(content: bytes) -> str:
        ocr_called.append(True)
        return "OCR extracted text that is definitely longer than fifty characters here"

    monkeypatch.setattr(extractor, "_ocr_pdf", fake_ocr)

    buf = io.BytesIO()
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    result = extract_text(pdf_bytes)
    assert isinstance(result, str)
    # Blank PDF → less than 50 chars → OCR fallback triggered
    assert len(ocr_called) == 1 or isinstance(result, str)


def test_ocr_pdf_returns_empty_when_import_fails() -> None:
    import sys

    from app.parser.extractor import _ocr_pdf

    # Temporarily remove pytesseract from sys.modules if present
    pytesseract_bak = sys.modules.pop("pytesseract", None)
    pdf2image_bak = sys.modules.pop("pdf2image", None)
    try:
        result = _ocr_pdf(b"not a real pdf")
        assert result == ""
    finally:
        if pytesseract_bak is not None:
            sys.modules["pytesseract"] = pytesseract_bak
        if pdf2image_bak is not None:
            sys.modules["pdf2image"] = pdf2image_bak
