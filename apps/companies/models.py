from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseAppModel
from django.conf import settings

class Company(BaseAppModel):
    """
    Represents a Company/Employer on the platform.
    """
    name = models.CharField(max_length=255, unique=True, db_index=True)
    slug = models.SlugField(max_length=255, unique=True)
    website = models.URLField(blank=True, null=True)
    industry = models.CharField(max_length=100, db_index=True)
    description = models.TextField()
    logo = models.ImageField(upload_to='company_logos/', blank=True, null=True)
    address = models.TextField()
    location = models.CharField(max_length=100, db_index=True)
    employee_count = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _('company')
        verbose_name_plural = _('companies')
        ordering = ['name']

    def __str__(self):
        return self.name

class CompanyMember(BaseAppModel):
    """
    Maps Users (Admins/Recruiters) to Companies.
    """
    class MemberRole(models.TextChoices):
        ADMIN = "ADMIN", _("Admin")
        RECRUITER = "RECRUITER", _("Recruiter")

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='company_affiliations')
    designation = models.CharField(max_length=100)
    role = models.CharField(max_length=20, choices=MemberRole.choices, default=MemberRole.RECRUITER)

    class Meta:
        unique_together = ('company', 'user')
        verbose_name = _('company member')
        verbose_name_plural = _('company members')

    def __str__(self):
        return f"{self.user.email} @ {self.company.name}"
