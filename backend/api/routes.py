from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status, Response
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.models.invoice import Invoice
from backend.schemas.invoice import (
    HealthResponse,
    InvoiceRead,
    InvoiceProcessResponse,
    InvoiceTextResponse,
    InvoiceStructuredResponse,
    InvoiceAnalysisResponse,
    AuditLogRead,
    DashboardSummarySchema,
    SpendAnalyticsSchema,
    SystemHealthSchema,
)
from backend.services.file_service import save_and_register_invoice
from backend.utils.validators import ValidationError

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System Health Check",
    tags=["Health"],
)
def get_health() -> HealthResponse:
    """Return application operational health status."""
    return HealthResponse(status="healthy")


@router.post(
    "/invoices/upload",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an invoice file",
    tags=["Invoices"],
)
async def upload_invoice(
    file: UploadFile = File(..., description="Invoice PDF or image file (PNG, JPG, JPEG)"),
    db: Session = Depends(get_db),
) -> InvoiceRead:
    """
    Upload and register an invoice document.
    Validates file extension and size, saves file to storage, and creates initial database record.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided in upload payload.",
        )

    try:
        content = await file.read()
        invoice = save_and_register_invoice(
            filename=file.filename,
            file_bytes=content,
            db=db,
        )
        return invoice
    except ValidationError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while processing the upload: {str(err)}",
        )


@router.get(
    "/invoices",
    response_model=List[InvoiceRead],
    summary="List all uploaded invoices",
    tags=["Invoices"],
)
def list_invoices(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> List[InvoiceRead]:
    """Retrieve paginated list of uploaded invoices, newest first."""
    invoices = (
        db.query(Invoice)
        .order_by(Invoice.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return invoices


@router.get(
    "/invoices/{invoice_id}",
    response_model=InvoiceRead,
    summary="Get invoice by ID",
    tags=["Invoices"],
)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
) -> InvoiceRead:
    """Retrieve an individual invoice record by its unique database ID."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice with ID {invoice_id} was not found.",
        )
    return invoice


@router.post(
    "/invoices/{invoice_id}/process",
    response_model=InvoiceProcessResponse,
    summary="Process invoice and extract text",
    tags=["Invoices"],
)
def process_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
) -> InvoiceProcessResponse:
    """
    Trigger text extraction pipeline on an uploaded invoice:
    - Identifies PDF vs image.
    - Native PyMuPDF extraction with fallback to OCR for scanned PDFs.
    - Tesseract OCR for PNG/JPG/JPEG images.
    - Normalizes and cleans extracted text.
    - Stores raw_text and updates invoice lifecycle status in SQLite.
    """
    from backend.services.document_service import (
        process_invoice_record,
        InvoiceNotFoundError,
        InvoiceFileNotFoundError,
    )
    from backend.services.ocr_service import TesseractNotFoundError, InvalidImageError
    from backend.services.pdf_service import CorruptPDFError, EmptyPDFError

    try:
        invoice = process_invoice_record(invoice_id=invoice_id, db=db)
        raw_len = len(invoice.raw_text) if invoice.raw_text else 0
        return InvoiceProcessResponse(
            invoice_id=invoice.id,
            status=invoice.status,
            extraction_method=invoice.extraction_method,
            text_length=raw_len,
            message="Invoice processed successfully.",
        )
    except InvoiceNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )
    except InvoiceFileNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )
    except TesseractNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        )
    except (CorruptPDFError, EmptyPDFError, InvalidImageError) as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {str(err)}",
        )


@router.get(
    "/invoices/{invoice_id}/text",
    response_model=InvoiceTextResponse,
    summary="Retrieve extracted text for invoice",
    tags=["Invoices"],
)
def get_invoice_text(
    invoice_id: int,
    db: Session = Depends(get_db),
) -> InvoiceTextResponse:
    """Retrieve raw extracted text and extraction metadata for an invoice."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice with ID {invoice_id} was not found.",
        )

    text = invoice.raw_text or ""
    return InvoiceTextResponse(
        invoice_id=invoice.id,
        status=invoice.status,
        extraction_method=invoice.extraction_method,
        raw_text=invoice.raw_text,
        text_length=len(text),
    )


@router.post(
    "/invoices/{invoice_id}/extract",
    response_model=InvoiceStructuredResponse,
    summary="Extract structured invoice fields with Gemini AI",
    tags=["Invoices"],
)
def extract_invoice_fields(
    invoice_id: int,
    db: Session = Depends(get_db),
) -> InvoiceStructuredResponse:
    """
    Trigger AI understanding on raw extracted invoice text:
    - Parses vendor details, invoice metadata, financial totals, and line items.
    - Validates AI JSON output against strict Pydantic schemas.
    - Persists structured fields and line items to SQLite.
    - Updates status to AI_EXTRACTED (or PROCESSING_FAILED on failure).
    """
    from backend.services.ai_extraction_service import (
        extract_and_persist_invoice,
        GeminiNotConfiguredError,
        MissingRawTextError,
        AIResponseParseError,
        AIExtractionError,
    )
    from backend.services.document_service import InvoiceNotFoundError

    try:
        invoice = extract_and_persist_invoice(invoice_id=invoice_id, db=db)
        return InvoiceStructuredResponse(
            invoice_id=invoice.id,
            status=invoice.status,
            extraction_method=invoice.extraction_method,
            original_filename=invoice.original_filename,
            vendor_name=invoice.vendor_name,
            vendor_address=invoice.vendor_address,
            vendor_gstin=invoice.vendor_gstin,
            invoice_number=invoice.invoice_number,
            invoice_date=invoice.invoice_date,
            due_date=invoice.due_date,
            purchase_order_number=invoice.purchase_order_number,
            payment_terms=invoice.payment_terms,
            currency=invoice.currency,
            subtotal=invoice.subtotal,
            tax_amount=invoice.tax_amount,
            total_amount=invoice.total_amount,
            line_items=invoice.line_items,
            raw_text=invoice.raw_text,
        )
    except InvoiceNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )
    except MissingRawTextError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )
    except GeminiNotConfiguredError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        )
    except AIResponseParseError as err:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI Output Validation Error: {str(err)}",
        )
    except AIExtractionError as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(err),
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected extraction error: {str(err)}",
        )


@router.get(
    "/invoices/{invoice_id}/extracted",
    response_model=InvoiceStructuredResponse,
    summary="Retrieve structured invoice data and line items",
    tags=["Invoices"],
)
def get_extracted_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
) -> InvoiceStructuredResponse:
    """Retrieve structured entity fields and line items for an invoice."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice with ID {invoice_id} was not found.",
        )

    return InvoiceStructuredResponse(
        invoice_id=invoice.id,
        status=invoice.status,
        extraction_method=invoice.extraction_method,
        original_filename=invoice.original_filename,
        vendor_name=invoice.vendor_name,
        vendor_address=invoice.vendor_address,
        vendor_gstin=invoice.vendor_gstin,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        due_date=invoice.due_date,
        purchase_order_number=invoice.purchase_order_number,
        payment_terms=invoice.payment_terms,
        currency=invoice.currency,
        subtotal=invoice.subtotal,
        tax_amount=invoice.tax_amount,
        total_amount=invoice.total_amount,
        line_items=invoice.line_items,
        raw_text=invoice.raw_text,
    )


@router.post(
    "/invoices/{invoice_id}/analyze",
    response_model=InvoiceAnalysisResponse,
    summary="Run intelligent validation, duplicate detection, anomaly analysis, and risk scoring",
    tags=["Automation"],
)
def analyze_invoice_endpoint(
    invoice_id: int,
    db: Session = Depends(get_db),
) -> InvoiceAnalysisResponse:
    """
    Run intelligent automation analysis on an invoice:
    - Multi-attribute validation (required fields, math reconciliation, line items, dates).
    - Multi-criteria duplicate invoice detection.
    - Expense category classification (10 standard business categories).
    - Statistical spending and tax anomaly detection.
    - Deterministic risk score calculation (0-100).
    - Automated approval recommendation (AUTO_APPROVE, MANUAL_REVIEW, REJECT_RECOMMENDED).
    """
    from backend.services.automation_service import analyze_invoice
    from backend.services.document_service import InvoiceNotFoundError

    try:
        result = analyze_invoice(invoice_id=invoice_id, db=db)
        return InvoiceAnalysisResponse(**result)
    except InvoiceNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Automation analysis failed: {str(err)}",
        )


@router.get(
    "/invoices/{invoice_id}/analysis",
    response_model=InvoiceAnalysisResponse,
    summary="Retrieve automation analysis results for an invoice",
    tags=["Automation"],
)
def get_invoice_analysis_endpoint(
    invoice_id: int,
    db: Session = Depends(get_db),
) -> InvoiceAnalysisResponse:
    """Retrieve stored automation analysis, risk metrics, and recommendations for an invoice."""
    from backend.services.automation_service import get_invoice_analysis
    from backend.services.document_service import InvoiceNotFoundError

    try:
        result = get_invoice_analysis(invoice_id=invoice_id, db=db)
        return InvoiceAnalysisResponse(**result)
    except InvoiceNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve invoice analysis: {str(err)}",
        )


@router.post(
    "/invoices/{invoice_id}/automate",
    response_model=InvoiceAnalysisResponse,
    summary="Run end-to-end invoice automation workflow",
    tags=["Automation"],
)
def automate_invoice_workflow_endpoint(
    invoice_id: int,
    db: Session = Depends(get_db),
) -> InvoiceAnalysisResponse:
    """
    Execute full automated end-to-end invoice workflow:
    1. Extract raw text if pending.
    2. Extract structured fields if pending and Gemini configured.
    3. Run intelligent validation, duplicate detection, classification, and anomaly checks.
    4. Compute risk score and approval recommendation.
    """
    from backend.services.automation_service import run_full_automation
    from backend.services.document_service import InvoiceNotFoundError

    try:
        result = run_full_automation(invoice_id=invoice_id, db=db)
        return InvoiceAnalysisResponse(**result)
    except InvoiceNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"End-to-end automation failed: {str(err)}",
        )


# ==============================================================================
# PHASE 5 ANALYTICS, DASHBOARD, REPORTS & AUDIT ENDPOINTS
# ==============================================================================

@router.get(
    "/dashboard/summary",
    response_model=DashboardSummarySchema,
    summary="Retrieve system overview KPI summary",
    tags=["Dashboard"],
)
def get_dashboard_summary_endpoint(
    db: Session = Depends(get_db),
) -> DashboardSummarySchema:
    """Retrieve actual database KPI metrics: invoice counts, spend volume, risk and duplicate stats."""
    from backend.services.analytics_service import get_dashboard_summary
    return DashboardSummarySchema(**get_dashboard_summary(db))


@router.get(
    "/analytics/spending",
    response_model=SpendAnalyticsSchema,
    summary="Retrieve spend analytics and distributions",
    tags=["Analytics"],
)
def get_spend_analytics_endpoint(
    vendor: Optional[str] = None,
    category: Optional[str] = None,
    risk: Optional[str] = None,
    status: Optional[str] = None,
    recommendation: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
) -> SpendAnalyticsSchema:
    """Retrieve category spend, vendor rankings, monthly timeline, and risk distributions."""
    from backend.services.analytics_service import get_spend_analytics
    data = get_spend_analytics(
        db=db,
        vendor_filter=vendor,
        category_filter=category,
        risk_filter=risk,
        status_filter=status,
        recommendation_filter=recommendation,
        date_from=date_from,
        date_to=date_to,
    )
    return SpendAnalyticsSchema(**data)


@router.get(
    "/invoices/{invoice_id}/audit",
    response_model=List[AuditLogRead],
    summary="Retrieve audit history for an invoice",
    tags=["Audit"],
)
def get_invoice_audit_endpoint(
    invoice_id: int,
    db: Session = Depends(get_db),
) -> List[AuditLogRead]:
    """Retrieve full chronological audit history for a specific invoice."""
    from backend.services.audit_service import get_invoice_audit_trail
    from backend.services.document_service import InvoiceNotFoundError

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice with ID {invoice_id} was not found.",
        )
    return get_invoice_audit_trail(db=db, invoice_id=invoice_id)


@router.get(
    "/audit/logs",
    response_model=List[AuditLogRead],
    summary="Retrieve system-wide audit activity logs",
    tags=["Audit"],
)
def get_system_audit_logs_endpoint(
    limit: int = 100,
    db: Session = Depends(get_db),
) -> List[AuditLogRead]:
    """Retrieve recent system audit activity events."""
    from backend.services.audit_service import get_system_audit_trail
    return get_system_audit_trail(db=db, limit=limit)


@router.get(
    "/reports/invoices/csv",
    summary="Export invoice registry to CSV",
    tags=["Reports"],
)
def export_invoices_csv_endpoint(
    db: Session = Depends(get_db),
) -> Response:
    """Download full invoice registry as CSV."""
    from backend.services.report_service import generate_invoices_csv
    csv_text = generate_invoices_csv(db)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=invoices_report.csv"},
    )


@router.get(
    "/reports/line-items/csv",
    summary="Export invoice line items to CSV",
    tags=["Reports"],
)
def export_line_items_csv_endpoint(
    invoice_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> Response:
    """Download itemized invoice line items as CSV."""
    from backend.services.report_service import generate_line_items_csv
    csv_text = generate_line_items_csv(db, invoice_id=invoice_id)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=line_items_report.csv"},
    )


@router.get(
    "/reports/summary/pdf",
    summary="Export executive analytics summary to PDF",
    tags=["Reports"],
)
def export_analytics_summary_pdf_endpoint(
    db: Session = Depends(get_db),
) -> Response:
    """Generate and download professional executive summary PDF."""
    from backend.services.report_service import generate_analytics_summary_pdf
    pdf_bytes = generate_analytics_summary_pdf(db)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=analytics_summary.pdf"},
    )


@router.get(
    "/invoices/{invoice_id}/report/pdf",
    summary="Export individual invoice audit report to PDF",
    tags=["Reports"],
)
def export_invoice_detail_pdf_endpoint(
    invoice_id: int,
    db: Session = Depends(get_db),
) -> Response:
    """Generate and download individual invoice audit report PDF."""
    from backend.services.report_service import generate_invoice_detail_pdf
    try:
        pdf_bytes = generate_invoice_detail_pdf(db, invoice_id=invoice_id)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=invoice_{invoice_id}_report.pdf"},
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.get(
    "/system/health",
    response_model=SystemHealthSchema,
    summary="Retrieve detailed operational system health",
    tags=["Health"],
)
def get_system_health_endpoint(
    db: Session = Depends(get_db),
) -> SystemHealthSchema:
    """Check database connectivity, Gemini API configuration, OCR binary availability, and document counts."""
    from backend.config import settings
    from backend.services.ai_extraction_service import is_gemini_configured
    from backend.services.ocr_service import is_tesseract_available, get_tesseract_command

    db_ok = True
    total_inv = 0
    failed_inv = 0
    try:
        total_inv = db.query(Invoice).count()
        failed_inv = db.query(Invoice).filter(Invoice.status == "PROCESSING_FAILED").count()
    except Exception:
        db_ok = False

    tess_ok = is_tesseract_available()
    tess_cmd = get_tesseract_command() if tess_ok else None
    gem_ok = is_gemini_configured()

    overall = "HEALTHY" if db_ok else "DEGRADED"

    return SystemHealthSchema(
        status=overall,
        database_connected=db_ok,
        gemini_configured=gem_ok,
        gemini_model=settings.GEMINI_MODEL,
        ocr_available=tess_ok,
        tesseract_command=tess_cmd,
        total_invoices=total_inv,
        failed_invoices=failed_inv,
    )
