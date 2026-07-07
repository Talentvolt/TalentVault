from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseAppModel
from apps.companies.models import Company
from django.conf import settings
from utils.salary_formatter import format_salary_lpa

class Job(BaseAppModel):
    """
    Job Posting model.
    """
    class JobStatus(models.TextChoices):
        DRAFT = "DRAFT", _("Draft")
        ACTIVE = "ACTIVE", _("Active")
        PAUSED = "PAUSED", _("Paused")
        ON_HOLD = "ON_HOLD", _("On Hold")
        CLOSED = "CLOSED", _("Closed")

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='jobs')
    client = models.ForeignKey('clients.Client', on_delete=models.SET_NULL, null=True, blank=True, related_name='jobs')
    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField()
    location = models.CharField(max_length=100, db_index=True)
    job_type = models.CharField(max_length=50, choices=[
        ('FULL_TIME', 'Full Time'),
        ('PART_TIME', 'Part Time'),
        ('CONTRACT', 'Contract'),
        ('FREELANCE', 'Freelance'),
        ('ON_SITE', 'On Site'),
        ('HYBRID', 'Hybrid'),
        ('WORK_FROM_HOME', 'Work From Home'),
    ], default='FULL_TIME')
    work_mode = models.CharField(max_length=50, choices=[
        ('ONSITE', 'Onsite'),
        ('HYBRID', 'Hybrid'),
        ('REMOTE', 'Remote'),
    ], default='ONSITE')
    
    jd_file = models.FileField(upload_to='jd_files/', null=True, blank=True)

    min_experience = models.PositiveIntegerField(default=0, help_text="Minimum experience in years")
    max_experience = models.PositiveIntegerField(default=1, help_text="Maximum experience in years")

    min_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    max_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='INR')

    assets_required = models.JSONField(default=list, blank=True, help_text="List of required assets (e.g. Bike, Laptop)")
    
    status = models.CharField(
        max_length=20, 
        choices=JobStatus.choices, 
        default=JobStatus.DRAFT,
        db_index=True
    )
    
    is_remote = models.BooleanField(default=False)
    application_deadline = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='closed_jobs')

    @property
    def min_salary_lpa(self):
        return format_salary_lpa(self.min_salary)

    @property
    def max_salary_lpa(self):
        return format_salary_lpa(self.max_salary)

    @property
    def salary_range_lpa(self):
        if self.min_salary and self.max_salary:
            return f"{self.min_salary_lpa} - {self.max_salary_lpa}"
        elif self.min_salary:
            return self.min_salary_lpa
        elif self.max_salary:
            return self.max_salary_lpa
        return "Not Specified"
    
    class Meta:
        verbose_name = _('job')
        verbose_name_plural = _('jobs')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} @ {self.company.name}"

class JobSkill(BaseAppModel):
    """
    Required skills for a Job.
    """
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='skills')
    skill_name = models.CharField(max_length=100, db_index=True)
    is_mandatory = models.BooleanField(default=True)

    class Meta:
        unique_together = ('job', 'skill_name')
        verbose_name = _('job skill')
        verbose_name_plural = _('job skills')

    def __str__(self):
        return f"{self.skill_name} ({'Mandatory' if self.is_mandatory else 'Optional'})"
