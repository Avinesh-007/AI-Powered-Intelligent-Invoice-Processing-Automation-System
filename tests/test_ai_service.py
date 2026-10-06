import json
import pytest
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
from backend.services.ai_extraction_service import (
    parse_gemini_json_response,
    extract_invoice_with_gemini,
    extract_and_persist_invoice,
    GeminiNotConfiguredError,
    MissingRawTextError,
    AIResponseParseError,
    AIExtractionError,
    is_gemini_configured,
)
from backend.services.document_service import InvoiceNotFoundError


def test_parse_valid_gemini_json():
    """Verify that pure valid JSON string is parsed into schema."""
    raw_json = json.dumps({
        "vendor_name": "Apex Global Corp",
        "vendor_address": "404 Cloud Blvd",
        "vendor_gstin": "29ABCDE1234F1Z5",
        "invoice_number": "INV-7788",
        "invoice_date": "2026-10-06",
        "due_date": "2026-11-06",
        "purchase_order_number": "PO-100",
        "currency": "USD",
        "subtotal": 500.0,
        "tax_amount": 50.0,
        "total_amount": 550.0,
        "payment_terms": "Net 15",
        "line_items": [
            {"description": "Consulting", "quantity": 5.0, "unit_price": 100.0, "tax_rate": 10.0, "line_total": 500.0}
        ],
    })
    result = parse_gemini_json_response(raw_json)
    assert result.vendor_name == "Apex Global Corp"
    assert result.total_amount == 550.0
    assert len(result.line_items) == 1
    assert result.line_items[0].description == "Consulting"


def test_parse_gemini_json_wrapped_in_markdown():
    """Verify that JSON wrapped in markdown code fences is cleaned and parsed."""
    markdown_wrapped = """```json
    {
      "vendor_name": "Markdown Vendor",
      "invoice_number": "INV-MD-1",
      "currency": "$",
      "total_amount": 99.99,
      "line_items": []
    }
    ```"""
    result = parse_gemini_json_response(markdown_wrapped)
    assert result.vendor_name == "Markdown Vendor"
    assert result.invoice_number == "INV-MD-1"
    assert result.total_amount == 99.99


def test_parse_gemini_empty_or_malformed_json_raises_error():
    """Verify that empty, non-dict, or broken JSON raises AIResponseParseError."""
    with pytest.raises(AIResponseParseError):
        parse_gemini_json_response("")

    with pytest.raises(AIResponseParseError):
        parse_gemini_json_response("This is not JSON at all")

    with pytest.raises(AIResponseParseError):
        parse_gemini_json_response("[1, 2, 3]")


def test_gemini_missing_api_key_raises_error(monkeypatch):
    """Verify that calling extract_invoice_with_gemini without an API key raises GeminiNotConfiguredError."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    with pytest.raises(GeminiNotConfiguredError):
        extract_invoice_with_gemini("Sample text", api_key=None)


def test_extract_and_persist_nonexistent_invoice(db_session: Session):
    """Verify that nonexistent invoice ID raises InvoiceNotFoundError."""
    with pytest.raises(InvoiceNotFoundError):
        extract_and_persist_invoice(999999, db_session)


def test_extract_and_persist_missing_raw_text(db_session: Session):
    """Verify that an invoice with no raw text raises MissingRawTextError."""
    inv = Invoice(
        original_filename="test.pdf",
        stored_filename="test_uniq.pdf",
        file_path="/tmp/test.pdf",
        file_size_bytes=100,
        status="UPLOADED",
        raw_text=None,
    )
    db_session.add(inv)
    db_session.commit()

    with pytest.raises(MissingRawTextError):
        extract_and_persist_invoice(inv.id, db_session)


def test_extract_and_persist_success(db_session: Session, monkeypatch):
    """Verify successful AI extraction lifecycle and database persistence."""
    inv = Invoice(
        original_filename="invoice_acme.pdf",
        stored_filename="invoice_acme_uniq.pdf",
        file_path="/tmp/invoice_acme.pdf",
        file_size_bytes=1024,
        status=STATUS_TEXT_EXTRACTED,
        raw_text="Vendor: Acme Inc\nInvoice: INV-9900\nTotal: $300.00",
    )
    db_session.add(inv)
    db_session.commit()

    mock_schema = InvoiceExtractionSchema(
        vendor_name="Acme Inc",
        vendor_address="100 Acme Way",
        vendor_gstin="27ABCDE1234F1Z1",
        invoice_number="INV-9900",
        invoice_date="2026-10-06",
        due_date="2026-11-06",
        currency="USD",
        subtotal=270.0,
        tax_amount=30.0,
        total_amount=300.0,
        payment_terms="Net 30",
        line_items=[
            LineItemSchema(description="Widget A", quantity=2.0, unit_price=100.0, tax_rate=10.0, line_total=200.0),
            LineItemSchema(description="Widget B", quantity=1.0, unit_price=70.0, tax_rate=10.0, line_total=70.0),
        ],
    )

    # Mock Gemini extraction call
    monkeypatch.setattr(
        "backend.services.ai_extraction_service.extract_invoice_with_gemini",
        lambda raw_text, api_key=None: mock_schema,
    )

    updated_inv = extract_and_persist_invoice(inv.id, db_session, api_key="test_key")

    assert updated_inv.status == STATUS_AI_EXTRACTED
    assert updated_inv.vendor_name == "Acme Inc"
    assert updated_inv.invoice_number == "INV-9900"
    assert updated_inv.total_amount == 300.0
    assert len(updated_inv.line_items) == 2
    assert updated_inv.line_items[0].description == "Widget A"
    assert updated_inv.line_items[1].line_total == 70.0


def test_extract_and_persist_failure_preserves_raw_text(db_session: Session, monkeypatch):
    """Verify that upon AI extraction failure, status is PROCESSING_FAILED and raw_text is preserved."""
    sample_text = "Vendor: Broken Invoice Data That Fails"
    inv = Invoice(
        original_filename="broken.pdf",
        stored_filename="broken_uniq.pdf",
        file_path="/tmp/broken.pdf",
        file_size_bytes=512,
        status=STATUS_TEXT_EXTRACTED,
        raw_text=sample_text,
    )
    db_session.add(inv)
    db_session.commit()

    def mock_failing_gemini(raw_text, api_key=None):
        raise AIExtractionError("Simulated Gemini API failure")

    monkeypatch.setattr(
        "backend.services.ai_extraction_service.extract_invoice_with_gemini",
        mock_failing_gemini,
    )

    with pytest.raises(AIExtractionError):
        extract_and_persist_invoice(inv.id, db_session, api_key="dummy_key")

    refreshed = db_session.query(Invoice).filter_by(id=inv.id).first()
    assert refreshed.status == STATUS_PROCESSING_FAILED
    assert refreshed.raw_text == sample_text
