"""Enrichment provider abstraction.

Defines the contract that any contact-enrichment backend must implement so the
person-match + email/phone enrichment flow stays decoupled from a concrete
vendor. Local development uses ``MockEnrichmentProvider`` (see mock_provider.py);
a real provider can be added later without touching the API view or the
extension.
"""
from abc import ABC, abstractmethod

# Allowed contact verification statuses returned to the side panel.
FOUND = "found"
NOT_FOUND = "not_found"
VERIFIED = "verified"
UNVERIFIED = "unverified"

CONTACT_STATUSES = (FOUND, NOT_FOUND, VERIFIED, UNVERIFIED)


class EnrichmentProviderError(Exception):
    """Raised when the enrichment provider is misconfigured or unreachable."""


class EnrichmentProvider(ABC):
    """Contract for a person-matching + contact-enrichment provider."""

    name = "base"

    @abstractmethod
    def match_person(self, person: dict) -> dict:
        """Match the given person against the provider's index.

        ``person`` contains keys: name, company, title, location, profile_url.

        Returns a dict with at least:
            ``matched`` (bool) and ``confidence`` (float).
        """

    @abstractmethod
    def find_email(self, person: dict, match: dict) -> dict:
        """Return enriched email for a matched person.

        Returns a dict with ``value`` (str or None) and ``status`` (one of
        CONTACT_STATUSES).
        """

    @abstractmethod
    def find_phone(self, person: dict, match: dict) -> dict:
        """Return enriched phone for a matched person.

        Returns a dict with ``value`` (str or None) and ``status`` (one of
        CONTACT_STATUSES).
        """


def get_enrichment_provider(name: str | None = None) -> EnrichmentProvider:
    """Resolve the configured enrichment provider.

    Selection is driven by ``settings.ENRICHMENT_PROVIDER``. The native
    TalentVault provider (ORM-backed, no HTTP, no recursion) is the default;
    ``mock`` is reserved for tests and ``http`` remains an optional future
    adapter. No provider-specific values ever live in the extension/frontend.
    """
    from django.conf import settings

    name = name or getattr(settings, "ENRICHMENT_PROVIDER", "native")

    if name == "mock":
        from services.enrichment.mock_provider import MockEnrichmentProvider

        return MockEnrichmentProvider()

    if name in ("native", "local", "talentvault"):
        from services.enrichment.native_provider import NativeEnrichmentProvider

        return NativeEnrichmentProvider()

    if name in ("http", "real"):
        from services.enrichment.http_provider import HTTPEnrichmentProvider

        return HTTPEnrichmentProvider()

    raise ValueError(f"Unknown enrichment provider: {name!r}")
