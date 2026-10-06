import io
import os
import shutil
from pathlib import Path
from typing import Union
from PIL import Image, UnidentifiedImageError
import pytesseract

from backend.config import settings


class OCRError(Exception):
    """Base exception for optical character recognition failures."""
    pass


class TesseractNotFoundError(OCRError):
    """Raised when the Tesseract OCR executable is not found on the system."""
    pass


class InvalidImageError(OCRError):
    """Raised when an uploaded image is corrupted or in an unreadable format."""
    pass


def get_tesseract_command() -> str | None:
    """
    Locate the Tesseract executable using the following priority:
    1. Explicit TESSERACT_CMD setting in configuration/.env
    2. System PATH (shutil.which('tesseract'))
    3. Common Windows installation directories
    """
    if settings.TESSERACT_CMD and Path(settings.TESSERACT_CMD).is_file():
        return settings.TESSERACT_CMD

    path_cmd = shutil.which("tesseract")
    if path_cmd:
        return path_cmd

    # Standard Windows install locations
    common_windows_paths = [
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        common_windows_paths.append(
            Path(local_app_data) / "Programs" / "Tesseract-OCR" / "tesseract.exe"
        )

    for p in common_windows_paths:
        if p.is_file():
            return str(p)

    return None


def is_tesseract_available() -> bool:
    """Check whether Tesseract is configured and accessible."""
    return get_tesseract_command() is not None


def configure_tesseract() -> None:
    """Configure pytesseract with the discovered executable path."""
    cmd = get_tesseract_command()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


def open_and_validate_image(
    image_input: Union[str, Path, bytes, Image.Image]
) -> Image.Image:
    """
    Safely open and validate an image from a file path, raw bytes, or PIL Image.
    Returns a loaded PIL Image in RGB format.
    """
    if isinstance(image_input, Image.Image):
        img = image_input
    elif isinstance(image_input, (str, Path)):
        path = Path(image_input)
        if not path.is_file():
            raise InvalidImageError(f"Image file does not exist: {path}")
        try:
            img = Image.open(path)
        except (UnidentifiedImageError, OSError) as exc:
            raise InvalidImageError(f"Cannot identify image file '{path.name}': {exc}")
    elif isinstance(image_input, bytes):
        if not image_input:
            raise InvalidImageError("Cannot process empty image byte stream.")
        try:
            img = Image.open(io.BytesIO(image_input))
        except (UnidentifiedImageError, OSError) as exc:
            raise InvalidImageError(f"Cannot decode image from bytes: {exc}")
    else:
        raise InvalidImageError(f"Unsupported image input type: {type(image_input)}")

    try:
        # Load pixels to detect truncated/corrupted files early
        img.load()
    except Exception as exc:
        raise InvalidImageError(f"Corrupt or truncated image data: {exc}")

    # Convert to RGB mode if in RGBA, CMYK, Palette (P), etc., to ensure OCR compatibility
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    return img


def extract_text_from_image(
    image_input: Union[str, Path, bytes, Image.Image],
    lang: str = "eng",
) -> str:
    """
    Perform Tesseract OCR on an image and return raw extracted text.
    Handles image validation, missing Tesseract binaries, and OCR failures.
    """
    tess_cmd = get_tesseract_command()
    if not tess_cmd:
        raise TesseractNotFoundError(
            "Tesseract OCR executable was not found. Please install Tesseract (e.g. from "
            "https://github.com/UB-Mannheim/tesseract/wiki) and configure TESSERACT_CMD in your .env "
            "file, or ensure it is added to your system PATH."
        )

    # Set configured command path
    pytesseract.pytesseract.tesseract_cmd = tess_cmd

    # Validate image input
    img = open_and_validate_image(image_input)

    try:
        raw_text = pytesseract.image_to_string(img, lang=lang)
        return raw_text or ""
    except pytesseract.TesseractNotFoundError:
        raise TesseractNotFoundError(
            f"Configured Tesseract command '{tess_cmd}' could not be executed."
        )
    except Exception as exc:
        raise OCRError(f"Tesseract OCR execution failed: {exc}")
