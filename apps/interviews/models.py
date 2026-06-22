from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseAppModel
from apps.applications.models import Application
from django.conf import settings

class Interview(BaseAppModel):
    """
    Interview scheduling and details.
    """
    class InterviewType(models.TextChoices):
        TELEPHONIC = "TELEPHONIC", _("Telephonic")
        VIDEO = "VIDEO", _("Video")
        IN_PERSON = "IN_PERSON", _("In-Person")
        TECHNICAL_ASSESSMENT = "TECHNICAL_ASSESSMENT", _("Technical Assessment")

    class InterviewStatus(models.TextChoices):
        SCHEDULED = "SCHEDULED", _("Scheduled")
        COMPLETED = "COMPLETED", _("Completed")
        CANCELLED = "CANCELLED", _("Cancelled")
        RESCHEDULED = "RESCHEDULED", _("Rescheduled")

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='interviews')
    interviewers = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='interviews_conducted')
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField()
    interview_type = models.CharField(max_length=30, choices=InterviewType.choices, default=InterviewType.VIDEO)
    status = models.CharField(max_length=20, choices=InterviewStatus.choices, default=InterviewStatus.SCHEDULED)
    meeting_link = models.URLField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    round = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. Technical Round 1")
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _('interview')
        verbose_name_plural = _('interviews')
        ordering = ['-start_time']

    def __str__(self):
        return f"Interview for {self.application.candidate.user.email}"

class InterviewFeedback(BaseAppModel):
    """
    Feedback from an interviewer.
    """
    interview = models.ForeignKey(Interview, on_delete=models.CASCADE, related_name='feedbacks')
    interviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(help_text="Rating from 1 to 5")
    comments = models.TextField()
    recommendation = models.CharField(max_length=20, choices=[
        ('STRONG_HIRE', 'Strong Hire'),
        ('HIRE', 'Hire'),
        ('NO_HIRE', 'No Hire'),
        ('STRONG_NO_HIRE', 'Strong No Hire'),
    ])

    class Meta:
        unique_together = ('interview', 'interviewer')
        verbose_name = _('interview feedback')
        verbose_name_plural = _('interview feedbacks')
