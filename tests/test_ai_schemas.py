import pytest
from pydantic import ValidationError
from backend.schemas.invoice import LineItemSchema, InvoiceExtractionSchema


def test_valid_invoice_schema():
    """Verify that a complete invoice dictionary validates into InvoiceExtractionSchema."""
    payload = {
        "vendor_name": "Acme Industrial Solutions",
        "vendor_address": "123 Technology Way, Silicon Valley, CA",
        "vendor_gstin": "06AAACA1234F1Z5",
        "invoice_number": "INV-2026-0042",
        "invoice_date": "2026-10-06",
        "due_date": "2026-11-06",
        "purchase_order_number": "PO-99120",
        "currency": "USD",
        "subtotal": 1200.0,
        "tax_amount": 120.0,
        "total_amount": 1320.0,
        "payment_terms": "Net 30",
        "line_items": [
            {
                "description": "Server Hosting",
                "quantity": 1.0,
                "unit_price": 800.0,
                "tax_rate": 10.0,
                "line_total": 800.0,
            },
            {
                "description": "Technical Support",
                "quantity": 4.0,
                "unit_price": 100.0,
                "tax_rate": 10.0,
                "line_total": 400.0,
            },
        ],
    }
    schema = InvoiceExtractionSchema.model_validate(payload)
    assert schema.vendor_name == "Acme Industrial Solutions"
    assert schema.invoice_number == "INV-2026-0042"
    assert schema.total_amount == 1320.0
    assert len(schema.line_items) == 2
    assert schema.line_items[0].description == "Server Hosting"
    assert schema.line_items[1].quantity == 4.0


def test_invoice_schema_optional_and_missing_fields():
    """Verify that absent/null fields default safely without error."""
    payload = {
        "vendor_name": None,
        "invoice_number": "INV-ONLY",
        "line_items": [],
    }
    schema = InvoiceExtractionSchema.model_validate(payload)
    assert schema.vendor_name is None
    assert schema.invoice_number == "INV-ONLY"
    assert schema.subtotal is None
    assert schema.tax_amount is None
    assert schema.total_amount is None
    assert schema.line_items == []


def test_multiple_line_items_validation():
    """Verify validation of multiple distinct line item objects."""
    items = [
        {"description": f"Item {i}", "quantity": float(i), "unit_price": 50.0, "line_total": i * 50.0}
        for i in range(1, 6)
    ]
    payload = {"invoice_number": "INV-MULTI", "line_items": items}
    schema = InvoiceExtractionSchema.model_validate(payload)
    assert len(schema.line_items) == 5
    assert schema.line_items[4].description == "Item 5"
    assert schema.line_items[4].quantity == 5.0
    assert schema.line_items[4].line_total == 250.0


def test_line_item_invalid_types_raise_validation_error():
    """Verify that type incompatibilities raise Pydantic ValidationError."""
    with pytest.raises(ValidationError):
        # quantity expecting float, passing non-numeric dict
        LineItemSchema(description="Bad item", quantity={"invalid": "type"})
