import pytest
from backend.utils.validators import (
    validate_file_extension,
    validate_file_size,
    sanitize_filename,
    InvalidFileExtensionError,
    FileTooLargeError,
    EmptyFileError,
)


def test_valid_file_extensions():
    """Verify that supported invoice document extensions pass validation."""
    valid_names = [
        "invoice.pdf",
        "INVOICE.PDF",
        "receipt.png",
        "scan.PNG",
        "bill.jpg",
        "document.jpeg",
    ]
    for name in valid_names:
        ext = validate_file_extension(name)
        assert ext in {".pdf", ".png", ".jpg", ".jpeg"}


def test_invalid_file_extensions():
    """Verify that unsupported extensions raise InvalidFileExtensionError."""
    invalid_names = [
        "script.exe",
        "document.docx",
        "sheet.xlsx",
        "notes.txt",
        "payload.sh",
        "noextension",
        "",
    ]
    for name in invalid_names:
        with pytest.raises(InvalidFileExtensionError):
            validate_file_extension(name)


def test_valid_file_size():
    """Verify that sizes within limit do not raise errors."""
    # 5 MB in bytes
    size_5mb = 5 * 1024 * 1024
    validate_file_size(size_5mb, max_size_mb=10)


def test_zero_byte_file_rejected():
    """Verify that empty 0-byte files raise EmptyFileError."""
    with pytest.raises(EmptyFileError):
        validate_file_size(0)


def test_oversized_file_rejected():
    """Verify that files exceeding maximum MB raise FileTooLargeError."""
    # 11 MB in bytes
    size_11mb = 11 * 1024 * 1024
    with pytest.raises(FileTooLargeError):
        validate_file_size(size_11mb, max_size_mb=10)


def test_sanitize_filename_traversal():
    """Verify that path traversal characters are stripped safely."""
    assert sanitize_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert sanitize_filename("..\\..\\windows\\system32\\cmd.png") == "cmd.png"
    assert sanitize_filename("nested/sub/invoice.pdf") == "invoice.pdf"


def test_sanitize_filename_illegal_characters():
    """Verify that dangerous OS filesystem characters are converted to underscores."""
    dangerous = 'test:invoice*file?"name<1>|bar.pdf'
    sanitized = sanitize_filename(dangerous)
    for bad_char in ['<', '>', ':', '"', '/', '\\', '|', '?', '*']:
        assert bad_char not in sanitized
    assert sanitized.endswith(".pdf")


def test_sanitize_filename_blank_or_dots():
    """Verify fallback for empty or all-dot filenames."""
    assert sanitize_filename("...") == "unnamed_file"
    assert sanitize_filename("..") == "unnamed_file"
    assert sanitize_filename(".") == "unnamed_file"
