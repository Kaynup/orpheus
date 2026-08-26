"""File validation and security safeguards for document ingestion."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Set, Tuple


class FileValidationError(Exception):
    """Raised when an uploaded or ingested file fails validation."""

    pass


def sanitize_filename(filename: str) -> str:
    """Strip path traversal characters and return a safe basename."""
    # Normalize backslashes to forward slashes for cross-platform path security
    normalized = str(filename).replace("\\", "/")
    safe_name = Path(normalized).name.lstrip(".")
    # Strip dangerous characters
    clean = "".join(c for c in safe_name if c.isalnum() or c in "._- ()")
    return clean.strip() or "unnamed_.txt"


def validate_file(
    file_path: str | Path,
    max_bytes: Optional[int] = None,
    allowed_extensions: Optional[Set[str]] = None,
) -> Tuple[bool, str]:
    """
    Validate that the file exists, is within size limits, has an allowed extension,
    and matches expected magic headers.

    Args:
        file_path: Path to the file to validate.
        max_bytes: Maximum file size in bytes. Defaults to config.storage.max_file_size_bytes.
        allowed_extensions: Set of permitted extensions (e.g. {'.txt', '.pdf'}).
                            Defaults to config.storage.allowed_extensions.

    Returns:
        Tuple of (True, "File is valid") on success.

    Raises:
        FileValidationError: If any validation check fails.
    """
    # Import here to avoid circular imports at module load time
    from app.config import config

    effective_max_bytes = max_bytes if max_bytes is not None else config.storage.max_file_size_bytes
    effective_extensions: Set[str] = (
        set(allowed_extensions) if allowed_extensions is not None else set(config.storage.allowed_extensions)
    )

    path = Path(file_path)

    if not path.exists() or not path.is_file():
        raise FileValidationError(f"File does not exist: {path}")

    # Check file size
    size = path.stat().st_size
    if size == 0:
        raise FileValidationError("File is empty (0 bytes).")
    if size > effective_max_bytes:
        raise FileValidationError(
            f"File size ({size / (1024 * 1024):.2f}MB) exceeds maximum limit of "
            f"{effective_max_bytes / (1024 * 1024):.0f}MB."
        )

    # Check extension
    ext = path.suffix.lower()
    if ext not in effective_extensions:
        raise FileValidationError(
            f"Unsupported file type '{ext}'. Allowed extensions: {', '.join(sorted(effective_extensions))}"
        )

    # Magic byte / content validation
    with open(path, "rb") as f:
        header = f.read(1024)

    if ext == ".pdf":
        if not header.startswith(b"%PDF-"):
            raise FileValidationError("Invalid PDF file: Missing standard %PDF- header magic bytes.")
    elif ext == ".txt":
        try:
            # Verify that text content is decodable UTF-8 / ASCII
            header.decode("utf-8")
        except UnicodeDecodeError as err:
            raise FileValidationError(f"Invalid text file encoding (must be UTF-8 or ASCII): {err}")

    return True, "File is valid"
