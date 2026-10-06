import re
from pathlib import Path
from typing import Set
from backend.config import settings


class ValidationError(Exception):
    """Base validation exception."""
    pass


class InvalidFileExtensionError(ValidationError):
    """Raised when uploaded file has an unsupported extension."""
    pass


class FileTooLargeError(ValidationError):
    """Raised when uploaded file exceeds maximum permitted size."""
    pass


class EmptyFileError(ValidationError):
    """Raised when uploaded file contains no data."""
    pass


def get_file_extension(filename: str) -> str:
    """Extract lowercased file extension with leading dot."""
    return Path(filename).suffix.lower()


def validate_file_extension(filename: str, allowed_extensions: Set[str] | None = None) -> str:
    """
    Validate that the file has an approved extension.
    Returns the normalized extension if valid; raises InvalidFileExtensionError otherwise.
    """
    if not filename:
        raise InvalidFileExtensionError("Filename cannot be empty.")

    allowed = allowed_extensions or settings.ALLOWED_EXTENSIONS
    ext = get_file_extension(filename)

    if not ext or ext not in {e.lower() for e in allowed}:
        allowed_list = ", ".join(sorted(allowed))
        raise InvalidFileExtensionError(
            f"Unsupported file extension '{ext}'. Allowed extensions are: {allowed_list}"
        )

    return ext


def validate_file_size(size_bytes: int, max_size_mb: int | None = None) -> None:
    """
    Validate that the file size is non-empty and does not exceed the maximum allowed size in MB.
    """
    if size_bytes <= 0:
        raise EmptyFileError("Uploaded file is empty (0 bytes).")

    limit_mb = max_size_mb if max_size_mb is not None else settings.MAX_UPLOAD_SIZE_MB
    max_bytes = limit_mb * 1024 * 1024

    if size_bytes > max_bytes:
        raise FileTooLargeError(
            f"File size ({size_bytes / (1024 * 1024):.2f} MB) exceeds maximum allowed limit of {limit_mb} MB."
        )


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing directory traversal patterns, illegal OS characters,
    and leading/trailing whitespace.
    """
    # Extract only the base name (prevents directory traversal e.g. ../../)
    base_name = Path(filename).name

    # Replace invalid filesystem characters (Windows and Unix) with an underscore
    # Forbidden in Windows: < > : " / \ | ? * and ASCII control characters
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', base_name).strip()

    # Disallow names that resolve to only dots or spaces
    if not sanitized or not sanitized.strip(". "):
        sanitized = "unnamed_file"

    return sanitized
