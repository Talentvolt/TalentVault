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
    Sends ATS email via Django EmailMessage, supports CC, BCC, attachments,
    tracking pixel injection, sender identity enforcement, and logs to EmailLog.
    """
    connected_account = email_account
    if connected_account:
        if connected_account.recruiter != sender or not connected_account.is_verified:
            raise ValueError("Unauthorized or unverified recruiter email account.")
    else:
        if sender and hasattr(sender, 'email_accounts'):
            connected_account = sender.email_accounts.filter(is_verified=True, is_default=True).first()
            if not connected_account:
                connected_account = sender.email_accounts.filter(is_verified=True).first()

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

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', '') or 'noreply@talentvault.com'
        reply_to_list = []
        connection = None

        if connected_account:
            from_email = connected_account.email_address
            reply_to_list = [connected_account.email_address]
            if connected_account.account_type == 'SMTP' and connected_account.smtp_host and not 'locmem' in getattr(settings, 'EMAIL_BACKEND', '').lower():
                from django.core.mail import get_connection
                connection = get_connection(
                    backend='django.core.mail.backends.smtp.EmailBackend',
                    host=connected_account.smtp_host,
                    port=connected_account.smtp_port or 587,
                    username=connected_account.smtp_username,
                    password=connected_account.smtp_password,
                    use_tls=connected_account.use_tls,
                    use_ssl=connected_account.use_ssl,
                )

        email_msg = EmailMessage(
            subject=subject,
            body=html_body,
            from_email=from_email,
            to=[recipient_email],
            cc=cc_list,
            bcc=bcc_list,
            reply_to=reply_to_list,
            connection=connection
        )
        email_msg.content_subtype = "html"

        if attachments:
            for att in attachments:
                try:
                    email_msg.attach(att.name, att.read(), getattr(att, 'content_type', 'application/octet-stream'))
                except Exception as att_err:
                    logger.warning(f"Failed to attach file {att.name}: {att_err}")

        email_msg.send(fail_silently=False)

        email_log.status = 'SENT'
        email_log.save(update_fields=['status'])
        return email_log, True, "Email sent successfully."
    except Exception as e:
        logger.error(f"Failed to send email to {recipient_email}: {e}")
        email_log.status = 'FAILED'
        email_log.error_message = str(e)
        email_log.save(update_fields=['status', 'error_message'])
        return email_log, False, str(e)
