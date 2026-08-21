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
    
    department = models.CharField(max_length=100, blank=True, default='')
    required_skills_text = models.TextField(blank=True, default='', help_text="Comma separated required skills")
    preferred_skills_text = models.TextField(blank=True, default='', help_text="Comma separated preferred skills")
    education = models.CharField(max_length=100, blank=True, default='')
    notice_period = models.PositiveIntegerField(default=30, help_text="Maximum notice period in days")
    ai_matching_enabled = models.BooleanField(default=True)

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

    screening_questions = models.JSONField(default=list, blank=True)

    @property
    def get_required_skills_list(self):
        if self.required_skills_text:
            return [s.strip() for s in self.required_skills_text.split(',') if s.strip()]
        return list(self.skills.filter(is_mandatory=True).values_list('skill_name', flat=True))

    @property
    def get_preferred_skills_list(self):
        if self.preferred_skills_text:
            return [s.strip() for s in self.preferred_skills_text.split(',') if s.strip()]
        return list(self.skills.filter(is_mandatory=False).values_list('skill_name', flat=True))

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

    @property
    def display_company(self):
        if self.client and getattr(self.client, 'company_name', None) and self.client.company_name.strip():
            return self.client.company_name.strip()
        if self.company and getattr(self.company, 'name', None) and self.company.name.strip():
            return self.company.name.strip()
        return "N/A"

    @property
    def client_name(self):
        return self.display_company
    
    class Meta:
        verbose_name = _('job')
        verbose_name_plural = _('jobs')
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.company_id:
            if self.client and getattr(self.client, 'company_name', None) and self.client.company_name.strip():
                from apps.companies.models import Company
                from django.utils.text import slugify
                comp_name = self.client.company_name.strip()
                company = Company.objects.filter(name__iexact=comp_name).first()
                if not company:
                    base_slug = slugify(comp_name) or 'company'
                    slug = base_slug
                    counter = 1
                    while Company.objects.filter(slug=slug).exists():
                        slug = f"{base_slug}-{counter}"
                        counter += 1
                    company = Company.objects.create(
                        name=comp_name,
                        slug=slug,
                        industry=getattr(self.client, 'industry', '') or 'General',
                        location=getattr(self.client, 'city', '') or 'India'
                    )
                self.company = company
            elif self.created_by:
                cm = self.created_by.company_affiliations.select_related('company').first()
                if cm and cm.company:
                    self.company = cm.company
            if not self.company_id:
                from apps.companies.models import Company
                company, _ = Company.objects.get_or_create(name="Default Company", defaults={'slug': 'default-company'})
                self.company = company
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} @ {self.display_company}"

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
