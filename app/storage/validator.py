import io
import zipfile

import filetype

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

# Allowed video formats for interview recordings
ALLOWED_VIDEO_EXTENSIONS = {".webm", ".mp4"}

# Magic-byte signatures for supported video containers
# WebM is an EBML container — first 4 bytes are always \x1aE\xdf\xa3
_WEBM_MAGIC = b"\x1a\x45\xdf\xa3"
# MP4/ISOBMFF: bytes 4-8 of the file form the "ftyp" box type
_MP4_FTYP = b"ftyp"


class FileValidationError(ValueError):
    pass


def _check_size(content_length: int, max_bytes: int, limit_label: str) -> None:
    """Shared size-gate used by both resume and video validators."""
    if content_length > max_bytes:
        mb = max_bytes // (1024 * 1024)
        raise FileValidationError(f"File exceeds {mb}MB limit ({limit_label})")


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
    _check_size(len(content), max_bytes, "resume")

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


def _read_video_header(content_or_path: bytes | str) -> bytes:
    """Return the first 12 bytes from either in-memory content or a file path."""
    if isinstance(content_or_path, (bytes, bytearray)):
        return bytes(content_or_path[:12])
    # It's a file path on disk — read only the header bytes
    with open(content_or_path, "rb") as f:
        return f.read(12)


def _detect_video_container(header: bytes) -> str | None:
    """Return 'webm', 'mp4', or None for unrecognised containers.

    WebM (EBML): first 4 bytes == \\x1aE\\xdf\\xa3
    MP4 (ISOBMFF ftyp box): bytes 4-8 == b'ftyp'
    """
    if len(header) >= 4 and header[:4] == _WEBM_MAGIC:
        return "webm"
    if len(header) >= 8 and header[4:8] == _MP4_FTYP:
        return "mp4"
    return None


def validate_video_upload(
    filename: str,
    content_or_path: bytes | str,
    max_bytes: int,
) -> None:
    """Gate-0 validation for interview video recordings.

    Accepts .webm (EBML magic) and .mp4 (ftyp box at offset 4).
    Rejects everything else or files over *max_bytes*.

    *content_or_path* may be raw ``bytes`` (from an upload buffer) or a
    ``str`` file-system path (from a MinIO-downloaded tempfile). When a path
    is supplied, only the header bytes are read so large files are never
    loaded into RAM.
    """
    # Size check — for in-memory content we know the full size immediately;
    # for on-disk files we stat the file.
    if isinstance(content_or_path, (bytes, bytearray)):
        size = len(content_or_path)
    else:
        import os

        size = os.path.getsize(content_or_path)
    _check_size(size, max_bytes, "video")

    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise FileValidationError(f"Extension {ext!r} not allowed for video uploads")

    header = _read_video_header(content_or_path)
    container = _detect_video_container(header)
    if container is None:
        raise FileValidationError("File magic bytes do not match a supported video container (webm/mp4)")
    # Cross-check extension vs detected container
    if ext == ".webm" and container != "webm":
        raise FileValidationError("File declared as .webm but magic bytes indicate a different format")
    if ext == ".mp4" and container != "mp4":
        raise FileValidationError("File declared as .mp4 but magic bytes indicate a different format")
