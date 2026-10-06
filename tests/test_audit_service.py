import pytest
from backend.models.invoice import Invoice
from backend.services.audit_service import (
    record_audit_event,
    get_invoice_audit_trail,
    get_system_audit_trail,
)


def test_record_and_retrieve_audit_events(db_session):
    """Verify audit log event creation and invoice-specific history retrieval."""
    inv = Invoice(
        original_filename="audit_test.pdf",
        stored_filename="audit_test.pdf",
        file_path="dummy/path",
        file_size_bytes=1024,
        status="UPLOADED",
    )
    db_session.add(inv)
    db_session.commit()

    # Record two lifecycle events
    e1 = record_audit_event(
        db=db_session,
        action="INVOICE_UPLOADED",
        status="SUCCESS",
        invoice_id=inv.id,
        message="Initial upload verified",
    )
    e2 = record_audit_event(
        db=db_session,
        action="TEXT_EXTRACTED",
        status="SUCCESS",
        invoice_id=inv.id,
        message="Extracted 500 characters",
    )

    trail = get_invoice_audit_trail(db_session, invoice_id=inv.id)
    assert len(trail) == 2
    assert trail[0].action == "INVOICE_UPLOADED"
    assert trail[1].action == "TEXT_EXTRACTED"
    assert trail[0].invoice_id == inv.id


def test_system_audit_trail_global_view(db_session):
    """Verify global system audit logs retrieval with limit."""
    record_audit_event(
        db=db_session,
        action="SYSTEM_MAINTENANCE",
        status="SUCCESS",
        message="Global maintenance check",
    )
    record_audit_event(
        db=db_session,
        action="REPORT_GENERATED",
        status="SUCCESS",
        message="Summary PDF generated",
    )

    logs = get_system_audit_trail(db_session, limit=10)
    assert len(logs) >= 2
    assert any(log.action == "SYSTEM_MAINTENANCE" for log in logs)
    assert any(log.action == "REPORT_GENERATED" for log in logs)
