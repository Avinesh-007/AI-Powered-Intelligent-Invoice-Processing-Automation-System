import os
import sys
from pathlib import Path
import datetime
import requests
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Add workspace root to Python path so backend modules can be resolved
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.config import settings
from backend.database.session import SessionLocal, init_db
from backend.models.invoice import Invoice, InvoiceLineItem, AuditLog
from backend.services.file_service import save_and_register_invoice
from backend.services.document_service import process_invoice_record
from backend.services.ocr_service import is_tesseract_available, get_tesseract_command
from backend.services.ai_extraction_service import (
    extract_and_persist_invoice,
    is_gemini_configured,
)
from backend.services.automation_service import (
    analyze_invoice,
    get_invoice_analysis,
    run_full_automation,
)
from backend.services.analytics_service import (
    get_dashboard_summary,
    get_spend_analytics,
)
from backend.services.report_service import (
    generate_invoices_csv,
    generate_line_items_csv,
    generate_analytics_summary_pdf,
    generate_invoice_detail_pdf,
)
from backend.services.audit_service import (
    get_invoice_audit_trail,
    get_system_audit_trail,
)
from backend.utils.validators import ValidationError

# Ensure database tables and schema migrations are initialized
init_db()

# Streamlit Page Setup
st.set_page_config(
    page_title="InvoiceAI — Enterprise Automation",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

BACKEND_API_URL = f"http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}{settings.API_V1_PREFIX}"


# ==============================================================================
# BACKEND API & FALLBACK DATA HELPERS
# ==============================================================================

def check_backend_health() -> bool:
    """Check if the FastAPI backend service is responding."""
    try:
        response = requests.get(f"{BACKEND_API_URL}/health", timeout=1.5)
        if response.status_code == 200 and response.json().get("status") == "healthy":
            return True
    except Exception:
        pass
    return False


def fetch_dashboard_summary():
    """Retrieve top-level KPI metrics via API or direct DB fallback."""
    if check_backend_health():
        try:
            resp = requests.get(f"{BACKEND_API_URL}/dashboard/summary", timeout=3)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass

    db = SessionLocal()
    try:
        return get_dashboard_summary(db)
    finally:
        db.close()


def fetch_spend_analytics(category=None, vendor=None, risk_level=None, start_date=None, end_date=None):
    """Retrieve aggregated spend analytics via API or direct DB fallback."""
    if check_backend_health():
        try:
            params = {}
            if category and category != "All":
                params["category"] = category
            if vendor and vendor != "All":
                params["vendor"] = vendor
            if risk_level and risk_level != "All":
                params["risk"] = risk_level
            if start_date:
                params["date_from"] = str(start_date)
            if end_date:
                params["date_to"] = str(end_date)
            resp = requests.get(f"{BACKEND_API_URL}/analytics/spending", params=params, timeout=5)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass

    db = SessionLocal()
    try:
        return get_spend_analytics(
            db=db,
            category_filter=category if category != "All" else None,
            vendor_filter=vendor if vendor != "All" else None,
            risk_filter=risk_level if risk_level != "All" else None,
            date_from=str(start_date) if start_date else None,
            date_to=str(end_date) if end_date else None,
        )
    finally:
        db.close()


def get_existing_invoices():
    """Retrieve existing invoices either from backend API or directly via DB session."""
    try:
        resp = requests.get(f"{BACKEND_API_URL}/invoices", timeout=2.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass

    db = SessionLocal()
    try:
        invoices = db.query(Invoice).order_by(Invoice.id.desc()).all()
        return [
            {
                "id": inv.id,
                "original_filename": inv.original_filename,
                "file_size_bytes": inv.file_size_bytes,
                "status": inv.status,
                "extraction_method": inv.extraction_method or "None",
                "vendor_name": inv.vendor_name or "N/A",
                "invoice_number": inv.invoice_number or "N/A",
                "invoice_date": inv.invoice_date or "",
                "total_amount": inv.total_amount,
                "currency": inv.currency or "",
                "expense_category": inv.expense_category or "Uncategorized",
                "risk_level": inv.risk_level or "N/A",
                "risk_score": inv.risk_score,
                "approval_recommendation": inv.approval_recommendation or "Pending",
                "duplicate_flag": bool(inv.duplicate_flag),
                "anomaly_flag": bool(inv.anomaly_flag),
                "is_anomalous": bool(inv.anomaly_flag),
                "upload_timestamp": inv.upload_timestamp.strftime("%Y-%m-%d %H:%M:%S")
                if inv.upload_timestamp
                else "",
            }
            for inv in invoices
        ]
    finally:
        db.close()


def fetch_invoice_text(invoice_id: int):
    """Retrieve raw extracted text for an invoice via API or direct DB."""
    try:
        resp = requests.get(f"{BACKEND_API_URL}/invoices/{invoice_id}/text", timeout=2.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass

    db = SessionLocal()
    try:
        inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if inv:
            return {
                "invoice_id": inv.id,
                "status": inv.status,
                "extraction_method": inv.extraction_method,
                "raw_text": inv.raw_text,
                "text_length": len(inv.raw_text or ""),
            }
    finally:
        db.close()
    return None


def fetch_structured_invoice(invoice_id: int):
    """Retrieve structured invoice data and line items via API or direct DB."""
    try:
        resp = requests.get(f"{BACKEND_API_URL}/invoices/{invoice_id}/extracted", timeout=2.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass

    db = SessionLocal()
    try:
        inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if inv:
            items = [
                {
                    "id": item.id,
                    "invoice_id": item.invoice_id,
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "tax_rate": item.tax_rate,
                    "line_total": item.line_total,
                }
                for item in inv.line_items
            ]
            return {
                "invoice_id": inv.id,
                "status": inv.status,
                "extraction_method": inv.extraction_method,
                "original_filename": inv.original_filename,
                "vendor_name": inv.vendor_name,
                "vendor_address": inv.vendor_address,
                "vendor_gstin": inv.vendor_gstin,
                "invoice_number": inv.invoice_number,
                "invoice_date": inv.invoice_date,
                "due_date": inv.due_date,
                "purchase_order_number": inv.purchase_order_number,
                "payment_terms": inv.payment_terms,
                "currency": inv.currency,
                "subtotal": inv.subtotal,
                "tax_amount": inv.tax_amount,
                "total_amount": inv.total_amount,
                "line_items": items,
                "raw_text": inv.raw_text,
            }
    finally:
        db.close()
    return None


def execute_invoice_processing(invoice_id: int):
    """Trigger text extraction via FastAPI endpoint or direct service fallback."""
    if check_backend_health():
        try:
            resp = requests.post(f"{BACKEND_API_URL}/invoices/{invoice_id}/process", timeout=30)
            if resp.status_code == 200:
                return resp.json(), None
            else:
                detail = resp.json().get("detail", resp.text)
                return None, f"Backend processing error: {detail}"
        except Exception as exc:
            return None, f"Failed to contact backend API: {exc}"

    db = SessionLocal()
    try:
        inv = process_invoice_record(invoice_id=invoice_id, db=db)
        return {
            "invoice_id": inv.id,
            "status": inv.status,
            "extraction_method": inv.extraction_method,
            "text_length": len(inv.raw_text or ""),
        }, None
    except Exception as exc:
        return None, str(exc)
    finally:
        db.close()


def execute_ai_extraction(invoice_id: int):
    """Trigger Gemini AI structured extraction via FastAPI endpoint or direct service."""
    if check_backend_health():
        try:
            resp = requests.post(f"{BACKEND_API_URL}/invoices/{invoice_id}/extract", timeout=45)
            if resp.status_code == 200:
                return resp.json(), None
            else:
                detail = resp.json().get("detail", resp.text)
                return None, f"AI Extraction error: {detail}"
        except Exception as exc:
            return None, f"Failed to contact backend API: {exc}"

    db = SessionLocal()
    try:
        inv = extract_and_persist_invoice(invoice_id=invoice_id, db=db)
        return {
            "invoice_id": inv.id,
            "status": inv.status,
            "vendor_name": inv.vendor_name,
            "invoice_number": inv.invoice_number,
            "total_amount": inv.total_amount,
        }, None
    except Exception as exc:
        return None, str(exc)
    finally:
        db.close()


def fetch_invoice_analysis(invoice_id: int):
    """Retrieve stored automation analysis data via API or direct DB fallback."""
    if check_backend_health():
        try:
            resp = requests.get(f"{BACKEND_API_URL}/invoices/{invoice_id}/analysis", timeout=5)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass

    db = SessionLocal()
    try:
        return get_invoice_analysis(invoice_id=invoice_id, db=db)
    except Exception:
        return None
    finally:
        db.close()


def execute_invoice_analysis(invoice_id: int):
    """Trigger intelligent validation, duplicate, classification, and risk analysis."""
    if check_backend_health():
        try:
            resp = requests.post(f"{BACKEND_API_URL}/invoices/{invoice_id}/analyze", timeout=20)
            if resp.status_code == 200:
                return resp.json(), None
            else:
                detail = resp.json().get("detail", resp.text)
                return None, f"Analysis error: {detail}"
        except Exception as exc:
            return None, f"Failed to contact backend API: {exc}"

    db = SessionLocal()
    try:
        result = analyze_invoice(invoice_id=invoice_id, db=db)
        return result, None
    except Exception as exc:
        return None, str(exc)
    finally:
        db.close()


def execute_full_automation(invoice_id: int):
    """Trigger full end-to-end automation workflow."""
    if check_backend_health():
        try:
            resp = requests.post(f"{BACKEND_API_URL}/invoices/{invoice_id}/automate", timeout=45)
            if resp.status_code == 200:
                return resp.json(), None
            else:
                detail = resp.json().get("detail", resp.text)
                return None, f"Automation error: {detail}"
        except Exception as exc:
            return None, f"Failed to contact backend API: {exc}"

    db = SessionLocal()
    try:
        result = run_full_automation(invoice_id=invoice_id, db=db)
        return result, None
    except Exception as exc:
        return None, str(exc)
    finally:
        db.close()


def fetch_audit_logs(invoice_id=None, limit=100):
    """Retrieve audit history from backend or direct DB."""
    if check_backend_health():
        try:
            if invoice_id is not None:
                resp = requests.get(f"{BACKEND_API_URL}/invoices/{invoice_id}/audit", timeout=5)
            else:
                resp = requests.get(f"{BACKEND_API_URL}/audit/logs?limit={limit}", timeout=5)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass

    db = SessionLocal()
    try:
        if invoice_id is not None:
            logs = get_invoice_audit_trail(invoice_id=invoice_id, db=db)
        else:
            logs = get_system_audit_trail(limit=limit, db=db)
        return [
            {
                "id": log.id,
                "invoice_id": log.invoice_id,
                "action": log.action,
                "status": log.status,
                "message": log.message,
                "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S") if log.timestamp else "",
            }
            for log in logs
        ]
    finally:
        db.close()


def get_csv_report_data(report_type="invoices"):
    """Get CSV string for invoices or line items."""
    db = SessionLocal()
    try:
        if report_type == "invoices":
            return generate_invoices_csv(db)
        else:
            return generate_line_items_csv(db)
    finally:
        db.close()


def get_pdf_summary_report():
    """Get summary PDF bytes."""
    db = SessionLocal()
    try:
        return generate_analytics_summary_pdf(db)
    finally:
        db.close()


def get_pdf_invoice_report(invoice_id: int):
    """Get single invoice detail PDF bytes."""
    db = SessionLocal()
    try:
        return generate_invoice_detail_pdf(db=db, invoice_id=invoice_id)
    finally:
        db.close()


# ==============================================================================
# SIDEBAR NAVIGATION & SYSTEM BADGES
# ==============================================================================
with st.sidebar:
    st.markdown("## 📄 **InvoiceAI Platform**")
    st.caption("Intelligent Ingestion, Extraction & Automation")
    st.divider()

    nav_selection = st.radio(
        "Navigation",
        options=[
            "📊 Dashboard",
            "🚀 Upload & Process",
            "📑 Invoice Registry",
            "🔍 Detailed Analysis",
            "⚖️ Approval Queue",
            "📈 Spend Analytics",
            "📥 Reports & Export",
            "📜 Audit Trail",
            "⚙️ System Health",
        ],
        index=0,
    )

    st.divider()
    st.markdown("### 🟢 Environment Status")
    backend_online = check_backend_health()
    if backend_online:
        st.success("FastAPI: Online")
    else:
        st.warning("FastAPI: Standalone Mode (Direct SQLite)")

    tess_avail = is_tesseract_available()
    if tess_avail:
        st.success("Tesseract OCR: Ready")
    else:
        st.info("PyMuPDF Native Engine")

    gemini_ready = is_gemini_configured()
    if gemini_ready:
        st.success(f"Gemini AI: Active ({settings.GEMINI_MODEL})")
    else:
        st.warning("Gemini AI: Mock Mode (Key Missing)")

    st.divider()
    st.caption("AI-Powered Intelligent Invoice Processing • v1.0.0")


# ==============================================================================
# PAGE 1: 📊 DASHBOARD (EXECUTIVE OVERVIEW)
# ==============================================================================
if nav_selection == "📊 Dashboard":
    st.title("📊 Executive Dashboard")
    st.markdown("Real-time summary of ingested invoices, financial commitments, and intelligent risk automation.")
    st.divider()

    summary = fetch_dashboard_summary()
    tot_inv = summary.get("total_invoices", 0)
    tot_spend = summary.get("total_invoice_value", summary.get("total_spend", 0.0))

    if tot_inv == 0:
        st.info("👋 **Welcome to the Intelligent Invoice Processing System!**\n\nNo invoices have been ingested into the system yet. Navigate to **🚀 Upload & Process** in the sidebar to upload your first invoice (PDF, PNG, JPG).")
    else:
        # Top 8 KPI Metric Cards
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Invoices", f"{tot_inv:,}")
        with col2:
            st.metric("Total Spend", f"${tot_spend:,.2f}")
        with col3:
            proc_count = summary.get("processed_invoices", 0)
            st.metric("Processed Documents", f"{proc_count:,}", f"{(proc_count / tot_inv * 100):.1f}% completed" if tot_inv else None)
        with col4:
            st.metric("Pending Invoices", f"{summary.get('pending_invoices', 0):,}")

        col5, col6, col7, col8 = st.columns(4)
        with col5:
            hi_risk = summary.get("high_risk_invoices", 0)
            st.metric("High Risk Invoices", f"{hi_risk:,}", delta=f"{hi_risk} flagged" if hi_risk else "None", delta_color="inverse")
        with col6:
            dup_cnt = summary.get("detected_duplicates", 0)
            st.metric("Detected Duplicates", f"{dup_cnt:,}", delta=f"{dup_cnt} matches" if dup_cnt else "0 duplicates", delta_color="inverse")
        with col7:
            anom_cnt = summary.get("detected_anomalies", 0)
            st.metric("Detected Anomalies", f"{anom_cnt:,}", delta=f"{anom_cnt} outliers" if anom_cnt else "Normal", delta_color="inverse")
        with col8:
            auto_app = summary.get("auto_approved_invoices", 0)
            st.metric("Auto-Approved", f"{auto_app:,}", delta=f"{(auto_app / tot_inv * 100):.1f}% pass-rate" if tot_inv else None)

        st.divider()

        # Split: Recent Activity & Quick Breakdown
        c_left, c_right = st.columns([1.6, 1.4])
        with c_left:
            st.subheader("🕒 Recent Processing Activity")
            invoices = get_existing_invoices()
            if invoices:
                recent_data = []
                for inv in invoices[:8]:
                    tot_val = inv.get("total_amount")
                    tot_str = f"${tot_val:,.2f}" if tot_val is not None else "—"
                    r_score = inv.get("risk_score")
                    score_str = f"{r_score}/100" if r_score is not None else "—"
                    recent_data.append({
                        "ID": inv.get("id"),
                        "Vendor": inv.get("vendor_name") or "—",
                        "Invoice #": inv.get("invoice_number") or "—",
                        "Total Amount": tot_str,
                        "Category": inv.get("expense_category") or "Uncategorized",
                        "Risk Score": score_str,
                        "Status": inv.get("status"),
                        "Recommendation": inv.get("approval_recommendation") or "Pending",
                    })
                st.dataframe(pd.DataFrame(recent_data), width="stretch", hide_index=True)
            else:
                st.write("No recent records.")

        with c_right:
            st.subheader("⚖️ AI Approval Breakdown")
            spend_data = fetch_spend_analytics()
            rec_dist = spend_data.get("recommendation_distribution", {})
            if any(rec_dist.values()):
                fig_rec = px.pie(
                    names=list(rec_dist.keys()),
                    values=list(rec_dist.values()),
                    color=list(rec_dist.keys()),
                    color_discrete_map={
                        "AUTO_APPROVE": "#28a745",
                        "MANUAL_REVIEW": "#ffc107",
                        "REJECT_RECOMMENDED": "#dc3545",
                        "PENDING": "#6c757d",
                    },
                    hole=0.45,
                )
                fig_rec.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=260)
                st.plotly_chart(fig_rec, width="stretch")
            else:
                st.info("Run automation on invoices to populate approval distributions.")


# ==============================================================================
# PAGE 2: 🚀 UPLOAD & PROCESS (INGESTION PIPELINE)
# ==============================================================================
elif nav_selection == "🚀 Upload & Process":
    st.title("🚀 Ingest & Process Invoices")
    st.markdown("Upload invoice documents (PDF, PNG, JPG, JPEG) and run multi-stage text extraction, Gemini AI understanding, and rule analysis.")
    st.divider()

    uploaded_file = st.file_uploader(
        label="Select Invoice Document:",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=False,
        help=f"File limit: {settings.MAX_UPLOAD_SIZE_MB} MB. Allowed formats: PDF, PNG, JPG, JPEG.",
    )

    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        file_size_mb = len(file_bytes) / (1024 * 1024)
        st.info(f"📁 Selected File: **{uploaded_file.name}** ({file_size_mb:.2f} MB)")

        if st.button("📥 Upload & Register Invoice", type="primary"):
            if file_size_mb > settings.MAX_UPLOAD_SIZE_MB:
                st.error(f"File exceeds limit of {settings.MAX_UPLOAD_SIZE_MB} MB.")
            else:
                with st.spinner("Registering invoice in SQLite database..."):
                    saved_invoice = None
                    error_msg = None

                    if backend_online:
                        try:
                            files = {
                                "file": (
                                    uploaded_file.name,
                                    file_bytes,
                                    uploaded_file.type or "application/octet-stream",
                                )
                            }
                            resp = requests.post(f"{BACKEND_API_URL}/invoices/upload", files=files, timeout=10)
                            if resp.status_code == 201:
                                saved_invoice = resp.json()
                            else:
                                error_msg = resp.json().get("detail", resp.text)
                        except Exception as exc:
                            error_msg = f"Backend upload error: {exc}"

                    if saved_invoice is None and not error_msg:
                        try:
                            db = SessionLocal()
                            try:
                                record = save_and_register_invoice(
                                    filename=uploaded_file.name,
                                    file_bytes=file_bytes,
                                    db=db,
                                )
                                saved_invoice = {
                                    "id": record.id,
                                    "original_filename": record.original_filename,
                                    "status": record.status,
                                    "file_size_bytes": record.file_size_bytes,
                                }
                            finally:
                                db.close()
                        except Exception as exc:
                            error_msg = str(exc)

                    if saved_invoice:
                        st.success(f"✅ Invoice registered successfully as **Invoice #{saved_invoice['id']}**!")
                        st.session_state["active_invoice_id"] = saved_invoice["id"]
                    else:
                        st.error(f"❌ Upload failed: {error_msg}")

    st.divider()

    # Step-by-Step Execution Pipeline Controls
    st.subheader("⚡ Processing Pipeline Controls")
    invoices_list = get_existing_invoices()
    if invoices_list:
        inv_options = {
            f"#{inv['id']} - {inv['original_filename']} ({inv['status']})": inv["id"]
            for inv in invoices_list
        }
        active_id = st.session_state.get("active_invoice_id")
        def_idx = 0
        if active_id:
            for idx, (lbl, iid) in enumerate(inv_options.items()):
                if iid == active_id:
                    def_idx = idx
                    break

        selected_label = st.selectbox("Select Target Invoice:", options=list(inv_options.keys()), index=def_idx)
        target_id = inv_options[selected_label]
        st.session_state["active_invoice_id"] = target_id

        b1, b2, b3, b4 = st.columns(4)
        with b1:
            p_clicked = st.button("⚡ 1. Process Document", help="Extract raw text using PyMuPDF / Tesseract OCR")
        with b2:
            e_clicked = st.button("🤖 2. Extract AI Fields", help="Use Gemini AI to extract structured entities & line items")
        with b3:
            a_clicked = st.button("🔎 3. Analyze Rules & Risk", help="Run deterministic validation, duplicates, categories, and risk scoring")
        with b4:
            f_clicked = st.button("🚀 Full End-to-End Pipeline", type="primary", help="Execute complete pipeline: Document -> AI -> Rules -> Risk Decision")

        if p_clicked:
            with st.spinner("Extracting text via PyMuPDF / Tesseract..."):
                res, err = execute_invoice_processing(target_id)
                if res:
                    st.success(f"✅ Document processed! Status: `{res.get('status')}` ({res.get('text_length', 0)} characters extracted)")
                    st.rerun()
                else:
                    st.error(f"Processing error: {err}")

        if e_clicked:
            with st.spinner("Extracting structured fields with Gemini AI..."):
                res, err = execute_ai_extraction(target_id)
                if res:
                    st.success(f"✅ AI Extraction complete! Vendor: `{res.get('vendor_name')}`, Invoice #: `{res.get('invoice_number')}`")
                    st.rerun()
                else:
                    st.error(f"AI Extraction error: {err}")

        if a_clicked:
            with st.spinner("Running rule validation, duplicate checks, categorization, and risk engine..."):
                res, err = execute_invoice_analysis(target_id)
                if res:
                    st.success(f"✅ Analysis complete! Risk: `{res.get('risk', {}).get('level')}` (Score: {res.get('risk', {}).get('score')}/100)")
                    st.rerun()
                else:
                    st.error(f"Analysis error: {err}")

        if f_clicked:
            with st.spinner("Executing end-to-end invoice automation..."):
                res, err = execute_full_automation(target_id)
                if res:
                    st.success(f"🚀 Full pipeline finished! Recommendation: `{res.get('approval', {}).get('recommendation')}`")
                    st.rerun()
                else:
                    st.error(f"Automation error: {err}")

        # Current Invoice Status Preview Card
        curr_text = fetch_invoice_text(target_id)
        if curr_text:
            st.markdown("#### 📋 Current Document State")
            stat_c1, stat_c2, stat_c3 = st.columns(3)
            with stat_c1:
                st.metric("Current Status", curr_text.get("status", "UNKNOWN"))
            with stat_c2:
                st.metric("Extraction Method", curr_text.get("extraction_method") or "Pending")
            with stat_c3:
                st.metric("Text Length", f"{curr_text.get('text_length', 0):,} chars")

            raw_txt = curr_text.get("raw_text")
            if raw_txt:
                with st.expander("📄 View Extracted Text Preview", expanded=False):
                    st.text_area("Raw Text Content", value=raw_txt[:1500] + ("..." if len(raw_txt) > 1500 else ""), height=180, disabled=True)
    else:
        st.write("No invoices currently registered. Upload a file above.")


# ==============================================================================
# PAGE 3: 📑 INVOICE REGISTRY (SEARCH & MULTI-ATTRIBUTE FILTERS)
# ==============================================================================
elif nav_selection == "📑 Invoice Registry":
    st.title("📑 Invoice Registry")
    st.markdown("Browse, search, and filter all registered invoices across operational and risk dimensions.")
    st.divider()

    invoices = get_existing_invoices()
    if not invoices:
        st.info("No invoices found in database. Ingest an invoice via **🚀 Upload & Process**.")
    else:
        # Filter Controls
        f_c1, f_c2, f_c3, f_c4 = st.columns(4)
        with f_c1:
            search_query = st.text_input("🔍 Search (Vendor / Invoice # / File)", placeholder="e.g. Acme, INV-1002")
        with f_c2:
            cats = ["All"] + sorted(list({inv.get("expense_category") for inv in invoices if inv.get("expense_category")}))
            sel_cat = st.selectbox("Expense Category", options=cats)
        with f_c3:
            risks = ["All", "LOW", "MEDIUM", "HIGH"]
            sel_risk = st.selectbox("Risk Level", options=risks)
        with f_c4:
            recs = ["All", "AUTO_APPROVE", "MANUAL_REVIEW", "REJECT_RECOMMENDED", "Pending"]
            sel_rec = st.selectbox("Approval Status", options=recs)

        # Filtering logic
        filtered = []
        for inv in invoices:
            if search_query:
                q = search_query.lower()
                matches_search = (
                    q in str(inv.get("vendor_name", "")).lower()
                    or q in str(inv.get("invoice_number", "")).lower()
                    or q in str(inv.get("original_filename", "")).lower()
                )
                if not matches_search:
                    continue
            if sel_cat != "All" and inv.get("expense_category") != sel_cat:
                continue
            if sel_risk != "All" and inv.get("risk_level") != sel_risk:
                continue
            if sel_rec != "All":
                rec_val = inv.get("approval_recommendation") or "Pending"
                if rec_val != sel_rec:
                    continue
            filtered.append(inv)

        st.caption(f"Showing **{len(filtered)}** of **{len(invoices)}** registered invoices.")

        df_display = []
        for inv in filtered:
            tot = inv.get("total_amount")
            tot_str = f"${tot:,.2f}" if tot is not None else "—"
            r_score = inv.get("risk_score")
            score_str = f"{r_score}" if r_score is not None else "—"
            dup_icon = "⚠️ Match" if inv.get("duplicate_flag") else "Clean"
            anom_icon = "⚠️ Outlier" if inv.get("is_anomalous") else "Normal"

            df_display.append({
                "ID": inv.get("id"),
                "Filename": inv.get("original_filename"),
                "Vendor": inv.get("vendor_name") or "—",
                "Invoice #": inv.get("invoice_number") or "—",
                "Date": inv.get("invoice_date") or "—",
                "Amount": tot_str,
                "Category": inv.get("expense_category") or "Uncategorized",
                "Risk": inv.get("risk_level") or "—",
                "Score": score_str,
                "Recommendation": inv.get("approval_recommendation") or "Pending",
                "Duplicate": dup_icon,
                "Anomaly": anom_icon,
                "Status": inv.get("status"),
            })

        st.dataframe(pd.DataFrame(df_display), width="stretch", hide_index=True)

        st.markdown("#### 🔍 Select Invoice for Inspection")
        if filtered:
            select_map = {f"#{inv['id']} - {inv['original_filename']} ({inv['vendor_name']})": inv["id"] for inv in filtered}
            chosen = st.selectbox("Inspect details for:", options=list(select_map.keys()))
            if st.button("Go to Detailed Analysis for Selected Invoice", type="primary"):
                st.session_state["active_invoice_id"] = select_map[chosen]
                st.success(f"Selected Invoice #{select_map[chosen]}. Switch to **🔍 Detailed Analysis** in the sidebar.")


# ==============================================================================
# PAGE 4: 🔍 DETAILED ANALYSIS (STRUCTURED DATA & 5 AUTOMATION PILLARS)
# ==============================================================================
elif nav_selection == "🔍 Detailed Analysis":
    st.title("🔍 Detailed Invoice Analysis")
    st.markdown("Comprehensive breakdown of extracted metadata, financial line items, validation math, duplicate detection, and risk scoring.")
    st.divider()

    invoices = get_existing_invoices()
    if not invoices:
        st.info("No invoices found. Please upload an invoice first.")
    else:
        inv_map = {f"#{inv['id']} - {inv['original_filename']} ({inv['vendor_name']})": inv["id"] for inv in invoices}
        active_id = st.session_state.get("active_invoice_id", invoices[0]["id"])
        def_idx = 0
        for idx, (lbl, iid) in enumerate(inv_map.items()):
            if iid == active_id:
                def_idx = idx
                break

        sel_label = st.selectbox("Select Invoice to Analyze:", options=list(inv_map.keys()), index=def_idx)
        current_id = inv_map[sel_label]
        st.session_state["active_invoice_id"] = current_id

        # Quick action controls
        q1, q2, q3, q4 = st.columns(4)
        with q1:
            if st.button("⚡ Process Text", key="dt_proc"):
                with st.spinner("Processing document..."):
                    execute_invoice_processing(current_id)
                    st.rerun()
        with q2:
            if st.button("🤖 Gemini AI Extract", key="dt_ai"):
                with st.spinner("Extracting with AI..."):
                    execute_ai_extraction(current_id)
                    st.rerun()
        with q3:
            if st.button("🔎 Analyze Rules", key="dt_rules"):
                with st.spinner("Analyzing rules & risk..."):
                    execute_invoice_analysis(current_id)
                    st.rerun()
        with q4:
            if st.button("🚀 Full End-to-End", key="dt_full", type="primary"):
                with st.spinner("Executing end-to-end pipeline..."):
                    execute_full_automation(current_id)
                    st.rerun()

        st.divider()

        # Structured Details
        structured = fetch_structured_invoice(current_id)
        analysis = fetch_invoice_analysis(current_id)

        # AI Recommendation Banner
        if analysis and analysis.get("approval"):
            appr = analysis["approval"]
            rec = appr.get("recommendation", "MANUAL_REVIEW")
            reason = appr.get("reason", "No details provided.")

            if rec == "AUTO_APPROVE":
                st.success(f"### 🟢 AI Recommendation: AUTO-APPROVE\n\n**Reason:** {reason}\n\n*Note: Clean document with zero validation errors, no duplicates, normal statistical spending, and low risk score.*")
            elif rec == "MANUAL_REVIEW":
                st.warning(f"### 🟡 AI Recommendation: MANUAL REVIEW REQUIRED\n\n**Reason:** {reason}\n\n*Human oversight required. Review flags before authorizing financial commitments.*")
            else:
                st.error(f"### 🛑 AI Recommendation: REJECT RECOMMENDED\n\n**Reason:** {reason}\n\n*Critical irregularities or severe duplicate detected.*")

        # 3 Metadata Columns
        if structured:
            c_vend, c_meta, c_fin = st.columns(3)
            with c_vend:
                st.markdown("#### 🏢 Vendor Details")
                st.write(f"**Vendor Name:** {structured.get('vendor_name') or 'N/A'}")
                st.write(f"**Address:** {structured.get('vendor_address') or 'N/A'}")
                st.write(f"**Tax ID / GSTIN:** {structured.get('vendor_gstin') or 'N/A'}")

            with c_meta:
                st.markdown("#### 📑 Invoice Metadata")
                st.write(f"**Invoice Number:** {structured.get('invoice_number') or 'N/A'}")
                st.write(f"**Invoice Date:** {structured.get('invoice_date') or 'N/A'}")
                st.write(f"**Due Date:** {structured.get('due_date') or 'N/A'}")
                st.write(f"**PO Number:** {structured.get('purchase_order_number') or 'N/A'}")
                st.write(f"**Payment Terms:** {structured.get('payment_terms') or 'N/A'}")

            with c_fin:
                st.markdown("#### 💰 Financial Reconciliation")
                curr = structured.get('currency') or "$"
                subt = f"{curr} {structured.get('subtotal'):,.2f}" if structured.get('subtotal') is not None else "N/A"
                tax = f"{curr} {structured.get('tax_amount'):,.2f}" if structured.get('tax_amount') is not None else "N/A"
                tot = f"{curr} {structured.get('total_amount'):,.2f}" if structured.get('total_amount') is not None else "N/A"
                st.write(f"**Subtotal:** {subt}")
                st.write(f"**Tax Amount:** {tax}")
                st.write(f"**Total Amount:** {tot}")

            # Line Items Table
            st.markdown("#### 📦 Relational Line Items")
            line_items = structured.get("line_items", [])
            if line_items:
                items_df = pd.DataFrame([
                    {
                        "Description": it.get("description", ""),
                        "Qty": it.get("quantity") if it.get("quantity") is not None else "—",
                        "Unit Price": f"{curr} {it.get('unit_price'):,.2f}" if it.get("unit_price") is not None else "—",
                        "Tax Rate": f"{it.get('tax_rate')}%" if it.get("tax_rate") is not None else "—",
                        "Line Total": f"{curr} {it.get('line_total'):,.2f}" if it.get("line_total") is not None else "—",
                    }
                    for it in line_items
                ])
                st.dataframe(items_df, width="stretch", hide_index=True)
            else:
                st.caption("No line items extracted for this invoice.")

            # Raw Extracted Text Expander
            raw_t = structured.get("raw_text")
            if raw_t:
                with st.expander("📄 View Raw Extracted OCR/PDF Text", expanded=False):
                    st.text_area("Raw Text", value=raw_t, height=200, disabled=True)

        # 5 Intelligent Automation Deep-Dive Tabs
        if analysis:
            st.divider()
            st.subheader("🛡️ The 5 Intelligent Automation Engines")

            tab_val, tab_dup, tab_cat, tab_anom, tab_risk = st.tabs([
                "📋 1. Validation Engine",
                "🔍 2. Duplicate Detection",
                "🏷️ 3. Expense Classification",
                "📈 4. Statistical Anomaly Detection",
                "⚖️ 5. Deterministic Risk Assessment",
            ])

            with tab_val:
                val = analysis.get("validation", {})
                st.markdown(f"#### Status: `{val.get('status', 'PASSED')}`")
                errs = val.get("errors", [])
                warns = val.get("warnings", [])
                if not errs and not warns:
                    st.success("✅ All mandatory fields present, mathematical consistency reconciled (Subtotal + Tax = Total), and dates verified.")
                else:
                    if errs:
                        st.error("**Critical Validation Errors:**")
                        for e in errs:
                            st.write(f"- ❌ {e}")
                    if warns:
                        st.warning("**Validation Warnings:**")
                        for w in warns:
                            st.write(f"- ⚠️ {w}")

            with tab_dup:
                dup = analysis.get("duplicate", {})
                if dup.get("is_duplicate"):
                    st.error(f"⚠️ **Duplicate Found:** {dup.get('reason')}")
                    st.write(f"- **Matching Invoice ID:** #{dup.get('duplicate_invoice_id')}")
                    st.write(f"- **Matching Rule:** `{dup.get('match_type')}`")
                    st.caption("Duplicates are flagged for auditor confirmation to prevent double disbursements.")
                else:
                    st.success("✅ No matching vendor invoice number, duplicate amounts, or identical document hashes found.")

            with tab_cat:
                cat = analysis.get("classification", {})
                st.markdown(f"#### Category: `{cat.get('category', 'Other')}`")
                st.write(f"- **Classification Method:** `{cat.get('method', 'RULE_BASED')}`")
                st.write(f"- **Confidence Score:** `{int(cat.get('confidence', 0) * 100)}%`")
                kws = cat.get("matched_keywords", [])
                if kws:
                    st.write(f"- **Trigger Keywords Matched:** `{', '.join(kws)}`")

            with tab_anom:
                anom = analysis.get("anomaly", {})
                if anom.get("is_anomalous"):
                    st.warning("⚠️ **Statistical Anomaly Detected:**")
                    for r in anom.get("reasons", []):
                        st.write(f"- ⚠️ {r}")
                else:
                    st.success("✅ Financial metrics are within standard statistical limits for this vendor and category.")

                if anom.get("z_score") is not None:
                    st.write(f"- **Calculated Z-Score:** `{anom.get('z_score')}`")
                    st.write(f"- **Vendor Historical Mean:** `${anom.get('mean_amount'):,.2f}`")
                    st.write(f"- **Vendor Historical Std Dev:** `${anom.get('std_amount'):,.2f}`")
                if anom.get("message"):
                    st.info(f"ℹ️ {anom.get('message')}")

            with tab_risk:
                risk = analysis.get("risk", {})
                r_score = risk.get("score", 0)
                r_lvl = risk.get("level", "LOW")
                st.markdown(f"#### Deterministic Risk Score: `{r_score} / 100` ({r_lvl})")
                st.progress(r_score / 100)
                st.write("**Itemized Risk Contributors:**")
                for r_reason in risk.get("reasons", []):
                    st.write(f"- {r_reason}")


# ==============================================================================
# PAGE 5: ⚖️ APPROVAL QUEUE (HUMAN-IN-THE-LOOP OVERSIGHT)
# ==============================================================================
elif nav_selection == "⚖️ Approval Queue":
    st.title("⚖️ Human-in-the-Loop Approval Queue")
    st.markdown("Dedicated review station for invoices flagged by AI for **Manual Review** or **Rejection Recommendation**.")
    st.info("💡 **Compliance Policy Notice:** In accordance with financial internal controls, approvals are strictly system recommendations. No automated bank dispatches or disbursements occur without human auditor authorization.")
    st.divider()

    invoices = get_existing_invoices()
    queue = [inv for inv in invoices if inv.get("approval_recommendation") in ("MANUAL_REVIEW", "REJECT_RECOMMENDED")]

    q_c1, q_c2, q_c3 = st.columns(3)
    with q_c1:
        st.metric("Total Items In Queue", f"{len(queue):,}")
    with q_c2:
        man_cnt = sum(1 for inv in queue if inv.get("approval_recommendation") == "MANUAL_REVIEW")
        st.metric("Pending Manual Review", f"{man_cnt:,}")
    with q_c3:
        rej_cnt = sum(1 for inv in queue if inv.get("approval_recommendation") == "REJECT_RECOMMENDED")
        st.metric("Rejection Recommended", f"{rej_cnt:,}")

    st.divider()

    if not queue:
        st.success("🎉 **Approval Queue is Clear!** There are currently no flagged or high-risk invoices pending human review.")
    else:
        st.subheader("⚠️ Invoices Requiring Auditor Attention")
        queue_rows = []
        for inv in queue:
            tot = inv.get("total_amount")
            tot_str = f"${tot:,.2f}" if tot is not None else "—"
            r_score = inv.get("risk_score")
            score_str = f"{r_score}/100" if r_score is not None else "—"

            queue_rows.append({
                "ID": inv.get("id"),
                "Vendor": inv.get("vendor_name") or "—",
                "Invoice #": inv.get("invoice_number") or "—",
                "Total Amount": tot_str,
                "Category": inv.get("expense_category") or "Uncategorized",
                "Risk Level": inv.get("risk_level") or "—",
                "Risk Score": score_str,
                "Recommendation": inv.get("approval_recommendation"),
                "Duplicate?": "⚠️ Yes" if inv.get("duplicate_flag") else "No",
                "Anomaly?": "⚠️ Yes" if inv.get("is_anomalous") else "No",
                "Uploaded At": str(inv.get("upload_timestamp", ""))[:19],
            })

        st.dataframe(pd.DataFrame(queue_rows), width="stretch", hide_index=True)

        st.markdown("#### 🔎 Open Queue Item in Deep Dive")
        q_options = {f"#{inv['id']} - {inv['vendor_name']} (${inv.get('total_amount') or 0:,.2f}) [{inv['approval_recommendation']}]": inv["id"] for inv in queue}
        sel_q = st.selectbox("Select invoice to inspect:", options=list(q_options.keys()))
        if st.button("Inspect in Detailed Analysis", type="primary"):
            st.session_state["active_invoice_id"] = q_options[sel_q]
            st.success(f"Selected Invoice #{q_options[sel_q]}. Switch to **🔍 Detailed Analysis** in the sidebar to review audit trail and line items.")


# ==============================================================================
# PAGE 6: 📈 SPEND ANALYTICS (6 INTERACTIVE PLOTLY CHARTS)
# ==============================================================================
elif nav_selection == "📈 Spend Analytics":
    st.title("📈 Interactive Spend Analytics")
    st.markdown("Dynamic visualization of organizational expenditure, vendor concentrations, category trends, and risk exposure.")
    st.divider()

    invoices = get_existing_invoices()
    if not invoices:
        st.info("No invoice data available for analytics yet. Upload invoices to generate charts.")
    else:
        # Dynamic Multi-Attribute Filter Bar
        st.markdown("### 🔍 Analytics Filters")
        af1, af2, af3 = st.columns(3)
        with af1:
            cat_list = ["All"] + sorted(list({inv.get("expense_category") for inv in invoices if inv.get("expense_category")}))
            filter_cat = st.selectbox("Filter Category:", options=cat_list)
        with af2:
            vendor_list = ["All"] + sorted(list({inv.get("vendor_name") for inv in invoices if inv.get("vendor_name")}))
            filter_vendor = st.selectbox("Filter Vendor:", options=vendor_list)
        with af3:
            filter_risk = st.selectbox("Filter Risk Level:", options=["All", "LOW", "MEDIUM", "HIGH"])

        # Fetch filtered analytics from service
        analytics = fetch_spend_analytics(
            category=filter_cat,
            vendor=filter_vendor,
            risk_level=filter_risk,
        )

        st.divider()

        # Row 1: Category Spend & Top Vendors
        c_chart1, c_chart2 = st.columns(2)
        with c_chart1:
            st.subheader("1. Spend by Expense Category")
            cat_data = analytics.get("category_spending", [])
            if cat_data:
                df_cat = pd.DataFrame(cat_data)
                fig_cat = px.bar(
                    df_cat,
                    x="category",
                    y="total_amount",
                    text_auto=".2s",
                    color="category",
                    title="Expenditure by Category ($)",
                )
                fig_cat.update_layout(showlegend=False, xaxis_title="Category", yaxis_title="Total ($)")
                st.plotly_chart(fig_cat, width="stretch")
            else:
                st.info("No category spend data matching current filters.")

        with c_chart2:
            st.subheader("2. Top Vendors by Spend")
            top_n = st.selectbox("Display Top:", options=[5, 10, 20], index=0)
            vendor_data = analytics.get("vendor_spending", [])[:top_n]
            if vendor_data:
                df_vendor = pd.DataFrame(vendor_data)
                fig_vendor = px.bar(
                    df_vendor,
                    x="total_amount",
                    y="vendor",
                    orientation="h",
                    text_auto=".2s",
                    color="total_amount",
                    color_continuous_scale="Blues",
                    title=f"Top {len(vendor_data)} Vendors ($)",
                )
                fig_vendor.update_layout(yaxis=dict(autorange="reversed"), xaxis_title="Spend ($)", yaxis_title="Vendor")
                st.plotly_chart(fig_vendor, width="stretch")
            else:
                st.info("No vendor spend data matching current filters.")

        st.divider()

        # Row 2: Monthly Spend Trend & Risk Distribution
        c_chart3, c_chart4 = st.columns(2)
        with c_chart3:
            st.subheader("3. Monthly Spend Trend")
            monthly_data = analytics.get("monthly_spending", [])
            if monthly_data:
                df_month = pd.DataFrame(monthly_data)
                fig_month = px.line(
                    df_month,
                    x="month",
                    y="total_amount",
                    markers=True,
                    title="Spending Velocity Over Time ($)",
                )
                fig_month.update_layout(xaxis_title="Month", yaxis_title="Total Spend ($)")
                st.plotly_chart(fig_month, width="stretch")
            else:
                st.info("No monthly trend data available.")

        with c_chart4:
            st.subheader("4. Risk Level Distribution")
            risk_dist = analytics.get("risk_distribution", {})
            if any(risk_dist.values()):
                fig_risk = px.pie(
                    names=list(risk_dist.keys()),
                    values=list(risk_dist.values()),
                    color=list(risk_dist.keys()),
                    color_discrete_map={
                        "LOW": "#28a745",
                        "MEDIUM": "#ffc107",
                        "HIGH": "#dc3545",
                    },
                    hole=0.4,
                    title="Portfolio Risk Exposure",
                )
                st.plotly_chart(fig_risk, width="stretch")
            else:
                st.info("No risk distribution data available.")

        st.divider()

        # Row 3: Status Distribution & Approval Recommendation Breakdown
        c_chart5, c_chart6 = st.columns(2)
        with c_chart5:
            st.subheader("5. Document Processing Status")
            stat_dist = analytics.get("status_distribution", {})
            if any(stat_dist.values()):
                df_stat = pd.DataFrame([{"Status": k, "Count": v} for k, v in stat_dist.items()])
                fig_stat = px.bar(
                    df_stat,
                    x="Status",
                    y="Count",
                    text_auto=True,
                    color="Status",
                    title="Pipeline Processing State Counts",
                )
                fig_stat.update_layout(showlegend=False)
                st.plotly_chart(fig_stat, width="stretch")
            else:
                st.info("No processing status data available.")

        with c_chart6:
            st.subheader("6. Approval Recommendation Distribution")
            rec_dist = analytics.get("recommendation_distribution", {})
            if any(rec_dist.values()):
                df_rec = pd.DataFrame([{"Recommendation": k, "Count": v} for k, v in rec_dist.items()])
                fig_rec = px.bar(
                    df_rec,
                    x="Recommendation",
                    y="Count",
                    text_auto=True,
                    color="Recommendation",
                    color_discrete_map={
                        "AUTO_APPROVE": "#28a745",
                        "MANUAL_REVIEW": "#ffc107",
                        "REJECT_RECOMMENDED": "#dc3545",
                        "PENDING": "#6c757d",
                    },
                    title="Recommendation Distribution",
                )
                fig_rec.update_layout(showlegend=False)
                st.plotly_chart(fig_rec, width="stretch")
            else:
                st.info("No recommendation data available.")


# ==============================================================================
# PAGE 7: 📥 REPORTS & EXPORT (CSV & PYMUPDF PDF GENERATION)
# ==============================================================================
elif nav_selection == "📥 Reports & Export":
    st.title("📥 Reports & Data Export")
    st.markdown("Export structured invoice data, line-item breakdowns, and executive audit reports in standard CSV and PDF formats.")
    st.divider()

    rep_col1, rep_col2 = st.columns(2)

    with rep_col1:
        st.subheader("📊 1. CSV Data Exports")
        st.markdown("Download structured database exports compatible with ERP systems, Excel, or downstream BI pipelines.")

        csv_invoices = get_csv_report_data("invoices")
        st.download_button(
            label="📄 Download Invoices Registry (CSV)",
            data=csv_invoices,
            file_name=f"invoices_registry_{datetime.date.today().isoformat()}.csv",
            mime="text/csv",
            help="Full master record of all invoices, risk scores, totals, and recommendations.",
        )

        csv_lines = get_csv_report_data("line_items")
        st.download_button(
            label="📦 Download Line Items Breakdown (CSV)",
            data=csv_lines,
            file_name=f"invoice_line_items_{datetime.date.today().isoformat()}.csv",
            mime="text/csv",
            help="Relational line-item details including quantities, prices, taxes, and descriptions.",
        )

    with rep_col2:
        st.subheader("📑 2. PDF Document Reports")
        st.markdown("Generate presentation-ready executive summaries and individual invoice audit briefs powered by PyMuPDF.")

        pdf_summary = get_pdf_summary_report()
        st.download_button(
            label="📊 Download Executive Summary (PDF)",
            data=pdf_summary,
            file_name=f"invoice_executive_summary_{datetime.date.today().isoformat()}.pdf",
            mime="application/pdf",
            help="A4 PDF executive report summarizing total spend, risk distribution, and category breakdown.",
        )

        invoices = get_existing_invoices()
        if invoices:
            st.markdown("#### Individual Invoice Audit PDF")
            pdf_map = {f"#{inv['id']} - {inv['original_filename']} ({inv['vendor_name']})": inv["id"] for inv in invoices}
            sel_pdf_inv = st.selectbox("Select invoice for PDF export:", options=list(pdf_map.keys()))
            target_pdf_id = pdf_map[sel_pdf_inv]

            pdf_invoice_bytes = get_pdf_invoice_report(target_pdf_id)
            if pdf_invoice_bytes:
                st.download_button(
                    label=f"📥 Download Invoice #{target_pdf_id} Audit PDF",
                    data=pdf_invoice_bytes,
                    file_name=f"invoice_{target_pdf_id}_audit_{datetime.date.today().isoformat()}.pdf",
                    mime="application/pdf",
                    help="Complete single-invoice report with line items and validation decision record.",
                )


# ==============================================================================
# PAGE 8: 📜 AUDIT TRAIL (IMMUTABLE LIFECYCLE LOGS)
# ==============================================================================
elif nav_selection == "📜 Audit Trail":
    st.title("📜 Audit Trail & Lifecycle History")
    st.markdown("Transparent and immutable audit logging for all invoice processing stages, validation evaluations, and risk scoring operations.")
    st.divider()

    invoices = get_existing_invoices()
    trail_tab1, trail_tab2 = st.tabs(["🌐 System-Wide Audit Log", "🔍 Invoice-Specific Lifecycle"])

    with trail_tab1:
        st.subheader("Recent System Activities (Global Stream)")
        system_logs = fetch_audit_logs(invoice_id=None, limit=100)
        if system_logs:
            df_sys = pd.DataFrame([
                {
                    "Timestamp": log.get("timestamp"),
                    "Invoice ID": f"#{log.get('invoice_id')}" if log.get("invoice_id") else "System",
                    "Action": log.get("action"),
                    "Status": log.get("status"),
                    "Message": log.get("message"),
                }
                for log in system_logs
            ])
            st.dataframe(df_sys, width="stretch", hide_index=True)
        else:
            st.info("No audit events recorded yet.")

    with trail_tab2:
        st.subheader("Invoice Lifecycle History")
        if invoices:
            inv_map = {f"#{inv['id']} - {inv['original_filename']} ({inv['vendor_name']})": inv["id"] for inv in invoices}
            active_id = st.session_state.get("active_invoice_id", invoices[0]["id"])
            def_idx = 0
            for idx, (lbl, iid) in enumerate(inv_map.items()):
                if iid == active_id:
                    def_idx = idx
                    break

            sel_inv_lbl = st.selectbox("Select Invoice to inspect lifecycle:", options=list(inv_map.keys()), index=def_idx)
            sel_inv_id = inv_map[sel_inv_lbl]

            inv_logs = fetch_audit_logs(invoice_id=sel_inv_id)
            if inv_logs:
                df_inv_log = pd.DataFrame([
                    {
                        "Timestamp": log.get("timestamp"),
                        "Action": log.get("action"),
                        "Status": log.get("status"),
                        "Detail": log.get("message"),
                    }
                    for log in inv_logs
                ])
                st.dataframe(df_inv_log, width="stretch", hide_index=True)
            else:
                st.info(f"No audit trail events found for Invoice #{sel_inv_id}.")
        else:
            st.info("No invoices registered to inspect.")


# ==============================================================================
# PAGE 9: ⚙️ SYSTEM HEALTH & CONFIGURATION
# ==============================================================================
elif nav_selection == "⚙️ System Health":
    st.title("⚙️ System Health & Engine Diagnostics")
    st.markdown("Live diagnostic status of backend services, database storage, document OCR, and AI engine.")
    st.divider()

    h_c1, h_c2 = st.columns(2)

    with h_c1:
        st.subheader("🩺 Service Diagnostics")
        is_be_online = check_backend_health()
        if is_be_online:
            st.success("🟢 **FastAPI Service:** Online & Healthy")
            st.write(f"- **URL:** `{BACKEND_API_URL}`")
            st.write(f"- **Documentation:** [Swagger UI]({BACKEND_API_URL.replace('/api/v1', '')}/docs)")
        else:
            st.warning("🟡 **FastAPI Service:** Offline (Direct SQLite Mode Active)")
            st.write(f"- **Target URL:** `{BACKEND_API_URL}`")
            st.caption("Streamlit is operating directly against SQLite database.")

        is_ocr = is_tesseract_available()
        if is_ocr:
            st.success("🟢 **OCR Engine:** Tesseract Active")
            st.write(f"- **Binary Path:** `{get_tesseract_command()}`")
        else:
            st.info("🔵 **OCR Engine:** PyMuPDF Native Parser")
            st.caption("Standard text PDFs extract with high precision natively. Install Tesseract for scanned bitmap fallback.")

        is_gem = is_gemini_configured()
        if is_gem:
            st.success(f"🟢 **AI Engine:** Google Gemini Configured (`{settings.GEMINI_MODEL}`)")
        else:
            st.warning("🟡 **AI Engine:** Gemini Key Missing")
            st.caption("Add `GEMINI_API_KEY` to `.env` to enable live LLM field parsing.")

    with h_c2:
        st.subheader("💾 Database & Storage Metrics")
        db_path = Path("data/database/invoices.db")
        upload_path = Path(settings.UPLOAD_DIR)

        st.write(f"- **Database Path:** `{db_path.resolve()}`")
        if db_path.exists():
            db_sz_kb = db_path.stat().st_size / 1024
            st.write(f"- **Database File Size:** `{db_sz_kb:.2f} KB`")

        st.write(f"- **Uploads Directory:** `{upload_path.resolve()}`")
        if upload_path.exists():
            upload_files = list(upload_path.glob("*"))
            st.write(f"- **Stored Document Files:** `{len(upload_files)} files`")

        invoices = get_existing_invoices()
        st.write(f"- **Total Registered Invoices:** `{len(invoices)}`")
        if invoices:
            proc_cnt = sum(1 for inv in invoices if inv.get("status") in ("TEXT_EXTRACTED", "OCR_COMPLETED", "AI_EXTRACTED"))
            st.write(f"- **Successfully Extracted Documents:** `{proc_cnt}`")

    st.divider()
    st.subheader("📋 Application Settings & Limits")
    st.write(f"- **App Environment:** `{settings.APP_ENV}`")
    st.write(f"- **Max Upload Size:** `{settings.MAX_UPLOAD_SIZE_MB} MB`")
    st.write(f"- **Allowed Extensions:** `{', '.join(sorted(settings.ALLOWED_EXTENSIONS))}`")
    st.write(f"- **Duplicate Hash Algorithm:** `SHA-256`")
    st.write(f"- **Risk Scoring Engine:** `Deterministic (0-100 scale)`")
    st.write(f"- **Supported Expense Categories:** `10 Enterprise Categories`")
