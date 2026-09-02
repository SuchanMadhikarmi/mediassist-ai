# ============================================================
# backend/security/pii_redactor.py
# Strips Personally Identifiable Information from text BEFORE
# it reaches the AI engine.
#
# WHY BEFORE? The LLM's answer is built from the prompt context.
# If a nurse pasted "contact jane@x.com, SSN 123-45-6789",
# that PII becomes part of the prompt -> part of the trace ->
# stored in logs. Redacting at the edge keeps PII out of the
# entire downstream pipeline.
#
# APPROACH: regex patterns. Simple, fast, deterministic, and
# transparent — unlike a fragile ML classifier. Trade-off: regex
# miss unusual formats, but for a security gate, false-positives
# (redacting something that wasn't PII) are acceptable; leaking
# real PII is not.
# ============================================================

import re

# name -> compiled regex. The regex finds the PII; we replace with a marker.
PII_PATTERNS: dict[str, re.Pattern[str]] = {
    # Email: standard local@domain.tld
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    # US SSN: 123-45-6789
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    # Phone (US-centric, flexible separators): 555-123-4567 / (555) 123-4567 / +1 555 123 4567
    "PHONE": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    # Credit card: 16 digits, optional group separators
    "CREDIT_CARD": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    # US zip+4
    "ZIP": re.compile(r"\b\d{5}(?:-\d{4})?\b"),
}

# What we replace matches with. Keeping the TYPE in the marker makes
# redaction auditable ("why did it blank that? -> it was an email").
REDACTED_LABEL = "[{pii_type}_REDACTED]"


def redact_pii(text: str) -> str:
    """Return `text` with all detected PII replaced by markers.

    Example:
        redact_pii("Call 555-123-4567 or email jane@x.com")
        -> "Call [PHONE_REDACTED] or email [EMAIL_REDACTED]"
    """
    if not text:
        return text
    result = text
    for pii_type, pattern in PII_PATTERNS.items():
        result = pattern.sub(REDACTED_LABEL.format(pii_type=pii_type), result)
    return result
