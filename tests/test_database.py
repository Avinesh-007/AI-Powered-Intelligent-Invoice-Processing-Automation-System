from sqlalchemy.orm import Session
from backend.models.invoice import Invoice


def test_database_table_creation(db_session: Session):
    """Test that the invoices table exists and can be queried."""
    count = db_session.query(Invoice).count()
    assert count == 0


def test_create_and_retrieve_invoice_record(db_session: Session):
    """Test creating an initial invoice record with defaults and nullable fields."""
    invoice = Invoice(
        original_filename="sample_invoice.pdf",
        stored_filename="unique_sample_invoice.pdf",
        file_path="/data/uploads/unique_sample_invoice.pdf",
        file_size_bytes=10240,
    )

    db_session.add(invoice)
    db_session.commit()
    db_session.refresh(invoice)

    assert invoice.id is not None
    assert invoice.original_filename == "sample_invoice.pdf"
    assert invoice.stored_filename == "unique_sample_invoice.pdf"
    assert invoice.file_size_bytes == 10240
    assert invoice.status == "UPLOADED"
    assert invoice.upload_timestamp is not None
    assert invoice.created_at is not None
    assert invoice.updated_at is not None

    # Verify all extraction-related fields are nullable initially
    assert invoice.vendor_name is None
    assert invoice.invoice_number is None
    assert invoice.invoice_date is None
    assert invoice.due_date is None
    assert invoice.subtotal is None
    assert invoice.tax_amount is None
    assert invoice.total_amount is None
    assert invoice.currency is None
    assert invoice.raw_text is None


def test_update_invoice_fields(db_session: Session):
    """Test updating fields on an existing invoice record."""
    invoice = Invoice(
        original_filename="bill.png",
        stored_filename="unique_bill.png",
        file_path="/data/uploads/unique_bill.png",
        file_size_bytes=4096,
    )
    db_session.add(invoice)
    db_session.commit()

    # Simulate subsequent phase extraction update
    invoice.vendor_name = "Acme Corp"
    invoice.total_amount = 450.00
    invoice.status = "COMPLETED"
    db_session.commit()
    db_session.refresh(invoice)

    updated_record = db_session.query(Invoice).filter_by(id=invoice.id).first()
    assert updated_record is not None
    assert updated_record.vendor_name == "Acme Corp"
    assert updated_record.total_amount == 450.00
    assert updated_record.status == "COMPLETED"
