from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from apps.jobs.models import Job


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
