"""Language detection for resume text.

Detects whether a resume is primarily written in Armenian, Russian, or English
and returns the ISO 639-1 language code.

Strategy: script-based heuristic (no external deps, O(n) over a sample).
- Armenian: Unicode block U+0531–U+058A (Armenian).
- Russian/Cyrillic: Unicode block U+0400–U+04FF.
- English/Latin: ASCII letters that are not Cyrillic or Armenian.

If ``langdetect`` is available it is used as a tiebreaker when the dominant
script share is below the confidence threshold; otherwise the heuristic alone
is used.

The heuristic is intentionally simple:
  1. Take up to 2000 chars of the text (fast, representative sample).
  2. Count letter characters per script group.
  3. If one group holds >40% of all letter chars → that language.
  4. Else → "unknown".
"""

_ARMENIAN_RANGE = (0x0531, 0x058A)
_CYRILLIC_RANGE = (0x0400, 0x04FF)

_CONFIDENCE_THRESHOLD = 0.40  # dominant script must own >40% of letters


def _script_shares(text: str) -> tuple[float, float, float]:
    """Return (armenian_share, cyrillic_share, latin_share) over letter chars."""
    sample = text[:2000]
    armenian = 0
    cyrillic = 0
    latin = 0
    for ch in sample:
        cp = ord(ch)
        if _ARMENIAN_RANGE[0] <= cp <= _ARMENIAN_RANGE[1]:
            armenian += 1
        elif _CYRILLIC_RANGE[0] <= cp <= _CYRILLIC_RANGE[1]:
            cyrillic += 1
        elif ch.isalpha():
            latin += 1
    total = armenian + cyrillic + latin
    if total == 0:
        return 0.0, 0.0, 0.0
    return armenian / total, cyrillic / total, latin / total


def detect_language(text: str) -> str:
    """Return ISO 639-1 language code for *text*: ``"hy"``, ``"ru"``, ``"en"``,
    or ``"unknown"``.

    Uses a script-frequency heuristic; falls back to ``langdetect`` when
    installed and the heuristic is ambiguous.
    """
    if not text or not text.strip():
        return "unknown"

    hy_share, ru_share, en_share = _script_shares(text)

    # Clear winner from the heuristic
    dominant_share = max(hy_share, ru_share, en_share)
    if dominant_share >= _CONFIDENCE_THRESHOLD:
        if hy_share == dominant_share:
            return "hy"
        if ru_share == dominant_share:
            return "ru"
        return "en"

    # Ambiguous — try langdetect if available
    try:
        from langdetect import LangDetectException, detect  # type: ignore[import-untyped]

        try:
            code = detect(text[:2000])
            # Normalise: langdetect returns "hy", "ru", "en" for the three targets
            if code in ("hy", "ru", "en"):
                return code
            # Cyrillic-adjacent codes (e.g. "uk", "bg") map to "ru" only when
            # the Cyrillic share is significant, otherwise stay "unknown".
            if ru_share > 0.10:
                return "ru"
            return "unknown"
        except LangDetectException:
            return "unknown"
    except ImportError:
        pass

    return "unknown"
