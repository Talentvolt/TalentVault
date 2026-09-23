from django.contrib.sitemaps import Sitemap
from django.contrib.sites.requests import RequestSite
from django.core.paginator import EmptyPage, PageNotAnInteger
from django.http import Http404, HttpResponse
from django.template.loader import render_to_string
from django.utils.encoding import smart_str
from django.urls import reverse
from apps.jobs.models import Job


def talentvault_sitemap_view(request, sitemaps, section=None, template_name="sitemap.xml", content_type="application/xml"):
    """
    Serve the public sitemap using the request's host as the domain.

    Django's stock sitemap view derives the domain from the django_site row
    selected by SITE_ID (via get_current_site). That single global row can be —
    and was — set to the wrong domain, causing https://talent-vault.in/sitemap.xml
    to emit https://hirenest.com.au/... URLs.

    Deriving the domain from the request host keeps TalentVault and HireNest
    separated without hardcoding either domain:

      - https://talent-vault.in/sitemap.xml  -> talent-vault.in URLs
      - https://hirenest.com.au/sitemap.xml -> hirenest.com.au URLs
    """
    req_protocol = request.scheme
    req_site = RequestSite(request)

    if section is not None:
        if section not in sitemaps:
            raise Http404("No sitemap available for section: %r" % section)
        maps = [sitemaps[section]]
    else:
        maps = list(sitemaps.values())

    page = request.GET.get("p", 1)
    urls = []
    for site in maps:
        if callable(site):
            site = site()
        try:
            urls.extend(site.get_urls(page=page, site=req_site, protocol=req_protocol))
        except EmptyPage:
            raise Http404("Page %s empty" % page)
        except PageNotAnInteger:
            raise Http404("No page '%s'" % page)

    xml = smart_str(render_to_string(template_name, {"urlset": urls}, request=request))
    response = HttpResponse(xml, content_type=content_type)
    response.headers["X-Robots-Tag"] = "noindex, noodp, noarchive"
    return response


class JobSitemap(Sitemap):
    """
    Sitemap for active public jobs.
    """
    changefreq = "daily"
    priority = 0.8
    protocol = "https"

    def items(self):
        return Job.objects.filter(status=Job.JobStatus.ACTIVE).order_by('-updated_at')

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse('frontend:public_job_share', kwargs={'pk': obj.pk})


class StaticViewSitemap(Sitemap):
    """
    Sitemap for public, indexable pages only.
    Private recruiter/admin/candidate/auth URLs are intentionally excluded.
    """
    priority = 0.5
    changefreq = "weekly"
    protocol = "https"

    def items(self):
        return [
            'frontend:dashboard',
            'frontend:jobs',
            'frontend:employer_landing',
        ]

    def location(self, item):
        return reverse(item)


sitemaps = {
    'jobs': JobSitemap,
    'static': StaticViewSitemap,
}
