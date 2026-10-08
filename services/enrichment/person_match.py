"""Person Match Service.

Orchestrates the enrichment flow: match a person, then look up their email and
phone through the configured ``EnrichmentProvider``.
"""
from services.enrichment.providers import get_enrichment_provider, NOT_FOUND

VALID_SCOPES = ("email", "phone", "all")


class PersonMatchService:
    @staticmethod
    def enrich(person: dict, scope: str = "all", provider=None) -> dict:
        """Run person matching + contact enrichment.

        ``scope`` controls which contact channels are queried: "email", "phone"
        or "all" (default). Unrequested channels return a ``not_found`` shape.
        """
        provider = provider or get_enrichment_provider()
        scope = scope if scope in VALID_SCOPES else "all"

        match = provider.match_person(person or {})

        result = {
            "matched": bool(match.get("matched")),
            "match_confidence": match.get("confidence", 0.0),
            "source": getattr(provider, "name", "mock"),
            "email": {"value": None, "status": NOT_FOUND},
            "phone": {"value": None, "status": NOT_FOUND},
        }

        if result["matched"]:
            if scope in ("email", "all"):
                result["email"] = provider.find_email(person, match)
            if scope in ("phone", "all"):
                result["phone"] = provider.find_phone(person, match)

        return result
