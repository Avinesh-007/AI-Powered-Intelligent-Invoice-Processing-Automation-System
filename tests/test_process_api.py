import io
from pathlib import Path
from fastapi.testclient import TestClient
import pymupdf

from backend.models.invoice import Invoice, STATUS_PROCESSING_FAILED, STATUS_TEXT_EXTRACTED, STATUS_OCR_COMPLETED


def create_pdf_bytes(content: str) -> bytes:
    """Generate in-memory PDF bytes with digital text."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(pymupdf.Point(50, 100), content, fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_process_valid_text_pdf_invoice(client: TestClient):
    """Test full pipeline: upload text PDF, trigger processing, verify database and response."""
    invoice_text = (
        "INVOICE #INV-5501\n"
        "Vendor: Nexus Software Solutions\n"
        "Date: 2026-10-06\n"
        "Subtotal: $1,000.00\n"
        "Tax (10%): $100.00\n"
        "Total Amount: $1,100.00"
    )
    pdf_bytes = create_pdf_bytes(invoice_text)

    # 1. Upload
    up_resp = client.post(
        "/api/v1/invoices/upload",
        files={"file": ("invoice_test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert up_resp.status_code == 201
    inv_id = up_resp.json()["id"]

    # 2. Process
    proc_resp = client.post(f"/api/v1/invoices/{inv_id}/process")
    assert proc_resp.status_code == 200
    proc_data = proc_resp.json()

    assert proc_data["invoice_id"] == inv_id
    assert proc_data["status"] == STATUS_TEXT_EXTRACTED
    assert proc_data["extraction_method"] == "PDF_TEXT"
    assert proc_data["text_length"] > 0

    # 3. Retrieve Text
    text_resp = client.get(f"/api/v1/invoices/{inv_id}/text")
    assert text_resp.status_code == 200
    text_data = text_resp.json()

    assert text_data["invoice_id"] == inv_id
    assert "Nexus Software Solutions" in text_data["raw_text"]
    assert "$1,100.00" in text_data["raw_text"]


def test_process_image_invoice_with_mocked_ocr(client: TestClient, monkeypatch):
    """Test processing an uploaded image invoice using deterministic OCR mock."""
    mock_text = "RECEIPT #9812\nSTORE: Fresh Mart\nTOTAL: $45.50"

    monkeypatch.setattr(
        "backend.services.ocr_service.get_tesseract_command",
        lambda: "mock_tesseract",
    )
    monkeypatch.setattr(
        "pytesseract.image_to_string",
        lambda img, lang="eng": mock_text,
    )

    # Generate valid 200x80 PNG bytes
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (200, 80), color=(255, 255, 255)).save(buf, format="PNG")
    png_bytes = buf.getvalue()

    up_resp = client.post(
        "/api/v1/invoices/upload",
        files={"file": ("receipt.png", io.BytesIO(png_bytes), "image/png")},
    )
    assert up_resp.status_code == 201
    inv_id = up_resp.json()["id"]

    proc_resp = client.post(f"/api/v1/invoices/{inv_id}/process")
    assert proc_resp.status_code == 200
    data = proc_resp.json()

    assert data["status"] == STATUS_OCR_COMPLETED
    assert data["extraction_method"] == "IMAGE_OCR"
    assert data["text_length"] > 0


def test_process_nonexistent_invoice(client: TestClient):
    """Verify processing a nonexistent ID returns 404."""
    resp = client.post("/api/v1/invoices/999999/process")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_process_invoice_missing_file_on_disk(client: TestClient, db_session):
    """Verify missing physical storage file sets status to PROCESSING_FAILED and returns 404."""
    # Create invoice record with nonexistent file path
    inv = Invoice(
        original_filename="deleted.pdf",
        stored_filename="deleted_unique.pdf",
        file_path="/tmp/definitely_missing_file.pdf",
        file_size_bytes=100,
        status="UPLOADED",
    )
    db_session.add(inv)
    db_session.commit()
    db_session.refresh(inv)

    resp = client.post(f"/api/v1/invoices/{inv.id}/process")
    assert resp.status_code == 404

    # Verify status in database was updated to PROCESSING_FAILED
    updated_inv = db_session.query(Invoice).filter_by(id=inv.id).first()
    assert updated_inv.status == STATUS_PROCESSING_FAILED


def test_get_invoice_text_nonexistent(client: TestClient):
    """Verify getting text for nonexistent invoice returns 404."""
    resp = client.get("/api/v1/invoices/999999/text")
    assert resp.status_code == 404
