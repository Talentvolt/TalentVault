import re
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from apps.core.models import BaseAppModel
from django.conf import settings
from django.core.validators import FileExtensionValidator
from utils.salary_formatter import format_salary_lpa

def validate_candidate_name(value):
    if not value:
        return
    val = value.strip()
    if val.isdigit():
        raise ValidationError("Candidate name cannot be a numeric string.")
    if re.match(r'^\+?\d[\d\s-]{8,}$', val):
        raise ValidationError("Candidate name cannot be a phone number.")
    if '@' in val:
        raise ValidationError("Candidate name cannot contain email addresses.")
    if val.lower().startswith('http'):
        raise ValidationError("Candidate name cannot be a URL.")
    if 'linkedin' in val.lower() or 'github' in val.lower():
        raise ValidationError("Candidate name cannot contain linkedin or github links.")
    # Reject if it's a phone number with formats like (+91) 9953699195 or similar
    digits_only = re.sub(r'[^\d+]', '', val)
    if len(digits_only) >= 8 and digits_only.replace('+', '').isdigit():
        raise ValidationError("Candidate name cannot be a phone number.")

class CandidateProfile(BaseAppModel):
    """
    Detailed profile for a Candidate.
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='candidate_profile')
    full_name = models.CharField(max_length=255, blank=True, null=True, db_index=True, validators=[validate_candidate_name])
    summary = models.TextField(blank=True)
    resume = models.FileField(
        upload_to='resumes/', 
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx'])],
        null=True, 
        blank=True
    )
    current_company = models.CharField(max_length=255, blank=True, null=True)
    current_designation = models.CharField(max_length=255, blank=True, null=True)
    location = models.CharField(max_length=100, db_index=True)
    total_experience = models.DecimalField(max_digits=4, decimal_places=1, default=0.0, help_text="Total experience in years")
    current_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    expected_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notice_period = models.PositiveIntegerField(default=30, help_text="Notice period in days")
    is_immediate_joiner = models.BooleanField(default=False)
    date_of_birth = models.DateField(null=True, blank=True)
    preferred_job_role = models.CharField(max_length=255, blank=True, null=True)
    preferred_location = models.CharField(max_length=255, blank=True, null=True)
    linkedin_url = models.URLField(blank=True, null=True)
    portfolio_url = models.URLField(blank=True, null=True)
    ats_score = models.PositiveIntegerField(default=0, db_index=True, help_text="Calculated ATS suitability score (0-100)")
    profile_photo = models.ImageField(upload_to='candidate_photos/', null=True, blank=True)
    recruiter_notes = models.TextField(blank=True, default="")

    @property
    def profile_completion_percentage(self) -> int:
        score = 0
        if self.has_resume:
            score += 25
        if self.skills.exists() or (self.original_skills and len(self.original_skills) > 0) or (self.ai_skills and len(self.ai_skills) > 0):
            score += 20
        if self.educations.exists():
            score += 15
        if self.experiences.exists() or (self.total_experience and float(self.total_experience) > 0):
            score += 15
        if self.summary and len(self.summary.strip()) >= 10:
            score += 15
        if self.full_name and self.location:
            score += 10
        return min(100, score)

    @property
    def is_verified(self) -> bool:

        return self.user.is_verified if self.user else False

    @property
    def email_verified(self) -> bool:
        return self.user.is_verified if self.user else False

    @property
    def has_profile_photo(self):

        try:
            return bool(self.profile_photo and self.profile_photo.name and self.profile_photo.storage.exists(self.profile_photo.name))
        except Exception:
            return False

    @property
    def has_resume(self):
        try:
            return bool(self.resume and self.resume.name and self.resume.storage.exists(self.resume.name))
        except Exception:
            return False

    @property
    def resume_exists(self):
        return self.has_resume

    @property
    def resume_size_display(self):
        try:
            if self.has_resume:
                size = self.resume.size
                if size < 1024 * 1024:
                    return f"{round(size / 1024, 1)} KB"
                return f"{round(size / (1024 * 1024), 1)} MB"
        except Exception:
            pass
        return "Resume not available"

    @property
    def resume_file_url(self):
        try:
            if self.has_resume:
                return self.resume.url
        except Exception:
            pass
        return "#"

    @property
    def current_salary_lpa(self):
        return format_salary_lpa(self.current_salary)

    @property
    def expected_salary_lpa(self):
        return format_salary_lpa(self.expected_salary)
    
    # Resume Intelligence Engine fields
    original_file = models.FileField(upload_to='resumes/original/', null=True, blank=True)
    generated_resume = models.FileField(upload_to='resumes/generated/', null=True, blank=True)
    parsed_json = models.JSONField(default=dict, blank=True)
    current_version = models.IntegerField(default=1)
    ocr_engine = models.CharField(max_length=50, blank=True, null=True)
    ocr_confidence = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    resume_type = models.CharField(max_length=50, blank=True, null=True)
    resume_versions = models.JSONField(default=dict, blank=True)
    audit_logs = models.JSONField(default=list, blank=True)
    edited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='edited_profiles')
    edited_at = models.DateTimeField(null=True, blank=True)

    # Security and File Processing Audit fields
    original_filename = models.CharField(max_length=255, blank=True, null=True)
    secure_filename = models.CharField(max_length=255, blank=True, null=True)
    sha256 = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    mime_type = models.CharField(max_length=100, blank=True, null=True)
    scan_status = models.CharField(max_length=50, blank=True, null=True)
    scan_timestamp = models.DateTimeField(blank=True, null=True)
    parser_status = models.CharField(max_length=50, blank=True, null=True)
    preview_status = models.CharField(max_length=50, blank=True, null=True)

    # Immutable original resume fields
    raw_resume_text = models.TextField(blank=True, default="")
    original_experience_json = models.JSONField(default=list, blank=True)
    original_skills = models.JSONField(default=list, blank=True)
    original_summary = models.TextField(blank=True, default="")

    # AI improved fields
    ai_summary = models.TextField(blank=True, default="")
    ai_skills = models.JSONField(default=list, blank=True)
    ai_experience_rewrite = models.JSONField(default=list, blank=True)

    @property
    def ats_score_badge_class(self):
        score = self.ats_score
        if score >= 90:
            return "bg-success text-white"
        elif score >= 75:
            return "bg-primary text-white"
        elif score >= 60:
            return "bg-warning text-dark"
        else:
            return "bg-danger text-white"

    class Meta:
        verbose_name = _('candidate profile')
        verbose_name_plural = _('candidate profiles')

    def __str__(self):
        return self.full_name or self.user.email

    def save(self, *args, **kwargs):
        version_str = str(self.current_version)
        if self.resume_versions and version_str in self.resume_versions:
            version_data = self.resume_versions[version_str].get("data", {})
            if "personal_info" not in version_data:
                version_data["personal_info"] = {}
            
            version_data["personal_info"]["name"] = self.full_name
            version_data["personal_info"]["current_company"] = self.current_company
            version_data["personal_info"]["current_designation"] = self.current_designation
            try:
                version_data["personal_info"]["total_experience"] = float(self.total_experience) if self.total_experience is not None else 0.0
            except Exception:
                pass
            try:
                version_data["personal_info"]["current_salary"] = float(self.current_salary) / 100000.0 if self.current_salary is not None else 0.0
                version_data["personal_info"]["expected_salary"] = float(self.expected_salary) / 100000.0 if self.expected_salary is not None else 0.0
            except Exception:
                pass
            version_data["personal_info"]["location"] = self.location
            version_data["summary"] = self.summary
            
            self.resume_versions[version_str]["data"] = version_data
            self.parsed_json = version_data

        super().save(*args, **kwargs)

class DuplicateResumeLog(BaseAppModel):
    email = models.EmailField(db_index=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    filename = models.CharField(max_length=255)
    action_taken = models.CharField(max_length=50, choices=[('SKIPPED', 'Skipped'), ('UPDATED', 'Updated')])
    
    class Meta:
        ordering = ['-created_at']

class CandidateSkill(BaseAppModel):
    """
    Skills possessed by a Candidate.
    """
    profile = models.ForeignKey(CandidateProfile, on_delete=models.CASCADE, related_name='skills')
    skill_name = models.CharField(max_length=100, db_index=True)
    years_of_experience = models.DecimalField(max_digits=4, decimal_places=1, default=0.0)
    proficiency = models.CharField(max_length=20, choices=[
        ('BEGINNER', 'Beginner'),
        ('INTERMEDIATE', 'Intermediate'),
        ('EXPERT', 'Expert'),
    ], default='INTERMEDIATE')

    class Meta:
        unique_together = ('profile', 'skill_name')
        verbose_name = _('candidate skill')
        verbose_name_plural = _('candidate skills')

class Experience(BaseAppModel):
    """
    Work experience entries for a Candidate.
    """
    profile = models.ForeignKey(CandidateProfile, on_delete=models.CASCADE, related_name='experiences')
    company_name = models.CharField(max_length=255)
    designation = models.CharField(max_length=255)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['-start_date']
        verbose_name = _('experience')
        verbose_name_plural = _('experiences')

class Education(BaseAppModel):
    """
    Educational background for a Candidate.
    """
    profile = models.ForeignKey(CandidateProfile, on_delete=models.CASCADE, related_name='educations')
    institution = models.CharField(max_length=255)
    degree = models.CharField(max_length=255)
    field_of_study = models.CharField(max_length=255, blank=True, null=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    percentage_or_cgpa = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        ordering = ['-end_date']
        verbose_name = _('education')
        verbose_name_plural = _('educations')

class Project(BaseAppModel):
    """
    Projects completed by a Candidate.
    """
    profile = models.ForeignKey(CandidateProfile, on_delete=models.CASCADE, related_name='projects')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    link = models.URLField(blank=True, null=True)

    class Meta:
        verbose_name = _('project')
        verbose_name_plural = _('projects')

class Certification(BaseAppModel):
    """
    Certifications earned by a Candidate.
    """
    profile = models.ForeignKey(CandidateProfile, on_delete=models.CASCADE, related_name='certifications')
    name = models.CharField(max_length=255)
    issuing_organization = models.CharField(max_length=255, blank=True, null=True)
    issue_date = models.DateField(null=True, blank=True)

class SavedJob(BaseAppModel):
    """
    Candidate Saved Jobs model.
    """
    candidate = models.ForeignKey(CandidateProfile, on_delete=models.CASCADE, related_name='saved_jobs')
    job = models.ForeignKey('jobs.Job', on_delete=models.CASCADE, related_name='saved_by_candidates')

    class Meta:
        unique_together = ('candidate', 'job')
        verbose_name = _('saved job')
        verbose_name_plural = _('saved jobs')

    def __str__(self):
        return f"{self.candidate.user.email} saved {self.job.title}"


from django.db.models.signals import pre_save
from django.dispatch import receiver

@receiver(pre_save, sender=SavedJob)
@receiver(pre_save, sender=CandidateProfile)
@receiver(pre_save, sender=Experience)
@receiver(pre_save, sender=Education)
@receiver(pre_save, sender=Project)
@receiver(pre_save, sender=Certification)
@receiver(pre_save, sender=CandidateSkill)
@receiver(pre_save, sender=DuplicateResumeLog)
def pre_save_sanitize_handler(sender, instance, **kwargs):
    from apps.candidates.utils import sanitize_text, sanitize_recursive
    import django.db.models as django_models
    for field in instance._meta.fields:
        val = getattr(instance, field.name)
        if val is not None:
            if isinstance(field, (django_models.CharField, django_models.TextField)):
                path = f"{instance.__class__.__name__}.{field.name}"
                sanitized = sanitize_text(val, path, print_on_nul=True)
                setattr(instance, field.name, sanitized)
            elif isinstance(field, django_models.JSONField):
                path = f"{instance.__class__.__name__}.{field.name}"
                sanitized = sanitize_recursive(val, path)
                setattr(instance, field.name, sanitized)


@receiver(pre_save, sender=settings.AUTH_USER_MODEL)
def pre_save_sanitize_user_handler(sender, instance, **kwargs):
    from apps.candidates.utils import sanitize_text
    import django.db.models as django_models
    for field in instance._meta.fields:
        val = getattr(instance, field.name)
        if val is not None:
            if isinstance(field, (django_models.CharField, django_models.TextField)):
                path = f"{instance.__class__.__name__}.{field.name}"
                sanitized = sanitize_text(val, path, print_on_nul=True)
                setattr(instance, field.name, sanitized)
