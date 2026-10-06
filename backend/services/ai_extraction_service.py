import json
import logging
import re
from typing import Optional
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.invoice import (
    Invoice,
    InvoiceLineItem,
    STATUS_AI_PROCESSING,
    STATUS_AI_EXTRACTED,
    STATUS_PROCESSING_FAILED,
)
from backend.schemas.invoice import InvoiceExtractionSchema
from backend.services.document_service import InvoiceNotFoundError

logger = logging.getLogger(__name__)


class AIExtractionError(Exception):
    """Base exception for AI extraction operations."""
    pass


class GeminiNotConfiguredError(AIExtractionError):
    """Raised when the Gemini API key is missing or empty."""
    pass


class MissingRawTextError(AIExtractionError):
    """Raised when an invoice has not yet undergone document text extraction."""
    pass


class AIResponseParseError(AIExtractionError):
    """Raised when the Gemini response is not valid JSON or fails schema validation."""
    pass


def is_gemini_configured() -> bool:
    """Return True if GEMINI_API_KEY is present and non-empty."""
    return bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.strip())


def get_gemini_client(api_key: Optional[str] = None):
    """Obtain initialized Google GenAI Client if configured, else None."""
    key = api_key or settings.GEMINI_API_KEY
    if not key or not key.strip():
        return None
    try:
        from google import genai
        return genai.Client(api_key=key.strip())
    except Exception:
        return None


EXTRACTION_SYSTEM_PROMPT = """You are an expert invoice understanding and financial data extraction AI.
Analyze the provided raw invoice text and extract the structured information adhering strictly to the JSON schema below.

CRITICAL RULES:
1. Extract facts ONLY from the supplied invoice text.
2. DO NOT hallucinate, infer, or guess missing information.
3. If any field or value is absent or cannot be confirmed from the text, return null for that field.
4. Preserve invoice numbers and purchase order codes EXACTLY as written.
5. Preserve GSTIN, VAT, or Tax identification numbers EXACTLY when present.
6. Extract dates in original format or standard YYYY-MM-DD.
7. Extract monetary amounts as floating point numbers (e.g., 1250.50), removing commas and currency symbols.
8. Identify the currency symbol or 3-letter ISO code (e.g., 'USD', '$', 'EUR', 'INR', '₹').
9. Extract all visible line items into the line_items array. If no line items exist, return an empty array [].
10. Return ONLY a valid JSON object. Do not wrap the JSON in markdown explanations or comments outside the JSON.

Expected JSON Structure:
{
  "vendor_name": "string or null",
  "vendor_address": "string or null",
  "vendor_gstin": "string or null",
  "invoice_number": "string or null",
  "invoice_date": "string or null",
  "due_date": "string or null",
  "purchase_order_number": "string or null",
  "currency": "string or null",
  "subtotal": 0.0 or null,
  "tax_amount": 0.0 or null,
  "total_amount": 0.0 or null,
  "payment_terms": "string or null",
  "line_items": [
    {
      "description": "string",
      "quantity": 0.0 or null,
      "unit_price": 0.0 or null,
      "tax_rate": 0.0 or null,
      "line_total": 0.0 or null
    }
  ]
}
"""


def parse_gemini_json_response(response_text: str) -> InvoiceExtractionSchema:
    """
    Safely parse Gemini response string into validated InvoiceExtractionSchema.
    Handles responses wrapped in ```json code fences.
    """
    if not response_text or not response_text.strip():
        raise AIResponseParseError("Gemini returned an empty response.")

    cleaned_text = response_text.strip()

    # Strip markdown code blocks if model wrapped output in ```json ... ```
    if cleaned_text.startswith("```"):
        cleaned_text = re.sub(r"^```(?:json)?\s*", "", cleaned_text, flags=re.IGNORECASE)
        cleaned_text = re.sub(r"\s*```$", "", cleaned_text)
        cleaned_text = cleaned_text.strip()

    try:
        data_dict = json.loads(cleaned_text)
    except json.JSONDecodeError as err:
        logger.error(f"Malformed JSON returned by Gemini: {cleaned_text}")
        raise AIResponseParseError(f"Failed to parse Gemini response as JSON: {err}")

    if not isinstance(data_dict, dict):
        raise AIResponseParseError("Gemini JSON response is not a valid JSON object.")

    try:
        validated_schema = InvoiceExtractionSchema.model_validate(data_dict)
        return validated_schema
    except Exception as val_err:
        logger.error(f"Pydantic validation failed for AI output: {val_err}")
        raise AIResponseParseError(f"Extracted JSON does not match required schema: {val_err}")


def extract_invoice_with_gemini(
    raw_text: str,
    api_key: Optional[str] = None,
) -> InvoiceExtractionSchema:
    """
    Send raw invoice text to Google Gemini and validate the structured response.
    """
    key = api_key or settings.GEMINI_API_KEY
    if not key or not key.strip():
        raise GeminiNotConfiguredError(
            "Google Gemini API key is not configured. Please set GEMINI_API_KEY in your .env file."
        )

    from google import genai
    from google.genai import types

    try:
        client = genai.Client(api_key=key.strip())
        prompt = f"{EXTRACTION_SYSTEM_PROMPT}\n\nINVOICE TEXT TO PROCESS:\n\"\"\"\n{raw_text}\n\"\"\""

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        )

        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=config,
        )

        response_text = response.text or ""
        return parse_gemini_json_response(response_text)

    except (GeminiNotConfiguredError, AIResponseParseError):
        raise
    except Exception as exc:
        logger.error(f"Gemini API request failed: {exc}", exc_info=True)
        raise AIExtractionError(f"Gemini API call failed: {exc}")


def extract_and_persist_invoice(
    invoice_id: int,
    db: Session,
    api_key: Optional[str] = None,
) -> Invoice:
    """
    Orchestrate full AI extraction lifecycle for an invoice:
    1. Validates invoice and raw_text existence.
    2. Updates status to AI_PROCESSING.
    3. Calls Gemini extraction service.
    4. Persists structured attributes and replaces line items.
    5. Updates status to AI_EXTRACTED.
    6. On failure, retains raw_text and marks status PROCESSING_FAILED.
    """
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise InvoiceNotFoundError(f"Invoice with ID {invoice_id} not found.")

    if not invoice.raw_text or not invoice.raw_text.strip():
        raise MissingRawTextError(
            f"Invoice #{invoice_id} does not contain extracted raw text. "
            "Please run document processing (PyMuPDF / OCR) first."
        )

    # Set status to AI_PROCESSING
    invoice.status = STATUS_AI_PROCESSING
    db.commit()
    db.refresh(invoice)

    try:
        extracted = extract_invoice_with_gemini(invoice.raw_text, api_key=api_key)

        # Update core invoice structured fields
        invoice.vendor_name = extracted.vendor_name
        invoice.vendor_address = extracted.vendor_address
        invoice.vendor_gstin = extracted.vendor_gstin
        invoice.invoice_number = extracted.invoice_number
        invoice.invoice_date = extracted.invoice_date
        invoice.due_date = extracted.due_date
        invoice.purchase_order_number = extracted.purchase_order_number
        invoice.payment_terms = extracted.payment_terms
        invoice.currency = extracted.currency
        invoice.subtotal = extracted.subtotal
        invoice.tax_amount = extracted.tax_amount
        invoice.total_amount = extracted.total_amount

        # Replace existing line items cleanly
        invoice.line_items.clear()
        for item in extracted.line_items:
            db_item = InvoiceLineItem(
                invoice_id=invoice.id,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                tax_rate=item.tax_rate,
                line_total=item.line_total,
            )
            invoice.line_items.append(db_item)

        invoice.status = STATUS_AI_EXTRACTED
        db.commit()
        db.refresh(invoice)

        from backend.services.audit_service import record_audit_event
        from backend.models.invoice import ACTION_AI_EXTRACTED
        try:
            record_audit_event(
                db=db,
                action=ACTION_AI_EXTRACTED,
                status="SUCCESS",
                invoice_id=invoice.id,
                message=(
                    f"Gemini AI extracted structured fields for vendor '{invoice.vendor_name or 'N/A'}' "
                    f"with {len(invoice.line_items)} line items."
                ),
            )
        except Exception:
            pass

        logger.info(f"Successfully extracted and saved structured data for Invoice #{invoice.id}")
        return invoice

    except Exception as exc:
        logger.error(f"AI extraction failed for Invoice #{invoice.id}: {exc}", exc_info=True)
        invoice.status = STATUS_PROCESSING_FAILED
        db.commit()
        from backend.services.audit_service import record_audit_event
        try:
            record_audit_event(
                db=db,
                action="AI_EXTRACTION_FAILED",
                status="FAILED",
                invoice_id=invoice.id,
                message=str(exc),
            )
        except Exception:
            pass
        raise
