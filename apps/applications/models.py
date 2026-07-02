from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseAppModel
from apps.jobs.models import Job
from apps.candidates.models import CandidateProfile

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
