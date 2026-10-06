from typing import Dict, Any, List, Optional
from collections import defaultdict
from sqlalchemy.orm import Session
from backend.models.invoice import Invoice


def get_dashboard_summary(db: Session) -> Dict[str, Any]:
    """
    Compute system overview KPI metrics directly from real database records.
    Returns exact counts and financial sums. If the database is empty, returns zero values.
    """
    invoices = db.query(Invoice).all()

    total_invoices = len(invoices)
    if total_invoices == 0:
        return {
            "total_invoices": 0,
            "total_invoice_value": 0.0,
            "processed_invoices": 0,
            "pending_invoices": 0,
            "high_risk_invoices": 0,
            "duplicate_invoices": 0,
            "anomalous_invoices": 0,
            "auto_approved_invoices": 0,
        }

    total_value = sum(inv.total_amount for inv in invoices if inv.total_amount is not None)
    processed_count = sum(
        1 for inv in invoices
        if inv.status in ("TEXT_EXTRACTED", "OCR_COMPLETED", "AI_EXTRACTED", "ANALYZED", "AUTOMATED")
    )
    pending_count = sum(
        1 for inv in invoices
        if inv.status in ("UPLOADED", "PROCESSING", "AI_PROCESSING")
    )
    high_risk_count = sum(1 for inv in invoices if inv.risk_level == "HIGH")
    duplicate_count = sum(1 for inv in invoices if inv.duplicate_flag)
    anomalous_count = sum(1 for inv in invoices if inv.anomaly_flag)
    auto_approved_count = sum(1 for inv in invoices if inv.approval_recommendation == "AUTO_APPROVE")

    return {
        "total_invoices": total_invoices,
        "total_invoice_value": round(total_value, 2),
        "processed_invoices": processed_count,
        "pending_invoices": pending_count,
        "high_risk_invoices": high_risk_count,
        "duplicate_invoices": duplicate_count,
        "anomalous_invoices": anomalous_count,
        "auto_approved_invoices": auto_approved_count,
    }


def get_spend_analytics(
    db: Session,
    vendor_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
    risk_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
    recommendation_filter: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compute granular spending, risk, and status distributions dynamically
    from database records with support for multi-attribute filtering.
    """
    query = db.query(Invoice)

    if vendor_filter and vendor_filter.strip():
        query = query.filter(Invoice.vendor_name.ilike(f"%{vendor_filter.strip()}%"))

    if category_filter and category_filter.strip():
        query = query.filter(Invoice.expense_category == category_filter.strip())

    if risk_filter and risk_filter.strip():
        query = query.filter(Invoice.risk_level == risk_filter.strip())

    if status_filter and status_filter.strip():
        query = query.filter(Invoice.status == status_filter.strip())

    if recommendation_filter and recommendation_filter.strip():
        query = query.filter(Invoice.approval_recommendation == recommendation_filter.strip())

    invoices = query.all()

    # Apply date filters in Python to handle diverse date formats safely
    if date_from or date_to:
        filtered_invoices = []
        for inv in invoices:
            dt_str = inv.invoice_date or (inv.upload_timestamp.strftime("%Y-%m-%d") if inv.upload_timestamp else None)
            if not dt_str:
                filtered_invoices.append(inv)
                continue
            # Basic ISO prefix comparison
            if date_from and dt_str < date_from:
                continue
            if date_to and dt_str > date_to:
                continue
            filtered_invoices.append(inv)
        invoices = filtered_invoices

    # 1. Category Spending
    cat_spend = defaultdict(float)
    cat_counts = defaultdict(int)
    for inv in invoices:
        cat = inv.expense_category or "Uncategorized"
        amt = inv.total_amount or 0.0
        cat_spend[cat] += amt
        cat_counts[cat] += 1

    category_data = [
        {"category": cat, "total_amount": round(total, 2), "count": cat_counts[cat]}
        for cat, total in sorted(cat_spend.items(), key=lambda x: x[1], reverse=True)
    ]

    # 2. Vendor Spending
    vendor_spend = defaultdict(float)
    vendor_counts = defaultdict(int)
    for inv in invoices:
        v = inv.vendor_name or "Unknown Vendor"
        amt = inv.total_amount or 0.0
        vendor_spend[v] += amt
        vendor_counts[v] += 1

    vendor_data = [
        {"vendor": v, "total_amount": round(total, 2), "count": vendor_counts[v]}
        for v, total in sorted(vendor_spend.items(), key=lambda x: x[1], reverse=True)
    ]

    # 3. Monthly Spending
    month_spend = defaultdict(float)
    month_counts = defaultdict(int)
    for inv in invoices:
        month_key = None
        if inv.invoice_date and len(inv.invoice_date) >= 7:
            # Handle YYYY-MM
            if inv.invoice_date[:4].isdigit() and inv.invoice_date[4] in ("-", "/"):
                month_key = inv.invoice_date[:7].replace("/", "-")
        if not month_key and inv.upload_timestamp:
            month_key = inv.upload_timestamp.strftime("%Y-%m")
        if not month_key:
            month_key = "Unspecified"

        amt = inv.total_amount or 0.0
        month_spend[month_key] += amt
        month_counts[month_key] += 1

    monthly_data = [
        {"month": m, "total_amount": round(total, 2), "count": month_counts[m]}
        for m, total in sorted(month_spend.items(), key=lambda x: x[0])
    ]

    # 4. Risk Distribution
    risk_dist = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "UNASSESSED": 0}
    for inv in invoices:
        if inv.risk_level in risk_dist:
            risk_dist[inv.risk_level] += 1
        else:
            risk_dist["UNASSESSED"] += 1

    # 5. Status Distribution (actual present statuses only)
    status_dist = defaultdict(int)
    for inv in invoices:
        status_dist[inv.status] += 1

    # 6. Recommendation Distribution
    rec_dist = {"AUTO_APPROVE": 0, "MANUAL_REVIEW": 0, "REJECT_RECOMMENDED": 0, "PENDING": 0}
    for inv in invoices:
        if inv.approval_recommendation in rec_dist:
            rec_dist[inv.approval_recommendation] += 1
        else:
            rec_dist["PENDING"] += 1

    return {
        "filtered_count": len(invoices),
        "category_spending": category_data,
        "vendor_spending": vendor_data,
        "monthly_spending": monthly_data,
        "risk_distribution": dict(risk_dist),
        "status_distribution": dict(status_dist),
        "recommendation_distribution": dict(rec_dist),
    }
