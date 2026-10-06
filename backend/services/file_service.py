import uuid
from pathlib import Path
from sqlalchemy.orm import Session
from backend.config import settings
from backend.models.invoice import Invoice
from backend.utils.validators import (
    validate_file_extension,
    validate_file_size,
    sanitize_filename,
)


def save_and_register_invoice(
    filename: str,
    file_bytes: bytes,
    db: Session,
) -> Invoice:
    """
    Validate, safely store an uploaded invoice document on disk,
    and persist an initial invoice record in the database.
    """
    # 1. Validate file extension
    validate_file_extension(filename)

    # 2. Validate file size
    validate_file_size(len(file_bytes))

    # 3. Sanitize original filename
    safe_name = sanitize_filename(filename)

    # 4. Generate unique stored filename to avoid collisions and directory traversal
    unique_prefix = uuid.uuid4().hex[:12]
    stored_filename = f"{unique_prefix}_{safe_name}"

    # 5. Persist file bytes to uploads directory
    upload_dir = settings.get_absolute_upload_dir()
    destination_path = upload_dir / stored_filename

    with open(destination_path, "wb") as f:
        f.write(file_bytes)

    # 6. Create database record
    invoice = Invoice(
        original_filename=safe_name,
        stored_filename=stored_filename,
        file_path=str(destination_path.resolve()),
        file_size_bytes=len(file_bytes),
        status="UPLOADED",
    )

    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    # 7. Record audit event
    from backend.services.audit_service import record_audit_event
    from backend.models.invoice import ACTION_UPLOAD
    try:
        record_audit_event(
            db=db,
            action=ACTION_UPLOAD,
            status="SUCCESS",
            invoice_id=invoice.id,
            message=f"Uploaded '{safe_name}' ({len(file_bytes):,} bytes)",
        )
    except Exception:
        pass

    return invoice
