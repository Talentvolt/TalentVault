from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from apps.jobs.models import Job
from apps.candidates.models import CandidateProfile


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


class CandidateProfileSitemap(Sitemap):
    """
    Sitemap for public candidate profile share pages.
    """
    changefreq = "weekly"
    priority = 0.6
    protocol = "https"

    def items(self):
        return CandidateProfile.objects.all().order_by('-updated_at')

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse('frontend:public_candidate_profile', kwargs={'pk': obj.pk})


class StaticViewSitemap(Sitemap):
    """
    Sitemap for static/public landing and account pages.
    """
    priority = 0.5
    changefreq = "weekly"
    protocol = "https"

    def items(self):
        return [
            'frontend:dashboard',
            'frontend:employer_landing',
            'frontend:candidate_career_resources',
            'account_login',
            'account_signup',
            'candidate_login',
            'candidate_signup',
            'employer_login',
            'employer_signup',
        ]

    def location(self, item):
        return reverse(item)


sitemaps = {
    'jobs': JobSitemap,
    'candidates': CandidateProfileSitemap,
    'static': StaticViewSitemap,
}
