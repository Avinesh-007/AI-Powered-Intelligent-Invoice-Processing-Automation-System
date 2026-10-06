from pathlib import Path
import pytest
import pymupdf

from backend.models.invoice import METHOD_PDF_TEXT, METHOD_PDF_OCR
from backend.services.pdf_service import (
    process_pdf,
    CorruptPDFError,
    PDFProcessingError,
)


def create_sample_text_pdf(path: Path, content: str) -> Path:
    """Helper to create a deterministic text-based PDF using PyMuPDF."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4
    page.insert_text(pymupdf.Point(50, 100), content, fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


def test_native_pdf_text_extraction(tmp_path: Path):
    """Verify that a standard digital PDF is extracted using native PDF_TEXT method."""
    pdf_content = (
        "INVOICE #INV-2026-8801\n"
        "Vendor: TechCorp Global Solutions\n"
        "Date: 2026-10-06\n"
        "Total Amount Due: $4,500.00\n"
        "Payment Terms: Net 30"
    )
    pdf_file = tmp_path / "valid_invoice.pdf"
    create_sample_text_pdf(pdf_file, pdf_content)

    extracted_text, method = process_pdf(pdf_file)

    assert method == METHOD_PDF_TEXT
    assert "INVOICE #INV-2026-8801" in extracted_text
    assert "TechCorp Global Solutions" in extracted_text
    assert "$4,500.00" in extracted_text


def test_multipage_pdf_order_preservation(tmp_path: Path):
    """Verify that text across multiple pages is extracted in correct sequential order."""
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text(pymupdf.Point(50, 100), "PAGE ONE CONTENT: Invoice Summary", fontsize=12)
    p2 = doc.new_page()
    p2.insert_text(pymupdf.Point(50, 100), "PAGE TWO CONTENT: Detailed Line Items", fontsize=12)

    pdf_file = tmp_path / "multipage.pdf"
    doc.save(str(pdf_file))
    doc.close()

    extracted_text, method = process_pdf(pdf_file)

    assert method == METHOD_PDF_TEXT
    idx_p1 = extracted_text.find("PAGE ONE CONTENT")
    idx_p2 = extracted_text.find("PAGE TWO CONTENT")
    assert idx_p1 != -1
    assert idx_p2 != -1
    assert idx_p1 < idx_p2


def test_scanned_pdf_fallback_to_ocr(tmp_path: Path, monkeypatch):
    """Verify that a PDF with little or no text falls back to OCR rendering."""
    # Create empty page PDF with no extractable text
    doc = pymupdf.open()
    doc.new_page()
    pdf_file = tmp_path / "scanned_doc.pdf"
    doc.save(str(pdf_file))
    doc.close()

    # Deterministic OCR mock
    expected_ocr_output = "OCR Extracted Text from Scanned Document: $1,200.00"
    monkeypatch.setattr(
        "backend.services.pdf_service.ocr_pdf_pages",
        lambda doc, dpi=200: expected_ocr_output,
    )

    extracted_text, method = process_pdf(pdf_file)

    assert method == METHOD_PDF_OCR
    assert extracted_text == expected_ocr_output


def test_corrupt_pdf_handling(tmp_path: Path):
    """Verify that corrupted or unreadable PDF bytes raise CorruptPDFError."""
    corrupt_file = tmp_path / "corrupted.pdf"
    corrupt_file.write_bytes(b"%PDF-1.4 completely broken garbage bytes not a real pdf\x00\xff")

    with pytest.raises(CorruptPDFError):
        process_pdf(corrupt_file)


def test_nonexistent_pdf_handling(tmp_path: Path):
    """Verify that a nonexistent PDF path raises PDFProcessingError."""
    missing = tmp_path / "does_not_exist.pdf"
    with pytest.raises(PDFProcessingError):
        process_pdf(missing)
