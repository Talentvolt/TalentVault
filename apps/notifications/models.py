from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseAppModel
from django.conf import settings

class Notification(BaseAppModel):
    """
    In-app notifications for users.
    """
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=50, choices=[
        ('APPLICATION_STATUS', 'Application Status Update'),
        ('INTERVIEW_SCHEDULED', 'Interview Scheduled'),
        ('NEW_JOB', 'New Job Matching Your Skills'),
        ('SYSTEM', 'System Notification'),
    ])
    is_read = models.BooleanField(default=False, db_index=True)
    link = models.URLField(blank=True, null=True, help_text="Optional link for notification action")

    class Meta:
        verbose_name = _('notification')
        verbose_name_plural = _('notifications')
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.recipient.email}: {self.title}"

class EmailLog(BaseAppModel):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='sent_emails')
    recipient_email = models.EmailField()
    subject = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(max_length=50, default='SENT')
    
    class Meta:
        ordering = ['-created_at']
