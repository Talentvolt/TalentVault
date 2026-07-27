"""
Utility functions for normalizing external URLs across TalentVault.
"""

def normalize_external_url(url):
    """
    Normalizes external profile and website URLs.
    If a URL does not start with http:// or https://, automatically prepends https://.
    Preserves internal relative links (starting with '/', '#'), javascript:, mailto:, and tel: links.
    """
    if not url:
        return url
    url_str = str(url).strip()
    if not url_str:
        return url_str

    # Do not modify internal URLs or specific protocols
    if url_str.startswith(('/', '#', 'javascript:', 'mailto:', 'tel:')):
        return url_str

    # Keep http:// or https:// unchanged
    if url_str.lower().startswith(('http://', 'https://')):
        return url_str

    # Prepend https:// for domain-based relative-looking external URLs
    return f"https://{url_str}"
