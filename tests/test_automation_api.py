import pytest
from fastapi.testclient import TestClient
from backend.models.invoice import Invoice, InvoiceLineItem


def test_api_analyze_invoice_success(client: TestClient, db_session):
    """POST /invoices/{id}/analyze executes validation, duplicate, classification, risk, and returns structured result."""
    inv = Invoice(
        original_filename="analyze_test.pdf",
        stored_filename="analyze_test.pdf",
        file_path="dummy/path",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="Google Cloud EMEA",
        invoice_number="GCP-2026-90",
        invoice_date="2026-03-01",
        due_date="2026-04-01",
        subtotal=2000.0,
        tax_amount=200.0,
        total_amount=2200.0,
        currency="USD",
        raw_text="Google Cloud Platform Compute and Storage subscription charges.",
    )
    db_session.add(inv)
    db_session.commit()

    resp = client.post(f"/api/v1/invoices/{inv.id}/analyze")
    assert resp.status_code == 200
    data = resp.json()

    assert data["invoice_id"] == inv.id
    assert data["status"] == "ANALYZED"
    assert data["validation"]["passed"] is True
    assert data["duplicate"]["is_duplicate"] is False
    assert data["classification"]["category"] == "IT & Software"
    assert data["risk"]["score"] < 30
    assert data["risk"]["level"] == "LOW"
    assert data["approval"]["recommendation"] == "AUTO_APPROVE"


def test_api_get_invoice_analysis(client: TestClient, db_session):
    """GET /invoices/{id}/analysis returns stored or dynamic analysis result."""
    inv = Invoice(
        original_filename="get_analysis.pdf",
        stored_filename="get_analysis.pdf",
        file_path="dummy/path",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="FedEx Shipping Services",
        invoice_number="FDX-5544",
        subtotal=300.0,
        tax_amount=30.0,
        total_amount=330.0,
        currency="USD",
        raw_text="Freight and shipping express courier delivery fee.",
    )
    db_session.add(inv)
    db_session.commit()

    resp = client.get(f"/api/v1/invoices/{inv.id}/analysis")
    assert resp.status_code == 200
    data = resp.json()
    assert data["invoice_id"] == inv.id
    assert data["classification"]["category"] == "Logistics"


def test_api_automate_invoice_workflow(client: TestClient, db_session):
    """POST /invoices/{id}/automate runs full automation and transitions status to AUTOMATED."""
    inv = Invoice(
        original_filename="automate_flow.pdf",
        stored_filename="automate_flow.pdf",
        file_path="dummy/path",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="PricewaterhouseCoopers LLP",
        invoice_number="PWC-1002",
        subtotal=5000.0,
        tax_amount=500.0,
        total_amount=5500.0,
        currency="USD",
        raw_text="Annual financial audit and corporate tax advisory services.",
    )
    db_session.add(inv)
    db_session.commit()

    resp = client.post(f"/api/v1/invoices/{inv.id}/automate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "AUTOMATED"
    assert data["classification"]["category"] == "Professional Services"


def test_api_automation_endpoints_nonexistent_invoice(client: TestClient):
    """Automation endpoints return 404 for unknown invoices."""
    resp1 = client.post("/api/v1/invoices/99999/analyze")
    assert resp1.status_code == 404

    resp2 = client.get("/api/v1/invoices/99999/analysis")
    assert resp2.status_code == 404

    resp3 = client.post("/api/v1/invoices/99999/automate")
    assert resp3.status_code == 404
