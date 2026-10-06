from typing import Dict, Any
from backend.models.invoice import (
    REC_AUTO_APPROVE,
    REC_MANUAL_REVIEW,
    REC_REJECT_RECOMMENDED,
    RISK_HIGH,
    RISK_MEDIUM,
)


def determine_approval_recommendation(
    validation_result: Dict[str, Any],
    duplicate_result: Dict[str, Any],
    anomaly_result: Dict[str, Any],
    risk_result: Dict[str, Any],
    total_amount: float = 0.0,
) -> Dict[str, Any]:
    """
    Generate automated approval recommendation:
    1. REJECT_RECOMMENDED:
       - Confirmed duplicate invoice.
       - Critical validation failure (negative amounts, math discrepancies).
       - Risk score >= 70 (HIGH).
    2. MANUAL_REVIEW:
       - Statistical anomalies detected.
       - Validation warnings present.
       - Risk level is MEDIUM (30-69).
       - High transaction amount (> $20,000).
    3. AUTO_APPROVE:
       - Validation passed cleanly.
       - No duplicates or anomalies.
       - Risk level is LOW (< 30).
       - Total amount > 0.
    """
    is_duplicate = duplicate_result.get("is_duplicate", False)
    val_status = validation_result.get("status")
    errors = validation_result.get("errors", [])
    warnings = validation_result.get("warnings", [])
    is_anomalous = anomaly_result.get("is_anomalous", False)
    risk_level = risk_result.get("level")
    risk_score = risk_result.get("score", 0)

    # 1. Rejection Triggers
    if is_duplicate:
        return {
            "recommendation": REC_REJECT_RECOMMENDED,
            "reason": (
                f"Duplicate invoice detected: {duplicate_result.get('reason')}. "
                "Immediate rejection recommended to prevent double payment."
            ),
        }

    if val_status == "FAILED" or any("mismatch" in e.lower() or "negative" in e.lower() for e in errors):
        return {
            "recommendation": REC_REJECT_RECOMMENDED,
            "reason": (
                f"Critical validation failures detected: {'; '.join(errors)}. "
                "Invoice must be rejected or returned to vendor for correction."
            ),
        }

    if risk_level == RISK_HIGH or risk_score >= 70:
        return {
            "recommendation": REC_REJECT_RECOMMENDED,
            "reason": (
                f"Elevated risk score ({risk_score}/100) exceeds safety threshold. "
                f"Key factors: {'; '.join(risk_result.get('reasons', []))}."
            ),
        }

    # 2. Manual Review Triggers
    review_reasons = []

    if is_anomalous:
        review_reasons.append(f"Statistical anomalies: {'; '.join(anomaly_result.get('reasons', []))}")

    if warnings:
        review_reasons.append(f"Validation warnings: {'; '.join(warnings)}")

    if risk_level == RISK_MEDIUM:
        review_reasons.append(f"Moderate risk score ({risk_score}/100)")

    if total_amount and total_amount > 20_000:
        review_reasons.append(f"Invoice amount ({total_amount:,.2f}) requires standard secondary approval")

    if review_reasons:
        return {
            "recommendation": REC_MANUAL_REVIEW,
            "reason": f"Manual inspection required due to: {'; '.join(review_reasons)}.",
        }

    # 3. Auto Approval
    return {
        "recommendation": REC_AUTO_APPROVE,
        "reason": (
            "Invoice passed all validation checks with complete financial consistency, "
            "no duplicate records, and low risk score."
        ),
    }
