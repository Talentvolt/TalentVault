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

    print(f"\n==================================================")
    print(f"[EMAIL OTP DEBUG] send_email_otp() CALLED!")
    print(f"[EMAIL OTP DEBUG] Target Email: '{target_email}'")
    print(f"[EMAIL OTP DEBUG] GENERATED OTP CODE: '{otp}'")
    print(f"[EMAIL OTP DEBUG] Purpose: '{purpose}'")

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
        print(f"[EMAIL OTP DEBUG] Attempting to send multi-part email via SMTP to {target_email}...")
        email_message = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=[target_email],
        )
        email_message.attach_alternative(html_content, "text/html")
        email_message.send(fail_silently=False)

        print(f"[EMAIL OTP DEBUG] SUCCESS! Multi-part Email sent to {masked_target}")
        print(f"==================================================\n")

        logger.info(f"Successfully sent multi-part Email OTP to {masked_target} for {purpose}")
        return True, "Verification code sent to your email successfully."

    except Exception as exc:
        print(f"\n[EMAIL OTP DEBUG] Exception CAUGHT while sending email!")
        print(f"[EMAIL OTP DEBUG] Exception Class: {exc.__class__.__name__}")
        print(f"[EMAIL OTP DEBUG] Exception Message: {str(exc)}")
        print(f"==================================================\n")

        logger.error(f"Failed to send Email OTP to {masked_target}: {str(exc)}")
        return False, f"Failed to send email OTP: {str(exc)}"
