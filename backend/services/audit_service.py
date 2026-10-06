from typing import List, Optional
from sqlalchemy.orm import Session
from backend.models.invoice import AuditLog, utc_now


def record_audit_event(
    db: Session,
    action: str,
    status: str,
    invoice_id: Optional[int] = None,
    message: Optional[str] = None,
) -> AuditLog:
    """
    Record an immutable audit event in the database.
    Captures major lifecycle milestones without logging sensitive credentials or secrets.
    """
    entry = AuditLog(
        invoice_id=invoice_id,
        action=action,
        status=status,
        message=message,
        timestamp=utc_now(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_invoice_audit_trail(db: Session, invoice_id: int) -> List[AuditLog]:
    """Retrieve full chronological audit history for a specific invoice."""
    return (
        db.query(AuditLog)
        .filter(AuditLog.invoice_id == invoice_id)
        .order_by(AuditLog.id.asc())
        .all()
    )


def get_system_audit_trail(db: Session, limit: int = 100) -> List[AuditLog]:
    """Retrieve recent system-wide audit activity logs, newest first."""
    return (
        db.query(AuditLog)
        .order_by(AuditLog.id.desc())
        .limit(limit)
        .all()
    )
