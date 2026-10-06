import pytest
from fastapi.testclient import TestClient
from backend.models.invoice import Invoice


def test_api_dashboard_summary(client: TestClient, db_session):
    """GET /api/v1/dashboard/summary returns KPI data."""
    inv = Invoice(
        original_filename="kpi_test.pdf",
        stored_filename="kpi_test.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AUTOMATED",
        total_amount=2500.0,
        approval_recommendation="AUTO_APPROVE",
    )
    db_session.add(inv)
    db_session.commit()

    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_invoices"] >= 1
    assert data["total_invoice_value"] >= 2500.0


def test_api_analytics_spending(client: TestClient, db_session):
    """GET /api/v1/analytics/spending returns spend distributions."""
    resp = client.get("/api/v1/analytics/spending")
    assert resp.status_code == 200
    data = resp.json()
    assert "category_spending" in data
    assert "vendor_spending" in data
    assert "risk_distribution" in data


def test_api_audit_endpoints(client: TestClient, db_session):
    """Verify invoice-specific and system-wide audit endpoints."""
    inv = Invoice(
        original_filename="audit_api.pdf",
        stored_filename="audit_api.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="UPLOADED",
    )
    db_session.add(inv)
    db_session.commit()

    # Query audit for valid invoice
    resp1 = client.get(f"/api/v1/invoices/{inv.id}/audit")
    assert resp1.status_code == 200
    assert isinstance(resp1.json(), list)

    # Query 404 for unknown invoice
    resp2 = client.get("/api/v1/invoices/99999/audit")
    assert resp2.status_code == 404

    # System-wide audit logs
    resp3 = client.get("/api/v1/audit/logs?limit=5")
    assert resp3.status_code == 200
    assert isinstance(resp3.json(), list)


def test_api_reports_csv_and_pdf(client: TestClient, db_session):
    """Verify CSV and PDF download endpoints return appropriate headers and content."""
    inv = Invoice(
        original_filename="report_test.pdf",
        stored_filename="report_test.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AUTOMATED",
        vendor_name="Global Tech Ltd",
        total_amount=1200.0,
    )
    db_session.add(inv)
    db_session.commit()

    # CSV Registry
    r_csv = client.get("/api/v1/reports/invoices/csv")
    assert r_csv.status_code == 200
    assert "text/csv" in r_csv.headers["content-type"]
    assert "Invoice ID" in r_csv.text

    # PDF Summary
    r_pdf_summary = client.get("/api/v1/reports/summary/pdf")
    assert r_pdf_summary.status_code == 200
    assert "application/pdf" in r_pdf_summary.headers["content-type"]
    assert r_pdf_summary.content.startswith(b"%PDF")

    # PDF Detail
    r_pdf_detail = client.get(f"/api/v1/invoices/{inv.id}/report/pdf")
    assert r_pdf_detail.status_code == 200
    assert "application/pdf" in r_pdf_detail.headers["content-type"]
    assert r_pdf_detail.content.startswith(b"%PDF")


def test_api_system_health(client: TestClient):
    """GET /api/v1/system/health returns complete operational health status."""
    resp = client.get("/api/v1/system/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["database_connected"] is True
    assert data["status"] in ("HEALTHY", "DEGRADED")
    assert "gemini_configured" in data
    assert "ocr_available" in data
