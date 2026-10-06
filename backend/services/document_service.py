import logging
from pathlib import Path
from typing import Tuple
from sqlalchemy.orm import Session

from backend.models.invoice import (
    Invoice,
    STATUS_PROCESSING,
    STATUS_TEXT_EXTRACTED,
    STATUS_OCR_COMPLETED,
    STATUS_PROCESSING_FAILED,
    METHOD_IMAGE_OCR,
    METHOD_PDF_OCR,
)
from backend.services.ocr_service import extract_text_from_image, OCRError
from backend.services.pdf_service import process_pdf, PDFProcessingError
from backend.utils.text_cleaner import clean_text

logger = logging.getLogger(__name__)


class DocumentServiceError(Exception):
    """Base exception for document service processing operations."""
    pass


class InvoiceNotFoundError(DocumentServiceError):
    """Raised when the specified invoice ID is not found in the database."""
    pass


class InvoiceFileNotFoundError(DocumentServiceError):
    """Raised when the physical invoice file is missing from storage."""
    pass


def extract_document_text(file_path: Path | str) -> Tuple[str, str]:
    """
    Detect document format, extract raw text via native PDF parsing or OCR,
    and normalize text formatting.

    Returns:
        Tuple[str, str]: (cleaned_text, extraction_method)
    """
    path = Path(file_path)
    if not path.is_file():
        raise InvoiceFileNotFoundError(f"Target file does not exist on disk: {path}")

    ext = path.suffix.lower()

    if ext == ".pdf":
        raw_text, method = process_pdf(path)
    elif ext in {".png", ".jpg", ".jpeg"}:
        raw_text = extract_text_from_image(path)
        method = METHOD_IMAGE_OCR
    else:
        raise DocumentServiceError(f"Unsupported file format for text extraction: '{ext}'")

    cleaned = clean_text(raw_text)
    return cleaned, method


def process_invoice_record(invoice_id: int, db: Session) -> Invoice:
    """
    Process an uploaded invoice record:
    1. Loads invoice from database.
    2. Validates physical file existence.
    3. Updates status to PROCESSING.
    4. Extracts and cleans text.
    5. Saves raw_text, extraction_method, and updates status to TEXT_EXTRACTED or OCR_COMPLETED.
    6. On failure, updates status to PROCESSING_FAILED without crashing.
    """
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise InvoiceNotFoundError(f"Invoice with ID {invoice_id} not found.")

    file_path = Path(invoice.file_path)
    if not file_path.is_file():
        invoice.status = STATUS_PROCESSING_FAILED
        db.commit()
        raise InvoiceFileNotFoundError(
            f"Physical file '{invoice.stored_filename}' not found at {invoice.file_path}"
        )

    # Set status to PROCESSING
    invoice.status = STATUS_PROCESSING
    db.commit()
    db.refresh(invoice)

    try:
        cleaned_text, method = extract_document_text(file_path)

        invoice.raw_text = cleaned_text
        invoice.extraction_method = method

        if method in (METHOD_PDF_OCR, METHOD_IMAGE_OCR):
            invoice.status = STATUS_OCR_COMPLETED
            action_name = "OCR_COMPLETED"
        else:
            invoice.status = STATUS_TEXT_EXTRACTED
            action_name = "TEXT_EXTRACTED"

        db.commit()
        db.refresh(invoice)

        from backend.services.audit_service import record_audit_event
        try:
            record_audit_event(
                db=db,
                action=action_name,
                status="SUCCESS",
                invoice_id=invoice.id,
                message=f"Extracted {len(cleaned_text):,} characters using {method}",
            )
        except Exception:
            pass

        logger.info(
            f"Successfully processed Invoice #{invoice.id} via {method} "
            f"({len(cleaned_text)} characters extracted)"
        )
        return invoice

    except Exception as exc:
        logger.error(f"Failed to process Invoice #{invoice.id}: {exc}", exc_info=True)
        invoice.status = STATUS_PROCESSING_FAILED
        db.commit()
        from backend.services.audit_service import record_audit_event
        try:
            record_audit_event(
                db=db,
                action="TEXT_EXTRACTION_FAILED",
                status="FAILED",
                invoice_id=invoice.id,
                message=str(exc),
            )
        except Exception:
            pass
        raise
