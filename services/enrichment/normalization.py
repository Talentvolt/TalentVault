"""Shared normalization + validation for enriched contact values.

Used both by the HTTP provider (to sanitize what the external service returns)
and by the enrichment API view (to validate before persisting). Values that are
absent, malformed, or known dummies are returned as empty strings.
"""
import re

from services.enrichment.providers import FOUND, NOT_FOUND, UNVERIFIED, VERIFIED

DUMMY_PHONE = "9876543210"


def validated_email(value) -> str:
    from apps.candidates.utils import VALID_EMAIL_RE, is_placeholder_email

    if not value:
        return ""
    value = str(value).strip().lower()
    if is_placeholder_email(value):
        return ""
    if VALID_EMAIL_RE.match(value):
        return value[:254]
    return ""


def validated_phone(value) -> str:
    if not value:
        return ""
    raw = str(value).strip()
    has_plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    if not (8 <= len(digits) <= 15):
        return ""
    if digits == DUMMY_PHONE:
        return ""
    return ("+" if has_plus else "") + digits


def contact_status(verified_flag, has_value: bool) -> str:
    """Map a value + optional verified flag into a contact status."""
    if not has_value:
        return NOT_FOUND
    if verified_flag is True:
        return VERIFIED
    if verified_flag is False:
        return UNVERIFIED
    return FOUND
