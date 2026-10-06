import io
import csv
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
import pymupdf  # PyMuPDF

from backend.models.invoice import (
    Invoice,
    InvoiceLineItem,
    ACTION_REPORT_GENERATED,
)
from backend.services.audit_service import record_audit_event
from backend.services.analytics_service import get_dashboard_summary, get_spend_analytics


def generate_invoices_csv(db: Session, filters: Optional[Dict[str, Any]] = None) -> str:
    """
    Generate CSV data for all registered invoices.
    """
    query = db.query(Invoice).order_by(Invoice.id.desc())
    invoices = query.all()

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Invoice ID",
        "Vendor",
        "Invoice Number",
        "Invoice Date",
        "Due Date",
        "Subtotal",
        "Tax",
        "Total",
        "Currency",
        "Category",
        "Risk Score",
        "Risk Level",
        "Duplicate Flag",
        "Anomaly Flag",
        "Approval Recommendation",
        "Status",
        "Uploaded At",
    ])

    for inv in invoices:
        writer.writerow([
            inv.id,
            inv.vendor_name or "",
            inv.invoice_number or "",
            inv.invoice_date or "",
            inv.due_date or "",
            f"{inv.subtotal:.2f}" if inv.subtotal is not None else "",
            f"{inv.tax_amount:.2f}" if inv.tax_amount is not None else "",
            f"{inv.total_amount:.2f}" if inv.total_amount is not None else "",
            inv.currency or "",
            inv.expense_category or "Uncategorized",
            inv.risk_score if inv.risk_score is not None else "",
            inv.risk_level or "",
            "YES" if inv.duplicate_flag else "NO",
            "YES" if inv.anomaly_flag else "NO",
            inv.approval_recommendation or "PENDING",
            inv.status,
            inv.upload_timestamp.strftime("%Y-%m-%d %H:%M:%S") if inv.upload_timestamp else "",
        ])

    try:
        record_audit_event(
            db=db,
            action=ACTION_REPORT_GENERATED,
            status="SUCCESS",
            message=f"Generated Invoice Registry CSV report ({len(invoices)} records)",
        )
    except Exception:
        pass

    return output.getvalue()


def generate_line_items_csv(db: Session, invoice_id: Optional[int] = None) -> str:
    """
    Generate CSV data for itemized line items across invoices.
    """
    query = db.query(InvoiceLineItem).join(Invoice)
    if invoice_id is not None:
        query = query.filter(InvoiceLineItem.invoice_id == invoice_id)

    items = query.order_by(InvoiceLineItem.invoice_id.desc(), InvoiceLineItem.id.asc()).all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Invoice ID",
        "Vendor",
        "Invoice Number",
        "Line Item ID",
        "Description",
        "Quantity",
        "Unit Price",
        "Tax Rate (%)",
        "Line Total",
    ])

    for it in items:
        inv = it.invoice
        writer.writerow([
            it.invoice_id,
            (inv.vendor_name if inv else "") or "",
            (inv.invoice_number if inv else "") or "",
            it.id,
            it.description,
            it.quantity if it.quantity is not None else "",
            f"{it.unit_price:.2f}" if it.unit_price is not None else "",
            it.tax_rate if it.tax_rate is not None else "",
            f"{it.line_total:.2f}" if it.line_total is not None else "",
        ])

    return output.getvalue()


def generate_analytics_summary_pdf(db: Session) -> bytes:
    """
    Generate an executive summary PDF report using PyMuPDF.
    Includes system KPIs, spend by category, top vendors, and risk overview.
    """
    summary = get_dashboard_summary(db)
    analytics = get_spend_analytics(db)

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Header Bar
    page.draw_rect(pymupdf.Rect(0, 0, 595, 70), color=None, fill=(0.12, 0.28, 0.54))
    page.insert_text(
        pymupdf.Point(36, 42),
        "AI INVOICE PROCESSING & AUTOMATION SYSTEM",
        fontsize=16,
        color=(1, 1, 1),
    )
    page.insert_text(
        pymupdf.Point(36, 58),
        f"Executive Analytics Summary Report • Generated {now_str}",
        fontsize=9,
        color=(0.85, 0.9, 0.98),
    )

    y = 100

    # Section 1: Key Performance Indicators
    page.insert_text(pymupdf.Point(36, y), "1. Operational KPI Overview", fontsize=12, color=(0.12, 0.28, 0.54))
    page.draw_line(pymupdf.Point(36, y + 4), pymupdf.Point(559, y + 4), color=(0.7, 0.7, 0.7), width=0.8)
    y += 24

    kpi_items = [
        ("Total Invoices", str(summary["total_invoices"])),
        ("Total Spend Value", f"${summary['total_invoice_value']:,.2f}"),
        ("Fully Processed", str(summary["processed_invoices"])),
        ("Pending Processing", str(summary["pending_invoices"])),
        ("High Risk Invoices", str(summary["high_risk_invoices"])),
        ("Duplicate Flags", str(summary["duplicate_invoices"])),
        ("Anomalous Invoices", str(summary["anomalous_invoices"])),
        ("Auto-Approved", str(summary["auto_approved_invoices"])),
    ]

    col_w = 260
    for idx, (label, val) in enumerate(kpi_items):
        cx = 36 + (idx % 2) * col_w
        cy = y + (idx // 2) * 18
        page.insert_text(pymupdf.Point(cx, cy), f"• {label}:", fontsize=9, color=(0.3, 0.3, 0.3))
        page.insert_text(pymupdf.Point(cx + 140, cy), val, fontsize=9, color=(0.1, 0.1, 0.1))

    y += 85

    # Section 2: Expense Breakdown by Category
    page.insert_text(pymupdf.Point(36, y), "2. Spending by Expense Category", fontsize=12, color=(0.12, 0.28, 0.54))
    page.draw_line(pymupdf.Point(36, y + 4), pymupdf.Point(559, y + 4), color=(0.7, 0.7, 0.7), width=0.8)
    y += 20

    cats = analytics.get("category_spending", [])
    if not cats:
        page.insert_text(pymupdf.Point(36, y), "No category data available.", fontsize=9, color=(0.5, 0.5, 0.5))
        y += 20
    else:
        # Table Header
        page.draw_rect(pymupdf.Rect(36, y - 10, 559, y + 6), fill=(0.92, 0.94, 0.98))
        page.insert_text(pymupdf.Point(40, y), "Category", fontsize=8, color=(0.2, 0.2, 0.2))
        page.insert_text(pymupdf.Point(300, y), "Invoice Count", fontsize=8, color=(0.2, 0.2, 0.2))
        page.insert_text(pymupdf.Point(450, y), "Total Amount (USD)", fontsize=8, color=(0.2, 0.2, 0.2))
        y += 16

        for c in cats[:8]:
            page.insert_text(pymupdf.Point(40, y), c["category"], fontsize=8, color=(0.1, 0.1, 0.1))
            page.insert_text(pymupdf.Point(310, y), str(c["count"]), fontsize=8, color=(0.1, 0.1, 0.1))
            page.insert_text(pymupdf.Point(450, y), f"${c['total_amount']:,.2f}", fontsize=8, color=(0.1, 0.1, 0.1))
            y += 14

    y += 15

    # Section 3: Top Vendors
    page.insert_text(pymupdf.Point(36, y), "3. Top Vendors by Invoiced Amount", fontsize=12, color=(0.12, 0.28, 0.54))
    page.draw_line(pymupdf.Point(36, y + 4), pymupdf.Point(559, y + 4), color=(0.7, 0.7, 0.7), width=0.8)
    y += 20

    vendors = analytics.get("vendor_spending", [])
    if not vendors:
        page.insert_text(pymupdf.Point(36, y), "No vendor data available.", fontsize=9, color=(0.5, 0.5, 0.5))
        y += 20
    else:
        page.draw_rect(pymupdf.Rect(36, y - 10, 559, y + 6), fill=(0.92, 0.94, 0.98))
        page.insert_text(pymupdf.Point(40, y), "Vendor", fontsize=8, color=(0.2, 0.2, 0.2))
        page.insert_text(pymupdf.Point(300, y), "Invoice Count", fontsize=8, color=(0.2, 0.2, 0.2))
        page.insert_text(pymupdf.Point(450, y), "Total Amount (USD)", fontsize=8, color=(0.2, 0.2, 0.2))
        y += 16

        for v in vendors[:8]:
            page.insert_text(pymupdf.Point(40, y), (v["vendor"] or "Unknown")[:40], fontsize=8, color=(0.1, 0.1, 0.1))
            page.insert_text(pymupdf.Point(310, y), str(v["count"]), fontsize=8, color=(0.1, 0.1, 0.1))
            page.insert_text(pymupdf.Point(450, y), f"${v['total_amount']:,.2f}", fontsize=8, color=(0.1, 0.1, 0.1))
            y += 14

    y += 15

    # Section 4: Risk & Recommendations Distribution
    page.insert_text(pymupdf.Point(36, y), "4. Risk & Approval Distribution", fontsize=12, color=(0.12, 0.28, 0.54))
    page.draw_line(pymupdf.Point(36, y + 4), pymupdf.Point(559, y + 4), color=(0.7, 0.7, 0.7), width=0.8)
    y += 20

    risk_dist = analytics.get("risk_distribution", {})
    rec_dist = analytics.get("recommendation_distribution", {})

    page.insert_text(pymupdf.Point(40, y), f"Risk Levels: LOW ({risk_dist.get('LOW', 0)}), MEDIUM ({risk_dist.get('MEDIUM', 0)}), HIGH ({risk_dist.get('HIGH', 0)})", fontsize=9, color=(0.2, 0.2, 0.2))
    y += 16
    page.insert_text(pymupdf.Point(40, y), f"Approval Recommendations: AUTO_APPROVE ({rec_dist.get('AUTO_APPROVE', 0)}), MANUAL_REVIEW ({rec_dist.get('MANUAL_REVIEW', 0)}), REJECT ({rec_dist.get('REJECT_RECOMMENDED', 0)})", fontsize=9, color=(0.2, 0.2, 0.2))

    # Footer
    page.insert_text(
        pymupdf.Point(36, 810),
        "Confidential • Generated by AI-Powered Intelligent Invoice Processing System",
        fontsize=8,
        color=(0.5, 0.5, 0.5),
    )

    pdf_bytes = doc.tobytes()
    doc.close()

    try:
        record_audit_event(
            db=db,
            action=ACTION_REPORT_GENERATED,
            status="SUCCESS",
            message="Generated Executive Analytics PDF Report",
        )
    except Exception:
        pass

    return pdf_bytes


def generate_invoice_detail_pdf(db: Session, invoice_id: int) -> bytes:
    """
    Generate an individual invoice audit report PDF using PyMuPDF.
    Contains vendor metadata, line items, mathematical validation, duplicate check, and approval recommendation.
    """
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise ValueError(f"Invoice #{invoice_id} not found.")

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Header Bar
    page.draw_rect(pymupdf.Rect(0, 0, 595, 70), color=None, fill=(0.12, 0.28, 0.54))
    page.insert_text(
        pymupdf.Point(36, 38),
        f"INVOICE AUDIT REPORT #{inv.id}",
        fontsize=16,
        color=(1, 1, 1),
    )
    page.insert_text(
        pymupdf.Point(36, 54),
        f"File: {inv.original_filename} • Generated {now_str}",
        fontsize=9,
        color=(0.85, 0.9, 0.98),
    )

    y = 95

    # 1. Metadata Block
    page.insert_text(pymupdf.Point(36, y), "1. Invoice Metadata & Vendor Details", fontsize=11, color=(0.12, 0.28, 0.54))
    page.draw_line(pymupdf.Point(36, y + 3), pymupdf.Point(559, y + 3), color=(0.7, 0.7, 0.7), width=0.8)
    y += 16

    metadata = [
        ("Vendor Name", inv.vendor_name or "N/A"),
        ("Invoice Number", inv.invoice_number or "N/A"),
        ("Invoice Date", inv.invoice_date or "N/A"),
        ("Due Date", inv.due_date or "N/A"),
        ("GSTIN / Tax ID", inv.vendor_gstin or "N/A"),
        ("PO Number", inv.purchase_order_number or "N/A"),
        ("Status", inv.status),
        ("Expense Category", inv.expense_category or "Uncategorized"),
    ]

    for idx, (label, val) in enumerate(metadata):
        cx = 36 + (idx % 2) * 260
        cy = y + (idx // 2) * 15
        page.insert_text(pymupdf.Point(cx, cy), f"• {label}:", fontsize=8, color=(0.3, 0.3, 0.3))
        page.insert_text(pymupdf.Point(cx + 90, cy), str(val)[:32], fontsize=8, color=(0.1, 0.1, 0.1))

    y += 65

    # 2. Financial Summary
    page.insert_text(pymupdf.Point(36, y), "2. Financial Summary", fontsize=11, color=(0.12, 0.28, 0.54))
    page.draw_line(pymupdf.Point(36, y + 3), pymupdf.Point(559, y + 3), color=(0.7, 0.7, 0.7), width=0.8)
    y += 16

    curr = inv.currency or "$"
    subt = f"{curr} {inv.subtotal:,.2f}" if inv.subtotal is not None else "N/A"
    tax = f"{curr} {inv.tax_amount:,.2f}" if inv.tax_amount is not None else "N/A"
    total = f"{curr} {inv.total_amount:,.2f}" if inv.total_amount is not None else "N/A"

    page.insert_text(pymupdf.Point(40, y), f"Subtotal: {subt}", fontsize=9, color=(0.2, 0.2, 0.2))
    page.insert_text(pymupdf.Point(220, y), f"Tax Amount: {tax}", fontsize=9, color=(0.2, 0.2, 0.2))
    page.insert_text(pymupdf.Point(400, y), f"Total: {total}", fontsize=9, color=(0.1, 0.4, 0.1))
    y += 24

    # 3. Line Items
    page.insert_text(pymupdf.Point(36, y), "3. Line Items", fontsize=11, color=(0.12, 0.28, 0.54))
    page.draw_line(pymupdf.Point(36, y + 3), pymupdf.Point(559, y + 3), color=(0.7, 0.7, 0.7), width=0.8)
    y += 16

    if not inv.line_items:
        page.insert_text(pymupdf.Point(40, y), "No itemized line items found.", fontsize=8, color=(0.5, 0.5, 0.5))
        y += 18
    else:
        page.draw_rect(pymupdf.Rect(36, y - 8, 559, y + 6), fill=(0.92, 0.94, 0.98))
        page.insert_text(pymupdf.Point(40, y), "Description", fontsize=7.5, color=(0.2, 0.2, 0.2))
        page.insert_text(pymupdf.Point(300, y), "Qty", fontsize=7.5, color=(0.2, 0.2, 0.2))
        page.insert_text(pymupdf.Point(360, y), "Unit Price", fontsize=7.5, color=(0.2, 0.2, 0.2))
        page.insert_text(pymupdf.Point(440, y), "Tax", fontsize=7.5, color=(0.2, 0.2, 0.2))
        page.insert_text(pymupdf.Point(500, y), "Total", fontsize=7.5, color=(0.2, 0.2, 0.2))
        y += 14

        for item in inv.line_items[:12]:
            page.insert_text(pymupdf.Point(40, y), item.description[:45], fontsize=7.5, color=(0.1, 0.1, 0.1))
            page.insert_text(pymupdf.Point(300, y), str(item.quantity) if item.quantity is not None else "—", fontsize=7.5, color=(0.1, 0.1, 0.1))
            page.insert_text(pymupdf.Point(360, y), f"{curr}{item.unit_price:.2f}" if item.unit_price is not None else "—", fontsize=7.5, color=(0.1, 0.1, 0.1))
            page.insert_text(pymupdf.Point(440, y), f"{item.tax_rate}%" if item.tax_rate is not None else "—", fontsize=7.5, color=(0.1, 0.1, 0.1))
            page.insert_text(pymupdf.Point(500, y), f"{curr}{item.line_total:.2f}" if item.line_total is not None else "—", fontsize=7.5, color=(0.1, 0.1, 0.1))
            y += 12

    y += 12

    # 4. Automation & Risk Assessment
    page.insert_text(pymupdf.Point(36, y), "4. AI & Deterministic Automation Analysis", fontsize=11, color=(0.12, 0.28, 0.54))
    page.draw_line(pymupdf.Point(36, y + 3), pymupdf.Point(559, y + 3), color=(0.7, 0.7, 0.7), width=0.8)
    y += 18

    # Recommendation Box
    rec = inv.approval_recommendation or "PENDING"
    rec_color = (0.1, 0.6, 0.2) if rec == "AUTO_APPROVE" else ((0.8, 0.6, 0.1) if rec == "MANUAL_REVIEW" else (0.8, 0.1, 0.1))
    page.insert_text(pymupdf.Point(40, y), f"AI Approval Recommendation: {rec}", fontsize=10, color=rec_color)
    y += 14
    page.insert_text(pymupdf.Point(40, y), f"Justification: {(inv.approval_reason or 'No details available.')[:100]}", fontsize=8, color=(0.2, 0.2, 0.2))
    y += 18

    # Risk & Validation Breakdown
    score_str = f"{inv.risk_score}/100 ({inv.risk_level or 'LOW'})" if inv.risk_score is not None else "Not calculated"
    page.insert_text(pymupdf.Point(40, y), f"• Risk Score: {score_str}", fontsize=8.5, color=(0.1, 0.1, 0.1))
    page.insert_text(pymupdf.Point(260, y), f"• Validation Status: {inv.validation_status or 'PENDING'}", fontsize=8.5, color=(0.1, 0.1, 0.1))
    y += 14

    dup_str = f"YES (Matched #{inv.duplicate_invoice_id})" if inv.duplicate_flag else "NO (Unique)"
    anom_str = "YES (Anomalous)" if inv.anomaly_flag else "NO (Standard)"
    page.insert_text(pymupdf.Point(40, y), f"• Duplicate Detected: {dup_str}", fontsize=8.5, color=(0.1, 0.1, 0.1))
    page.insert_text(pymupdf.Point(260, y), f"• Spending Anomaly: {anom_str}", fontsize=8.5, color=(0.1, 0.1, 0.1))
    y += 20

    # 5. Audit Trail Summary
    page.insert_text(pymupdf.Point(36, y), "5. Invoice Audit Events History", fontsize=11, color=(0.12, 0.28, 0.54))
    page.draw_line(pymupdf.Point(36, y + 3), pymupdf.Point(559, y + 3), color=(0.7, 0.7, 0.7), width=0.8)
    y += 16

    logs = inv.audit_logs[-6:] if inv.audit_logs else []
    if not logs:
        page.insert_text(pymupdf.Point(40, y), "No audit events logged yet.", fontsize=8, color=(0.5, 0.5, 0.5))
    else:
        for entry in logs:
            ts_str = entry.timestamp.strftime("%Y-%m-%d %H:%M") if entry.timestamp else ""
            msg = (entry.message or entry.action)[:65]
            page.insert_text(pymupdf.Point(40, y), f"[{ts_str}] {entry.action} ({entry.status}): {msg}", fontsize=7.5, color=(0.2, 0.2, 0.2))
            y += 12

    # Footer
    page.insert_text(
        pymupdf.Point(36, 810),
        "Confidential • Generated by AI-Powered Intelligent Invoice Processing System",
        fontsize=8,
        color=(0.5, 0.5, 0.5),
    )

    pdf_bytes = doc.tobytes()
    doc.close()

    try:
        record_audit_event(
            db=db,
            action=ACTION_REPORT_GENERATED,
            status="SUCCESS",
            invoice_id=inv.id,
            message=f"Generated PDF Audit Report for Invoice #{inv.id}",
        )
    except Exception:
        pass

    return pdf_bytes
