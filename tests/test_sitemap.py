import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_sitemap_returns_xml(client):
    response = client.get('/sitemap.xml', HTTP_HOST='talent-vault.in')
    assert response.status_code == 200
    assert response.headers['Content-Type'].startswith('application/xml')
    content = response.content.decode('utf-8')
    assert content.strip().startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert '<urlset' in content
    assert 'https://talent-vault.in/' in content
    # Ensure candidate share and resume URLs are never in sitemap
    assert '/share/candidate/' not in content
    assert 'resume-preview' not in content


@pytest.mark.django_db
def test_robots_txt_returns_plain_text(client):
    response = client.get('/robots.txt')
    assert response.status_code == 200
    assert response.headers['Content-Type'].startswith('text/plain')
    content = response.content.decode('utf-8')
    assert 'User-agent: *' in content
    assert 'Sitemap: https://talent-vault.in/sitemap.xml' in content

    # Allow candidate share & resume URLs for crawling so noindex is observed
    assert 'Allow: /share/candidate/' in content
    assert 'Disallow: /share/candidate/' not in content

    # Keep private areas blocked
    assert 'Disallow: /admin/' in content
    assert 'Disallow: /dashboard/' in content
    assert 'Disallow: /candidates/' in content
    assert 'Disallow: /pipeline/' in content
    assert 'Disallow: /settings/' in content
