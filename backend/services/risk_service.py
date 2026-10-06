from typing import Dict, Any, List
from backend.models.invoice import RISK_LOW, RISK_MEDIUM, RISK_HIGH


def calculate_risk_score(
    validation_result: Dict[str, Any],
    duplicate_result: Dict[str, Any],
    anomaly_result: Dict[str, Any],
    invoice_amount: float = 0.0,
) -> Dict[str, Any]:
    """
    Calculate deterministic, explainable risk score (0-100) based on weighted factors:
    - Suspected duplicate: +45 pts
    - Validation math errors / hard failures: +30 pts
    - Statistical anomaly detected: +20 pts
    - Negative values / illegal fields: +30 pts
    - Validation warnings (e.g., missing metadata): +10 pts
    - Unusually high dollar volume: +15 pts

    Classifies into LOW (0-29), MEDIUM (30-69), and HIGH (70-100) with itemized reasons.
    """
    score = 0
    reasons: List[str] = []

    # 1. Duplicate Factor
    if duplicate_result.get("is_duplicate"):
        score += 45
        reasons.append(f"Duplicate invoice detected (+45 pts): {duplicate_result.get('reason')}")

    # 2. Validation Errors
    errors = validation_result.get("errors", [])
    if errors:
        # Check if there are negative numbers or critical calculation errors
        has_negative = any("negative" in err.lower() for err in errors)
        has_math = any("mismatch" in err.lower() or "calculation" in err.lower() for err in errors)

        if has_negative:
            score += 30
            reasons.append("Invalid negative amounts detected (+30 pts).")

        if has_math:
            score += 30
            reasons.append("Financial calculation mismatch (+30 pts).")

        if not has_negative and not has_math:
            score += 25
            reasons.append(f"Validation errors detected (+25 pts): {', '.join(errors)}")

    # 3. Validation Warnings
    warnings = validation_result.get("warnings", [])
    if warnings and not errors:
        score += min(15, len(warnings) * 5)
        reasons.append(f"Validation warnings detected (+{min(15, len(warnings) * 5)} pts).")

    # 4. Statistical Anomalies
    if anomaly_result.get("is_anomalous"):
        score += 20
        reasons.append(
            f"Statistical / tax anomalies detected (+20 pts): {'; '.join(anomaly_result.get('reasons', []))}"
        )

    # 5. High-Value Threshold Check ($50,000+)
    if invoice_amount and invoice_amount >= 50_000:
        score += 15
        reasons.append(f"Large transaction volume exceeds $50,000 threshold (+15 pts).")

    # Clamp score between 0 and 100
    final_score = max(0, min(100, score))

    # Determine Risk Level
    if final_score < 30:
        level = RISK_LOW
    elif final_score < 70:
        level = RISK_MEDIUM
    else:
        level = RISK_HIGH

    if not reasons:
        reasons.append("No risk factors identified; clean invoice.")

    return {
        "score": final_score,
        "level": level,
        "reasons": reasons,
    }
