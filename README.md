# AI-Powered Intelligent Invoice Processing & Automation System

An enterprise-grade, end-to-end intelligent invoice processing and automation platform designed to ingest invoices (PDF or image), extract high-fidelity text via native PyMuPDF parsing and Tesseract OCR, convert unstructured documents into structured entities using Large Language Models (Google Gemini AI), detect duplicates and statistical financial anomalies, classify corporate expenses across 10 domains, evaluate deterministic risk scores, formulate explainable approval recommendations, generate dynamic Plotly spend analytics, and produce executive audit reports in CSV and presentation-ready PDF formats.

---

## 🎯 Project Status: All 5 Phases Complete & Fully Verified

* **Phase 1: Foundation & Architecture** (Complete) — Modular service architecture, SQLite persistence, FastAPI backend, strict file validation, and Streamlit ingestion interface.
* **Phase 2: Document Processing & OCR** (Complete) — Dual-engine extraction pipeline (PyMuPDF for digital text PDFs, Tesseract OCR for scanned documents and images), non-destructive text cleaning, and processing status tracking.
* **Phase 3: AI-Powered Invoice Field Extraction** (Complete) — LLM understanding layer using Google Gemini AI, zero-hallucination prompting, Pydantic schema validation, and relational database persistence for line items and metadata.
* **Phase 4: Intelligent Invoice Automation** (Complete) — Multi-attribute mathematical validation engine, multi-criteria duplicate detection, 10-category expense classification, explainable statistical anomaly detection, deterministic 0–100 risk scoring, and automated approval recommendations.
* **Phase 5: Interactive Analytics Dashboard, Reports & Audit Trail** (Complete) — 9-page enterprise Streamlit dashboard, 6 interactive Plotly visualizations, CSV data exports, PyMuPDF-powered executive summary and invoice audit PDF reports, immutable audit trail logging, and system health diagnostics.
* **Automated Test Suite**: **102 Automated Tests Passing** (100% pass rate).

---

## 🛠️ Complete Technology Stack

| Architecture Layer | Technologies |
|---|---|
| **Backend Web Framework** | Python 3.11+, FastAPI, Uvicorn, Pydantic v2, Pydantic-Settings |
| **Document Processing & OCR** | PyMuPDF (fitz), Tesseract OCR, Pillow (PIL) |
| **Generative AI & LLM** | Google Gemini API (`google-genai` / REST integration), Structured JSON Prompts |
| **Database & ORM** | SQLite, SQLAlchemy 2.0 (Relational Line Items & Audit Logs) |
| **Automation & Statistics** | Python `statistics`, `math`, Deterministic Rule Engines |
| **Frontend Web Interface** | Streamlit, Pandas, CSS Layouts |
| **Interactive Visualizations** | Plotly Express & Plotly Graph Objects (`plotly>=5.20.0`) |
| **Reporting & Document Export**| Standard CSV (`csv`, `io`), PyMuPDF A4 PDF Generation (`pymupdf`) |
| **Testing & Quality Assurance** | Pytest (102 tests), FastAPI TestClient, Streamlit AppTest, Mocking |

---

## 📐 End-to-End Workflow Architecture

```text
       [UPLOAD INVOICE] (PDF / PNG / JPG / JPEG)
              │
              ▼
    [DOCUMENT PROCESSING]
     ├─ Native Text Extraction (PyMuPDF)
     └─ Optical Character Recognition (Tesseract OCR Fallback)
              │
              ▼
   [CLEAN RAW TEXT PERSISTENCE] (Stored in SQLite `invoices.raw_text`)
              │
              ▼
  [GEMINI AI FIELD EXTRACTION]
     ├─ Zero-hallucination structured prompt
     ├─ Vendor info, Invoice #, Dates, Currency, Totals
     └─ Line Items Table (Desc, Qty, Unit Price, Tax, Total)
              │
              ▼
 [PYDANTIC SCHEMA VALIDATION & RELATIONAL DB]
              │
              ▼
 [INTELLIGENT AUTOMATION ENGINES]
     ├─ 1. Validation Engine (Required fields, subtotal + tax = total math check)
     ├─ 2. Multi-Attribute Duplicate Detection (Vendor + Inv#, Vendor + Date + Amt, Hash)
     ├─ 3. Expense Classification (10 corporate categories via domain keywords)
     ├─ 4. Statistical Anomaly Detection (Z-score vs vendor history, tax rate check)
     └─ 5. Deterministic Risk Assessment (0-100 Score, Low / Medium / High)
              │
              ▼
 [AI APPROVAL RECOMMENDATION] (AUTO_APPROVE / MANUAL_REVIEW / REJECT_RECOMMENDED)
              │
              ├─────────────────────────────┬─────────────────────────────┐
              ▼                             ▼                             ▼
    [SPEND ANALYTICS]             [REPORTS & EXPORTS]            [AUDIT TRAIL]
   (6 Plotly Visualizations)     (CSV & PyMuPDF PDF Reports)    (Immutable History Log)
```

---

## 🖥️ Streamlit Application Interface (9 Dedicated Modules)

The frontend application provides a cohesive, multi-page workflow accessible via the sidebar navigation:

1. **📊 Executive Dashboard**: High-level KPI summary cards (Total Invoices, Total Spend, Processed Count, Pending Invoices, High Risk Items, Duplicates, Anomalies, Auto-Approved Count), recent activity feed, and live approval status distribution. Clean empty states if database has no records.
2. **🚀 Upload & Process**: Ingestion station with file size and format enforcement, plus step-by-step pipeline controls (`⚡ Process Doc`, `🤖 Extract AI`, `🔎 Analyze Rules`) and a 1-click `🚀 Full End-to-End Pipeline` button.
3. **📑 Invoice Registry**: Comprehensive repository table with real-time search (by Vendor, Invoice Number, or File) and multi-attribute filters (Category, Risk Level, Approval Status).
4. **🔍 Detailed Analysis**: Deep-dive inspection view for any selected invoice. Displays vendor metadata, line items table, financial reconciliation card, raw OCR text expander, and 5 interactive tabs for each automation engine.
5. **⚖️ Approval Queue**: Dedicated human-in-the-loop review station filtering invoices flagged as `MANUAL_REVIEW` or `REJECT_RECOMMENDED`. Displays flag reasons, financial totals, and risk scores with clear compliance warnings.
6. **📈 Spend Analytics**: Dynamic financial dashboard with 6 interactive Plotly charts:
   - Spend by Expense Category (Bar chart)
   - Top Vendors by Spend (Horizontal bar chart with Top 5 / 10 / 20 selector)
   - Monthly Spending Velocity Trend (Line chart with markers)
   - Portfolio Risk Exposure Distribution (Donut chart)
   - Document Processing Pipeline Status (Bar chart)
   - Approval Recommendation Distribution (Bar chart)
7. **📥 Reports & Export**:
   - Master Invoice Registry (CSV)
   - Relational Line Items Breakdown (CSV)
   - Executive Summary Analytics Report (A4 PDF generated via PyMuPDF)
   - Individual Invoice Audit Brief (A4 PDF generated via PyMuPDF)
8. **📜 Audit Trail**: Chronological lifecycle history tracking every state transition (`INVOICE_UPLOADED`, `TEXT_EXTRACTED`, `AI_EXTRACTION_COMPLETED`, `VALIDATION_COMPLETED`, `RISK_ASSESSMENT_COMPLETED`, etc.) both globally and per-invoice.
9. **⚙️ System Health**: Real-time service diagnostics covering FastAPI backend connection latency, SQLite storage metrics, Tesseract OCR binary availability, Gemini AI configuration, and document throughput counts.

---

## 🛡️ Risk Scoring & Explainability Matrix

The system utilizes an explainable, deterministic scoring model (0–100 points):

| Factor / Irregularity | Penalty Added | Resulting Action |
|---|---|---|
| Critical Validation Error (Missing Total, Math Mismatch) | +35 pts | Triggers `REJECT_RECOMMENDED` or `MANUAL_REVIEW` |
| Multi-Attribute Duplicate Found | +45 pts | Triggers `REJECT_RECOMMENDED` |
| Statistical Spending Outlier ($Z > 2.5$) | +20 pts | Triggers `MANUAL_REVIEW` |
| Unusual Tax Rate Detected ($>30\%$) | +15 pts | Triggers `MANUAL_REVIEW` |
| Missing Optional Metadata (Due Date, PO#) | +5 pts | Low severity warning |
| Clean Invoice, High Historical Consistency | 0 pts | Eligible for `AUTO_APPROVE` (Score $\le 20$) |

> **Human Oversight Compliance Notice**: In compliance with standard corporate accounting controls, system approvals represent automated *recommendations*. The system does not initiate financial payments or bank disbursements without human auditor sign-off.

---

## 🚀 Local Installation & Execution (Windows)

### 1. Clone & Set Up Python Environment
```powershell
# Clone the repository
git clone https://github.com/Avinesh-007/AI-Powered-Intelligent-Invoice-Processing-Automation-System.git
cd AI-Powered-Intelligent-Invoice-Processing-Automation-System

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install all dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
cp .env.example .env
```
Edit `.env` to configure your settings:
```ini
APP_ENV=development
DATABASE_URL=sqlite:///./data/database/invoices.db
UPLOAD_DIR=./data/uploads
PROCESSED_DIR=./data/processed
MAX_UPLOAD_SIZE_MB=10
ALLOWED_EXTENSIONS=pdf,png,jpg,jpeg
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000

# Optional: Set your Google Gemini API key to enable live AI field extraction
GEMINI_API_KEY=your_actual_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```
*(Note: If `GEMINI_API_KEY` is not provided, the application continues to run in OCR/document processing mode, with deterministic mocked test suites.)*

### 3. Run FastAPI Backend Server
In Terminal 1:
```powershell
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```
Interactive Swagger documentation is available at: `http://127.0.0.1:8000/docs`

### 4. Run Streamlit Frontend Dashboard
In Terminal 2:
```powershell
streamlit run frontend/app.py
```
Open your browser at: `http://localhost:8501`

---

## 🧪 Automated Test Suite

The test suite covers unit, integration, API, and UI testing across all 5 phases:

```powershell
# Run the complete test suite (102 tests)
python -m pytest -v
```

Test breakdown:
- `test_health.py` & `test_database.py` — Database schema, transactions, migrations
- `test_validation.py` & `test_upload.py` — File type security, sizes, path traversal protection
- `test_text_cleaner.py` — Character normalization and entity preservation
- `test_pdf_processing.py` & `test_ocr_processing.py` — PyMuPDF extraction, Tesseract discovery & OCR fallback
- `test_process_api.py` — Document processing API endpoints
- `test_ai_schemas.py`, `test_ai_service.py`, `test_extract_api.py` — Gemini AI prompt generation & entity extraction
- `test_validation_service.py` — Arithmetic subtotal/tax consistency & date validation
- `test_duplicate_service.py` — Triple-tier duplicate detection (number, amount/date, content hash)
- `test_classification_service.py` — 10-category expense classification
- `test_anomaly_service.py` & `test_risk_and_approval_service.py` — Statistical outliers & deterministic risk scoring
- `test_automation_api.py` — Automated invoice analysis & full workflow REST endpoints
- `test_analytics_service.py` — Real KPI summary calculation & dynamic spend aggregation
- `test_report_service.py` — CSV data generation & PyMuPDF A4 PDF report generation
- `test_audit_service.py` — Audit log lifecycle event tracking
- `test_phase5_api.py` — Phase 5 dashboard, analytics, report, and audit API routes
- `test_streamlit_navigation.py` — Streamlit `AppTest` verifying clean rendering across all 9 pages
