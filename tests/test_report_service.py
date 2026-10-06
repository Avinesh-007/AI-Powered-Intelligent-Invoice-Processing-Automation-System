import pytest
from backend.models.invoice import Invoice, InvoiceLineItem
from backend.services.report_service import (
    generate_invoices_csv,
    generate_line_items_csv,
    generate_analytics_summary_pdf,
    generate_invoice_detail_pdf,
)


def test_generate_invoices_csv(db_session):
    """Verify CSV string contains required columns and invoice data."""
    inv = Invoice(
        original_filename="sample.pdf",
        stored_filename="sample.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AUTOMATED",
        vendor_name="Acme Solutions",
        invoice_number="INV-2026-99",
        total_amount=1500.0,
        expense_category="Equipment",
    )
    db_session.add(inv)
    db_session.commit()

    csv_data = generate_invoices_csv(db_session)
    assert "Invoice ID,Vendor,Invoice Number" in csv_data
    assert "Acme Solutions" in csv_data
    assert "INV-2026-99" in csv_data
    assert "1500.00" in csv_data
    assert "Equipment" in csv_data


def test_generate_line_items_csv(db_session):
    """Verify line items CSV export structure."""
    inv = Invoice(
        original_filename="items.pdf",
        stored_filename="items.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="Server Parts Co",
        invoice_number="SPC-100",
    )
    db_session.add(inv)
    db_session.commit()

    it = InvoiceLineItem(
        invoice_id=inv.id,
        description="SSD Storage Drive 2TB",
        quantity=5.0,
        unit_price=120.0,
        tax_rate=10.0,
        line_total=600.0,
    )
    db_session.add(it)
    db_session.commit()

    csv_data = generate_line_items_csv(db_session)
    assert "Description,Quantity,Unit Price" in csv_data
    assert "SSD Storage Drive 2TB" in csv_data
    assert "600.00" in csv_data


def test_generate_analytics_summary_pdf(db_session):
    """Verify executive summary PDF generation returns valid PDF binary."""
    pdf_bytes = generate_analytics_summary_pdf(db_session)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF")  # Valid standard PDF header


def test_generate_invoice_detail_pdf(db_session):
    """Verify individual invoice PDF generation returns valid PDF binary."""
    inv = Invoice(
        original_filename="invoice_report.pdf",
        stored_filename="invoice_report.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AUTOMATED",
        vendor_name="Apex Logistics",
        invoice_number="AL-777",
        subtotal=1000.0,
        tax_amount=100.0,
        total_amount=1100.0,
        currency="USD",
        approval_recommendation="AUTO_APPROVE",
    )
    db_session.add(inv)
    db_session.commit()

    pdf_bytes = generate_invoice_detail_pdf(db_session, invoice_id=inv.id)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF")
