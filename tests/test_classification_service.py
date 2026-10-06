import pytest
from backend.models.invoice import Invoice, InvoiceLineItem
from backend.services.expense_classification_service import classify_expense


def test_classify_it_and_software():
    """Vendor and line items mentioning cloud, software, or AWS classify as IT & Software."""
    inv = Invoice(
        original_filename="aws_bill.pdf",
        stored_filename="aws_bill.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="Amazon Web Services Inc",
        raw_text="Monthly cloud hosting and database server charges.",
    )
    item = InvoiceLineItem(
        description="EC2 Cloud Compute and S3 Storage subscription",
        line_total=450.0,
    )
    inv.line_items = [item]

    res = classify_expense(inv)
    assert res["category"] == "IT & Software"
    assert res["method"] == "RULE_BASED"
    assert res["confidence"] >= 0.70
    assert any(kw in res["matched_keywords"] for kw in ["aws", "cloud", "server", "subscription"])


def test_classify_office_supplies():
    """Office stationery, paper, pens classify as Office Supplies."""
    inv = Invoice(
        original_filename="supplies.pdf",
        stored_filename="supplies.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="Office Depot Supplies",
        raw_text="Paper reams, ink cartridges, and ballpoint pens.",
    )
    item = InvoiceLineItem(
        description="A4 Copy Paper and Stationery Binders",
        line_total=125.0,
    )
    inv.line_items = [item]

    res = classify_expense(inv)
    assert res["category"] == "Office Supplies"
    assert res["method"] == "RULE_BASED"


def test_classify_travel():
    """Airlines, flights, hotels classify as Travel."""
    inv = Invoice(
        original_filename="flight.pdf",
        stored_filename="flight.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="Delta Airlines",
        raw_text="Round trip airfare flight ticket from NYC to SFO.",
    )
    item = InvoiceLineItem(
        description="Business Class Flight Airfare",
        line_total=850.0,
    )
    inv.line_items = [item]

    res = classify_expense(inv)
    assert res["category"] == "Travel"
    assert res["method"] == "RULE_BASED"


def test_classify_utilities():
    """Electricity, telecom, water classify as Utilities."""
    inv = Invoice(
        original_filename="electric.pdf",
        stored_filename="electric.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="ConEd Electric & Power",
        raw_text="Commercial electricity and gas utility charges.",
    )
    res = classify_expense(inv)
    assert res["category"] == "Utilities"
    assert res["method"] == "RULE_BASED"


def test_classify_professional_services():
    """Legal, auditing, and consulting classify as Professional Services."""
    inv = Invoice(
        original_filename="legal.pdf",
        stored_filename="legal.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="Baker & McKenzie LLP",
        raw_text="Legal counsel and regulatory compliance consulting fee.",
    )
    res = classify_expense(inv)
    assert res["category"] == "Professional Services"
    assert res["method"] == "RULE_BASED"


def test_classify_default_other_when_unmatched():
    """Unknown terms default to Other with standard confidence."""
    inv = Invoice(
        original_filename="random.pdf",
        stored_filename="random.pdf",
        file_path="dummy",
        file_size_bytes=1000,
        status="AI_EXTRACTED",
        vendor_name="XYZ Corporation 123",
        raw_text="General unspecified charges invoice.",
    )
    res = classify_expense(inv)
    assert res["category"] == "Other"
    assert res["confidence"] == 0.30
    assert res["method"] == "DEFAULT"
