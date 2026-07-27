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
