from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, Boolean
from backend.database.base import Base


def utc_now() -> datetime:
    """Return current UTC timestamp without timezone offset issues."""
    return datetime.now(timezone.utc)


# Processing status constants
STATUS_UPLOADED = "UPLOADED"
STATUS_PROCESSING = "PROCESSING"
STATUS_TEXT_EXTRACTED = "TEXT_EXTRACTED"
STATUS_OCR_COMPLETED = "OCR_COMPLETED"
STATUS_AI_PROCESSING = "AI_PROCESSING"
STATUS_AI_EXTRACTED = "AI_EXTRACTED"
STATUS_ANALYZED = "ANALYZED"
STATUS_AUTOMATED = "AUTOMATED"
STATUS_PROCESSING_FAILED = "PROCESSING_FAILED"

# Approval recommendation constants
REC_AUTO_APPROVE = "AUTO_APPROVE"
REC_MANUAL_REVIEW = "MANUAL_REVIEW"
REC_REJECT_RECOMMENDED = "REJECT_RECOMMENDED"

# Risk level constants
RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"

# Validation status constants
VAL_PASSED = "PASSED"
VAL_WARNINGS = "WARNINGS"
VAL_FAILED = "FAILED"

# Audit Action Constants (Phase 5)
ACTION_UPLOAD = "INVOICE_UPLOADED"
ACTION_TEXT_EXTRACTED = "TEXT_EXTRACTED"
ACTION_OCR_COMPLETED = "OCR_COMPLETED"
ACTION_AI_EXTRACTED = "AI_EXTRACTION_COMPLETED"
ACTION_VALIDATION_COMPLETED = "VALIDATION_COMPLETED"
ACTION_DUPLICATE_CHECK_COMPLETED = "DUPLICATE_CHECK_COMPLETED"
ACTION_CLASSIFICATION_COMPLETED = "CLASSIFICATION_COMPLETED"
ACTION_ANOMALY_COMPLETED = "ANOMALY_ANALYSIS_COMPLETED"
ACTION_RISK_COMPLETED = "RISK_ASSESSMENT_COMPLETED"
ACTION_AUTOMATION_COMPLETED = "AUTOMATION_COMPLETED"
ACTION_REPORT_GENERATED = "REPORT_GENERATED"
ACTION_STATUS_UPDATED = "STATUS_UPDATED"

# Extraction method constants
METHOD_PDF_TEXT = "PDF_TEXT"
METHOD_PDF_OCR = "PDF_OCR"
METHOD_IMAGE_OCR = "IMAGE_OCR"


class Invoice(Base):
    """SQLAlchemy model representing an uploaded and processed invoice document."""

    __tablename__ = "invoices"

    # Primary key identifier
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Document file attributes
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False, unique=True, index=True)
    file_path = Column(String(500), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    upload_timestamp = Column(DateTime, default=utc_now, nullable=False)

    # Processing lifecycle status
    status = Column(String(50), default="UPLOADED", nullable=False, index=True)

    # Extraction method used: 'PDF_TEXT', 'PDF_OCR', 'IMAGE_OCR'
    extraction_method = Column(String(50), nullable=True, index=True)

    # Vendor information (extracted in Phase 3)
    vendor_name = Column(String(255), nullable=True)
    vendor_address = Column(Text, nullable=True)
    vendor_gstin = Column(String(50), nullable=True)

    # Invoice metadata
    invoice_number = Column(String(100), nullable=True, index=True)
    invoice_date = Column(String(50), nullable=True)
    due_date = Column(String(50), nullable=True)
    purchase_order_number = Column(String(100), nullable=True)
    payment_terms = Column(String(255), nullable=True)

    # Financial totals
    subtotal = Column(Float, nullable=True)
    tax_amount = Column(Float, nullable=True)
    total_amount = Column(Float, nullable=True)
    currency = Column(String(10), nullable=True)

    # Full raw extracted text content
    raw_text = Column(Text, nullable=True)

    # Intelligent Automation & Validation (Phase 4)
    expense_category = Column(String(100), nullable=True, index=True)
    classification_method = Column(String(50), nullable=True)
    validation_status = Column(String(50), nullable=True, index=True)
    validation_errors = Column(Text, nullable=True)
    validation_warnings = Column(Text, nullable=True)
    duplicate_flag = Column(Boolean, default=False, nullable=False, index=True)
    duplicate_invoice_id = Column(Integer, nullable=True)
    duplicate_reason = Column(String(255), nullable=True)
    anomaly_flag = Column(Boolean, default=False, nullable=False, index=True)
    anomaly_reasons = Column(Text, nullable=True)
    risk_score = Column(Integer, nullable=True, index=True)
    risk_level = Column(String(20), nullable=True, index=True)
    risk_reasons = Column(Text, nullable=True)
    approval_recommendation = Column(String(50), nullable=True, index=True)
    approval_reason = Column(Text, nullable=True)
    automation_processed_at = Column(DateTime, nullable=True)

    # Record audit timestamps
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # One-to-many relationship with parsed line items
    from sqlalchemy.orm import relationship
    line_items = relationship(
        "InvoiceLineItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceLineItem.id",
    )

    def __repr__(self) -> str:
        return f"<Invoice(id={self.id}, file='{self.original_filename}', status='{self.status}')>"


class InvoiceLineItem(Base):
    """SQLAlchemy model representing an individual invoice line item."""

    __tablename__ = "invoice_line_items"

    from sqlalchemy import ForeignKey
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)

    description = Column(String(500), nullable=False)
    quantity = Column(Float, nullable=True)
    unit_price = Column(Float, nullable=True)
    tax_rate = Column(Float, nullable=True)
    line_total = Column(Float, nullable=True)

    from sqlalchemy.orm import relationship
    invoice = relationship("Invoice", back_populates="line_items")

    def __repr__(self) -> str:
        return f"<InvoiceLineItem(id={self.id}, invoice_id={self.invoice_id}, desc='{self.description[:25]}', total={self.line_total})>"


class AuditLog(Base):
    """SQLAlchemy model representing an audit log entry for invoice lifecycle events."""

    __tablename__ = "audit_logs"

    from sqlalchemy import ForeignKey
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)
    status = Column(String(50), nullable=False)
    message = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=utc_now, nullable=False, index=True)

    from sqlalchemy.orm import relationship
    invoice = relationship("Invoice", backref="audit_logs")

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, invoice_id={self.invoice_id}, action='{self.action}', status='{self.status}')>"
