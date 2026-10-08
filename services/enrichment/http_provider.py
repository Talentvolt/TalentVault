"""Real HTTP enrichment provider adapter.

Talks to a custom/internal enrichment HTTP service. Configuration comes from
environment variables (never the extension/frontend):

    ENRICHMENT_BASE_URL         base URL (e.g. https://enrich.example.internal)
    ENRICHMENT_API_KEY          secret API key
    ENRICHMENT_API_KEY_HEADER   header name (default "X-Api-Key")
    ENRICHMENT_TIMEOUT          seconds (default 10)

Request (POST {base}/api/v1/enrich, JSON):
    {"name", "company", "title", "location", "linkedin_url"}

Response (flat JSON):
    {"email": str|null, "phone": str|null, "confidence": float,
     "email_verified": bool, "phone_verified": bool}
    (a 404 status means "person not found")
"""
import logging
import os

import requests
from django.conf import settings

from services.enrichment.normalization import contact_status, validated_email, validated_phone
from services.enrichment.providers import EnrichmentProvider, EnrichmentProviderError

logger = logging.getLogger(__name__)


def _as_float(value, default=1.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class HTTPEnrichmentProvider(EnrichmentProvider):
    name = "http"

    @classmethod
    def get_base_url(cls) -> str:
        return (
            getattr(settings, "ENRICHMENT_BASE_URL", None)
            or os.environ.get("ENRICHMENT_BASE_URL", "")
        ).rstrip("/")

    @classmethod
    def get_api_key(cls) -> str:
        return getattr(settings, "ENRICHMENT_API_KEY", None) or os.environ.get("ENRICHMENT_API_KEY", "")

    @classmethod
    def get_api_key_header(cls) -> str:
        return (
            getattr(settings, "ENRICHMENT_API_KEY_HEADER", None)
            or os.environ.get("ENRICHMENT_API_KEY_HEADER", "X-Api-Key")
        )

    @classmethod
    def get_timeout(cls) -> float:
        return float(
            getattr(settings, "ENRICHMENT_TIMEOUT", None)
            or os.environ.get("ENRICHMENT_TIMEOUT", "10")
        )

    @classmethod
    def is_configured(cls) -> bool:
        return bool(cls.get_base_url() and cls.get_api_key())

    def _request(self, payload: dict) -> tuple:
        base_url = self.get_base_url()
        api_key = self.get_api_key()

        if not base_url or not api_key:
            raise EnrichmentProviderError(
                "Enrichment provider is not configured "
                "(set ENRICHMENT_BASE_URL and ENRICHMENT_API_KEY)."
            )

        endpoint = f"{base_url}/api/v1/enrich"
        headers = {
            self.get_api_key_header(): api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        logger.info("[ENRICHMENT] POST %s", endpoint)
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=self.get_timeout(),
            )
        except requests.exceptions.Timeout as exc:
            raise EnrichmentProviderError("Enrichment provider timed out.") from exc
        except requests.exceptions.RequestException as exc:
            raise EnrichmentProviderError(f"Enrichment provider unreachable: {exc}") from exc

        if response.status_code in (401, 403):
            raise EnrichmentProviderError("Enrichment provider rejected the API key.")
        if response.status_code >= 500:
            raise EnrichmentProviderError(
                f"Enrichment provider error (HTTP {response.status_code})."
            )

        try:
            data = response.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}

        return response.status_code, data

    def match_person(self, person: dict) -> dict:
        person = person or {}
        payload = {
            "name": (person.get("name") or "").strip(),
            "company": (person.get("company") or "").strip(),
            "title": (person.get("title") or "").strip(),
            "location": (person.get("location") or "").strip(),
            "linkedin_url": (
                (person.get("linkedin_url") or person.get("profile_url") or "").strip()
            ),
        }

        status_code, data = self._request(payload)

        if status_code == 404:
            return {"matched": False, "confidence": 0.0, "record": None}

        if data.get("matched") is False or data.get("found") is False:
            return {"matched": False, "confidence": 0.0, "record": None}

        return {
            "matched": True,
            "confidence": _as_float(data.get("confidence"), default=1.0),
            "record": data,
        }

    def find_email(self, person: dict, match: dict) -> dict:
        record = (match or {}).get("record") or {}
        value = validated_email(record.get("email"))
        return {"value": value, "status": contact_status(record.get("email_verified"), bool(value))}

    def find_phone(self, person: dict, match: dict) -> dict:
        record = (match or {}).get("record") or {}
        value = validated_phone(record.get("phone"))
        return {"value": value, "status": contact_status(record.get("phone_verified"), bool(value))}
