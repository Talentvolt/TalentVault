from django import template
from utils.url_helpers import normalize_external_url

register = template.Library()

@register.filter(name='external_url')
def external_url(value):
    """
    Template filter to format external URLs with http:// or https://.
    Usage: {{ profile.linkedin_url|external_url }}
    """
    if not value:
        return ""
    return normalize_external_url(value) or ""


@register.filter(name='user_initials')
def user_initials(user):
    """
    Returns a safe 2-letter initials string for the given user (or "CV" fallback).
    Safely handles AnonymousUser and missing candidate profiles without ever
    raising or performing subscript/index lookups on the user object.
    """
    try:
        if not getattr(user, 'is_authenticated', False):
            return "CV"
        profile = getattr(user, 'candidate_profile', None)
        name = ""
        if profile is not None:
            name = getattr(profile, 'full_name', '') or ''
        if not name:
            name = getattr(user, 'get_full_name', None)
            if callable(name):
                name = name()
        name = (name or '').strip()
        if not name:
            return "CV"
        initials = name[:2].upper()
        return initials or "CV"
    except Exception:
        return "CV"
