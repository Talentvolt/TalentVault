import logging
import secrets
from typing import Tuple

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def generate_otp() -> str:
    """
    Generate a secure random 6-digit OTP string.
    """
    return f"{secrets.randbelow(900000) + 100000:06d}"


def mask_email(email: str) -> str:
    """
    Mask email address for privacy in logs.
    Example: 'johndoe@example.com' -> 'j***e@example.com'
    """
    email = email.strip()
    if '@' not in email:
        return '***'
    user_part, domain_part = email.split('@', 1)
    if len(user_part) <= 2:
        masked_user = user_part[0] + '*'
    else:
        masked_user = user_part[0] + '*' * (len(user_part) - 2) + user_part[-1]
    return f"{masked_user}@{domain_part}"


def send_email_otp(email: str, otp: str, purpose: str = "signup") -> Tuple[bool, str]:
    """
    Send multi-part HTML & Plain-Text Email OTP message using Gmail SMTP.

    Args:
        email: Recipient email address
        otp: 6-digit OTP string
        purpose: 'signup' or 'reset_password'

    Returns:
        Tuple of (success: bool, message: str)
    """
    target_email = email.strip().lower()
    masked_target = mask_email(target_email)

    subject = "Your TalentVault Verification Code"
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', '') or 'noreply@talent-vault.in'
    context = {'otp': otp, 'purpose': purpose, 'email': target_email}

    # Render HTML and Plain-Text templates
    try:
        html_content = render_to_string('emails/otp_email.html', context)
    except Exception as render_err:
        logger.warning(f"Could not render otp_email.html: {render_err}")
        html_content = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #FAF9FF; text-align: center;">
            <h2 style="color: #0F172A;">Your TalentVault Verification Code</h2>
            <div style="font-size: 36px; font-weight: bold; color: #6D4AFF; background: #F3F0FF; padding: 15px; border-radius: 12px; margin: 20px 0; letter-spacing: 8px;">{otp}</div>
            <p style="color: #64748B;">This verification code expires in 5 minutes.</p>
            <p style="color: #64748B; font-size: 13px;">Notice: If you don't find this email in your Inbox, please check your Spam or Promotions folder.</p>
        </div>
        """

    try:
        text_content = render_to_string('emails/otp_email.txt', context)
    except Exception as render_err:
        text_content = (
            f"Your TalentVault Verification Code is: {otp}\n\n"
            f"This verification code expires in 5 minutes.\n\n"
            f"Notice: If you don't find this email in your Inbox, please check your Spam or Promotions folder.\n\n"
            f"© 2026 TalentVault"
        )

    try:
        email_message = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=[target_email],
        )
        email_message.attach_alternative(html_content, "text/html")
        email_message.send(fail_silently=False)

        logger.info(f"Successfully sent multi-part Email OTP to {masked_target} for {purpose}")
        return True, "Verification code sent to your email successfully."

    except Exception as exc:
        logger.error(f"Failed to send Email OTP to {masked_target}: {str(exc)}")
        return False, f"Failed to send email OTP: {str(exc)}"


ADMIN_NOTIFICATION_EMAIL = "talentvault2020@gmail.com"


def send_recruiter_registration_admin_notification(
    company_name: str,
    recruiter_name: str,
    email: str,
    phone: str,
    hiring_type: str,
    registration_time: str,
    approval_url: str = ""
) -> bool:
    """
    Send admin notification email to talentvault2020@gmail.com when a new recruiter/employer registers.
    """
    try:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', '') or 'noreply@talent-vault.in'
        subject = "New Recruiter Registration - Approval Required"

        html_content = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #f8fafc; color: #1e293b;">
            <div style="max-width: 600px; margin: 0 auto; background: #ffffff; padding: 24px; border-radius: 8px; border: 1px solid #e2e8f0;">
                <h2 style="color: #4f46e5; margin-top: 0;">New Recruiter Registration - Approval Required</h2>
                <p>A new recruiter/employer has registered on TalentVault and is awaiting verification and approval.</p>

                <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                    <tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 8px; font-weight: bold; width: 40%;">Company Name:</td><td style="padding: 8px;">{company_name}</td></tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 8px; font-weight: bold;">Recruiter Name:</td><td style="padding: 8px;">{recruiter_name}</td></tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 8px; font-weight: bold;">Email:</td><td style="padding: 8px;">{email}</td></tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 8px; font-weight: bold;">Phone:</td><td style="padding: 8px;">{phone}</td></tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 8px; font-weight: bold;">Hiring Type:</td><td style="padding: 8px;">{hiring_type}</td></tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 8px; font-weight: bold;">Registration Time:</td><td style="padding: 8px;">{registration_time}</td></tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 8px; font-weight: bold;">Current Status:</td><td style="padding: 8px; color: #d97706; font-weight: bold;">Pending Verification</td></tr>
                </table>

                {"<div style='margin-top: 24px; text-align: center;'><a href='" + approval_url + "' style='background-color: #4f46e5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;'>Review & Approve Recruiter</a></div>" if approval_url else ""}
                <p style="color: #64748b; font-size: 12px; margin-top: 30px;">TalentVault System Notification</p>
            </div>
        </div>
        """

        text_content = (
            f"New Recruiter Registration - Approval Required\n\n"
            f"A new recruiter/employer has registered on TalentVault and requires approval.\n\n"
            f"Registration Details:\n"
            f"- Company Name: {company_name}\n"
            f"- Recruiter Name: {recruiter_name}\n"
            f"- Email: {email}\n"
            f"- Phone: {phone}\n"
            f"- Hiring Type: {hiring_type}\n"
            f"- Registration Time: {registration_time}\n"
            f"- Current Status: Pending Verification\n\n"
            f"Admin Approval URL: {approval_url}\n"
        )

        email_message = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=[ADMIN_NOTIFICATION_EMAIL],
        )
        email_message.attach_alternative(html_content, "text/html")
        email_message.send(fail_silently=False)
        logger.info(f"Successfully sent recruiter registration admin notification to {ADMIN_NOTIFICATION_EMAIL} for {email}")
        return True
    except Exception as exc:
        logger.error(f"Failed to send admin recruiter registration notification email for {email}: {exc}")
        return False


def send_recruiter_approval_emails(
    recruiter_email: str,
    company_name: str,
    approval_timestamp: str,
    login_url: str = ""
) -> Tuple[bool, bool]:
    """
    Send approval confirmation email to recruiter and notification email to admin (talentvault2020@gmail.com).
    Returns tuple of (recruiter_email_sent, admin_email_sent).
    """
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', '') or 'noreply@talent-vault.in'
    recruiter_sent = False
    admin_sent = False

    # 1. Send confirmation email to recruiter
    try:
        subject = "Your TalentVault Recruiter Account Has Been Approved!"
        text_content = (
            f"Hello,\n\n"
            f"Your TalentVault recruiter account ({recruiter_email}) for {company_name} has been verified and approved by our admin team.\n\n"
            f"Approval Timestamp: {approval_timestamp}\n\n"
            f"You can now log in to your recruiter workspace at:\n{login_url}\n\n"
            f"Best regards,\n"
            f"TalentVault Team"
        )
        html_content = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #f8fafc; color: #1e293b;">
            <div style="max-width: 600px; margin: 0 auto; background: #ffffff; padding: 24px; border-radius: 8px; border: 1px solid #e2e8f0;">
                <h2 style="color: #16a34a; margin-top: 0;">Account Approved!</h2>
                <p>Hello,</p>
                <p>Your TalentVault recruiter account for <strong>{company_name}</strong> has been verified and approved by our admin team.</p>
                <p><strong>Approval Timestamp:</strong> {approval_timestamp}</p>
                {"<div style='margin-top: 24px; text-align: center;'><a href='" + login_url + "' style='background-color: #16a34a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;'>Log In to Recruiter Workspace</a></div>" if login_url else ""}
                <p style="margin-top: 24px;">Best regards,<br>TalentVault Team</p>
            </div>
        </div>
        """
        msg = EmailMultiAlternatives(subject=subject, body=text_content, from_email=from_email, to=[recruiter_email])
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        recruiter_sent = True
        logger.info(f"Successfully sent recruiter approval email to {recruiter_email}")
    except Exception as exc:
        logger.error(f"Failed to send approval email to recruiter {recruiter_email}: {exc}")

    # 2. Send notification email to Admin (talentvault2020@gmail.com)
    try:
        admin_subject = "Recruiter Approved"
        admin_text = (
            f"Recruiter Approved\n\n"
            f"A recruiter account has been approved by Admin.\n\n"
            f"Details:\n"
            f"- Recruiter Email: {recruiter_email}\n"
            f"- Company: {company_name}\n"
            f"- Approval Timestamp: {approval_timestamp}\n"
            f"- Status: Active / Approved\n"
        )
        admin_html = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #f8fafc; color: #1e293b;">
            <div style="max-width: 600px; margin: 0 auto; background: #ffffff; padding: 24px; border-radius: 8px; border: 1px solid #e2e8f0;">
                <h2 style="color: #16a34a; margin-top: 0;">Recruiter Approved</h2>
                <p>A recruiter account has been approved by Admin.</p>
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                    <tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 8px; font-weight: bold; width: 40%;">Recruiter Email:</td><td style="padding: 8px;">{recruiter_email}</td></tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 8px; font-weight: bold;">Company:</td><td style="padding: 8px;">{company_name}</td></tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 8px; font-weight: bold;">Approval Timestamp:</td><td style="padding: 8px;">{approval_timestamp}</td></tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 8px; font-weight: bold;">Status:</td><td style="padding: 8px; color: #16a34a; font-weight: bold;">Active / Approved</td></tr>
                </table>
                <p style="color: #64748b; font-size: 12px; margin-top: 30px;">TalentVault System Notification</p>
            </div>
        </div>
        """
        msg_admin = EmailMultiAlternatives(subject=admin_subject, body=admin_text, from_email=from_email, to=[ADMIN_NOTIFICATION_EMAIL])
        msg_admin.attach_alternative(admin_html, "text/html")
        msg_admin.send(fail_silently=False)
        admin_sent = True
        logger.info(f"Successfully sent recruiter approval admin notification for {recruiter_email}")
    except Exception as exc:
        logger.error(f"Failed to send recruiter approval admin notification for {recruiter_email}: {exc}")

    return recruiter_sent, admin_sent


def send_recruiter_rejection_emails(
    recruiter_email: str,
    company_name: str,
    rejection_timestamp: str
) -> Tuple[bool, bool]:
    """
    Send rejection email to recruiter and notification email to admin (talentvault2020@gmail.com).
    Returns tuple of (recruiter_email_sent, admin_email_sent).
    """
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', '') or 'noreply@talent-vault.in'
    recruiter_sent = False
    admin_sent = False

    # 1. Send rejection email to recruiter
    try:
        subject = "TalentVault Recruiter Account Status Update"
        text_content = (
            f"Hello,\n\n"
            f"Thank you for registering your company ({company_name}) on TalentVault.\n\n"
            f"After reviewing your application, we regret to inform you that your recruiter account ({recruiter_email}) could not be approved at this time.\n\n"
            f"If you believe this was in error or if you have any questions, please contact TalentVault Support.\n\n"
            f"Best regards,\n"
            f"TalentVault Team"
        )
        html_content = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #f8fafc; color: #1e293b;">
            <div style="max-width: 600px; margin: 0 auto; background: #ffffff; padding: 24px; border-radius: 8px; border: 1px solid #e2e8f0;">
                <h2 style="color: #dc2626; margin-top: 0;">Account Verification Update</h2>
                <p>Hello,</p>
                <p>Thank you for registering your company (<strong>{company_name}</strong>) on TalentVault.</p>
                <p>After reviewing your application, we regret to inform you that your recruiter account (<strong>{recruiter_email}</strong>) could not be approved at this time.</p>
                <p>If you believe this was in error or if you have any questions, please contact TalentVault Support.</p>
                <p style="margin-top: 24px;">Best regards,<br>TalentVault Team</p>
            </div>
        </div>
        """
        msg = EmailMultiAlternatives(subject=subject, body=text_content, from_email=from_email, to=[recruiter_email])
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        recruiter_sent = True
        logger.info(f"Successfully sent rejection email to recruiter {recruiter_email}")
    except Exception as exc:
        logger.error(f"Failed to send rejection email to recruiter {recruiter_email}: {exc}")

    # 2. Send notification email to Admin (talentvault2020@gmail.com)
    try:
        admin_subject = "Recruiter Rejected"
        admin_text = (
            f"Recruiter Rejected\n\n"
            f"A recruiter account has been rejected by Admin.\n\n"
            f"Details:\n"
            f"- Recruiter Email: {recruiter_email}\n"
            f"- Company: {company_name}\n"
            f"- Rejection Timestamp: {rejection_timestamp}\n"
            f"- Status: Rejected\n"
        )
        admin_html = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #f8fafc; color: #1e293b;">
            <div style="max-width: 600px; margin: 0 auto; background: #ffffff; padding: 24px; border-radius: 8px; border: 1px solid #e2e8f0;">
                <h2 style="color: #dc2626; margin-top: 0;">Recruiter Rejected</h2>
                <p>A recruiter account has been rejected by Admin.</p>
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                    <tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 8px; font-weight: bold; width: 40%;">Recruiter Email:</td><td style="padding: 8px;">{recruiter_email}</td></tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 8px; font-weight: bold;">Company:</td><td style="padding: 8px;">{company_name}</td></tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 8px; font-weight: bold;">Rejection Timestamp:</td><td style="padding: 8px;">{rejection_timestamp}</td></tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 8px; font-weight: bold;">Status:</td><td style="padding: 8px; color: #dc2626; font-weight: bold;">Rejected</td></tr>
                </table>
                <p style="color: #64748b; font-size: 12px; margin-top: 30px;">TalentVault System Notification</p>
            </div>
        </div>
        """
        msg_admin = EmailMultiAlternatives(subject=admin_subject, body=admin_text, from_email=from_email, to=[ADMIN_NOTIFICATION_EMAIL])
        msg_admin.attach_alternative(admin_html, "text/html")
        msg_admin.send(fail_silently=False)
        admin_sent = True
        logger.info(f"Successfully sent recruiter rejection admin notification for {recruiter_email}")
    except Exception as exc:
        logger.error(f"Failed to send recruiter rejection admin notification for {recruiter_email}: {exc}")

    return recruiter_sent, admin_sent


def _send_candidate_profile_invitation_email_now(
    profile,
    candidate_email: str,
    candidate_name: str,
    request=None
) -> Tuple[bool, str]:
    """
    Internal function to send the invitation email immediately.
    Used by the queue processor and manual send endpoints.
    Assumes email validation and idempotency checks have been done.
    """
    from apps.candidates.utils import is_placeholder_email, VALID_EMAIL_RE
    from apps.candidates.models import CandidateProfile
    from django.utils import timezone

    # Resolve candidate name
    resolved_name = (candidate_name or profile.full_name or "Candidate").strip()
    if not resolved_name or resolved_name.lower() in ('unknown', 'unknown candidate', 'none', 'null'):
        resolved_name = "Candidate"

    # Generate unique profile URL dynamically
    profile_link = profile.get_full_profile_url(request=request)

    subject = "Complete Your TalentVault Profile"
    from_name = getattr(settings, 'EMAIL_FROM_NAME', 'TalentVault') or 'TalentVault'
    default_from = getattr(settings, 'DEFAULT_FROM_EMAIL', '') or 'noreply@talent-vault.in'
    if '<' in default_from and '>' in default_from:
        from_email = default_from
    else:
        from_email = f"{from_name} <{default_from}>"

    reply_to_email = getattr(settings, 'SUPPORT_EMAIL', 'support@talent-vault.in') or 'support@talent-vault.in'
    
    import uuid
    domain = getattr(settings, 'SITE_DOMAIN', 'talent-vault.in') or 'talent-vault.in'
    if domain.startswith('http://') or domain.startswith('https://'):
        domain = domain.split('://')[-1]
    domain = domain.split('/')[0].split(':')[0]
    msg_id = f"<{uuid.uuid4()}@{domain}>"

    custom_headers = {
        'Message-ID': msg_id,
        'X-Mailer': 'TalentVault Notification Service',
        'Auto-Submitted': 'auto-generated',
    }

    context = {
        'candidate_name': resolved_name,
        'candidate_profile_link': profile_link,
        'candidate': profile,
        'email': candidate_email
    }

    # Render templates with robust fallbacks
    try:
        text_content = render_to_string('emails/candidate_profile_invitation.txt', context)
    except Exception as render_err:
        logger.warning(f"Could not render candidate_profile_invitation.txt: {render_err}")
        text_content = (
            f"Hi {resolved_name},\n\n"
            f"Your CV has been successfully processed and your profile has been created on TalentVault.\n\n"
            f"To complete your profile and make it available for relevant job opportunities, please review your information and complete your TalentVault profile.\n\n"
            f"Your CV / Profile:\n\n"
            f"{profile_link}\n\n"
            f"Please click the link above to view your CV details and complete your profile.\n\n"
            f"Once your profile is completed, recruiters can consider your profile for suitable job opportunities.\n\n"
            f"Regards,\n"
            f"TalentVault Team\n"
            f"TalentVault Technologies\n"
        )

    try:
        html_content = render_to_string('emails/candidate_profile_invitation.html', context)
    except Exception as render_err:
        logger.warning(f"Could not render candidate_profile_invitation.html: {render_err}")
        html_content = f"""
        <div style="font-family: Arial, sans-serif; padding: 24px; background-color: #FAF9FF; color: #0F172A;">
            <p>Hi {resolved_name},</p>
            <p>Your CV has been successfully processed and your profile has been created on TalentVault.</p>
            <p>To complete your profile and make it available for relevant job opportunities, please review your information and complete your TalentVault profile.</p>
            <p><strong>Your CV / Profile:</strong></p>
            <p style="margin: 24px 0;"><a href="{profile_link}" style="background-color: #2563EB; color: #fff; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">Complete Your TalentVault Profile</a></p>
            <p>Direct Link: <a href="{profile_link}">{profile_link}</a></p>
            <p>Please click the link above to view your CV details and complete your profile.</p>
            <p>Once your profile is completed, recruiters can consider your profile for suitable job opportunities.</p>
            <p style="margin-top: 24px;">Regards,<br><strong>TalentVault Team</strong><br>TalentVault Technologies</p>
        </div>
        """

    masked_target = mask_email(candidate_email)
    try:
        email_message = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=[candidate_email],
            reply_to=[reply_to_email],
            headers=custom_headers,
        )
        email_message.attach_alternative(html_content, "text/html")
        email_message.send(fail_silently=False)

        # Log email to EmailLog if available
        try:
            from apps.notifications.models import EmailLog
            EmailLog.objects.create(
                sender=profile.uploaded_by or profile.created_by,
                recipient_email=candidate_email,
                subject=subject,
                body=text_content,
                status='SENT'
            )
        except Exception as log_err:
            logger.warning(f"Could not log email to EmailLog: {log_err}")

        # Update candidate profile tracking fields
        now = timezone.now()
        CandidateProfile.objects.filter(id=profile.id).update(
            profile_invitation_sent=True,
            profile_invitation_sent_at=now
        )
        profile.profile_invitation_sent = True
        profile.profile_invitation_sent_at = now

        logger.info(f"[INVITATION SENT] Successfully sent candidate profile invitation email to {masked_target} for profile {profile.id}")
        return True, "Invitation email sent successfully."

    except Exception as exc:
        logger.error(f"[INVITATION FAILED] Failed to send candidate profile invitation email to {masked_target} for profile {profile.id}: {str(exc)}", exc_info=True)
        try:
            from apps.notifications.models import EmailLog
            EmailLog.objects.create(
                sender=profile.uploaded_by or profile.created_by,
                recipient_email=candidate_email,
                subject=subject,
                body=f"{text_content}\n\n[DELIVERY ERROR]: {str(exc)}",
                status='FAILED'
            )
        except Exception:
            pass
        return False, f"Failed to send invitation email: {str(exc)}"


def send_candidate_profile_invitation_email(
    profile,
    candidate_email: str = None,
    candidate_name: str = None,
    request=None,
    force_resend: bool = False,
    queue_email: bool = True
) -> Tuple[bool, str]:
    """
    Queue or send profile invitation email to candidate after CV parsing.
    
    Includes idempotency protection (prevents duplicate invitation emails),
    dynamic candidate profile URL generation, multi-part plain-text and HTML
    rendering with professional CTA button, error logging, and database tracking.

    When queue_email=True (default for automatic parsing), the email is added
    to a persistent queue for delayed sequential delivery (3-minute intervals).
    When queue_email=False (manual sends), the email is sent immediately.

    Returns:
        Tuple of (success: bool, message: str)
    """
    if not profile:
        return False, "Candidate profile is missing."

    # Idempotency check: Do not resend if already sent unless force_resend is explicitly requested
    if profile.profile_invitation_sent and not force_resend:
        logger.info(f"[INVITATION SKIPPED] Invitation email already sent to candidate {profile.id} at {profile.profile_invitation_sent_at}")
        return False, "Invitation email has already been sent."

    from apps.candidates.utils import is_placeholder_email, VALID_EMAIL_RE
    from apps.candidates.models import CandidateProfile

    # Resolve candidate email: provided argument -> profile.contact_email -> profile.user.email
    target_email = (candidate_email or "").strip().lower()
    if not target_email or is_placeholder_email(target_email):
        target_email = (profile.contact_email or "").strip().lower()
    if not target_email or is_placeholder_email(target_email):
        user_email = getattr(profile.user, 'email', '') or ''
        if not is_placeholder_email(user_email):
            target_email = user_email.strip().lower()

    if not target_email or is_placeholder_email(target_email) or not VALID_EMAIL_RE.match(target_email):
        logger.warning(f"[INVITATION SKIPPED] No valid email address found for candidate {profile.id}. Email: '{target_email}'")
        return False, "No valid candidate email found."

    # Resolve candidate name
    resolved_name = (candidate_name or profile.full_name or "Candidate").strip()
    if not resolved_name or resolved_name.lower() in ('unknown', 'unknown candidate', 'none', 'null'):
        resolved_name = "Candidate"

    if not queue_email:
        # Manual send - send immediately
        return _send_candidate_profile_invitation_email_now(profile, target_email, resolved_name, request)

    # Queue the email for delayed sequential delivery
    from apps.candidates.models import CandidateInvitationEmailQueue
    from django.utils import timezone
    from datetime import timedelta

    # Check if already queued for this candidate (prevent duplicates from bulk parsing retries)
    existing_queued = CandidateInvitationEmailQueue.objects.filter(
        candidate_profile=profile,
        status__in=['PENDING', 'SENDING']
    ).first()
    if existing_queued:
        logger.info(f"[INVITATION QUEUE SKIPPED] Already queued for candidate {profile.id}")
        return False, "Invitation email already queued."

    # Calculate scheduled time: first email waits 3 minutes, subsequent ones wait 3 min after previous
    now = timezone.now()
    last_queued = CandidateInvitationEmailQueue.objects.filter(
        status__in=['PENDING', 'SENDING']
    ).order_by('-scheduled_at').first()
    
    if last_queued:
        scheduled_at = last_queued.scheduled_at + timedelta(minutes=3)
        # Ensure it's at least 3 minutes from now
        if scheduled_at < now + timedelta(minutes=3):
            scheduled_at = now + timedelta(minutes=3)
    else:
        # First email in queue - wait 3 minutes
        scheduled_at = now + timedelta(minutes=3)

    CandidateInvitationEmailQueue.objects.create(
        candidate_profile=profile,
        candidate_email=target_email,
        candidate_name=resolved_name,
        scheduled_at=scheduled_at,
        status='PENDING',
        max_attempts=3
    )

    logger.info(f"[INVITATION QUEUED] Candidate {profile.id} ({target_email}) scheduled for {scheduled_at}")
    return True, f"Invitation email queued for delivery at {scheduled_at.strftime('%H:%M:%S')}."