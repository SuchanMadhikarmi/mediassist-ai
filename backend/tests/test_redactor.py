# ============================================================
# backend/tests/test_redactor.py
# Deterministic tests for the PII redaction middleware (Phase 3).
#
# WHY: PII leaked into an LLM prompt (emails, phone numbers, SSNs) is a
# data-protection breach. The redactor is pure regex on strings — fully
# deterministic — so every PR must prove emails and SSNs disappear before
# anything sensitive is sent to Ollama.
# ============================================================

from security.pii_redactor import redact_pii


class TestPiiRedactor:
    def test_email_redacted(self):
        out = redact_pii("Contact jane.smith@hosp.local for details")
        assert "jane.smith@hosp.local" not in out
        assert "[EMAIL_REDACTED]" in out

    def test_ssn_redacted(self):
        out = redact_pii("SSN 123-45-6789 must be hidden")
        assert "123-45-6789" not in out
        assert "[SSN_REDACTED]" in out

    def test_phone_redacted(self):
        out = redact_pii("Call 555-123-4567 right away")
        assert "555-123-4567" not in out
        assert "[PHONE_REDACTED]" in out

    def test_credit_card_redacted(self):
        out = redact_pii("card 4111 1111 1111 1111 expires soon")
        assert "4111" not in out
        assert "[CREDIT_CARD_REDACTED]" in out

    def test_plain_text_untouched(self):
        out = redact_pii("What does error code 4012 mean?")
        assert out == "What does error code 4012 mean?"

    def test_empty_input_is_safe(self):
        assert redact_pii("") == ""
        assert redact_pii(None) is None

    def test_multiple_pii_types_in_one_string(self):
        out = redact_pii("email a@b.com phone 555-123-4567 ssn 123-45-6789")
        assert "[EMAIL_REDACTED]" in out
        assert "[PHONE_REDACTED]" in out
        assert "[SSN_REDACTED]" in out
        # No raw PII fragments survive at all
        assert "@" not in out