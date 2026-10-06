from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import re
from backend.models.invoice import Invoice, VAL_PASSED, VAL_WARNINGS, VAL_FAILED


def parse_date_string(date_str: Optional[str]) -> Optional[datetime]:
    """
    Attempt to parse a date string across various common international and business formats.
    Returns datetime in UTC or None if unparseable.
    """
    if not date_str or not isinstance(date_str, str):
        return None

    cleaned = date_str.strip()
    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%Y.%m.%d",
        "%d %b %Y",
        "%d %B %Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    # Fallback regex for ISO dates with possible trailing characters
    iso_match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", cleaned)
    if iso_match:
        try:
            y, m, d = map(int, iso_match.groups())
            return datetime(y, m, d, tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


def validate_invoice(invoice: Invoice, tolerance: float = 0.05) -> Dict[str, Any]:
    """
    Perform multi-attribute validation on an invoice record:
    1. Required and recommended field presence.
    2. Financial reconciliation (subtotal + tax ≈ total).
    3. Line item arithmetic and subtotal alignment.
    4. Negative value validation.
    5. Date sanity checks (due date >= invoice date, not absurdly in future).

    Returns a structured dictionary with passed boolean, status, errors, and warnings.
    """
    errors: List[str] = []
    warnings: List[str] = []

    # 1. Required / Important Fields Check
    if invoice.total_amount is None:
        errors.append("Missing required financial field: Total Amount.")
    elif invoice.total_amount < 0:
        errors.append(f"Invalid negative total amount ({invoice.total_amount:.2f}).")
    elif invoice.total_amount == 0:
        warnings.append("Total amount is 0.00 (verify if promotional or zero-value invoice).")

    if not invoice.vendor_name or not invoice.vendor_name.strip():
        warnings.append("Missing vendor name.")

    if not invoice.invoice_number or not invoice.invoice_number.strip():
        warnings.append("Missing invoice number identifier.")

    if not invoice.invoice_date or not invoice.invoice_date.strip():
        warnings.append("Missing invoice issue date.")

    if not invoice.currency or not invoice.currency.strip():
        warnings.append("Missing currency specification.")

    # 2. Financial Reconciliation Check (subtotal + tax_amount ≈ total_amount)
    subtotal = invoice.subtotal
    tax = invoice.tax_amount
    total = invoice.total_amount

    if subtotal is not None and tax is not None and total is not None:
        expected_total = subtotal + tax
        discrepancy = abs(expected_total - total)
        if discrepancy > tolerance:
            errors.append(
                f"Financial calculation mismatch: Subtotal ({subtotal:.2f}) + Tax ({tax:.2f}) "
                f"= {expected_total:.2f}, but Total is {total:.2f} (Discrepancy: {discrepancy:.2f})."
            )

    # 3. Line Item Consistency Checks
    if invoice.line_items:
        line_item_totals: List[float] = []

        for idx, item in enumerate(invoice.line_items, start=1):
            desc = item.description or f"Item #{idx}"

            # Check for negative values
            if item.quantity is not None and item.quantity < 0:
                errors.append(f"Line item '{desc}' contains negative quantity ({item.quantity}).")
            if item.unit_price is not None and item.unit_price < 0:
                errors.append(f"Line item '{desc}' contains negative unit price ({item.unit_price:.2f}).")
            if item.line_total is not None and item.line_total < 0:
                errors.append(f"Line item '{desc}' contains negative line total ({item.line_total:.2f}).")

            # Check quantity * unit_price == line_total
            if (
                item.quantity is not None
                and item.unit_price is not None
                and item.line_total is not None
            ):
                computed_line_total = item.quantity * item.unit_price
                if abs(computed_line_total - item.line_total) > tolerance:
                    warnings.append(
                        f"Line item '{desc}' quantity ({item.quantity}) * unit price ({item.unit_price:.2f}) "
                        f"= {computed_line_total:.2f}, but line total is {item.line_total:.2f}."
                    )

            if item.line_total is not None:
                line_item_totals.append(item.line_total)

        # Compare sum of line items with subtotal or total
        if line_item_totals and subtotal is not None:
            sum_line_items = sum(line_item_totals)
            if abs(sum_line_items - subtotal) > (tolerance * 2):
                warnings.append(
                    f"Sum of line item totals ({sum_line_items:.2f}) does not match "
                    f"invoice subtotal ({subtotal:.2f})."
                )

    # 4. Date Validation
    parsed_inv_date = parse_date_string(invoice.invoice_date)
    parsed_due_date = parse_date_string(invoice.due_date)

    now_utc = datetime.now(timezone.utc)

    if parsed_inv_date:
        # Flag if invoice date is suspiciously far in the future (> 30 days ahead)
        if parsed_inv_date > now_utc + timedelta(days=30):
            warnings.append(
                f"Invoice issue date ({invoice.invoice_date}) is in the future."
            )

    if parsed_inv_date and parsed_due_date:
        if parsed_due_date < parsed_inv_date:
            errors.append(
                f"Due date ({invoice.due_date}) is earlier than invoice date ({invoice.invoice_date})."
            )

    # Overall Status Determination
    if errors:
        val_status = VAL_FAILED
        passed = False
    elif warnings:
        val_status = VAL_WARNINGS
        passed = True
    else:
        val_status = VAL_PASSED
        passed = True

    return {
        "passed": passed,
        "status": val_status,
        "errors": errors,
        "warnings": warnings,
    }
