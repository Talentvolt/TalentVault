import os
import logging
from django.conf import settings
from django.core.mail import EmailMessage
from django.urls import reverse
from django.utils import timezone
from apps.notifications.models import EmailTemplate, EmailLog

logger = logging.getLogger(__name__)

DEFAULT_EMAIL_TEMPLATES = [
    {
        "name": "Candidate Shortlist to Client",
        "category": "CLIENT",
        "subject": "Candidate Shortlist for {{job_title}} - {{company_name}}",
        "body": "Dear {{client_name}},\n\nWe are pleased to present the shortlisted candidate profiles for the {{job_title}} position.\n\nCandidate Name: {{candidate_name}}\nExperience: {{experience}}\nSkills: {{skills}}\nLocation: {{location}}\nProfile Link: {{candidate_profile_url}}\n\nPlease review the attached resume and let us know your feedback or interview availability.\n\nBest regards,\n{{recruiter_name}}\n{{company_name}}"
    },
    {
        "name": "Candidate Profile Sharing",
        "category": "CLIENT",
        "subject": "Candidate Profile: {{candidate_name}} for {{job_title}}",
        "body": "Dear {{client_name}},\n\nPlease find attached the candidate profile and resume for {{candidate_name}}, who has strong expertise in {{skills}} with {{experience}} of experience.\n\nProfile Link: {{candidate_profile_url}}\n\nLooking forward to your thoughts.\n\nBest regards,\n{{recruiter_name}}\n{{company_name}}"
    },
    {
        "name": "Bulk Candidate Sharing",
        "category": "CLIENT",
        "subject": "Bulk Candidate Shortlist for {{job_title}}",
        "body": "Dear {{client_name}},\n\nHere is the bulk candidate shortlist for {{job_title}}. All candidate resumes and profiles have been attached for your evaluation.\n\nBest regards,\n{{recruiter_name}}\n{{company_name}}"
    },
    {
        "name": "Urgent Hiring Shortlist",
        "category": "CLIENT",
        "subject": "URGENT SHORTLIST: Top Candidates for {{job_title}}",
        "body": "Dear {{client_name}},\n\nIn response to your urgent requirement for {{job_title}}, we have shortlisted top-tier candidates matching your criteria.\n\nCandidate: {{candidate_name}}\nSkills: {{skills}}\nExperience: {{experience}}\n\nPlease review immediately to schedule priority interviews.\n\nBest regards,\n{{recruiter_name}}\n{{company_name}}"
    },
    {
        "name": "Interview Request",
        "category": "CANDIDATE",
        "subject": "Interview Invitation: {{job_title}} at {{company_name}}",
        "body": "Hi {{candidate_name}},\n\nWe were highly impressed by your profile and would like to invite you for an interview for the {{job_title}} position.\n\nPlease let us know your availability this week.\n\nBest regards,\n{{recruiter_name}}\n{{company_name}}"
    },
    {
        "name": "Interview Confirmation",
        "category": "CANDIDATE",
        "subject": "Interview Confirmed: {{job_title}}",
        "body": "Hi {{candidate_name}},\n\nYour interview for {{job_title}} with {{company_name}} has been successfully confirmed. Please ensure you are available on time.\n\nBest regards,\n{{recruiter_name}}\n{{company_name}}"
    },
    {
        "name": "Interview Feedback Request",
        "category": "CANDIDATE",
        "subject": "Feedback & Next Steps - {{job_title}} Interview",
        "body": "Hi {{candidate_name}},\n\nThank you for taking the time to interview for {{job_title}} with {{company_name}}. We would love to hear your thoughts and feedback on the discussion.\n\nBest regards,\n{{recruiter_name}}\n{{company_name}}"
    },
    {
        "name": "Client Follow-up",
        "category": "CLIENT",
        "subject": "Follow-up: Candidate Shortlist for {{job_title}}",
        "body": "Dear {{client_name}},\n\nFollowing up on our recent candidate submission for {{job_title}}. Have you had a chance to review the profiles?\n\nBest regards,\n{{recruiter_name}}\n{{company_name}}"
    },
    {
        "name": "Replacement Candidate Submission",
        "category": "CLIENT",
        "subject": "Replacement Candidate Submission for {{job_title}}",
        "body": "Dear {{client_name}},\n\nAs requested, here is a replacement candidate profile for the {{job_title}} requirement.\n\nCandidate: {{candidate_name}}\nSkills: {{skills}}\n\nBest regards,\n{{recruiter_name}}\n{{company_name}}"
    },
    {
        "name": "Job Requirement Request",
        "category": "CLIENT",
        "subject": "New Job Requirement Discussion - {{company_name}}",
        "body": "Dear {{client_name}},\n\nWe would love to discuss your upcoming hiring requirements for {{job_title}} and how we can assist you.\n\nBest regards,\n{{recruiter_name}}\n{{company_name}}"
    },
    {
        "name": "Candidate Invitation",
        "category": "CANDIDATE",
        "subject": "Invitation to Join {{company_name}} Talent Network",
        "body": "Hi {{candidate_name}},\n\nWe came across your profile and would like to invite you to join our talent network for exciting roles like {{job_title}}.\n\nBest regards,\n{{recruiter_name}}\n{{company_name}}"
    },
    {
        "name": "Job Application Acknowledgement",
        "category": "CANDIDATE",
        "subject": "Application Received: {{job_title}}",
        "body": "Hi {{candidate_name}},\n\nThank you for applying for the {{job_title}} position at {{company_name}}. We have received your application and are reviewing your profile.\n\nBest regards,\n{{recruiter_name}}\n{{company_name}}"
    },
    {
        "name": "Candidate Rejection",
        "category": "CANDIDATE",
        "subject": "Update on your application for {{job_title}}",
        "body": "Hi {{candidate_name}},\n\nThank you for your interest in the {{job_title}} role at {{company_name}}. While your background is impressive, we have decided to move forward with other candidates whose profiles more closely align with our current needs.\n\nBest regards,\n{{recruiter_name}}\n{{company_name}}"
    },
    {
        "name": "Job Offer Communication",
        "category": "CANDIDATE",
        "subject": "Job Offer: {{job_title}} at {{company_name}}",
        "body": "Hi {{candidate_name}},\n\nCongratulations! We are thrilled to offer you the position of {{job_title}} at {{company_name}}. Please review the attached offer details.\n\nBest regards,\n{{recruiter_name}}\n{{company_name}}"
    },
    {
        "name": "Candidate Profile Completion",
        "category": "CANDIDATE",
        "subject": "Please Complete Your Profile - {{company_name}}",
        "body": "Hi {{candidate_name}},\n\nPlease take a moment to update your profile details and skills on TalentVault so we can match you with relevant opportunities like {{job_title}}.\n\nBest regards,\n{{recruiter_name}}\n{{company_name}}"
    }
]

def seed_default_email_templates():
    for tpl in DEFAULT_EMAIL_TEMPLATES:
        EmailTemplate.objects.get_or_create(
            name=tpl["name"],
            defaults={
                "category": tpl["category"],
                "subject": tpl["subject"],
                "body": tpl["body"],
                "is_system": True
            }
        )

def render_email_content(template_text, candidate=None, job=None, recruiter=None, client_name="Hiring Manager", company_name="TalentVault"):
    if not template_text:
        return ""
    
    candidate_name = "Candidate"
    experience = "N/A"
    location = "N/A"
    skills = "N/A"
    candidate_profile_url = "#"
    
    if candidate:
        if hasattr(candidate, 'full_name') and candidate.full_name:
            candidate_name = candidate.full_name
        elif hasattr(candidate, 'user') and candidate.user and candidate.user.get_full_name():
            candidate_name = candidate.user.get_full_name()
        elif hasattr(candidate, 'contact_email'):
            candidate_name = candidate.contact_email
            
        if hasattr(candidate, 'total_experience') and candidate.total_experience:
            experience = str(candidate.total_experience)
        elif hasattr(candidate, 'experience_years') and candidate.experience_years:
            experience = f"{candidate.experience_years} years"
            
        if hasattr(candidate, 'current_location') and candidate.current_location:
            location = candidate.current_location
        elif hasattr(candidate, 'location') and candidate.location:
            location = candidate.location
            
        # Skills
        try:
            if hasattr(candidate, 'skills') and candidate.skills.exists():
                skills = ", ".join([s.skill_name for s in candidate.skills.all()[:5]])
        except Exception:
            pass
            
        # Profile URL
        try:
            from django.urls import reverse
            candidate_profile_url = f"https://talentvault.in/candidates/{candidate.id}/"
        except Exception:
            pass

    job_title = "Open Position"
    if job:
        if hasattr(job, 'title') and job.title:
            job_title = job.title
        elif isinstance(job, str):
            job_title = job

    recruiter_name = "Recruiter"
    if recruiter:
        if hasattr(recruiter, 'get_full_name') and recruiter.get_full_name():
            recruiter_name = recruiter.get_full_name()
        elif hasattr(recruiter, 'email'):
            recruiter_name = recruiter.email

    replacements = {
        "{{client_name}}": client_name,
        "{{candidate_name}}": candidate_name,
        "{{job_title}}": job_title,
        "{{experience}}": experience,
        "{{location}}": location,
        "{{skills}}": skills,
        "{{candidate_profile_url}}": candidate_profile_url,
        "{{recruiter_name}}": recruiter_name,
        "{{company_name}}": company_name,
    }

    result = template_text
    for placeholder, val in replacements.items():
        result = result.replace(placeholder, str(val))
    return result

def send_ats_email(sender, recipient_email, subject, body, cc=None, bcc=None, template_name=None, candidate_ids=None, attachments=None, request=None, email_account=None):
    """
    Sends recruiter-to-client ATS email exclusively via direct Gmail API OAuth2 (users.messages.send)
    through the recruiter's authenticated Gmail/Google Workspace account.
    Enforces From: <Recruiter Name> <profiles@2020technologies.in>,
    Reply-To: <Recruiter Work Email>, verifies alias via users.settings.sendAs.list,
    places email in the recruiter's Gmail Sent folder, and blocks sending if alias is missing/unverified.
    Never falls back to TalentVault's shared Gmail.
    """
    connected_account = email_account
    if connected_account:
        if connected_account.recruiter != sender or not connected_account.is_verified:
            raise ValueError("Unauthorized or unverified recruiter email account.")
    else:
        if sender and hasattr(sender, 'email_accounts'):
            connected_account = sender.email_accounts.filter(
                is_verified=True, 
                account_type='OAUTH',
                provider__in=['GMAIL', 'GOOGLE_WORKSPACE'],
                is_default=True
            ).first()
            if not connected_account:
                connected_account = sender.email_accounts.filter(
                    is_verified=True,
                    account_type='OAUTH',
                    provider__in=['GMAIL', 'GOOGLE_WORKSPACE']
                ).first()
            if not connected_account:
                connected_account = sender.email_accounts.filter(is_verified=True, is_default=True).first()
                if not connected_account:
                    connected_account = sender.email_accounts.filter(is_verified=True).first()

    if not connected_account or not connected_account.is_verified:
        raise ValueError("No connected and verified Gmail/Google Workspace mailbox found. Please connect your Gmail account in Settings under 'My Email Accounts'.")

    if connected_account.account_type != 'OAUTH' or connected_account.provider not in ('GMAIL', 'GOOGLE_WORKSPACE'):
        raise ValueError("Recruiter-to-client emails must be sent through an authenticated Gmail or Google Workspace account. Never using shared Gmail fallback.")

    recruiter_name = "Recruiter"
    if sender:
        if hasattr(sender, 'get_full_name') and sender.get_full_name():
            recruiter_name = sender.get_full_name().strip()
        elif hasattr(sender, 'first_name') and sender.first_name:
            recruiter_name = f"{sender.first_name} {sender.last_name}".strip()
        elif hasattr(sender, 'email') and sender.email:
            recruiter_name = sender.email.split('@')[0].capitalize()

    alias_email = getattr(settings, 'RECRUITER_CLIENT_ALIAS_EMAIL', 'profiles@2020technologies.in')
    recruiter_work_email = connected_account.email_address or (sender.email if sender else alias_email)

    from_email = f"{recruiter_name} <{alias_email}>"
    reply_to_email = recruiter_work_email

    email_log = EmailLog.objects.create(
        sender=sender,
        recipient_email=recipient_email,
        cc=cc or "",
        bcc=bcc or "",
        subject=subject,
        body=body,
        template_name=template_name,
        candidate_ids=candidate_ids or [],
        status='SENDING',
        has_attachment=bool(attachments),
        attachment_names=", ".join([att.name for att in attachments]) if attachments else None
    )

    try:
        # Verify alias via Gmail API users.settings.sendAs.list
        alias_verified, alias_error = connected_account.verify_sendas_alias(alias_email)
        if not alias_verified:
            logger.error(f"Gmail alias verification failed for {connected_account.email_address}: {alias_error}")
            raise ValueError(alias_error)

        # Inject tracking pixel
        pixel_url = ""
        if request:
            try:
                pixel_url = f"{request.scheme}://{request.get_host()}{reverse('notifications:track_open', kwargs={'uuid': email_log.tracking_uuid})}"
            except Exception:
                pixel_url = f"http://localhost:8000/notifications/track/open/{email_log.tracking_uuid}/"
        else:
            pixel_url = f"http://localhost:8000/notifications/track/open/{email_log.tracking_uuid}/"

        html_body = f"{body.replace(chr(10), '<br>')}<br><img src='{pixel_url}' width='1' height='1' style='display:none;' alt='' />"

        cc_list = [c.strip() for c in cc.split(',')] if cc else []
        bcc_list = [b.strip() for b in bcc.split(',')] if bcc else []

        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders
        import base64
        import requests

        # Check and refresh token if expired
        if connected_account.token_expires_at and connected_account.token_expires_at <= timezone.now():
            connected_account.refresh_access_token()

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = recipient_email
        msg['Reply-To'] = reply_to_email
        if cc_list:
            msg['Cc'] = ", ".join(cc_list)
        if bcc_list:
            msg['Bcc'] = ", ".join(bcc_list)

        msg.attach(MIMEText(html_body, 'html'))

        if attachments:
            for att in attachments:
                try:
                    part = MIMEBase('application', 'octet-stream')
                    att_content = att.read() if hasattr(att, 'read') else b""
                    part.set_payload(att_content)
                    encoders.encode_base64(part)
                    filename = getattr(att, 'name', 'attachment.pdf')
                    part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                    msg.attach(part)
                except Exception as att_err:
                    logger.warning(f"Failed to attach file to Gmail API message: {att_err}")

        raw_mime = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')

        access_token = connected_account.oauth_access_token or "mock_oauth_access_token"
        api_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

        def send_gmail_request(token):
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            payload = {
                "raw": raw_mime
            }
            return requests.post(api_url, headers=headers, json=payload, timeout=20)

        response = send_gmail_request(access_token)
        if response.status_code == 401:
            refreshed = connected_account.refresh_access_token()
            if refreshed:
                access_token = connected_account.oauth_access_token
                response = send_gmail_request(access_token)
            else:
                connected_account.is_verified = False
                connected_account.save(update_fields=['is_verified'])
                raise ValueError("Gmail authorization expired or revoked (401). Please reconnect your Google account in Settings.")

        if response.status_code == 403:
            connected_account.is_verified = False
            connected_account.save(update_fields=['is_verified'])
            raise ValueError(
                "Google authorization lacks required Gmail sending scope (gmail.send). "
                "Please reconnect your Google account in Settings."
            )

        if response.status_code not in (200, 201):
            if response.status_code == 401:
                connected_account.is_verified = False
                connected_account.save(update_fields=['is_verified'])
            raise Exception(f"Gmail API error ({response.status_code}): {response.text}")

        email_log.status = 'SENT'
        email_log.save(update_fields=['status'])
        return email_log, True, "Email sent successfully via authorized recruiter mailbox."
    except Exception as e:
        logger.error(f"Failed to send email to {recipient_email}: {e}")
        email_log.status = 'FAILED'
        email_log.error_message = str(e)
        email_log.save(update_fields=['status', 'error_message'])
        return email_log, False, str(e)
