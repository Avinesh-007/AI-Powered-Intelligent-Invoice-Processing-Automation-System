import re
from typing import Dict, Any, List, Set, Tuple
from backend.models.invoice import Invoice
from backend.services.ai_extraction_service import is_gemini_configured, get_gemini_client
from backend.config import settings

# Canonical expense categories
VALID_CATEGORIES = [
    "IT & Software",
    "Office Supplies",
    "Travel",
    "Utilities",
    "Professional Services",
    "Equipment",
    "Maintenance",
    "Marketing",
    "Logistics",
    "Other",
]

# Rule-based domain keyword mappings
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "IT & Software": [
        "software", "cloud", "aws", "azure", "google cloud", "saas", "hosting", "github",
        "gitlab", "microsoft", "license", "api", "server", "domain", "it services",
        "tech", "subscription", "database", "cybersecurity", "antivirus", "datadog",
        "atlassian", "slack", "zoom", "salesforce", "devops", "ssl certificate",
    ],
    "Office Supplies": [
        "stationery", "paper", "pen", "desk", "chair", "stapler", "toner", "cartridge",
        "printer paper", "office depot", "supplies", "notebook", "folders", "binders",
        "whiteboard", "markers", "envelopes", "staples",
    ],
    "Travel": [
        "flight", "airline", "hotel", "lodging", "uber", "taxi", "cab", "railway",
        "train", "airfare", "travel", "per diem", "car rental", "boarding", "stay",
        "lyft", "expedia", "booking.com", "delta", "united airlines", "emirates",
    ],
    "Utilities": [
        "electricity", "water", "gas", "internet", "broadband", "telecom", "phone",
        "power", "utility", "electric", "sewer", "airtel", "verizon", "at&t", "vodafone",
        "comcast", "coned", "energy", "mobile",
    ],
    "Professional Services": [
        "consulting", "legal", "audit", "advisory", "accounting", "counsel", "retainer",
        "attorney", "tax preparation", "compliance", "professional fee", "notary",
        "recruitment", "hr consulting", "management consulting", "deloitte", "pwc", "ey", "kpmg",
    ],
    "Equipment": [
        "hardware", "laptop", "monitor", "machinery", "computer", "printer", "projector",
        "device", "cables", "tools", "workstation", "server rack", "keyboard", "mouse",
        "docking station", "router", "switch", "ups system",
    ],
    "Maintenance": [
        "repair", "maintenance", "cleaning", "janitorial", "servicing", "facility",
        "inspection", "hvac", "plumbing", "sanitation", "upkeep", "waste disposal",
        "landscaping", "pest control", "elevator maintenance",
    ],
    "Marketing": [
        "advertising", "adwords", "campaign", "social media", "seo", "branding",
        "sponsorship", "promotion", "marketing", "facebook ads", "google ads", "pr agency",
        "billboard", "influencer", "commercial", "creative agency", "banner",
    ],
    "Logistics": [
        "freight", "shipping", "courier", "delivery", "customs", "transport",
        "cargo", "postage", "fedex", "dhl", "ups", "warehouse", "logistics", "hauling",
        "import duty", "drayage", "pallet",
    ],
}


def _match_keywords_in_text(text: str, keywords: List[str]) -> List[str]:
    """Find whole-word or substring matches for keywords in normalized text."""
    normalized = text.lower()
    matches = []
    for kw in keywords:
        pattern = r"\b" + re.escape(kw) + r"\b"
        if re.search(pattern, normalized):
            matches.append(kw)
    return matches


def classify_expense_by_rules(invoice: Invoice) -> Tuple[str, float, List[str]]:
    """
    Classify invoice expense using weighted multi-attribute keyword matching across:
    - Vendor Name (weight: 2.5)
    - Line item descriptions (weight: 2.0)
    - Raw text content (weight: 1.0)

    Returns (category, confidence, matched_keywords).
    """
    vendor_text = (invoice.vendor_name or "").lower()
    line_items_text = " ".join([item.description or "" for item in invoice.line_items]).lower()
    raw_text = (invoice.raw_text or "").lower()

    scores: Dict[str, float] = {cat: 0.0 for cat in VALID_CATEGORIES if cat != "Other"}
    matched_by_cat: Dict[str, Set[str]] = {cat: set() for cat in VALID_CATEGORIES if cat != "Other"}

    for cat, keywords in CATEGORY_KEYWORDS.items():
        v_matches = _match_keywords_in_text(vendor_text, keywords)
        l_matches = _match_keywords_in_text(line_items_text, keywords)
        r_matches = _match_keywords_in_text(raw_text, keywords)

        score = (len(v_matches) * 2.5) + (len(l_matches) * 2.0) + (len(r_matches) * 1.0)
        scores[cat] = score
        matched_by_cat[cat].update(v_matches)
        matched_by_cat[cat].update(l_matches)
        matched_by_cat[cat].update(r_matches)

    best_cat, max_score = max(scores.items(), key=lambda x: x[1])

    if max_score > 0:
        # Confidence scales between 0.60 and 0.95 depending on score
        confidence = min(0.95, round(0.55 + (0.10 * min(max_score, 4.0)), 2))
        return best_cat, confidence, sorted(list(matched_by_cat[best_cat]))

    return "Other", 0.0, []


def classify_expense_with_ai(invoice: Invoice) -> Tuple[Optional[str], float]:
    """
    Fallback classifier using Gemini AI when keyword rules yield no match.
    Returns (category, confidence) or (None, 0.0) if unavailable.
    """
    if not is_gemini_configured():
        return None, 0.0

    client = get_gemini_client()
    if not client:
        return None, 0.0

    categories_list_str = ", ".join(f"'{c}'" for c in VALID_CATEGORIES)
    vendor = invoice.vendor_name or "Unknown"
    items_summary = ", ".join([item.description for item in invoice.line_items if item.description]) or "None"
    text_snippet = (invoice.raw_text or "")[:1000]

    prompt = (
        f"You are a corporate expense categorization assistant. Categorize this invoice into EXACTLY ONE of the "
        f"following categories: {categories_list_str}.\n\n"
        f"Vendor: {vendor}\n"
        f"Items: {items_summary}\n"
        f"Text excerpt: {text_snippet}\n\n"
        f"Respond ONLY with the exact category name and nothing else."
    )

    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
        )
        if response and response.text:
            cleaned = response.text.strip().replace("'", "").replace('"', "")
            for valid_cat in VALID_CATEGORIES:
                if valid_cat.lower() == cleaned.lower():
                    return valid_cat, 0.85
    except Exception:
        pass

    return None, 0.0


def classify_expense(invoice: Invoice) -> Dict[str, Any]:
    """
    Orchestrate expense classification:
    1. Try multi-attribute deterministic rule-based matching.
    2. If inconclusive, try Gemini AI fallback if configured.
    3. Default to 'Other' if neither produces a match.
    """
    # 1. Deterministic Rule-Based
    cat, conf, matched = classify_expense_by_rules(invoice)
    if cat != "Other" and conf > 0.0:
        return {
            "category": cat,
            "confidence": conf,
            "method": "RULE_BASED",
            "matched_keywords": matched,
        }

    # 2. AI Fallback (if Gemini key configured)
    ai_cat, ai_conf = classify_expense_with_ai(invoice)
    if ai_cat:
        return {
            "category": ai_cat,
            "confidence": ai_conf,
            "method": "AI_FALLBACK",
            "matched_keywords": [],
        }

    # 3. Default
    return {
        "category": "Other",
        "confidence": 0.30,
        "method": "DEFAULT",
        "matched_keywords": [],
    }
