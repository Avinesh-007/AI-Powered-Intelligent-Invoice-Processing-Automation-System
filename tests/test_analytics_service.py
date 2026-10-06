import pytest
from backend.models.invoice import Invoice
from backend.services.analytics_service import get_dashboard_summary, get_spend_analytics


def test_dashboard_summary_empty_database(db_session):
    """Empty database must return all zeroes and never crash or fake values."""
    summary = get_dashboard_summary(db_session)
    assert summary["total_invoices"] == 0
    assert summary["total_invoice_value"] == 0.0
    assert summary["processed_invoices"] == 0
    assert summary["pending_invoices"] == 0
    assert summary["high_risk_invoices"] == 0
    assert summary["duplicate_invoices"] == 0
    assert summary["anomalous_invoices"] == 0
    assert summary["auto_approved_invoices"] == 0


def test_dashboard_summary_populated_database(db_session):
    """Accurately aggregate KPIs from database records."""
    inv1 = Invoice(
        original_filename="inv1.pdf",
        stored_filename="inv1.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AUTOMATED",
        total_amount=1500.0,
        risk_level="LOW",
        duplicate_flag=False,
        anomaly_flag=False,
        approval_recommendation="AUTO_APPROVE",
    )
    inv2 = Invoice(
        original_filename="inv2.pdf",
        stored_filename="inv2.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AUTOMATED",
        total_amount=3500.0,
        risk_level="HIGH",
        duplicate_flag=True,
        anomaly_flag=True,
        approval_recommendation="REJECT_RECOMMENDED",
    )
    inv3 = Invoice(
        original_filename="inv3.pdf",
        stored_filename="inv3.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="UPLOADED",  # Pending
        total_amount=500.0,
    )
    db_session.add_all([inv1, inv2, inv3])
    db_session.commit()

    summary = get_dashboard_summary(db_session)
    assert summary["total_invoices"] == 3
    assert summary["total_invoice_value"] == 5500.0
    assert summary["processed_invoices"] == 2
    assert summary["pending_invoices"] == 1
    assert summary["high_risk_invoices"] == 1
    assert summary["duplicate_invoices"] == 1
    assert summary["anomalous_invoices"] == 1
    assert summary["auto_approved_invoices"] == 1


def test_spend_analytics_aggregations_and_filters(db_session):
    """Verify category, vendor, monthly distributions and multi-criteria filters."""
    inv1 = Invoice(
        original_filename="aws.pdf",
        stored_filename="aws.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AUTOMATED",
        vendor_name="Amazon Web Services",
        expense_category="IT & Software",
        invoice_date="2026-01-15",
        total_amount=2000.0,
        risk_level="LOW",
        approval_recommendation="AUTO_APPROVE",
    )
    inv2 = Invoice(
        original_filename="delta.pdf",
        stored_filename="delta.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AUTOMATED",
        vendor_name="Delta Airlines",
        expense_category="Travel",
        invoice_date="2026-02-10",
        total_amount=1200.0,
        risk_level="MEDIUM",
        approval_recommendation="MANUAL_REVIEW",
    )
    db_session.add_all([inv1, inv2])
    db_session.commit()

    # Unfiltered analytics
    analytics = get_spend_analytics(db_session)
    assert analytics["filtered_count"] == 2
    assert len(analytics["category_spending"]) == 2
    assert analytics["category_spending"][0]["category"] == "IT & Software"
    assert analytics["category_spending"][0]["total_amount"] == 2000.0

    assert len(analytics["vendor_spending"]) == 2
    assert analytics["vendor_spending"][0]["vendor"] == "Amazon Web Services"

    # Filtered by category
    filtered = get_spend_analytics(db_session, category_filter="Travel")
    assert filtered["filtered_count"] == 1
    assert filtered["category_spending"][0]["category"] == "Travel"
    assert filtered["category_spending"][0]["total_amount"] == 1200.0

    # Filtered by risk
    risk_filtered = get_spend_analytics(db_session, risk_filter="LOW")
    assert risk_filtered["filtered_count"] == 1
    assert risk_filtered["vendor_spending"][0]["vendor"] == "Amazon Web Services"
