from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseAppModel
from apps.jobs.models import Job
from apps.candidates.models import CandidateProfile

def format_ctc_lpa(value):
    if value is None or value == "":
        return "N/A"
    try:
        val = float(value)
        if val <= 0:
            return "N/A"
        if val >= 1000:
            val = val / 100000.0
        if val == int(val):
            return f"₹{int(val)} LPA"
        else:
            s = f"{val:.2f}"
            if s.endswith('.00'):
                return f"₹{int(val)} LPA"
            elif s.endswith('0'):
                return f"₹{s[:-1]} LPA"
            return f"₹{s} LPA"
    except (ValueError, TypeError):
        return str(value)

class Application(BaseAppModel):
    """
    Applicant Tracking System (ATS) - Application model.
    """
    class ApplicationStage(models.TextChoices):
        OPEN = "OPEN", _("Open")
        SYSTEM_SELECTED = "SYSTEM_SELECTED", _("System Selected")
        SYSTEM_REJECTED = "SYSTEM_REJECTED", _("System Rejected")
        SYSTEM_SUBMITTED = "SYSTEM_SUBMITTED", _("System Submitted")
        AUTOMATION_SKIPPED = "AUTOMATION_SKIPPED", _("Automation Skipped")
        SCREENING_FEEDBACK_PENDING = "SCREENING_FEEDBACK_PENDING", _("Screening Feedback Pending")
        SCREENING_SELECT = "SCREENING_SELECT", _("Screening Select")
        SCREENING_REJECT = "SCREENING_REJECT", _("Screening Reject")
        INTERVIEW_SCHEDULE = "INTERVIEW_SCHEDULE", _("Interview Schedule")
        INTERVIEW_IN_PROCESS = "INTERVIEW_IN_PROCESS", _("Interview In Process")
        INTERVIEW_SELECT = "INTERVIEW_SELECT", _("Interview Select")
        INTERVIEW_REJECT = "INTERVIEW_REJECT", _("Interview Reject")
        DOCUMENTATION_STAGE = "DOCUMENTATION_STAGE", _("Documentation Stage")
        NEGOTIATION_STAGE = "NEGOTIATION_STAGE", _("Negotiation Stage")
        OFFER_STAGE = "OFFER_STAGE", _("Offer Stage")
        ACCEPTED = "ACCEPTED", _("Accepted")
        JOINING_CONFIRMATION_REQUESTED = "JOINING_CONFIRMATION_REQUESTED", _("Joining Confirmation Requested")
        JOINING_CONFIRMATION_RECEIVED = "JOINING_CONFIRMATION_RECEIVED", _("Joining Confirmation Received")
        JOINED = "JOINED", _("Joined")
        DROPOUT = "DROPOUT", _("Dropout")
        CLIENT_DUPLICATE = "CLIENT_DUPLICATE", _("Client Duplicate")
        HOLD = "HOLD", _("Hold")
        RESIGNED = "RESIGNED", _("Resigned")
        RELIEVED = "RELIEVED", _("Relieved")

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='applications')
    candidate = models.ForeignKey(CandidateProfile, on_delete=models.CASCADE, related_name='job_applications')
    recruiter = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recruiter_applications'
    )
    stage = models.CharField(
        max_length=40, 
        choices=ApplicationStage.choices, 
        default=ApplicationStage.OPEN,
        db_index=True
    )
    match_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0.0,
        help_text="Calculated match score percentage"
    )
    cover_letter = models.TextField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    in_pipeline = models.BooleanField(default=False, db_index=True)

    @property
    def candidate_status_display(self):
        if self.stage in [Application.ApplicationStage.OPEN, Application.ApplicationStage.SYSTEM_SUBMITTED]:
            return "Applied"
        elif self.stage in [Application.ApplicationStage.SCREENING_FEEDBACK_PENDING, Application.ApplicationStage.SYSTEM_SELECTED, Application.ApplicationStage.AUTOMATION_SKIPPED]:
            return "Under Review"
        elif self.stage in [Application.ApplicationStage.SCREENING_SELECT]:
            return "Shortlisted"
        elif self.stage in [Application.ApplicationStage.INTERVIEW_SCHEDULE, Application.ApplicationStage.INTERVIEW_IN_PROCESS]:
            return "Interview Scheduled"
        elif self.stage in [Application.ApplicationStage.INTERVIEW_SELECT, Application.ApplicationStage.ACCEPTED, Application.ApplicationStage.JOINED, Application.ApplicationStage.OFFER_STAGE, Application.ApplicationStage.DOCUMENTATION_STAGE, Application.ApplicationStage.NEGOTIATION_STAGE]:
            return "Selected"
        elif self.stage in [Application.ApplicationStage.SCREENING_REJECT, Application.ApplicationStage.INTERVIEW_REJECT, Application.ApplicationStage.SYSTEM_REJECTED, Application.ApplicationStage.DROPOUT]:
            return "Rejected"
        return "Under Review"

    @property
    def formatted_current_ctc(self):
        val = self.current_ctc if self.current_ctc is not None else (self.candidate.current_salary if self.candidate else None)
        return format_ctc_lpa(val)

    @property
    def formatted_expected_ctc(self):
        val = self.expected_ctc if self.expected_ctc is not None else (self.candidate.expected_salary if self.candidate else None)
        return format_ctc_lpa(val)

    @property
    def skills_list(self):
        if self.key_skills:
            if isinstance(self.key_skills, list):
                return self.key_skills
            elif isinstance(self.key_skills, str):
                return [s.strip() for s in self.key_skills.split(',') if s.strip()]
        if self.candidate and self.candidate.skills.exists():
            return [s.skill_name for s in self.candidate.skills.all()]
        return []

    # Application Snapshot Fields
    current_company = models.CharField(max_length=255, blank=True, null=True)
    current_designation = models.CharField(max_length=255, blank=True, null=True)
    total_experience = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    relevant_experience = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    current_ctc = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    expected_ctc = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notice_period = models.PositiveIntegerField(null=True, blank=True, help_text="Notice period in days")
    is_immediate_joiner = models.BooleanField(default=False)
    preferred_location = models.CharField(max_length=255, blank=True, null=True)
    current_location = models.CharField(max_length=255, blank=True, null=True)
    current_location_city = models.CharField(max_length=100, blank=True, null=True)
    current_location_state = models.CharField(max_length=100, blank=True, null=True)
    current_location_tier = models.CharField(max_length=20, blank=True, null=True)
    preferred_locations = models.JSONField(default=list, blank=True, null=True)
    preferred_locations_info = models.JSONField(default=list, blank=True, null=True)
    key_skills = models.JSONField(default=list, blank=True, null=True)
    preferred_work_mode = models.CharField(max_length=50, blank=True, null=True)
    mobile_number = models.CharField(max_length=20, blank=True, null=True)
    date_of_birth = models.DateField(null=True, blank=True)
    note_to_recruiter = models.TextField(max_length=500, blank=True, null=True)
    linkedin_url = models.URLField(max_length=500, blank=True, null=True)
    portfolio_url = models.URLField(max_length=500, blank=True, null=True)
    resume = models.FileField(upload_to='application_resumes/', null=True, blank=True)
    screening_answers = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ('job', 'candidate')
        verbose_name = _('application')
        verbose_name_plural = _('applications')
        ordering = ['-match_score', '-created_at']

    def __str__(self):
        return f"{self.candidate.user.email} -> {self.job.title}"

    @property
    def badge_class(self):
        stage_val = self.stage
        if stage_val == 'OPEN':
            return 'bg-primary text-white' # blue
        elif stage_val in ['SCREENING_SELECT', 'INTERVIEW_SELECT']:
            return 'bg-success text-white' # green
        elif stage_val in ['SCREENING_REJECT', 'INTERVIEW_REJECT', 'SYSTEM_REJECTED']:
            return 'bg-danger text-white' # red
        elif stage_val == 'INTERVIEW_SCHEDULE':
            return 'bg-warning text-dark' # yellow
        elif stage_val == 'OFFER_STAGE':
            return 'bg-purple text-white' # purple
        elif stage_val == 'ACCEPTED':
            return 'bg-teal text-white' # teal
        elif stage_val == 'JOINED':
            return 'bg-dark-green text-white' # dark green
        elif stage_val == 'DROPOUT':
            return 'bg-secondary text-white' # gray
        elif stage_val in ['SYSTEM_SELECTED', 'SYSTEM_SUBMITTED', 'INTERVIEW_IN_PROCESS', 'DOCUMENTATION_STAGE', 'NEGOTIATION_STAGE', 'JOINING_CONFIRMATION_REQUESTED', 'JOINING_CONFIRMATION_RECEIVED']:
            return 'bg-info text-dark'
        else:
            return 'bg-secondary text-white'

    @property
    def stage_color(self):
        stage_colors = {
            'OPEN': '#3b82f6',
            'SCREENING_SELECT': '#198754',
            'SCREENING_REJECT': '#dc3545',
            'INTERVIEW_SCHEDULE': '#ffc107',
            'INTERVIEW_SELECT': '#198754',
            'INTERVIEW_REJECT': '#dc3545',
            'OFFER_STAGE': '#6f42c1',
            'ACCEPTED': '#20c997',
            'JOINED': '#0f5132',
            'DROPOUT': '#6c757d',
        }
        return stage_colors.get(self.stage, '#cbd5e1')

    @property
    def ats_analysis(self):
        from services.candidate_matching_service import CandidateMatchingService
        return CandidateMatchingService.calculate_job_ats_score(self.candidate, self.job)


class ApplicationHistory(BaseAppModel):
    """
    Tracks stage transitions and notes for an application.
    """
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='history')
    from_stage = models.CharField(max_length=40, choices=Application.ApplicationStage.choices)
    to_stage = models.CharField(max_length=40, choices=Application.ApplicationStage.choices)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _('application history')
        verbose_name_plural = _('application histories')
        ordering = ['-created_at']
