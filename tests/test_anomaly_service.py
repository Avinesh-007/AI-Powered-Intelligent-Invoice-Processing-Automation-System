import pytest
from backend.models.invoice import Invoice
from backend.services.anomaly_detection_service import detect_invoice_anomalies


def test_anomaly_insufficient_historical_data(db_session):
    """When vendor has < 3 invoices, report insufficient data and do not flag anomaly."""
    # Add only 1 past invoice for Acme
    past = Invoice(
        original_filename="p1.pdf",
        stored_filename="p1.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="Acme Corp",
        total_amount=500.0,
    )
    curr = Invoice(
        original_filename="p2.pdf",
        stored_filename="p2.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="Acme Corp",
        total_amount=950.0,
    )
    db_session.add_all([past, curr])
    db_session.commit()

    res = detect_invoice_anomalies(curr, db_session)
    assert res["is_anomalous"] is False
    assert res["historical_count"] == 1
    assert "Insufficient historical data" in (res["message"] or "")


def test_anomaly_normal_spending_within_distribution(db_session):
    """Invoice within 2.5 stddev of historical spending is not anomalous."""
    # Add 4 past invoices with amounts ~1000
    for idx, amt in enumerate([950.0, 1050.0, 980.0, 1020.0]):
        past = Invoice(
            original_filename=f"p_{idx}.pdf",
            stored_filename=f"p_{idx}.pdf",
            file_path="dummy",
            file_size_bytes=1000,
            status="AI_EXTRACTED",
            vendor_name="Standard Vendor",
            total_amount=amt,
        )
        db_session.add(past)

    curr = Invoice(
        original_filename="curr.pdf",
        stored_filename="curr.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="Standard Vendor",
        total_amount=1010.0,
    )
    db_session.add(curr)
    db_session.commit()

    res = detect_invoice_anomalies(curr, db_session)
    assert res["is_anomalous"] is False
    assert res["historical_count"] == 4
    assert res["z_score"] is not None
    assert abs(res["z_score"]) < 2.0


def test_anomaly_statistical_outlier_high_amount(db_session):
    """Invoice significantly higher than historical mean is flagged with Z-score."""
    for idx, amt in enumerate([100.0, 105.0, 98.0, 102.0]):
        past = Invoice(
            original_filename=f"norm_{idx}.pdf",
            stored_filename=f"norm_{idx}.pdf",
            file_path="dummy",
            file_size_bytes=1000,
            status="AI_EXTRACTED",
            vendor_name="Coffee Supplies",
            total_amount=amt,
        )
        db_session.add(past)

    curr = Invoice(
        original_filename="spike.pdf",
        stored_filename="spike.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="Coffee Supplies",
        total_amount=2500.0,  # Extreme spike (25x normal amount)
    )
    db_session.add(curr)
    db_session.commit()

    res = detect_invoice_anomalies(curr, db_session)
    assert res["is_anomalous"] is True
    assert res["z_score"] > 2.5
    assert any("Unusually high invoice amount" in r for r in res["reasons"])


def test_anomaly_abnormal_tax_rate(db_session):
    """Effective tax rate > 35% triggers tax anomaly."""
    inv = Invoice(
        original_filename="tax_anomaly.pdf",
        stored_filename="tax_anomaly.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="New Vendor",
        subtotal=1000.0,
        tax_amount=450.0,  # 45% tax rate
        total_amount=1450.0,
    )
    db_session.add(inv)
    db_session.commit()

    res = detect_invoice_anomalies(inv, db_session)
    assert res["is_anomalous"] is True
    assert any("tax rate (45.0%) exceeds standard threshold" in r for r in res["reasons"])
