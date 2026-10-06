import io
from pathlib import Path
from typing import Tuple
from PIL import Image
import pymupdf

from backend.config import settings
from backend.models.invoice import METHOD_PDF_TEXT, METHOD_PDF_OCR
from backend.services.ocr_service import extract_text_from_image, OCRError


class PDFProcessingError(Exception):
    """Base exception for PDF document processing errors."""
    pass


class CorruptPDFError(PDFProcessingError):
    """Raised when a PDF file is damaged, encrypted, or cannot be parsed."""
    pass


class EmptyPDFError(PDFProcessingError):
    """Raised when a PDF document has no pages."""
    pass


def extract_native_pdf_text(doc: pymupdf.Document) -> Tuple[str, int]:
    """
    Extract embedded native digital text page by page preserving page order.
    Returns (combined_text, total_non_whitespace_char_count).
    """
    page_texts = []
    total_chars = 0

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text") or ""
        trimmed = text.strip()
        if trimmed:
            total_chars += len(trimmed)
            page_texts.append(text)

    combined = "\n\n".join(page_texts)
    return combined, total_chars


def ocr_pdf_pages(doc: pymupdf.Document, dpi: int = 200) -> str:
    """
    Render each PDF page as an image and run Tesseract OCR.
    Preserves page order and joins extracted page text.
    """
    ocr_page_texts = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        # Render page to high-quality image pixmap for OCR
        pix = page.get_pixmap(dpi=dpi)
        image_bytes = pix.tobytes("png")

        page_text = extract_text_from_image(image_bytes)
        if page_text.strip():
            ocr_page_texts.append(page_text)

    return "\n\n".join(ocr_page_texts)


def process_pdf(pdf_path: Path | str) -> Tuple[str, str]:
    """
    Process a PDF invoice file:
    1. Attempts native digital text extraction via PyMuPDF.
    2. If sufficient extractable text is found, returns (text, METHOD_PDF_TEXT).
    3. If little or no text is detected (scanned PDF), renders pages and runs Tesseract OCR,
       returning (text, METHOD_PDF_OCR).

    Raises CorruptPDFError if the PDF is damaged or cannot be parsed.
    """
    file_path = Path(pdf_path)
    if not file_path.is_file():
        raise PDFProcessingError(f"PDF file not found: {file_path}")

    try:
        doc = pymupdf.open(str(file_path))
    except Exception as exc:
        raise CorruptPDFError(f"Failed to open PDF '{file_path.name}': {exc}")

    try:
        if len(doc) == 0:
            raise EmptyPDFError(f"PDF '{file_path.name}' has 0 pages.")

        # Step 1: Attempt native text extraction
        native_text, char_count = extract_native_pdf_text(doc)

        # Step 2: Evaluate if native text is sufficient
        if char_count >= settings.PDF_MIN_TEXT_CHARS:
            return native_text, METHOD_PDF_TEXT

        # Step 3: Fall back to rendering pages and executing OCR for scanned PDFs
        ocr_text = ocr_pdf_pages(doc)
        return ocr_text, METHOD_PDF_OCR

    except (PDFProcessingError, OCRError):
        raise
    except Exception as exc:
        raise PDFProcessingError(f"Unexpected error while processing PDF: {exc}")
    finally:
        doc.close()
