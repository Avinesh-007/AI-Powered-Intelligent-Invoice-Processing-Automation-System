import io
from pathlib import Path
from PIL import Image
import pytest

from backend.config import settings
from backend.services.ocr_service import (
    extract_text_from_image,
    open_and_validate_image,
    get_tesseract_command,
    is_tesseract_available,
    InvalidImageError,
    TesseractNotFoundError,
)


def create_sample_image_bytes(format_name: str = "PNG") -> bytes:
    """Create deterministic valid test image bytes."""
    img = Image.new("RGB", (200, 80), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format=format_name)
    return buf.getvalue()


def test_open_and_validate_image_valid_formats():
    """Verify image validator correctly handles PNG and JPEG bytes."""
    png_bytes = create_sample_image_bytes("PNG")
    img_png = open_and_validate_image(png_bytes)
    assert img_png.mode == "RGB"
    assert img_png.size == (200, 80)

    jpg_bytes = create_sample_image_bytes("JPEG")
    img_jpg = open_and_validate_image(jpg_bytes)
    assert img_jpg.mode == "RGB"


def test_open_and_validate_image_invalid_bytes():
    """Verify that corrupt or invalid image data raises InvalidImageError."""
    with pytest.raises(InvalidImageError):
        open_and_validate_image(b"Not an image at all")

    with pytest.raises(InvalidImageError):
        open_and_validate_image(b"")


def test_open_and_validate_image_missing_file(tmp_path: Path):
    """Verify that a nonexistent file path raises InvalidImageError."""
    missing_file = tmp_path / "nonexistent.png"
    with pytest.raises(InvalidImageError):
        open_and_validate_image(missing_file)


def test_ocr_extraction_with_controlled_mock(monkeypatch):
    """Verify OCR execution pipeline using deterministic fixture."""
    expected_text = "INVOICE #9981\nVENDOR: Acme Services\nTOTAL: $750.00"

    # Mock Tesseract presence and execution
    monkeypatch.setattr(
        "backend.services.ocr_service.get_tesseract_command",
        lambda: "mock_tesseract",
    )
    monkeypatch.setattr(
        "pytesseract.image_to_string",
        lambda img, lang="eng": expected_text,
    )

    img_bytes = create_sample_image_bytes("PNG")
    result = extract_text_from_image(img_bytes)

    assert result == expected_text
    assert "$750.00" in result


def test_ocr_missing_tesseract_raises_informative_error(monkeypatch):
    """Verify that when Tesseract is missing, a clear actionable error is raised."""
    monkeypatch.setattr(
        "backend.services.ocr_service.get_tesseract_command",
        lambda: None,
    )

    img_bytes = create_sample_image_bytes("PNG")
    with pytest.raises(TesseractNotFoundError) as exc_info:
        extract_text_from_image(img_bytes)

    err_msg = str(exc_info.value)
    assert "Tesseract OCR executable was not found" in err_msg
    assert "TESSERACT_CMD" in err_msg


def test_tesseract_discovery_with_explicit_setting(tmp_path: Path, monkeypatch):
    """Verify that settings.TESSERACT_CMD takes priority when configured."""
    fake_exe = tmp_path / "tesseract.exe"
    fake_exe.write_text("dummy binary")

    original_setting = settings.TESSERACT_CMD
    settings.TESSERACT_CMD = str(fake_exe)
    try:
        assert get_tesseract_command() == str(fake_exe)
        assert is_tesseract_available() is True
    finally:
        settings.TESSERACT_CMD = original_setting
