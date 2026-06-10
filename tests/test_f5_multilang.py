"""Tests for F5: multi-language resume support (Armenian / Russian / English).

Covers:
- detect_language() heuristic for all three target languages + unknown
- OCR prompt uses hye+rus+eng lang codes
- LLM extraction prompt includes multi-language instructions
- resume_language is set on CandidateData after parse_and_validate
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.parser.lang_detect import detect_language

# ── detect_language — Armenian ────────────────────────────────────────────────

def test_detect_language_armenian_script() -> None:
    # Pure Armenian text (block U+0531–U+058A)
    text = "Անուն Ազգանուն Ծրագրավորող Հայաստան Երևան"
    assert detect_language(text) == "hy"


def test_detect_language_armenian_mixed_with_numbers() -> None:
    # Realistic Armenian CV fragment with numbers and punctuation
    text = (
        "Անձնական տեղեկություններ\n"
        "Անուն՝ Արման Հովհաննիսյան\n"
        "Հասցե՝ Երևան, Հայաստան\n"
        "Հեռախոս՝ +374 77 123456\n"
        "Փորձ՝ 5 տարի"
    )
    assert detect_language(text) == "hy"


# ── detect_language — Russian ─────────────────────────────────────────────────

def test_detect_language_russian_script() -> None:
    text = "Иванов Иван Иванович Программист Москва Россия"
    assert detect_language(text) == "ru"


def test_detect_language_russian_resume_fragment() -> None:
    text = (
        "Опыт работы: 7 лет\n"
        "Навыки: Python, Django, PostgreSQL\n"
        "Образование: Московский государственный университет\n"
        "Должность: Старший разработчик"
    )
    assert detect_language(text) == "ru"


# ── detect_language — English ─────────────────────────────────────────────────

def test_detect_language_english() -> None:
    text = "Senior Software Engineer with expertise in Python, FastAPI, and PostgreSQL."
    assert detect_language(text) == "en"


def test_detect_language_english_resume() -> None:
    text = (
        "John Smith\nSoftware Developer\nYerevan, Armenia\n"
        "Experience: Five years of backend development using Python and Django.\n"
        "Education: Bachelor of Science in Computer Science, Yerevan State University"
    )
    assert detect_language(text) == "en"


# ── detect_language — edge cases ─────────────────────────────────────────────

def test_detect_language_empty_string() -> None:
    assert detect_language("") == "unknown"


def test_detect_language_whitespace_only() -> None:
    assert detect_language("   \n\t  ") == "unknown"


def test_detect_language_digits_and_symbols_only() -> None:
    result = detect_language("123 456 789 *** +374 77 000000")
    # No letters → cannot determine language; must not crash
    assert result in ("en", "unknown")


# ── OCR uses hye+rus+eng lang string ─────────────────────────────────────────

def test_ocr_pdf_uses_multilang_tesseract() -> None:
    """_ocr_pdf must pass lang='hye+rus+eng' to pytesseract."""
    import sys
    import types

    # Build fake pytesseract + pdf2image modules so the import succeeds.
    captured_kwargs: list[dict] = []

    def fake_image_to_string(img, **kwargs):  # type: ignore[no-untyped-def]
        captured_kwargs.append(kwargs)
        return "OCR text"

    fake_pytesseract = types.ModuleType("pytesseract")
    fake_pytesseract.image_to_string = fake_image_to_string  # type: ignore[attr-defined]

    def fake_convert_from_bytes(content, dpi=200):  # type: ignore[no-untyped-def]
        return [MagicMock()]  # one fake image

    fake_pdf2image = types.ModuleType("pdf2image")
    fake_pdf2image.convert_from_bytes = fake_convert_from_bytes  # type: ignore[attr-defined]

    orig_pytesseract = sys.modules.get("pytesseract")
    orig_pdf2image = sys.modules.get("pdf2image")
    sys.modules["pytesseract"] = fake_pytesseract
    sys.modules["pdf2image"] = fake_pdf2image
    try:
        # Force reimport so the patched modules are used.
        import importlib

        from app.parser import extractor
        importlib.reload(extractor)
        result = extractor._ocr_pdf(b"fake-pdf-bytes")
    finally:
        if orig_pytesseract is not None:
            sys.modules["pytesseract"] = orig_pytesseract
        else:
            sys.modules.pop("pytesseract", None)
        if orig_pdf2image is not None:
            sys.modules["pdf2image"] = orig_pdf2image
        else:
            sys.modules.pop("pdf2image", None)
        # Reload with original state restored
        import importlib

        from app.parser import extractor as _ext  # noqa: F401
        importlib.reload(_ext)

    assert result == "OCR text"
    assert len(captured_kwargs) == 1
    assert captured_kwargs[0].get("lang") == "hye+rus+eng"


# ── LLM extraction prompt includes multilang instructions ────────────────────

def test_extraction_prompt_contains_multilang_instruction() -> None:
    """_EXTRACT_PROMPT must instruct the model to handle Armenian and Russian."""
    from app.llm.ollama import _EXTRACT_PROMPT

    prompt_lower = _EXTRACT_PROMPT.lower()
    assert "armenian" in prompt_lower, "Prompt must mention Armenian"
    assert "russian" in prompt_lower or "cyrillic" in prompt_lower, (
        "Prompt must mention Russian or Cyrillic"
    )
    assert "normalize" in prompt_lower or "canonical" in prompt_lower, (
        "Prompt must instruct normalization to canonical form"
    )
    assert "english" in prompt_lower, "Prompt must instruct English output for skills/seniority"


def test_ai_system_prompt_mentions_multilang() -> None:
    """build_system_prompt must note that resumes may be Armenian/Russian."""
    from unittest.mock import MagicMock as MM

    from app.ai.prompts import build_system_prompt

    candidate = MM()
    candidate.name = "Test"
    candidate.email = "t@t.com"
    candidate.phone = None
    candidate.location = None
    candidate.seniority = None
    candidate.years_experience = None
    candidate.summary = None
    candidate.desired_position = None
    candidate.desired_salary = None
    candidate.skills = []
    candidate.certifications = []
    candidate.languages = []
    candidate.education = []
    candidate.work_experiences = []
    candidate.linkedin_url = None
    candidate.github_url = None

    prompt = build_system_prompt(candidate, None)
    assert "armenian" in prompt.lower() or "russian" in prompt.lower(), (
        "System prompt must acknowledge multilang resumes"
    )


# ── parse_and_validate sets resume_language ──────────────────────────────────

@pytest.mark.asyncio
async def test_parse_and_validate_sets_resume_language() -> None:
    """parse_and_validate must detect language and annotate CandidateData."""
    from unittest.mock import MagicMock

    from app.parser.schemas import CandidateData
    from app.parser.service import parse_and_validate

    _VALID_UUID4 = "550e8400-e29b-41d4-a716-446655440000"

    fake_candidate = CandidateData(
        name="Արման Հովհաննիսյան",
        email="arman@example.com",
        skills=["Python"],
        years_experience=3.0,
        seniority="mid",
    )

    # Armenian-heavy text so detect_language returns "hy"
    armenian_text = (
        "Անձնական տեղեկություններ Անուն՝ Արման Հովհաննիսյան "
        "Ծրագրավորող Հայաստան Երևան Python Django"
    ) * 5  # repeat to exceed the 40% threshold

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    with (
        patch("app.parser.service.fetch_file_bytes", new=AsyncMock(return_value=b"fake")),
        patch("app.parser.service.extract_text", new=MagicMock(return_value=armenian_text)),
        patch("app.parser.service._llm.extract", new=AsyncMock(return_value=fake_candidate)),
    ):
        result = await parse_and_validate(_VALID_UUID4, mock_db)

    assert result.resume_language == "hy", (
        f"Expected 'hy', got {result.resume_language!r}"
    )
