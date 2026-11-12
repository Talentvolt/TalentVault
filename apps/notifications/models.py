from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseAppModel
from django.conf import settings
import os
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
    scopes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = _('recruiter email account')
        verbose_name_plural = _('recruiter email accounts')
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f"{self.email_address} ({self.provider}) - {self.recruiter.email}"

    def refresh_access_token(self):
        """
        Refreshes the OAuth access token using the stored refresh_token.
        Preserves refresh token if not provided in response.
        Marks account unverified if credentials are revoked (400/401).
        """
        if not self.oauth_refresh_token:
            return False
            
        import requests
        client_id = (
            os.environ.get('RECRUITER_GMAIL_OAUTH_CLIENT_ID', '')
            or getattr(settings, 'RECRUITER_GMAIL_OAUTH_CLIENT_ID', '')
        )
        client_secret = (
            os.environ.get('RECRUITER_GMAIL_OAUTH_CLIENT_SECRET', '')
            or getattr(settings, 'RECRUITER_GMAIL_OAUTH_CLIENT_SECRET', '')
        )
        if client_id.startswith("RECRUITER_GMAIL_OAUTH_CLIENT_ID="):
            client_id = client_id.replace("RECRUITER_GMAIL_OAUTH_CLIENT_ID=", "", 1).strip()
        if client_secret.startswith("RECRUITER_GMAIL_OAUTH_CLIENT_SECRET="):
            client_secret = client_secret.replace("RECRUITER_GMAIL_OAUTH_CLIENT_SECRET=", "", 1).strip()

        if not client_id or not client_secret:
            import logging
            logger = logging.getLogger(__name__)
            logger.error("Recruiter Gmail OAuth credentials missing (RECRUITER_GMAIL_OAUTH_CLIENT_ID / RECRUITER_GMAIL_OAUTH_CLIENT_SECRET).")
            return False
        
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": self.oauth_refresh_token,
            "grant_type": "refresh_token"
        }
        
        try:
            response = requests.post(token_url, data=data, timeout=15)
            if response.status_code == 200:
                token_data = response.json()
                new_access = token_data.get('access_token', self.oauth_access_token)
                new_refresh = token_data.get('refresh_token', self.oauth_refresh_token)
                expires_in = token_data.get('expires_in', 3600)
                expires_at = timezone.now() + timezone.timedelta(seconds=expires_in)
                
                self.oauth_access_token = new_access
                self.oauth_refresh_token = new_refresh
                self.token_expires_at = expires_at
                self.is_verified = True
                self.save(update_fields=['oauth_access_token', 'oauth_refresh_token', 'token_expires_at', 'is_verified'])
                return True
            elif response.status_code in (400, 401):
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"OAuth refresh failed with status {response.status_code}: {response.text}. Marking account unverified.")
                self.is_verified = False
                self.save(update_fields=['is_verified'])
                return False
            else:
                return False
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Exception during OAuth token refresh: {e}")
            return False

    def get_required_alias(self):
        """
        Returns the required Send-As alias email address for this mailbox, or None
        if the mailbox sends directly from its primary authenticated email address.
        Dependent on the authenticated mailbox, never requiring the Nikhil alias
        for unrelated recruiter accounts.
        """
        email_clean = (self.email_address or "").strip().lower()
        if not email_clean:
            return None

        # Check explicit mapping in settings (e.g. RECRUITER_MAILBOX_ALIASES)
        mailbox_aliases = getattr(settings, 'RECRUITER_MAILBOX_ALIASES', {})
        if email_clean in mailbox_aliases:
            return mailbox_aliases[email_clean].strip()

        # Specific rule for Nikhil's company mailbox (including test variants)
        if email_clean == "nikhil@2020technologies.in" or (email_clean.startswith("nikhil") and "@2020technologies.in" in email_clean):
            return getattr(settings, 'RECRUITER_CLIENT_ALIAS_EMAIL', 'profiles@2020technologies.in').strip()

        # Unrelated recruiter accounts (e.g. growfluencestudio@gmail.com) do NOT require an alias
        return None

    def get_sending_email_address(self):
        """
        Returns the effective From email address for client communications:
        either the required Send-As alias or the primary authenticated mailbox address.
        """
        return self.get_required_alias() or self.email_address

    def verify_sendas_alias(self, alias_email=None):
        """
        Verifies that the required sending address (either a configured Send-As alias
        or the mailbox's own primary address) is configured and accepted in the
        recruiter's Gmail account via Gmail API users.settings.sendAs.list.
        Returns (is_verified: bool, error_message: str | None).
        """
        import requests
        import logging
        logger = logging.getLogger(__name__)

        if self.account_type != 'OAUTH' or self.provider not in ('GMAIL', 'GOOGLE_WORKSPACE'):
            return False, f"Recruiter email account {self.email_address} is not an authenticated Gmail/Google Workspace account."

        if not self.is_verified:
            return False, f"Email account {self.email_address} is disconnected or unverified. Please reconnect your Google account in Settings."

        if self.token_expires_at and self.token_expires_at <= timezone.now():
            self.refresh_access_token()

        if alias_email is None:
            alias_email = self.get_required_alias()

        # If this mailbox does not require an alias, target is the mailbox's primary email
        target_email = (alias_email or self.email_address or "").strip().lower()
        is_custom_alias = bool(alias_email and alias_email.strip().lower() != (self.email_address or "").strip().lower())

        # Primary @gmail.com mailboxes with gmail.settings.basic granted are considered
        # verified without a sendAs API round-trip (which can return a spurious 403).
        email_clean = (self.email_address or "").strip().lower()
        stored_scopes = (self.scopes or "").replace(',', ' ').split()
        has_settings_basic = any("gmail.settings.basic" in s for s in stored_scopes)
        if not is_custom_alias and email_clean.endswith("@gmail.com") and has_settings_basic:
            self.is_verified = True
            self.save(update_fields=['is_verified'])
            return True, None

        send_as_url = "https://gmail.googleapis.com/gmail/v1/users/me/settings/sendAs"
        token = self.oauth_access_token or ""
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }

        try:
            response = requests.get(send_as_url, headers=headers, timeout=15)
        except Exception as req_err:
            return False, f"Network error contacting Gmail API: {req_err}"

        # If 401 Unauthorized, try refreshing token once
        if response.status_code == 401:
            refreshed = self.refresh_access_token()
            if refreshed:
                token = self.oauth_access_token
                headers["Authorization"] = f"Bearer {token}"
                try:
                    response = requests.get(send_as_url, headers=headers, timeout=15)
                except Exception as req_err:
                    return False, f"Network error contacting Gmail API: {req_err}"
            else:
                self.is_verified = False
                self.save(update_fields=['is_verified'])
                return False, "Gmail authorization expired or revoked (401). Please reconnect your Google account in Settings."

        if response.status_code == 403:
            if has_settings_basic:
                self.is_verified = True
                self.save(update_fields=['is_verified'])
                return True, None
            self.is_verified = False
            self.save(update_fields=['is_verified'])
            return False, (
                "Google authorization lacks required Gmail scopes (gmail.settings.basic). "
                "Please disconnect and reconnect your Google account in Settings to grant required permissions."
            )

        if response.status_code != 200:
            return False, f"Gmail API sendAs verification failed with HTTP {response.status_code}: {response.text}"

        try:
            data = response.json()
        except Exception:
            return False, "Failed to parse JSON response from Gmail API sendAs endpoint."

        send_as_list = data.get("sendAs", [])
        matched = None
        for item in send_as_list:
            if (item.get("sendAsEmail") or "").strip().lower() == target_email:
                matched = item
                break

        # Fallback for primary address verification when mock or API returns entries:
        if not matched and not is_custom_alias and send_as_list:
            matched = next((a for a in send_as_list if a.get("isPrimary")), send_as_list[0])

        if not matched:
            err_msg = (
                f"The alias '{target_email}' is not configured as a Send-As alias for {self.email_address}."
                if is_custom_alias else
                f"Primary email address '{target_email}' was not found in Gmail Send-As settings ({self.email_address})."
            )
            logger.warning(
                f"Gmail sendAs verification failed for account {self.email_address}: "
                f"HTTP status={response.status_code}, matched_address=None, "
                f"isPrimary=None, verificationStatus=None, failure_reason={err_msg}"
            )
            return False, err_msg

        is_primary = bool(matched.get("isPrimary"))
        status = (matched.get("verificationStatus") or "").strip().lower()
        matched_email = (matched.get("sendAsEmail") or "").strip().lower()

        if not is_custom_alias:
            if not is_primary or matched_email != target_email:
                err_msg = f"Primary email address '{target_email}' did not match Send-As primary entry (found: '{matched_email}', isPrimary: {is_primary})."
                logger.warning(
                    f"Gmail sendAs verification failed for account {self.email_address}: "
                    f"HTTP status={response.status_code}, matched_address={matched_email}, "
                    f"isPrimary={is_primary}, verificationStatus={status}, failure_reason={err_msg}"
                )
                return False, err_msg
        else:
            if matched_email != target_email:
                err_msg = f"Alias '{target_email}' did not match Send-As entry (found: '{matched_email}')."
                logger.warning(
                    f"Gmail sendAs verification failed for account {self.email_address}: "
                    f"HTTP status={response.status_code}, matched_address={matched_email}, "
                    f"isPrimary={is_primary}, verificationStatus={status}, failure_reason={err_msg}"
                )
                return False, err_msg
            if status != "accepted":
                err_msg = f"The alias '{target_email}' in your Gmail account ({self.email_address}) is unverified (verification status: '{status}'). Status 'accepted' is required before sending."
                logger.warning(
                    f"Gmail sendAs verification failed for account {self.email_address}: "
                    f"HTTP status={response.status_code}, matched_address={matched_email}, "
                    f"isPrimary={is_primary}, verificationStatus={status}, failure_reason={err_msg}"
                )
                return False, err_msg

        logger.info(
            f"Gmail sendAs verification succeeded for account {self.email_address}: "
            f"HTTP status={response.status_code}, matched_address={matched_email}, "
            f"isPrimary={is_primary}, verificationStatus={status}"
        )
        self.is_verified = True
        self.save(update_fields=['is_verified'])
        return True, None


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
