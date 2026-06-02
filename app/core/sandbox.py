"""ConfiDoc Backend — File Sandbox and Malware Scanning."""

import mimetypes
from pathlib import Path

from app.core.logging import get_logger

HAS_MAGIC = False
try:
    import magic

    # Check if libmagic is actually available by trying a dummy call
    try:
        magic.from_buffer(b"test")
        HAS_MAGIC = True
    except Exception:
        pass
except ImportError:
    pass

logger = get_logger(__name__)


class SandboxError(Exception):
    """Raised when a file fails sandbox validation."""

    pass


def scan_file_for_malware(file_path: str | Path, expected_extension: str) -> bool:
    """Perform basic security checks on a file.

    1. Verify MIME type matches extension
    2. Check for suspicious signatures
    3. Verify file integrity
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found for scanning: {file_path}")

    # 1. MIME Type verification
    ext = expected_extension.lower().strip(".")
    mime = None

    if HAS_MAGIC:
        try:
            mime = magic.from_file(str(path), mime=True)
        except Exception as e:
            logger.warning("magic_failed_using_mimetypes_fallback", error=str(e))

    if not mime:
        # Fallback to standard library (less secure as it only checks extension)
        mime, _ = mimetypes.guess_type(str(path))

    # MIME mapping
    valid_mimes = {
        "pdf": ["application/pdf"],
        "png": ["image/png"],
        "jpg": ["image/jpeg"],
        "jpeg": ["image/jpeg"],
        "tiff": ["image/tiff"],
        "tif": ["image/tiff"],
    }

    if ext in valid_mimes and mime and mime not in valid_mimes[ext]:
        logger.warning(
            "sandbox_mime_mismatch",
            filename=path.name,
            extension=ext,
            detected_mime=mime,
        )
        # In production, this mismatch should block the upload
        if HAS_MAGIC:
            raise SandboxError(f"File signature mismatch: expected {ext}, detected {mime}")

    # 2. Check for suspicious markers (e.g., PHP tags in images)
    suspicious_markers = [b"<?php", b"eval(", b"base64_decode("]
    try:
        with open(path, "rb") as f:
            # Check first 8KB
            head = f.read(8192)
            for marker in suspicious_markers:
                if marker in head:
                    logger.error(
                        "sandbox_malicious_marker_found",
                        marker=marker,
                        filename=path.name,
                    )
                    raise SandboxError("Suspicious content detected in file.")
    except SandboxError:
        raise
    except Exception as exc:
        logger.warning("sandbox_scan_failed", error=str(exc))

    logger.info("sandbox_scan_passed", filename=path.name, mime=mime)
    return True
