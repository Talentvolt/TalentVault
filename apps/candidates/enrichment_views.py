import logging

from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from services.enrichment.normalization import DUMMY_PHONE, validated_email, validated_phone
from services.enrichment.person_match import PersonMatchService
from services.enrichment.providers import NOT_FOUND, EnrichmentProviderError

logger = logging.getLogger(__name__)

VALID_SCOPES = ("email", "phone", "all")


def _find_candidate(person, email, phone):
    from apps.accounts.models import User
    from apps.candidates.models import CandidateProfile

    profile = None
    profile_url = (person.get("profile_url") or "").strip()
    if profile_url:
        clean_url = profile_url.split("?")[0].rstrip("/")
        profile = (
            CandidateProfile.objects.filter(linkedin_url__icontains=clean_url).first()
            or CandidateProfile.objects.filter(portfolio_url__icontains=clean_url).first()
        )

    if not profile and email:
        user = User.objects.filter(email__iexact=email).first()
        if user and hasattr(user, "candidate_profile"):
            profile = user.candidate_profile

    if not profile and phone:
        user = User.objects.filter(phone_number=phone).first()
        if user and hasattr(user, "candidate_profile"):
            profile = user.candidate_profile

    return profile


def _save_enrichment(person, result):
    """Persist validated email/phone onto the matching candidate.

    Only validated values are written, existing real contacts are never
    overwritten, and enrichment provenance is stored in ``parsed_json``.
    """
    from apps.accounts.models import User
    from apps.candidates.models import CandidateProfile
    from apps.candidates.utils import is_placeholder_email

    email_result = result.get("email") or {}
    phone_result = result.get("phone") or {}

    email = validated_email(email_result.get("value"))
    phone = validated_phone(phone_result.get("value"))

    if not email and not phone:
        return {"saved": False, "reason": "No validated email or phone to save."}

    profile = _find_candidate(person, email, phone)
    if not profile:
        return {"saved": False, "reason": "No matching candidate found to update."}

    user = profile.user
    email_changed = False
    phone_changed = False

    if email and (not user.email or is_placeholder_email(user.email)):
        if not User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
            user.email = email
            email_changed = True

    if phone and (not user.phone_number or user.phone_number == DUMMY_PHONE):
        if not User.objects.filter(phone_number=phone).exclude(pk=user.pk).exists():
            user.phone_number = phone
            phone_changed = True

    if email_changed or phone_changed:
        user.save(update_fields=["email", "phone_number"])

    parsed = dict(profile.parsed_json or {})
    parsed["enrichment"] = {
        "source": result.get("source"),
        "confidence": result.get("match_confidence"),
        "email": {"value": email, "status": email_result.get("status") or NOT_FOUND},
        "phone": {"value": phone, "status": phone_result.get("status") or NOT_FOUND},
        "last_verified_at": timezone.now().isoformat(),
    }
    profile.parsed_json = parsed
    profile.save(update_fields=["parsed_json"])

    return {
        "saved": True,
        "candidate_id": str(profile.id),
        "email_saved": email_changed,
        "phone_saved": phone_changed,
    }


class PersonEnrichmentAPIView(APIView):
    """
    Local email + phone enrichment for an imported candidate profile.

    Accepts the currently imported profile's name/company/title/location/URL,
    runs person matching + contact enrichment through the configured provider,
    and (optionally) persists validated contacts onto the matching candidate.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        data = request.data or {}
        if not isinstance(data, dict):
            return Response({"error": "Invalid payload."}, status=status.HTTP_400_BAD_REQUEST)

        person = {
            "name": (data.get("name") or "").strip(),
            "company": (data.get("company") or "").strip(),
            "title": (data.get("title") or "").strip(),
            "location": (data.get("location") or "").strip(),
            "profile_url": (data.get("profile_url") or "").strip(),
        }

        if not any(person.values()):
            return Response(
                {"error": "At least one of name, company, title, location or profile_url is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        scope = data.get("scope") or "all"
        if scope not in VALID_SCOPES:
            scope = "all"

        try:
            result = PersonMatchService.enrich(person, scope=scope)
        except EnrichmentProviderError as exc:
            logger.warning("[ENRICHMENT] Provider error: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        if bool(data.get("save")):
            result["save"] = _save_enrichment(person, result)

        return Response(result, status=status.HTTP_200_OK)
