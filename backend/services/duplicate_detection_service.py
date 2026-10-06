import hashlib
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.models.invoice import Invoice


def _normalize_str(val: Optional[str]) -> str:
    """Normalize string for robust comparison: lowercase, strip extra whitespace."""
    if not val:
        return ""
    return " ".join(val.strip().lower().split())


def _compute_text_hash(text: Optional[str]) -> Optional[str]:
    """Compute sha256 hash of normalized text content."""
    if not text or len(text.strip()) < 40:
        return None
    normalized = " ".join(text.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def detect_duplicate_invoice(invoice: Invoice, db: Session) -> Dict[str, Any]:
    """
    Detect whether the given invoice is a duplicate of any existing record in the database.

    Multi-attribute criteria:
    1. Exact Vendor + Invoice Number match.
    2. Identical Vendor + Invoice Date + Total Amount match.
    3. Document Content Hash match (identical extracted text).

    Note:
    - Never uses file name alone for duplicate detection.
    - Excludes the invoice itself from comparisons.
    - Suspicious duplicates are flagged with explanatory metadata rather than deleted.
    """
    # Query potential duplicates excluding self
    query = db.query(Invoice).filter(Invoice.id != invoice.id)

    curr_vendor = _normalize_str(invoice.vendor_name)
    curr_number = _normalize_str(invoice.invoice_number)
    curr_date = _normalize_str(invoice.invoice_date)
    curr_total = invoice.total_amount
    curr_hash = _compute_text_hash(invoice.raw_text)

    # 1. Exact Vendor + Invoice Number Match
    if curr_vendor and curr_number:
        candidates = query.all()
        for cand in candidates:
            cand_vendor = _normalize_str(cand.vendor_name)
            cand_number = _normalize_str(cand.invoice_number)
            if cand_vendor and cand_number and cand_vendor == curr_vendor and cand_number == curr_number:
                return {
                    "is_duplicate": True,
                    "duplicate_invoice_id": cand.id,
                    "reason": (
                        f"Duplicate invoice number '{invoice.invoice_number}' already exists "
                        f"for vendor '{invoice.vendor_name}' in Invoice #{cand.id}."
                    ),
                    "match_type": "VENDOR_AND_INVOICE_NUMBER",
                }

    # 2. Identical Vendor + Invoice Date + Total Amount Match
    if curr_vendor and curr_date and curr_total is not None:
        candidates = query.all()
        for cand in candidates:
            cand_vendor = _normalize_str(cand.vendor_name)
            cand_date = _normalize_str(cand.invoice_date)
            cand_total = cand.total_amount
            if (
                cand_vendor == curr_vendor
                and cand_date == curr_date
                and cand_total is not None
                and abs(cand_total - curr_total) < 0.01
            ):
                return {
                    "is_duplicate": True,
                    "duplicate_invoice_id": cand.id,
                    "reason": (
                        f"Identical vendor '{invoice.vendor_name}', date '{invoice.invoice_date}', "
                        f"and total ({curr_total:.2f}) matches existing Invoice #{cand.id}."
                    ),
                    "match_type": "VENDOR_DATE_AMOUNT",
                }

    # 3. Document Content Hash Match (Identical OCR / Extracted Text)
    if curr_hash:
        candidates = query.filter(Invoice.raw_text.isnot(None)).all()
        for cand in candidates:
            cand_hash = _compute_text_hash(cand.raw_text)
            if cand_hash and cand_hash == curr_hash:
                return {
                    "is_duplicate": True,
                    "duplicate_invoice_id": cand.id,
                    "reason": (
                        f"Extracted document text content is identical to existing Invoice #{cand.id}."
                    ),
                    "match_type": "CONTENT_HASH",
                }

    return {
        "is_duplicate": False,
        "duplicate_invoice_id": None,
        "reason": None,
        "match_type": None,
    }
