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
        validators=[FileExtensionValidator(allowed_extensions=['pdf'])],
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

    # Candidate Workspace & Taxonomy Classification Fields
    department = models.CharField(max_length=150, blank=True, default='', db_index=True)
    industry = models.CharField(max_length=150, blank=True, default='', db_index=True)
    role_name = models.CharField(max_length=150, blank=True, default='', db_index=True)
    employment_type = models.CharField(
        max_length=50, 
        default='FULL_TIME', 
        choices=[
            ('FULL_TIME', 'Full Time'), 
            ('PART_TIME', 'Part Time'), 
            ('CONTRACT', 'Contract'), 
            ('FREELANCE', 'Freelance'), 
            ('INTERNSHIP', 'Internship'), 
            ('TEMPORARY', 'Temporary')
        ], 
        db_index=True
    )
    willing_to_relocate = models.BooleanField(default=True, db_index=True)
    work_permit_countries = models.JSONField(default=list, blank=True)
    
    # Candidate Status & Workspace Flagging
    candidate_status = models.CharField(
        max_length=50, 
        default='ACTIVE', 
        choices=[
            ('ACTIVE', 'Active'), 
            ('PASSIVE', 'Passive'), 
            ('OPEN_TO_WORK', 'Open to Work'), 
            ('SHORTLISTED', 'Shortlisted'), 
            ('SAVED_FOR_LATER', 'Saved for Later'), 
            ('HIRED', 'Hired'), 
            ('REJECTED', 'Rejected')
        ], 
        db_index=True
    )
    is_shortlisted = models.BooleanField(default=False, db_index=True)
    is_saved_for_later = models.BooleanField(default=False, db_index=True)

    # Diversity & Affirmative Hiring (Explicit Self-Declared Candidate Data Only)
    gender = models.CharField(
        max_length=30, 
        default='NOT_SPECIFIED', 
        choices=[
            ('NOT_SPECIFIED', 'Not Specified'), 
            ('MALE', 'Male'), 
            ('FEMALE', 'Female'), 
            ('OTHER', 'Other')
        ], 
        db_index=True
    )
    has_career_break = models.BooleanField(default=False, db_index=True)
    career_break_duration_months = models.PositiveIntegerField(default=0)
    is_differently_abled = models.BooleanField(default=False, db_index=True)
    disability_category = models.CharField(max_length=100, blank=True, default='')
    has_defence_background = models.BooleanField(default=False, db_index=True)
    defence_branch = models.CharField(max_length=100, blank=True, default='')

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
        if not self.profile_photo or not self.profile_photo.name:
            return False
        try:
            return self.profile_photo.storage.exists(self.profile_photo.name)
        except Exception:
            return False

    @property
    def has_resume(self):
        return bool(self.resume and self.resume.name)

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
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='uploaded_candidates')

    @property
    def uploader_name(self):
        user_obj = self.uploaded_by or self.created_by
        if not user_obj:
            app = self.job_applications.filter(created_by__isnull=False).first()
            if app and app.created_by:
                user_obj = app.created_by
            elif self.edited_by:
                user_obj = self.edited_by

        if user_obj:
            full_name = user_obj.get_full_name().strip()
            if full_name:
                return full_name
            if getattr(user_obj, 'email', None):
                email_name = user_obj.email.split('@')[0]
                clean_name = re.sub(r'[._\d+]+', ' ', email_name).strip().title()
                if clean_name and len(clean_name) >= 3:
                    return clean_name
                return user_obj.email
            return getattr(user_obj, 'username', None)
        return None

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

    @property
    def normalized_linkedin_url(self):
        from utils.url_helpers import normalize_external_url
        return normalize_external_url(self.linkedin_url)

    @property
    def normalized_portfolio_url(self):
        from utils.url_helpers import normalize_external_url
        return normalize_external_url(self.portfolio_url)

    def save(self, *args, **kwargs):
        from utils.url_helpers import normalize_external_url
        if self.linkedin_url:
            self.linkedin_url = normalize_external_url(self.linkedin_url)
        if self.portfolio_url:
            self.portfolio_url = normalize_external_url(self.portfolio_url)

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
    class QualificationLevel(models.TextChoices):
        UG = 'UG', _('Undergraduate (UG / Bachelor\'s)')
        PG = 'PG', _('Postgraduate (PG / Master\'s)')
        DOCTORATE = 'DOCTORATE', _('Doctorate / Ph.D')
        DIPLOMA = 'DIPLOMA', _('Diploma / Vocational')
        CERTIFICATE = 'CERTIFICATE', _('Certificate')
        OTHER = 'OTHER', _('Other Qualification')

    class EducationType(models.TextChoices):
        FULL_TIME = 'FULL_TIME', _('Full Time')
        PART_TIME = 'PART_TIME', _('Part Time')
        CORRESPONDENCE = 'CORRESPONDENCE', _('Correspondence / Distance')
        ONLINE = 'ONLINE', _('Online Learning')
        ANY = 'ANY', _('Any / Other')

    profile = models.ForeignKey(CandidateProfile, on_delete=models.CASCADE, related_name='educations')
    institution = models.CharField(max_length=255, db_index=True)
    degree = models.CharField(max_length=255, db_index=True)
    field_of_study = models.CharField(max_length=255, blank=True, null=True)
    specialization = models.CharField(max_length=255, blank=True, default='')
    qualification_level = models.CharField(
        max_length=30, 
        choices=QualificationLevel.choices, 
        default=QualificationLevel.UG, 
        db_index=True
    )
    education_type = models.CharField(
        max_length=30, 
        choices=EducationType.choices, 
        default=EducationType.FULL_TIME, 
        db_index=True
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    passing_year = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    is_pursuing = models.BooleanField(default=False)
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

    @property
    def normalized_link(self):
        from utils.url_helpers import normalize_external_url
        return normalize_external_url(self.link)

    def save(self, *args, **kwargs):
        from utils.url_helpers import normalize_external_url
        if self.link:
            self.link = normalize_external_url(self.link)
        super().save(*args, **kwargs)

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


class TaxonomySkill(BaseAppModel):
    """
    Universal Centralized Taxonomy for Skills, Tools, Technologies & Domains.
    """
    CATEGORY_CHOICES = [
        ('TECHNICAL', 'Technical Skill'),
        ('FUNCTIONAL', 'Functional / Domain Skill'),
        ('SOFT', 'Soft Skill'),
        ('TOOL', 'Tool / Technology'),
        ('DOMAIN', 'Industry / Domain'),
        ('CERTIFICATION', 'Certification'),
    ]

    name = models.CharField(max_length=150, db_index=True)
    canonical_name = models.CharField(max_length=150, db_index=True)
    normalized_name = models.CharField(max_length=150, db_index=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='TECHNICAL', db_index=True)
    domain = models.CharField(max_length=100, blank=True, db_index=True)
    aliases = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    weight = models.FloatField(default=1.0)

    class Meta:
        ordering = ['canonical_name']
        verbose_name = _('taxonomy skill')
        verbose_name_plural = _('taxonomy skills')
        indexes = [
            models.Index(fields=['normalized_name', 'is_active']),
            models.Index(fields=['canonical_name', 'is_active']),
            models.Index(fields=['domain', 'category']),
        ]

    def save(self, *args, **kwargs):
        if not self.normalized_name:
            self.normalized_name = (self.canonical_name or self.name).strip().lower()
        if not self.canonical_name:
            self.canonical_name = self.name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.canonical_name} ({self.get_category_display()})"


class TaxonomyDesignation(BaseAppModel):
    """
    Universal Centralized Taxonomy for Job Titles & Designations across all domains.
    """
    SENIORITY_CHOICES = [
        ('ENTRY', 'Entry Level / Fresher'),
        ('JUNIOR', 'Junior / Associate'),
        ('MID', 'Mid-Level / Specialist'),
        ('SENIOR', 'Senior / Lead'),
        ('MANAGER', 'Manager / Head'),
        ('DIRECTOR', 'Director / VP'),
        ('EXECUTIVE', 'C-Level / Executive'),
    ]

    name = models.CharField(max_length=150, db_index=True)
    canonical_name = models.CharField(max_length=150, db_index=True)
    normalized_name = models.CharField(max_length=150, db_index=True)
    department = models.CharField(max_length=100, blank=True, db_index=True)
    industry = models.CharField(max_length=100, blank=True, db_index=True)
    seniority = models.CharField(max_length=50, choices=SENIORITY_CHOICES, default='MID', db_index=True)
    aliases = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    weight = models.FloatField(default=1.0)

    class Meta:
        ordering = ['canonical_name']
        verbose_name = _('taxonomy designation')
        verbose_name_plural = _('taxonomy designations')
        indexes = [
            models.Index(fields=['normalized_name', 'is_active']),
            models.Index(fields=['canonical_name', 'is_active']),
            models.Index(fields=['department', 'industry']),
            models.Index(fields=['seniority']),
        ]

    def save(self, *args, **kwargs):
        if not self.normalized_name:
            self.normalized_name = (self.canonical_name or self.name).strip().lower()
        if not self.canonical_name:
            self.canonical_name = self.name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.canonical_name} ({self.department or self.industry or 'General'})"


class RoleRelation(BaseAppModel):
    """
    Dynamic Graph Relationship between Designations (Seniority, Related, Functional Equivalents).
    """
    RELATION_TYPE_CHOICES = [
        ('SENIORITY_VARIANT', 'Seniority Variant'),
        ('RELATED_ROLE', 'Related Role'),
        ('FUNCTIONAL_EQUIVALENT', 'Functional Equivalent'),
        ('PARENT_ROLE', 'Parent Role'),
        ('CHILD_ROLE', 'Child Role'),
        ('ADJACENT_ROLE', 'Adjacent Role'),
        ('ALIAS', 'Alias'),
    ]

    source_role = models.ForeignKey(TaxonomyDesignation, on_delete=models.CASCADE, related_name='outgoing_relations')
    target_role = models.ForeignKey(TaxonomyDesignation, on_delete=models.CASCADE, related_name='incoming_relations')
    relation_type = models.CharField(max_length=50, choices=RELATION_TYPE_CHOICES, default='RELATED_ROLE', db_index=True)
    weight = models.FloatField(default=0.85, db_index=True)
    is_bidirectional = models.BooleanField(default=True)

    class Meta:
        unique_together = ('source_role', 'target_role', 'relation_type')
        verbose_name = _('role relationship')
        verbose_name_plural = _('role relationships')
        indexes = [
            models.Index(fields=['relation_type', 'weight']),
        ]

    def __str__(self):
        return f"{self.source_role.canonical_name} -> {self.target_role.canonical_name} ({self.get_relation_type_display()}: {self.weight})"


class RoleSkillRelation(BaseAppModel):
    """
    Dynamic Graph Relationship between Job Designations and relevant Skills / Tools.
    """
    RELATION_TYPE_CHOICES = [
        ('PRIMARY_SKILL', 'Primary Core Skill'),
        ('SECONDARY_SKILL', 'Secondary Skill'),
        ('SUPPORTING_SKILL', 'Supporting Skill'),
        ('DOMAIN_SKILL', 'Domain Skill'),
        ('TOOL', 'Tool / Technology'),
    ]

    role = models.ForeignKey(TaxonomyDesignation, on_delete=models.CASCADE, related_name='skill_relations')
    skill = models.ForeignKey(TaxonomySkill, on_delete=models.CASCADE, related_name='role_relations')
    relation_type = models.CharField(max_length=50, choices=RELATION_TYPE_CHOICES, default='PRIMARY_SKILL', db_index=True)
    weight = models.FloatField(default=0.90, db_index=True)

    class Meta:
        unique_together = ('role', 'skill', 'relation_type')
        verbose_name = _('role skill relationship')
        verbose_name_plural = _('role skill relationships')
        indexes = [
            models.Index(fields=['relation_type', 'weight']),
        ]

    def __str__(self):
        return f"{self.role.canonical_name} <-> {self.skill.canonical_name} ({self.get_relation_type_display()}: {self.weight})"


class CandidateTag(BaseAppModel):
    """
    Normalized, Source-Attributed & Confidence-Scored Search Tag for Candidates.
    """
    TAG_TYPE_CHOICES = [
        ('DESIGNATION', 'Designation / Role'),
        ('PREVIOUS_DESIGNATION', 'Previous Designation'),
        ('SKILL', 'Skill'),
        ('TOOL', 'Tool / Technology'),
        ('DOMAIN', 'Domain / Function'),
        ('INDUSTRY', 'Industry'),
        ('CERTIFICATION', 'Certification'),
        ('EDUCATION', 'Education / Degree'),
        ('INFERRED_KEYWORD', 'Inferred Keyword'),
    ]

    SOURCE_CHOICES = [
        ('resume_parser', 'Resume Parser'),
        ('manual', 'Manual Entry'),
        ('recruiter', 'Recruiter Tagged'),
        ('job_application', 'Job Application'),
        ('AI', 'AI Inferred'),
        ('taxonomy', 'Taxonomy Mapped'),
        ('inferred', 'Inferred Rule'),
    ]

    profile = models.ForeignKey(CandidateProfile, on_delete=models.CASCADE, related_name='candidate_tags')
    name = models.CharField(max_length=150, db_index=True)
    canonical_name = models.CharField(max_length=150, db_index=True)
    normalized_name = models.CharField(max_length=150, db_index=True)
    tag_type = models.CharField(max_length=50, choices=TAG_TYPE_CHOICES, default='SKILL', db_index=True)
    confidence = models.FloatField(default=0.90, db_index=True)
    source = models.CharField(max_length=50, choices=SOURCE_CHOICES, default='resume_parser', db_index=True)
    is_current = models.BooleanField(default=False)
    years_of_experience = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)

    class Meta:
        unique_together = ('profile', 'normalized_name', 'tag_type')
        verbose_name = _('candidate tag')
        verbose_name_plural = _('candidate tags')
        indexes = [
            models.Index(fields=['normalized_name', 'tag_type']),
            models.Index(fields=['canonical_name']),
            models.Index(fields=['confidence', 'source']),
            models.Index(fields=['profile', 'tag_type']),
        ]

    def save(self, *args, **kwargs):
        if not self.normalized_name:
            self.normalized_name = (self.canonical_name or self.name).strip().lower()
        if not self.canonical_name:
            self.canonical_name = self.name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.profile.full_name or self.profile.id} - {self.name} ({self.get_tag_type_display()}, conf: {self.confidence})"


class SavedCandidateSearch(BaseAppModel):
    """
    Saved Recruiter Searches with full filters, tags, and boolean logic.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_candidate_searches')
    name = models.CharField(max_length=255)
    search_query = models.CharField(max_length=255, blank=True)
    selected_tags = models.JSONField(default=list, blank=True)
    filters_payload = models.JSONField(default=dict, blank=True)
    results_count = models.IntegerField(default=0)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('saved candidate search')
        verbose_name_plural = _('saved candidate searches')

    def __str__(self):
        return f"{self.name} ({self.user.email})"


class RecentCandidateSearch(BaseAppModel):
    """
    Recent Search History for Recruiters to quickly revisit searches.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='recent_candidate_searches')
    search_query = models.CharField(max_length=255, blank=True)
    selected_tags = models.JSONField(default=list, blank=True)
    filters_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('recent candidate search')
        verbose_name_plural = _('recent candidate searches')

    def __str__(self):
        return f"{self.user.email} searched '{self.search_query}'"


class BulkResumeJob(BaseAppModel):
    """
    Asynchronous bulk resume parsing job tracker.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending')
        VALIDATING = 'VALIDATING', _('Validating')
        PROCESSING = 'PROCESSING', _('Processing')
        COMPLETED = 'COMPLETED', _('Completed')
        FAILED = 'FAILED', _('Failed')
        CANCELLED = 'CANCELLED', _('Cancelled')

    job_number = models.CharField(max_length=50, unique=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='bulk_resume_jobs')
    job = models.ForeignKey('jobs.Job', on_delete=models.SET_NULL, null=True, blank=True, related_name='bulk_resume_jobs')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    
    zip_filename = models.CharField(max_length=255, blank=True, default='')
    excel_filename = models.CharField(max_length=255, blank=True, default='')
    storage_dir = models.CharField(max_length=500, blank=True, default='')
    
    overwrite = models.BooleanField(default=False)
    
    total_files = models.PositiveIntegerField(default=0)
    processed_files = models.PositiveIntegerField(default=0)
    successful_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    
    current_file = models.CharField(max_length=255, blank=True, default='')
    validation_summary = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default='')
    
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('bulk resume job')
        verbose_name_plural = _('bulk resume jobs')

    def __str__(self):
        return f"Bulk Job {self.job_number} ({self.status})"

    @property
    def progress_percentage(self):
        if self.total_files == 0:
            return 0
        return min(100, int((self.processed_files / self.total_files) * 100))


class BulkResumeItem(BaseAppModel):
    """
    Individual file item inside a bulk resume parsing job.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending')
        PROCESSING = 'PROCESSING', _('Processing')
        COMPLETED = 'COMPLETED', _('Completed')
        UPDATED = 'UPDATED', _('Updated')
        SKIPPED = 'SKIPPED', _('Skipped')
        FAILED = 'FAILED', _('Failed')

    job = models.ForeignKey(BulkResumeJob, on_delete=models.CASCADE, related_name='items')
    filename = models.CharField(max_length=255, db_index=True)
    file_path = models.CharField(max_length=500, blank=True, default='')
    file_size = models.PositiveIntegerField(default=0)
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    action_taken = models.CharField(max_length=50, blank=True, default='')
    reason = models.TextField(blank=True, default='')
    
    candidate = models.ForeignKey(CandidateProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='bulk_parsed_items')
    candidate_name = models.CharField(max_length=255, blank=True, default='')
    candidate_email = models.CharField(max_length=255, blank=True, default='')
    candidate_phone = models.CharField(max_length=50, blank=True, default='')
    
    excel_metadata = models.JSONField(default=dict, blank=True)
    parsed_data = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = _('bulk resume item')
        verbose_name_plural = _('bulk resume items')

    def __str__(self):
        return f"{self.job.job_number} - {self.filename} ({self.status})"


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
@receiver(pre_save, sender=TaxonomySkill)
@receiver(pre_save, sender=TaxonomyDesignation)
@receiver(pre_save, sender=RoleRelation)
@receiver(pre_save, sender=RoleSkillRelation)
@receiver(pre_save, sender=CandidateTag)
@receiver(pre_save, sender=SavedCandidateSearch)
@receiver(pre_save, sender=RecentCandidateSearch)
@receiver(pre_save, sender=BulkResumeJob)
@receiver(pre_save, sender=BulkResumeItem)
def pre_save_sanitize_handler(sender, instance, **kwargs):
    from apps.candidates.utils import sanitize_text, sanitize_recursive
    import django.db.models as django_models
    for field in instance._meta.fields:
        if isinstance(field, (django_models.CharField, django_models.TextField)):
            val = getattr(instance, field.name, None)
            if val is not None:
                path = f"{instance.__class__.__name__}.{field.name}"
                sanitized = sanitize_text(val, path, print_on_nul=True)
                setattr(instance, field.name, sanitized)
        elif isinstance(field, django_models.JSONField):
            val = getattr(instance, field.name, None)
            if val is not None:
                path = f"{instance.__class__.__name__}.{field.name}"
                sanitized = sanitize_recursive(val, path)
                setattr(instance, field.name, sanitized)


@receiver(pre_save, sender=settings.AUTH_USER_MODEL)
def pre_save_sanitize_user_handler(sender, instance, **kwargs):
    from apps.candidates.utils import sanitize_text
    import django.db.models as django_models
    for field in instance._meta.fields:
        if isinstance(field, (django_models.CharField, django_models.TextField)):
            val = getattr(instance, field.name, None)
            if val is not None:
                path = f"{instance.__class__.__name__}.{field.name}"
                sanitized = sanitize_text(val, path, print_on_nul=True)
                setattr(instance, field.name, sanitized)

