from backend.utils.text_cleaner import clean_text


def test_clean_text_empty_and_none():
    """Verify clean_text handles empty and None inputs without error."""
    assert clean_text("") == ""
    assert clean_text(None) == ""
    assert clean_text("    \n\n  \t  ") == ""


def test_clean_text_whitespace_normalization():
    """Verify multiple horizontal spaces and tabs are normalized to single spaces."""
    raw = "Invoice    Number:   \t\t INV-2026-001  \n   Date:     2026-10-06   "
    cleaned = clean_text(raw)
    assert cleaned == "Invoice Number: INV-2026-001\nDate: 2026-10-06"


def test_clean_text_excessive_newlines():
    """Verify 3+ consecutive newlines are compressed to a single blank line between blocks."""
    raw = "Header Block\n\n\n\n\nItem 1: $50.00\n\n\nItem 2: $100.00\n\n\n\nTotal: $150.00"
    cleaned = clean_text(raw)
    assert cleaned == "Header Block\n\nItem 1: $50.00\n\nItem 2: $100.00\n\nTotal: $150.00"


def test_clean_text_preserves_numbers_and_currencies():
    """Verify monetary symbols and numeric precision are preserved intact."""
    raw = (
        "Subtotal: $1,250.50\n"
        "VAT (20%): £250.10\n"
        "Euro Total: €1,500.60\n"
        "Rupees: ₹95,000.00\n"
        "Yen: ¥12,000"
    )
    cleaned = clean_text(raw)
    assert "$1,250.50" in cleaned
    assert "£250.10" in cleaned
    assert "€1,500.60" in cleaned
    assert "₹95,000.00" in cleaned
    assert "¥12,000" in cleaned


def test_clean_text_preserves_invoice_identifiers_and_dates():
    """Verify invoice numbers, PO codes, and dates remain intact."""
    raw = (
        "INVOICE #: INV-2026/OCT/9901\n"
        "PO NUMBER: PO-9812-XYZ\n"
        "ISSUE DATE: 2026-10-06\n"
        "DUE DATE: 06/11/2026\n"
        "GSTIN: 27AAAAA0000A1Z5\n"
        "Tax Rate: CGST 9% + SGST 9%"
    )
    cleaned = clean_text(raw)
    assert "INV-2026/OCT/9901" in cleaned
    assert "PO-9812-XYZ" in cleaned
    assert "2026-10-06" in cleaned
    assert "06/11/2026" in cleaned
    assert "27AAAAA0000A1Z5" in cleaned
    assert "CGST 9% + SGST 9%" in cleaned


def test_clean_text_removes_unprintable_control_characters():
    """Verify non-printable control characters are stripped while keeping valid UTF-8 symbols."""
    raw = "Company\x00 Name\x07 LLC\x1f - \u00a0$500.00"
    cleaned = clean_text(raw)
    assert cleaned == "Company Name LLC - $500.00"
