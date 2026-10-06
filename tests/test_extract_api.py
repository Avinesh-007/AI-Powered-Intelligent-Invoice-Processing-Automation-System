from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.invoice import (
    Invoice,
    InvoiceLineItem,
    STATUS_TEXT_EXTRACTED,
    STATUS_AI_EXTRACTED,
    STATUS_PROCESSING_FAILED,
)
from backend.schemas.invoice import InvoiceExtractionSchema, LineItemSchema


def test_api_extract_success(client: TestClient, db_session: Session, monkeypatch):
    """Test successful AI extraction endpoint execution with mocked AI service."""
    inv = Invoice(
        original_filename="server_bill.pdf",
        stored_filename="server_bill_uniq.pdf",
        file_path="/tmp/server_bill.pdf",
        file_size_bytes=2048,
        status=STATUS_TEXT_EXTRACTED,
        raw_text="Cloud Systems Inc\nInvoice: INV-4411\nTotal: $1,500.00",
    )
    db_session.add(inv)
    db_session.commit()
    db_session.refresh(inv)

    mock_schema = InvoiceExtractionSchema(
        vendor_name="Cloud Systems Inc",
        vendor_address="10 Silicon Alley",
        vendor_gstin="07AAAAA0000A1Z5",
        invoice_number="INV-4411",
        invoice_date="2026-10-06",
        currency="USD",
        subtotal=1350.0,
        tax_amount=150.0,
        total_amount=1500.0,
        line_items=[
            LineItemSchema(description="Cloud Virtual Machines", quantity=3.0, unit_price=450.0, line_total=1350.0)
        ],
    )

    monkeypatch.setattr(
        "backend.services.ai_extraction_service.extract_invoice_with_gemini",
        lambda raw_text, api_key=None: mock_schema,
    )
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "mock_key")

    resp = client.post(f"/api/v1/invoices/{inv.id}/extract")
    assert resp.status_code == 200
    data = resp.json()

    assert data["invoice_id"] == inv.id
    assert data["status"] == STATUS_AI_EXTRACTED
    assert data["vendor_name"] == "Cloud Systems Inc"
    assert data["invoice_number"] == "INV-4411"
    assert data["total_amount"] == 1500.0
    assert len(data["line_items"]) == 1
    assert data["line_items"][0]["description"] == "Cloud Virtual Machines"


def test_api_extract_missing_raw_text(client: TestClient, db_session: Session):
    """Verify that attempting AI extraction before text extraction returns 400 Bad Request."""
    inv = Invoice(
        original_filename="raw_missing.pdf",
        stored_filename="raw_missing_uniq.pdf",
        file_path="/tmp/raw_missing.pdf",
        file_size_bytes=100,
        status="UPLOADED",
        raw_text=None,
    )
    db_session.add(inv)
    db_session.commit()

    resp = client.post(f"/api/v1/invoices/{inv.id}/extract")
    assert resp.status_code == 400
    assert "extracted raw text" in resp.json()["detail"].lower()


def test_api_extract_nonexistent_invoice(client: TestClient):
    """Verify that extracting a nonexistent invoice ID returns 404."""
    resp = client.post("/api/v1/invoices/999999/extract")
    assert resp.status_code == 404


def test_api_extract_unconfigured_gemini(client: TestClient, db_session: Session, monkeypatch):
    """Verify that unconfigured Gemini API key returns 422 Unprocessable Entity."""
    inv = Invoice(
        original_filename="no_gemini.pdf",
        stored_filename="no_gemini_uniq.pdf",
        file_path="/tmp/no_gemini.pdf",
        file_size_bytes=100,
        status=STATUS_TEXT_EXTRACTED,
        raw_text="Sample text content",
    )
    db_session.add(inv)
    db_session.commit()

    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)

    resp = client.post(f"/api/v1/invoices/{inv.id}/extract")
    assert resp.status_code == 422
    assert "gemini api key is not configured" in resp.json()["detail"].lower()


def test_api_get_extracted_invoice(client: TestClient, db_session: Session):
    """Verify retrieving structured invoice and line items via GET /invoices/{id}/extracted."""
    inv = Invoice(
        original_filename="stored_invoice.pdf",
        stored_filename="stored_invoice_uniq.pdf",
        file_path="/tmp/stored.pdf",
        file_size_bytes=500,
        status=STATUS_AI_EXTRACTED,
        vendor_name="Tech Solutions",
        invoice_number="INV-2026-11",
        total_amount=999.0,
        currency="USD",
    )
    db_session.add(inv)
    db_session.commit()
    db_session.refresh(inv)

    item = InvoiceLineItem(
        invoice_id=inv.id,
        description="Database License",
        quantity=1.0,
        unit_price=999.0,
        line_total=999.0,
    )
    db_session.add(item)
    db_session.commit()

    resp = client.get(f"/api/v1/invoices/{inv.id}/extracted")
    assert resp.status_code == 200
    data = resp.json()

    assert data["invoice_id"] == inv.id
    assert data["vendor_name"] == "Tech Solutions"
    assert data["total_amount"] == 999.0
    assert len(data["line_items"]) == 1
    assert data["line_items"][0]["description"] == "Database License"


def test_api_get_extracted_nonexistent(client: TestClient):
    """Verify GET /invoices/{id}/extracted for nonexistent ID returns 404."""
    resp = client.get("/api/v1/invoices/999999/extracted")
    assert resp.status_code == 404
