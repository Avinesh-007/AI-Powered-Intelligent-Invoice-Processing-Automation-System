import json
from typing import Dict, Any
from sqlalchemy.orm import Session

from backend.models.invoice import (
    Invoice,
    STATUS_ANALYZED,
    STATUS_AUTOMATED,
    utc_now,
)
from backend.services.document_service import process_invoice_record, InvoiceNotFoundError
from backend.services.ai_extraction_service import (
    extract_and_persist_invoice,
    is_gemini_configured,
)
from backend.services.invoice_validation_service import validate_invoice
from backend.services.duplicate_detection_service import detect_duplicate_invoice
from backend.services.expense_classification_service import classify_expense
from backend.services.anomaly_detection_service import detect_invoice_anomalies
from backend.services.risk_service import calculate_risk_score
from backend.services.approval_service import determine_approval_recommendation


class AutomationServiceError(Exception):
    """Base exception for invoice automation workflow errors."""
    pass


def analyze_invoice(invoice_id: int, db: Session) -> Dict[str, Any]:
    """
    Run full intelligent analysis and risk assessment on an invoice:
    - Validation engine
    - Duplicate detection
    - Expense classification
    - Anomaly detection
    - Risk scoring
    - Automated approval recommendation
    Persists results directly to SQLite and marks invoice as ANALYZED.
    """
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise InvoiceNotFoundError(f"Invoice with ID {invoice_id} not found.")

    # 1. Validation Engine
    val_res = validate_invoice(invoice)

    # 2. Duplicate Detection
    dup_res = detect_duplicate_invoice(invoice, db)

    # 3. Expense Classification
    class_res = classify_expense(invoice)

    # 4. Anomaly Detection
    anom_res = detect_invoice_anomalies(invoice, db)

    # 5. Risk Assessment
    total_val = invoice.total_amount or 0.0
    risk_res = calculate_risk_score(
        validation_result=val_res,
        duplicate_result=dup_res,
        anomaly_result=anom_res,
        invoice_amount=total_val,
    )

    # 6. Approval Recommendation
    appr_res = determine_approval_recommendation(
        validation_result=val_res,
        duplicate_result=dup_res,
        anomaly_result=anom_res,
        risk_result=risk_res,
        total_amount=total_val,
    )

    # 7. Persist Results to SQLite
    now = utc_now()
    invoice.expense_category = class_res["category"]
    invoice.classification_method = class_res["method"]
    invoice.validation_status = val_res["status"]
    invoice.validation_errors = json.dumps(val_res["errors"])
    invoice.validation_warnings = json.dumps(val_res["warnings"])
    invoice.duplicate_flag = dup_res["is_duplicate"]
    invoice.duplicate_invoice_id = dup_res["duplicate_invoice_id"]
    invoice.duplicate_reason = dup_res["reason"]
    invoice.anomaly_flag = anom_res["is_anomalous"]
    invoice.anomaly_reasons = json.dumps(anom_res["reasons"])
    invoice.risk_score = risk_res["score"]
    invoice.risk_level = risk_res["level"]
    invoice.risk_reasons = json.dumps(risk_res["reasons"])
    invoice.approval_recommendation = appr_res["recommendation"]
    invoice.approval_reason = appr_res["reason"]
    invoice.automation_processed_at = now
    invoice.status = STATUS_ANALYZED

    db.commit()
    db.refresh(invoice)

    from backend.services.audit_service import record_audit_event
    from backend.models.invoice import (
        ACTION_VALIDATION_COMPLETED,
        ACTION_RISK_COMPLETED,
    )
    try:
        record_audit_event(
            db=db,
            action=ACTION_VALIDATION_COMPLETED,
            status=val_res["status"],
            invoice_id=invoice.id,
            message=f"Validation {val_res['status']}. Category: {class_res['category']}. Duplicate: {dup_res['is_duplicate']}.",
        )
        record_audit_event(
            db=db,
            action=ACTION_RISK_COMPLETED,
            status="SUCCESS",
            invoice_id=invoice.id,
            message=f"Risk Score: {risk_res['score']}/100 ({risk_res['level']}). Rec: {appr_res['recommendation']}.",
        )
    except Exception:
        pass

    return {
        "invoice_id": invoice.id,
        "status": invoice.status,
        "validation": val_res,
        "duplicate": dup_res,
        "classification": class_res,
        "anomaly": anom_res,
        "risk": risk_res,
        "approval": appr_res,
        "automation_processed_at": invoice.automation_processed_at,
    }


def get_invoice_analysis(invoice_id: int, db: Session) -> Dict[str, Any]:
    """
    Retrieve stored analysis results for an invoice without re-running computations.
    If the invoice has not yet been analyzed, runs analyze_invoice dynamically.
    """
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise InvoiceNotFoundError(f"Invoice with ID {invoice_id} not found.")

    if not invoice.automation_processed_at:
        return analyze_invoice(invoice_id, db)

    # Parse stored JSON columns
    errors = json.loads(invoice.validation_errors or "[]")
    warnings = json.loads(invoice.validation_warnings or "[]")
    anomaly_reasons = json.loads(invoice.anomaly_reasons or "[]")
    risk_reasons = json.loads(invoice.risk_reasons or "[]")

    val_res = {
        "passed": invoice.validation_status in ("PASSED", "WARNINGS"),
        "status": invoice.validation_status or "PASSED",
        "errors": errors,
        "warnings": warnings,
    }
    dup_res = {
        "is_duplicate": invoice.duplicate_flag,
        "duplicate_invoice_id": invoice.duplicate_invoice_id,
        "reason": invoice.duplicate_reason,
        "match_type": "STORED",
    }
    class_res = {
        "category": invoice.expense_category or "Other",
        "confidence": 0.85 if invoice.expense_category else 0.30,
        "method": invoice.classification_method or "RULE_BASED",
        "matched_keywords": [],
    }
    anom_res = {
        "is_anomalous": invoice.anomaly_flag,
        "reasons": anomaly_reasons,
        "historical_count": 0,
        "mean_amount": None,
        "std_amount": None,
        "z_score": None,
        "message": None,
    }
    risk_res = {
        "score": invoice.risk_score if invoice.risk_score is not None else 0,
        "level": invoice.risk_level or "LOW",
        "reasons": risk_reasons,
    }
    appr_res = {
        "recommendation": invoice.approval_recommendation or "AUTO_APPROVE",
        "reason": invoice.approval_reason or "Automated assessment stored.",
    }

    return {
        "invoice_id": invoice.id,
        "status": invoice.status,
        "validation": val_res,
        "duplicate": dup_res,
        "classification": class_res,
        "anomaly": anom_res,
        "risk": risk_res,
        "approval": appr_res,
        "automation_processed_at": invoice.automation_processed_at,
    }


def run_full_automation(invoice_id: int, db: Session) -> Dict[str, Any]:
    """
    Execute end-to-end automated pipeline on an invoice:
    1. If raw_text is missing: run document processing (PyMuPDF / OCR).
    2. If structured fields missing and Gemini configured: run AI extraction.
    3. Run complete analysis (validation, duplicate, classification, anomaly, risk, approval).
    4. Mark status as AUTOMATED.
    """
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise InvoiceNotFoundError(f"Invoice with ID {invoice_id} not found.")

    # Step 1: Text extraction if not done yet
    if not invoice.raw_text or not invoice.raw_text.strip():
        invoice = process_invoice_record(invoice_id=invoice_id, db=db)

    # Step 2: AI extraction if Gemini configured and not extracted yet
    if is_gemini_configured() and (not invoice.vendor_name or invoice.total_amount is None):
        try:
            invoice = extract_and_persist_invoice(invoice_id=invoice_id, db=db)
        except Exception:
            # Continue pipeline even if Gemini call fails
            pass

    # Step 3: Run analysis
    analysis = analyze_invoice(invoice_id=invoice_id, db=db)

    # Step 4: Update status to AUTOMATED
    invoice.status = STATUS_AUTOMATED
    db.commit()
    db.refresh(invoice)

    from backend.services.audit_service import record_audit_event
    from backend.models.invoice import ACTION_AUTOMATION_COMPLETED
    try:
        record_audit_event(
            db=db,
            action=ACTION_AUTOMATION_COMPLETED,
            status="SUCCESS",
            invoice_id=invoice.id,
            message="End-to-end automation workflow completed successfully.",
        )
    except Exception:
        pass

    analysis["status"] = STATUS_AUTOMATED
    return analysis
