from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseAppModel
from django.conf import settings
import uuid

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


class EmailTemplate(BaseAppModel):
    """
    Professional ATS Email Templates for recruiters and clients.
    """
    CATEGORY_CHOICES = [
        ('CLIENT', 'Client'),
        ('CANDIDATE', 'Candidate'),
    ]

    name = models.CharField(max_length=255, unique=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='CLIENT')
    subject = models.CharField(max_length=255)
    body = models.TextField()
    is_system = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_email_templates')

    class Meta:
        verbose_name = _('email template')
        verbose_name_plural = _('email templates')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.category})"


class EmailLog(BaseAppModel):
    """
    Tracks sent, queued, failed, opened, and clicked emails with tracking UUIDs and metadata.
    """
    STATUS_CHOICES = [
        ('QUEUED', 'Queued'),
        ('SENDING', 'Sending'),
        ('SENT', 'Sent'),
        ('FAILED', 'Failed'),
        ('OPENED', 'Opened'),
        ('CLICKED', 'Clicked'),
    ]

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='sent_emails')
    recipient_email = models.EmailField()
    cc = models.TextField(blank=True, null=True, help_text="Comma or semicolon separated CC emails")
    bcc = models.TextField(blank=True, null=True, help_text="Comma or semicolon separated BCC emails")
    subject = models.CharField(max_length=255)
    body = models.TextField()
    template_name = models.CharField(max_length=255, blank=True, null=True)
    candidate_ids = models.JSONField(blank=True, null=True, help_text="List of candidate profile IDs associated with this email")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='SENT', db_index=True)
    error_message = models.TextField(blank=True, null=True)
    
    # Tracking
    tracking_uuid = models.UUIDField(default=uuid.uuid4, db_index=True)
    open_count = models.IntegerField(default=0)
    click_count = models.IntegerField(default=0)
    last_opened_at = models.DateTimeField(null=True, blank=True)
    last_clicked_at = models.DateTimeField(null=True, blank=True)
    
    # Attachments
    has_attachment = models.BooleanField(default=False)
    attachment_names = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = _('email log')
        verbose_name_plural = _('email logs')
        ordering = ['-created_at']

    def __str__(self):
        return f"Email to {self.recipient_email} - {self.subject} [{self.status}]"


class RecruiterEmailAccount(BaseAppModel):
    """
    Recruiter's connected email accounts (Gmail, Google Workspace, Outlook, SMTP).
    """
    ACCOUNT_TYPE_CHOICES = [
        ('OAUTH', 'OAuth (Google / Microsoft)'),
        ('SMTP', 'SMTP / IMAP'),
    ]
    PROVIDER_CHOICES = [
        ('GMAIL', 'Gmail / Google Workspace'),
        ('OUTLOOK', 'Microsoft Outlook'),
        ('SMTP', 'Custom SMTP'),
    ]

    recruiter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='email_accounts')
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES, default='SMTP')
    provider = models.CharField(max_length=30, choices=PROVIDER_CHOICES, default='SMTP')
    email_address = models.EmailField()
    is_verified = models.BooleanField(default=False)
    is_default = models.BooleanField(default=False)
    
    # SMTP settings
    smtp_host = models.CharField(max_length=255, blank=True, null=True)
    smtp_port = models.IntegerField(default=587, blank=True, null=True)
    smtp_username = models.CharField(max_length=255, blank=True, null=True)
    smtp_password = models.CharField(max_length=255, blank=True, null=True)
    use_tls = models.BooleanField(default=True)
    use_ssl = models.BooleanField(default=False)
    
    # OAuth tokens
    oauth_access_token = models.TextField(blank=True, null=True)
    oauth_refresh_token = models.TextField(blank=True, null=True)
    token_expires_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = _('recruiter email account')
        verbose_name_plural = _('recruiter email accounts')
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f"{self.email_address} ({self.provider}) - {self.recruiter.email}"


class CandidateMessage(BaseAppModel):
    """
    Direct recruiter-candidate messages similar to Internshala messaging.
    """
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_candidate_messages')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_candidate_messages')
    candidate = models.ForeignKey('candidates.CandidateProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='messages')
    message_text = models.TextField(blank=True)
    attachment = models.FileField(upload_to='candidate_messages/attachments/', null=True, blank=True)
    attachment_name = models.CharField(max_length=255, blank=True, null=True)
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('candidate message')
        verbose_name_plural = _('candidate messages')
        ordering = ['created_at']

    def __str__(self):
        return f"Message from {self.sender.email} to {self.recipient.email}: {self.message_text[:30]}"
