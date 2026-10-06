import pytest
from backend.services.risk_service import calculate_risk_score
from backend.services.approval_service import determine_approval_recommendation
from backend.models.invoice import (
    RISK_LOW,
    RISK_MEDIUM,
    RISK_HIGH,
    REC_AUTO_APPROVE,
    REC_MANUAL_REVIEW,
    REC_REJECT_RECOMMENDED,
)


def test_clean_invoice_risk_and_auto_approval():
    """A clean invoice should receive LOW risk and AUTO_APPROVE recommendation."""
    val = {"passed": True, "status": "PASSED", "errors": [], "warnings": []}
    dup = {"is_duplicate": False, "duplicate_invoice_id": None, "reason": None}
    anom = {"is_anomalous": False, "reasons": []}

    risk = calculate_risk_score(val, dup, anom, invoice_amount=1500.0)
    assert risk["score"] < 30
    assert risk["level"] == RISK_LOW

    appr = determine_approval_recommendation(val, dup, anom, risk, total_amount=1500.0)
    assert appr["recommendation"] == REC_AUTO_APPROVE
    assert "passed all validation checks" in appr["reason"]


def test_duplicate_invoice_triggers_rejection():
    """Duplicate invoice should produce high risk and REJECT_RECOMMENDED."""
    val = {"passed": True, "status": "PASSED", "errors": [], "warnings": []}
    dup = {"is_duplicate": True, "duplicate_invoice_id": 12, "reason": "Matching invoice number"}
    anom = {"is_anomalous": False, "reasons": []}

    risk = calculate_risk_score(val, dup, anom, invoice_amount=1500.0)
    assert risk["score"] >= 45

    appr = determine_approval_recommendation(val, dup, anom, risk, total_amount=1500.0)
    assert appr["recommendation"] == REC_REJECT_RECOMMENDED
    assert "Duplicate invoice detected" in appr["reason"]


def test_validation_math_mismatch_triggers_rejection():
    """Math discrepancies should produce REJECT_RECOMMENDED."""
    val = {
        "passed": False,
        "status": "FAILED",
        "errors": ["Financial calculation mismatch: Subtotal + Tax != Total"],
        "warnings": [],
    }
    dup = {"is_duplicate": False, "duplicate_invoice_id": None, "reason": None}
    anom = {"is_anomalous": False, "reasons": []}

    risk = calculate_risk_score(val, dup, anom, invoice_amount=1500.0)
    assert risk["score"] >= 30

    appr = determine_approval_recommendation(val, dup, anom, risk, total_amount=1500.0)
    assert appr["recommendation"] == REC_REJECT_RECOMMENDED
    assert "Critical validation failures detected" in appr["reason"]


def test_anomaly_triggers_manual_review():
    """Invoice with statistical anomaly should trigger MANUAL_REVIEW recommendation."""
    val = {"passed": True, "status": "PASSED", "errors": [], "warnings": []}
    dup = {"is_duplicate": False, "duplicate_invoice_id": None, "reason": None}
    anom = {"is_anomalous": True, "reasons": ["Unusually high invoice amount (Z-score: 3.1)"]}

    risk = calculate_risk_score(val, dup, anom, invoice_amount=5000.0)
    assert risk["score"] >= 20

    appr = determine_approval_recommendation(val, dup, anom, risk, total_amount=5000.0)
    assert appr["recommendation"] == REC_MANUAL_REVIEW
    assert "Manual inspection required" in appr["reason"]
