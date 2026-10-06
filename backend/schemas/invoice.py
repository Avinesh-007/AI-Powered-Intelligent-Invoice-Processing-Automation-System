from datetime import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Health check response schema."""
    status: str


class LineItemSchema(BaseModel):
    """Schema representing an individual line item parsed from an invoice."""
    description: str = Field(..., description="Description or product/service name")
    quantity: Optional[float] = Field(None, description="Quantity of items or hours")
    unit_price: Optional[float] = Field(None, description="Price per unit or hourly rate")
    tax_rate: Optional[float] = Field(None, description="Tax percentage or rate applied to line item")
    line_total: Optional[float] = Field(None, description="Total amount for this line item")


class LineItemRead(LineItemSchema):
    """Schema representing a stored invoice line item with identifiers."""
    id: int
    invoice_id: int

    model_config = ConfigDict(from_attributes=True)


class InvoiceExtractionSchema(BaseModel):
    """Schema representing the validated structured output from Gemini AI extraction."""
    vendor_name: Optional[str] = None
    vendor_address: Optional[str] = None
    vendor_gstin: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    purchase_order_number: Optional[str] = None
    currency: Optional[str] = None
    subtotal: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    payment_terms: Optional[str] = None
    line_items: List[LineItemSchema] = Field(default_factory=list)


class InvoiceBase(BaseModel):
    """Base schema for invoice fields."""
    original_filename: str
    status: str
    extraction_method: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_address: Optional[str] = None
    vendor_gstin: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    purchase_order_number: Optional[str] = None
    payment_terms: Optional[str] = None
    subtotal: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = None
    expense_category: Optional[str] = None
    classification_method: Optional[str] = None
    validation_status: Optional[str] = None
    duplicate_flag: Optional[bool] = False
    duplicate_invoice_id: Optional[int] = None
    duplicate_reason: Optional[str] = None
    anomaly_flag: Optional[bool] = False
    risk_score: Optional[int] = None
    risk_level: Optional[str] = None
    approval_recommendation: Optional[str] = None
    approval_reason: Optional[str] = None
    automation_processed_at: Optional[datetime] = None


class InvoiceRead(InvoiceBase):
    """Schema representing an invoice returned to clients."""
    id: int
    stored_filename: str
    file_path: str
    file_size_bytes: int
    upload_timestamp: datetime
    raw_text: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvoiceProcessResponse(BaseModel):
    """Response returned when an invoice document processing run finishes."""
    invoice_id: int
    status: str
    extraction_method: Optional[str] = None
    text_length: int
    message: Optional[str] = None


class InvoiceTextResponse(BaseModel):
    """Response returned when querying extracted text for an invoice."""
    invoice_id: int
    status: str
    extraction_method: Optional[str] = None
    raw_text: Optional[str] = None
    text_length: int


class InvoiceStructuredResponse(BaseModel):
    """Complete structured response representing an invoice and its line items."""
    invoice_id: int
    status: str
    extraction_method: Optional[str] = None
    original_filename: str
    vendor_name: Optional[str] = None
    vendor_address: Optional[str] = None
    vendor_gstin: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    purchase_order_number: Optional[str] = None
    payment_terms: Optional[str] = None
    currency: Optional[str] = None
    subtotal: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    expense_category: Optional[str] = None
    classification_method: Optional[str] = None
    validation_status: Optional[str] = None
    duplicate_flag: Optional[bool] = False
    duplicate_invoice_id: Optional[int] = None
    duplicate_reason: Optional[str] = None
    anomaly_flag: Optional[bool] = False
    risk_score: Optional[int] = None
    risk_level: Optional[str] = None
    approval_recommendation: Optional[str] = None
    approval_reason: Optional[str] = None
    automation_processed_at: Optional[datetime] = None
    line_items: List[LineItemRead] = Field(default_factory=list)
    raw_text: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# PHASE 4 AUTOMATION SCHEMAS
# ==============================================================================

class ValidationResultSchema(BaseModel):
    """Detailed result of invoice mathematical, field, and date validation."""
    passed: bool
    status: str = Field(..., description="PASSED, WARNINGS, or FAILED")
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class DuplicateResultSchema(BaseModel):
    """Result of duplicate invoice detection checks."""
    is_duplicate: bool
    duplicate_invoice_id: Optional[int] = None
    reason: Optional[str] = None
    match_type: Optional[str] = None


class ClassificationResultSchema(BaseModel):
    """Result of automated expense category classification."""
    category: str
    confidence: float
    method: str = Field(..., description="RULE_BASED, AI_FALLBACK, or DEFAULT")
    matched_keywords: List[str] = Field(default_factory=list)


class AnomalyResultSchema(BaseModel):
    """Result of statistical spending and tax anomaly detection."""
    is_anomalous: bool
    reasons: List[str] = Field(default_factory=list)
    historical_count: int = 0
    mean_amount: Optional[float] = None
    std_amount: Optional[float] = None
    z_score: Optional[float] = None
    message: Optional[str] = None


class RiskResultSchema(BaseModel):
    """Result of deterministic risk score calculation."""
    score: int = Field(..., ge=0, le=100, description="Risk score from 0 (clean) to 100 (high risk)")
    level: str = Field(..., description="LOW, MEDIUM, or HIGH")
    reasons: List[str] = Field(default_factory=list)


class ApprovalResultSchema(BaseModel):
    """AI and rule-based approval recommendation."""
    recommendation: str = Field(..., description="AUTO_APPROVE, MANUAL_REVIEW, or REJECT_RECOMMENDED")
    reason: str


class InvoiceAnalysisResponse(BaseModel):
    """Consolidated response for complete invoice automation and risk analysis."""
    invoice_id: int
    status: str
    validation: ValidationResultSchema
    duplicate: DuplicateResultSchema
    classification: ClassificationResultSchema
    anomaly: AnomalyResultSchema
    risk: RiskResultSchema
    approval: ApprovalResultSchema
    automation_processed_at: Optional[datetime] = None


# ==============================================================================
# PHASE 5 ANALYTICS, AUDIT & DASHBOARD SCHEMAS
# ==============================================================================

class AuditLogRead(BaseModel):
    """Schema representing an audit trail log entry."""
    id: int
    invoice_id: Optional[int] = None
    action: str
    status: str
    message: Optional[str] = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class DashboardSummarySchema(BaseModel):
    """System overview KPI summary metrics."""
    total_invoices: int
    total_invoice_value: float
    processed_invoices: int
    pending_invoices: int
    high_risk_invoices: int
    duplicate_invoices: int
    anomalous_invoices: int
    auto_approved_invoices: int


class CategorySpendItem(BaseModel):
    """Category spend aggregation."""
    category: str
    total_amount: float
    count: int


class VendorSpendItem(BaseModel):
    """Vendor spend aggregation."""
    vendor: str
    total_amount: float
    count: int


class MonthlySpendItem(BaseModel):
    """Monthly spend trend aggregation."""
    month: str
    total_amount: float
    count: int


class SpendAnalyticsSchema(BaseModel):
    """Granular spend analytics and risk distribution response."""
    filtered_count: int
    category_spending: List[CategorySpendItem]
    vendor_spending: List[VendorSpendItem]
    monthly_spending: List[MonthlySpendItem]
    risk_distribution: Dict[str, int]
    status_distribution: Dict[str, int]
    recommendation_distribution: Dict[str, int]


class SystemHealthSchema(BaseModel):
    """Comprehensive system operational health schema."""
    status: str
    database_connected: bool
    gemini_configured: bool
    gemini_model: str
    ocr_available: bool
    tesseract_command: Optional[str] = None
    total_invoices: int
    failed_invoices: int
