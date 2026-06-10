import io
import zipfile

import filetype

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


class FileValidationError(ValueError):
    pass


def _is_valid_docx(content: bytes) -> bool:
    """A DOCX is a ZIP archive that contains word/document.xml.

    We verify this directly via stdlib zipfile rather than via filetype.guess,
    because filetype 1.2.0 cannot reliably distinguish DOCX from a plain ZIP:
    its DOCX matcher inspects fixed byte offsets that differ between DOCX
    producers (Word, LibreOffice, Google Docs), and frequently falls back to
    the generic zip matcher on perfectly valid DOCX files.
    """
    if not content.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            return "word/document.xml" in zf.namelist()
    except zipfile.BadZipFile:
        return False


def validate_file(filename: str, content: bytes, max_bytes: int) -> None:
    if len(content) > max_bytes:
        raise FileValidationError(f"File exceeds {max_bytes // (1024 * 1024)}MB limit")

    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise FileValidationError(f"Extension {ext!r} not allowed")

    if ext == ".txt":
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            raise FileValidationError("TXT file contains non-UTF-8 bytes")
        return

    if ext == ".docx":
        is_docx = _is_valid_docx(content)
        if not is_docx:
            raise FileValidationError("File content does not match declared extension")
        return

    # ext == ".pdf" — filetype's PDF matcher (literal %PDF magic) is reliable.
    kind = filetype.guess(content)
    if kind is None or kind.extension != "pdf":
        raise FileValidationError("File content does not match declared extension")
