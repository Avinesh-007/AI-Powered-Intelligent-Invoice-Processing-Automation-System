import statistics
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from backend.models.invoice import Invoice


def detect_invoice_anomalies(
    invoice: Invoice,
    db: Session,
    z_threshold: float = 2.5,
    tax_rate_threshold: float = 35.0,
) -> Dict[str, Any]:
    """
    Perform explainable statistical anomaly detection on invoice financials:
    1. Historical Vendor Spending Deviation (Z-score / IQR):
       - If vendor has < 3 historical invoices, explicitly reports insufficient data.
       - If >= 3 invoices exist, calculates vendor mean, stddev, and Z-score.
    2. Effective Tax Rate Anomaly:
       - Compares tax_amount / subtotal against standard threshold (35%).
    3. Extreme Value Operational Check:
       - Flags unusually large transactions exceeding threshold.
    """
    reasons: List[str] = []
    historical_count = 0
    mean_val: Optional[float] = None
    std_val: Optional[float] = None
    z_score: Optional[float] = None
    historical_msg: Optional[str] = None

    # 1. Historical Vendor Spending Analysis
    vendor_name = invoice.vendor_name
    curr_amount = invoice.total_amount

    if vendor_name and vendor_name.strip() and curr_amount is not None:
        norm_vendor = vendor_name.strip().lower()

        # Query past invoices for this vendor (excluding current invoice)
        past_invoices = (
            db.query(Invoice)
            .filter(
                Invoice.id != invoice.id,
                Invoice.vendor_name.isnot(None),
                Invoice.total_amount.isnot(None),
            )
            .all()
        )

        vendor_amounts = [
            inv.total_amount
            for inv in past_invoices
            if inv.vendor_name.strip().lower() == norm_vendor
            and inv.total_amount is not None
            and inv.total_amount > 0
        ]

        historical_count = len(vendor_amounts)

        if historical_count < 3:
            historical_msg = (
                f"Insufficient historical data for vendor anomaly analysis "
                f"(found {historical_count} previous invoices for '{vendor_name}', minimum 3 required)."
            )
        else:
            mean_val = round(statistics.mean(vendor_amounts), 2)
            std_val = round(statistics.stdev(vendor_amounts), 2) if historical_count > 1 else 0.0

            if std_val > 0.01:
                z_score = round((curr_amount - mean_val) / std_val, 2)
                if z_score > z_threshold:
                    reasons.append(
                        f"Unusually high invoice amount {curr_amount:,.2f} "
                        f"(Z-score: {z_score:.2f}, Vendor historical mean: {mean_val:,.2f} ± {std_val:,.2f})."
                    )
                elif z_score < -z_threshold:
                    reasons.append(
                        f"Unusually low invoice amount {curr_amount:,.2f} "
                        f"(Z-score: {z_score:.2f}, Vendor historical mean: {mean_val:,.2f} ± {std_val:,.2f})."
                    )
            else:
                # All historical invoices were identical amounts
                if curr_amount > (mean_val * 2.0):
                    reasons.append(
                        f"Invoice amount {curr_amount:,.2f} is significantly higher than historical "
                        f"constant value of {mean_val:,.2f}."
                    )

    # 2. Tax Rate Anomaly Check
    if (
        invoice.subtotal is not None
        and invoice.tax_amount is not None
        and invoice.subtotal > 0
    ):
        effective_tax_pct = round((invoice.tax_amount / invoice.subtotal) * 100, 2)
        if effective_tax_pct > tax_rate_threshold:
            reasons.append(
                f"Unusually high effective tax rate ({effective_tax_pct:.1f}%) "
                f"exceeds standard threshold ({tax_rate_threshold:.0f}%)."
            )
        elif effective_tax_pct < 0:
            reasons.append(
                f"Negative effective tax rate detected ({effective_tax_pct:.1f}%)."
            )

    # 3. High-Value Transaction Operational Check ($1,000,000 threshold)
    if curr_amount is not None and curr_amount >= 1_000_000:
        reasons.append(
            f"High-value transaction amount ({curr_amount:,.2f}) requires executive approval."
        )

    is_anomalous = len(reasons) > 0

    return {
        "is_anomalous": is_anomalous,
        "reasons": reasons,
        "historical_count": historical_count,
        "mean_amount": mean_val,
        "std_amount": std_val,
        "z_score": z_score,
        "message": historical_msg,
    }
