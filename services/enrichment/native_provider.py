"""Native TalentVault enrichment provider.

Matches profile identifiers directly against the TalentVault People/Email/Phone
database (``EnrichmentPerson``) using the ORM. This is the default LOCAL
implementation — it never makes an outbound HTTP call and never calls the
enrichment API back (no recursion).

Matching weights (same scoring model as the mock provider):
    linkedin_url  -> exact match (0.50)
    name          -> exact match (0.30)
    company       -> exact match (0.15)
    title         -> exact match (0.15)
    location      -> exact match (0.05)
A combined score >= 0.40 is considered a verified match.
"""
from django.db.models import Q

from services.enrichment.normalization import validated_email, validated_phone
from services.enrichment.providers import (
    EnrichmentProvider,
    FOUND,
    NOT_FOUND,
    UNVERIFIED,
    VERIFIED,
)

MATCH_THRESHOLD = 0.40

_VALID_STATUSES = (FOUND, VERIFIED, UNVERIFIED)


def _norm(value):
    return " ".join((value or "").strip().lower().split())


class NativeEnrichmentProvider(EnrichmentProvider):
    name = "talentvault"

    def match_person(self, person: dict) -> dict:
        from apps.candidates.models import EnrichmentPerson

        person = person or {}
        name = _norm(person.get("name"))
        company = _norm(person.get("company"))
        title = _norm(person.get("title"))
        location = _norm(person.get("location"))
        profile_url = (person.get("profile_url") or person.get("linkedin_url") or "").strip()

        # A LinkedIn URL is the strongest unique identifier.
        if profile_url:
            clean_url = profile_url.split("?")[0].rstrip("/")
            record = EnrichmentPerson.objects.filter(linkedin_url__icontains=clean_url).first()
            if record:
                return {"matched": True, "confidence": 1.0, "record": record}

        # Narrow the candidate set by any shared identifier, then score.
        qs = EnrichmentPerson.objects.all()
        filters = Q()
        if name:
            filters |= Q(full_name__iexact=name)
        if company:
            filters |= Q(company__iexact=company)
        if title:
            filters |= Q(title__iexact=title)
        if filters:
            qs = qs.filter(filters)

        best = None
        best_score = 0.0
        for record in qs.iterator():
            score = 0.0
            if name and _norm(record.full_name) == name:
                score += 0.30
            if company and _norm(record.company) == company:
                score += 0.15
            if title and _norm(record.title) == title:
                score += 0.15
            if location and _norm(record.location) == location:
                score += 0.05
            if score > best_score:
                best = record
                best_score = score

        if best is None or best_score < MATCH_THRESHOLD:
            return {"matched": False, "confidence": 0.0, "record": None}

        return {"matched": True, "confidence": round(min(best_score, 1.0), 2), "record": best}

    def find_email(self, person: dict, match: dict) -> dict:
        record = (match or {}).get("record")
        if record is None:
            return {"value": None, "status": NOT_FOUND}

        value = validated_email(record.email)
        if not value:
            return {"value": None, "status": NOT_FOUND}

        status = record.email_status if record.email_status in _VALID_STATUSES else FOUND
        return {"value": value, "status": status}

    def find_phone(self, person: dict, match: dict) -> dict:
        record = (match or {}).get("record")
        if record is None:
            return {"value": None, "status": NOT_FOUND}

        value = validated_phone(record.phone)
        if not value:
            return {"value": None, "status": NOT_FOUND}

        status = record.phone_status if record.phone_status in _VALID_STATUSES else FOUND
        return {"value": value, "status": status}
