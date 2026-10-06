import pytest
from backend.models.invoice import Invoice, InvoiceLineItem, VAL_PASSED, VAL_WARNINGS, VAL_FAILED
from backend.services.invoice_validation_service import validate_invoice, parse_date_string


def test_parse_date_string():
    """Verify robust date parsing across formats."""
    d1 = parse_date_string("2026-03-15")
    assert d1 is not None and d1.year == 2026 and d1.month == 3 and d1.day == 15

    d2 = parse_date_string("15/03/2026")
    assert d2 is not None and d2.day == 15

    d3 = parse_date_string("March 15, 2026")
    assert d3 is not None and d3.month == 3

    assert parse_date_string(None) is None
    assert parse_date_string("") is None
    assert parse_date_string("invalid-date-string") is None


def test_validation_clean_invoice(db_session):
    """Clean, mathematically sound invoice should pass validation cleanly."""
    inv = Invoice(
        original_filename="valid.pdf",
        stored_filename="valid_1.pdf",
        file_path="dummy/path",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="Acme Corp",
        invoice_number="INV-2026-001",
        invoice_date="2026-01-15",
        due_date="2026-02-15",
        subtotal=1000.0,
        tax_amount=100.0,
        total_amount=1100.0,
        currency="USD",
    )
    db_session.add(inv)
    db_session.commit()

    item = InvoiceLineItem(
        invoice_id=inv.id,
        description="Software License",
        quantity=2.0,
        unit_price=500.0,
        tax_rate=10.0,
        line_total=1000.0,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(inv)

    res = validate_invoice(inv)
    assert res["passed"] is True
    assert res["status"] == VAL_PASSED
    assert len(res["errors"]) == 0
    assert len(res["warnings"]) == 0


def test_validation_financial_mismatch(db_session):
    """Subtotal + Tax != Total should result in validation failure."""
    inv = Invoice(
        original_filename="mismatch.pdf",
        stored_filename="mismatch_1.pdf",
        file_path="dummy/path",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="Acme Corp",
        invoice_number="INV-2026-002",
        invoice_date="2026-01-15",
        subtotal=1000.0,
        tax_amount=100.0,
        total_amount=1500.0,  # Intentional discrepancy ($400 difference)
        currency="USD",
    )
    db_session.add(inv)
    db_session.commit()

    res = validate_invoice(inv)
    assert res["passed"] is False
    assert res["status"] == VAL_FAILED
    assert any("Discrepancy" in err for err in res["errors"])


def test_validation_missing_total_and_negative_total(db_session):
    """Missing or negative total amount must trigger validation errors."""
    inv1 = Invoice(
        original_filename="no_total.pdf",
        stored_filename="no_total_1.pdf",
        file_path="dummy/path",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="Acme Corp",
        total_amount=None,
    )
    db_session.add(inv1)
    db_session.commit()

    res1 = validate_invoice(inv1)
    assert res1["passed"] is False
    assert any("Total Amount" in err for err in res1["errors"])

    inv2 = Invoice(
        original_filename="neg_total.pdf",
        stored_filename="neg_total_1.pdf",
        file_path="dummy/path",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="Acme Corp",
        total_amount=-50.0,
    )
    db_session.add(inv2)
    db_session.commit()

    res2 = validate_invoice(inv2)
    assert res2["passed"] is False
    assert any("negative" in err.lower() for err in res2["errors"])


def test_validation_due_date_earlier_than_invoice_date(db_session):
    """Due date before invoice date must trigger error."""
    inv = Invoice(
        original_filename="bad_dates.pdf",
        stored_filename="bad_dates_1.pdf",
        file_path="dummy/path",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="Acme Corp",
        invoice_number="INV-2026-003",
        invoice_date="2026-02-15",
        due_date="2026-01-15",  # Earlier than invoice date
        total_amount=100.0,
        currency="USD",
    )
    db_session.add(inv)
    db_session.commit()

    res = validate_invoice(inv)
    assert res["passed"] is False
    assert any("earlier than invoice date" in err for err in res["errors"])


def test_validation_missing_optional_fields_triggers_warnings_not_rejection(db_session):
    """Missing optional fields like invoice_number, currency yield warnings but passed=True."""
    inv = Invoice(
        original_filename="minimal.pdf",
        stored_filename="minimal_1.pdf",
        file_path="dummy/path",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        total_amount=250.0,
        # Missing vendor_name, invoice_number, invoice_date, currency
    )
    db_session.add(inv)
    db_session.commit()

    res = validate_invoice(inv)
    assert res["passed"] is True
    assert res["status"] == VAL_WARNINGS
    assert len(res["errors"]) == 0
    assert len(res["warnings"]) >= 3
