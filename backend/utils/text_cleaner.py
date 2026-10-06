import re


def clean_text(raw_text: str | None) -> str:
    """
    Clean and normalize extracted raw text from invoices while strictly preserving
    business-critical entities (numbers, dates, currency symbols, invoice identifiers, taxes).

    Rules:
    - Normalizes non-standard unicode spaces and line breaks.
    - Strips non-printable ASCII control characters without touching UTF-8 symbols.
    - Collapses multiple horizontal spaces/tabs into a single space on each line.
    - Trims leading and trailing whitespace per line.
    - Compresses excessive consecutive blank lines (max 1 empty line between blocks).
    - Preserves case, punctuation, numbers, dates, symbols ($ € £ ₹ ¥ % # - / : .).
    """
    if not raw_text:
        return ""

    # Replace Windows and old Mac line breaks with \n
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

    # Replace non-breaking space and other unicode spacing variants with standard space
    text = text.replace("\u00a0", " ").replace("\u200b", "")

    # Strip unprintable control characters, but preserve tabs and newlines
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Process lines: normalize horizontal whitespace and trim line edges
    cleaned_lines = []
    for line in text.split("\n"):
        # Collapse multiple spaces or tabs into a single space
        normalized_line = re.sub(r"[ \t]+", " ", line).strip()
        cleaned_lines.append(normalized_line)

    # Rejoin lines
    joined = "\n".join(cleaned_lines)

    # Compress 3 or more consecutive newlines into 2 (one blank line between text blocks)
    compressed = re.sub(r"\n{3,}", "\n\n", joined)

    return compressed.strip()
