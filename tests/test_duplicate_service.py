import pytest
from backend.models.invoice import Invoice
from backend.services.duplicate_detection_service import detect_duplicate_invoice


def test_duplicate_vendor_and_invoice_number(db_session):
    """Detect duplicate when vendor and invoice number match existing record."""
    inv1 = Invoice(
        original_filename="inv1.pdf",
        stored_filename="inv1.pdf",
        file_path="dummy/path",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="TechCorp Global",
        invoice_number="TCG-9988",
        total_amount=500.0,
    )
    db_session.add(inv1)
    db_session.commit()

    inv2 = Invoice(
        original_filename="inv2.pdf",
        stored_filename="inv2.pdf",
        file_path="dummy/path",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="techcorp global",  # Case difference
        invoice_number="TCG-9988",
        total_amount=500.0,
    )
    db_session.add(inv2)
    db_session.commit()

    res = detect_duplicate_invoice(inv2, db_session)
    assert res["is_duplicate"] is True
    assert res["duplicate_invoice_id"] == inv1.id
    assert res["match_type"] == "VENDOR_AND_INVOICE_NUMBER"
    assert "TCG-9988" in res["reason"]


def test_duplicate_vendor_date_and_amount(db_session):
    """Detect duplicate when vendor, date, and amount match even if invoice numbers differ."""
    inv1 = Invoice(
        original_filename="bill1.pdf",
        stored_filename="bill1.pdf",
        file_path="dummy/path",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="Office Supplies Depot",
        invoice_date="2026-03-01",
        total_amount=450.75,
    )
    db_session.add(inv1)
    db_session.commit()

    inv2 = Invoice(
        original_filename="bill2.pdf",
        stored_filename="bill2.pdf",
        file_path="dummy/path",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="Office Supplies Depot",
        invoice_date="2026-03-01",
        total_amount=450.75,
    )
    db_session.add(inv2)
    db_session.commit()

    res = detect_duplicate_invoice(inv2, db_session)
    assert res["is_duplicate"] is True
    assert res["duplicate_invoice_id"] == inv1.id
    assert res["match_type"] == "VENDOR_DATE_AMOUNT"


def test_duplicate_content_hash(db_session):
    """Detect duplicate when extracted document text is identical."""
    text_content = (
        "INVOICE FOR CONSULTING SERVICES\n"
        "Billed to: Acme Industries\n"
        "Total Due: 3200.00 USD\n"
        "Payment terms: Net 30 days\n"
        "Thank you for your business!"
    )
    inv1 = Invoice(
        original_filename="doc1.pdf",
        stored_filename="doc1.pdf",
        file_path="dummy/path",
        file_size_bytes=1000,
        status="TEXT_EXTRACTED",
        raw_text=text_content,
    )
    db_session.add(inv1)
    db_session.commit()

    inv2 = Invoice(
        original_filename="doc2.pdf",
        stored_filename="doc2.pdf",
        file_path="dummy/path",
        file_size_bytes=1000,
        status="TEXT_EXTRACTED",
        raw_text=text_content,
    )
    db_session.add(inv2)
    db_session.commit()

    res = detect_duplicate_invoice(inv2, db_session)
    assert res["is_duplicate"] is True
    assert res["duplicate_invoice_id"] == inv1.id
    assert res["match_type"] == "CONTENT_HASH"


def test_distinct_invoices_not_flagged(db_session):
    """Different invoice numbers from same vendor should not be marked as duplicates."""
    inv1 = Invoice(
        original_filename="legit1.pdf",
        stored_filename="legit1.pdf",
        file_path="dummy/path",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="Cloud Hosting Inc",
        invoice_number="CHI-100",
        total_amount=120.0,
        invoice_date="2026-01-01",
    )
    inv2 = Invoice(
        original_filename="legit2.pdf",
        stored_filename="legit2.pdf",
        file_path="dummy/path",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="Cloud Hosting Inc",
        invoice_number="CHI-101",
        total_amount=150.0,
        invoice_date="2026-02-01",
    )
    db_session.add_all([inv1, inv2])
    db_session.commit()

    res = detect_duplicate_invoice(inv2, db_session)
    assert res["is_duplicate"] is False
    assert res["duplicate_invoice_id"] is None
