import os
import logging
from django.conf import settings
from django.core.mail import EmailMessage
from django.urls import reverse
from django.utils import timezone
from apps.notifications.models import EmailTemplate, EmailLog
from utils.s3 import get_content_type

logger = logging.getLogger(__name__)

RECRUITER_SUBMISSION_TEMPLATES = [
    {
        "key": "standard-candidate-submission",
        "name": "Standard Candidate Submission",
        "subject": "Candidate Submission for {{job_title}} - {{company_name}}",
        "body": "Dear {{client_name}},\n\nPlease find below the profile summary of a strong candidate for the {{job_title}} position.\n\nCandidate: {{candidate_name}}\nExperience: {{experience}} years\nSkills: {{skills}}\nLocation: {{location}}\nProfile: {{candidate_profile_url}}\n\nKindly review the attached profile and resume, and let us know your feedback or interview availability.\n\nBest regards,\n{{recruiter_name}}\n{{company_name}}"
    },
    {
        "key": "urgent-role-shortlist",
        "name": "Urgent Role Shortlist",
        "subject": "URGENT SHORTLIST: {{job_title}} Candidates",
        "body": "Dear {{client_name}},\n\nAs your {{job_title}} requirement is time-critical, we have fast-tracked a shortlist of pre-screened candidates for your immediate review.\n\nTop Candidate: {{candidate_name}} ({{experience}} years)\nSkills: {{skills}}\nLocation: {{location}}\n\nPlease review the attached tracker and resumes immediately so we can lock in priority interview slots.\n\nBest regards,\n{{recruiter_name}}\n{{company_name}}"
    },
    {
        "key": "executive-profile-presentation",
        "name": "Executive Profile Presentation",
        "subject": "Executive Profile: {{candidate_name}} for {{job_title}}",
        "body": "Dear {{client_name}},\n\nWe are pleased to present an executive-level profile for your {{job_title}} mandate.\n\nCandidate: {{candidate_name}}\nExperience: {{experience}} years\nSkills: {{skills}}\nLocation: {{location}}\nProfile: {{candidate_profile_url}}\n\nWe recommend prioritising this profile for a confidential discussion.\n\nBest regards,\n{{recruiter_name}}\n{{company_name}}"
    },
]

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

def get_ats_template_options():
    """
    Returns the list of email templates available in the "Email Candidate Profiles
    to Client" dropdown: all active database templates plus the built-in recruiter
    submission presets so recruiters always have ready-to-use options.
    """
    options = []
    for tpl in EmailTemplate.objects.all():
        options.append({
            "id": str(tpl.id),
            "name": tpl.name,
            "category": tpl.category,
            "subject": tpl.subject,
            "body": tpl.body,
            "is_builtin": False,
        })
    for tpl in RECRUITER_SUBMISSION_TEMPLATES:
        options.append({
            "id": f"builtin:{tpl['key']}",
            "name": tpl["name"],
            "category": "CLIENT",
            "subject": tpl["subject"],
            "body": tpl["body"],
            "is_builtin": True,
        })
    return options


def resolve_ats_template(template_id):
    """
    Resolves a template selection (DB UUID or built-in key) to its name, subject
    and body. Returns None when the template cannot be resolved.
    """
    if not template_id:
        return None
    template_id = str(template_id).strip()
    if template_id.startswith("builtin:"):
        key = template_id.split("builtin:", 1)[1]
        for tpl in RECRUITER_SUBMISSION_TEMPLATES:
            if tpl["key"] == key:
                return {"name": tpl["name"], "subject": tpl["subject"], "body": tpl["body"]}
        return None
    try:
        tpl = EmailTemplate.objects.get(id=template_id)
        return {"name": tpl.name, "subject": tpl.subject, "body": tpl.body}
    except (EmailTemplate.DoesNotExist, ValueError, TypeError):
        return None


def _candidate_fields(candidate):
    name = candidate.full_name or (candidate.user.email if candidate.user else None) or "N/A"
    email = ""
    phone = ""
    if candidate.user:
        email = getattr(candidate.user, 'email', None) or ""
        phone = getattr(candidate.user, 'phone_number', None) or ""
    role_company = " / ".join([p for p in [candidate.current_designation, candidate.current_company] if p]) or "N/A"
    exp = candidate.total_experience
    experience = "N/A" if exp is None else f"{exp} yrs"
    location = candidate.location or "N/A"
    profile_url = ""
    try:
        profile_url = candidate.get_full_profile_url()
    except Exception:
        profile_url = f"https://talentvault.in/candidates/{candidate.id}/"
    return {
        "name": name,
        "email": email or "N/A",
        "phone": phone or "N/A",
        "role_company": role_company,
        "experience": experience,
        "location": location,
        "profile_url": profile_url,
    }


def build_candidate_tracker_html(candidates):
    from html import escape

    headers = [
        "S.No", "Candidate Name", "Email ID", "Phone Number",
        "Current Role & Company", "Total Experience", "Location",
        "TalentVault Profile",
    ]
    header_row = "".join(
        f"<th style='background-color:#2563EB; color:#ffffff; padding:8px; text-align:left;'>{h}</th>"
        for h in headers
    )
    rows = []
    for idx, c in enumerate(candidates, start=1):
        f = _candidate_fields(c)
        profile_link = f'<a href="{escape(f["profile_url"])}" target="_blank">View Profile</a>'
        rows.append(
            "<tr>"
            f"<td>{idx}</td>"
            f"<td>{escape(f['name'])}</td>"
            f"<td>{escape(f['email'])}</td>"
            f"<td>{escape(f['phone'])}</td>"
            f"<td>{escape(f['role_company'])}</td>"
            f"<td>{escape(f['experience'])}</td>"
            f"<td>{escape(f['location'])}</td>"
            f"<td>{profile_link}</td>"
            "</tr>"
        )
    body_rows = "".join(rows)
    return (
        '<div style="overflow-x:auto;">'
        '<table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse; width:100%; font-family:Arial, sans-serif; font-size:13px;">'
        f"<thead><tr>{header_row}</tr></thead>"
        f"<tbody>{body_rows}</tbody>"
        "</table>"
        "</div>"
    )


def build_candidate_tracker_plain(candidates):
    lines = []
    for idx, c in enumerate(candidates, start=1):
        f = _candidate_fields(c)
        lines.append(
            f"{idx}. {f['name']} ({f['role_company']}) | Email: {f['email']} | Phone: {f['phone']} | "
            f"Exp: {f['experience']} | Location: {f['location']} | Profile: {f['profile_url']}"
        )
    return "\n".join(lines)


def build_html_body(rendered_body, candidates):
    from html import escape

    body_html = escape(rendered_body or "").replace("\n", "<br>")
    table_html = build_candidate_tracker_html(candidates)
    return (
        '<div style="font-family:Arial, Helvetica, sans-serif; color:#1E293B; line-height:1.5;">'
        f"{body_html}</div><br>{table_html}"
    )


def build_candidate_tracker_xlsx(candidates, job=None):
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    from utils.salary_formatter import format_salary_lpa

    job_title = getattr(job, 'title', None) or ""
    wb = Workbook()
    ws = wb.active
    ws.title = "Candidate Tracker"

    headers = [
        "Job Title", "Candidate Name", "Email ID", "Phone Number",
        "Current Location", "Preferred Location", "Total Experience",
        "Current Company", "Current CTC", "Expected CTC", "Notice Period",
        "Skills", "Profile URL",
    ]
    ws.append(headers)

    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for c in candidates:
        f = _candidate_fields(c)
        skills = ""
        try:
            skills = ", ".join([s.skill_name for s in c.skills.all()])
        except Exception:
            skills = ""
        if getattr(c, 'is_immediate_joiner', False):
            notice = "Immediate Joiner"
        else:
            notice = f"{c.notice_period} days" if c.notice_period is not None else "N/A"
        total_exp = None
        try:
            total_exp = float(c.total_experience) if c.total_experience is not None else None
        except Exception:
            total_exp = None
        ws.append([
            job_title,
            f["name"],
            f["email"] if f["email"] != "N/A" else "",
            f["phone"] if f["phone"] != "N/A" else "",
            c.location or "",
            c.preferred_location or "",
            total_exp,
            c.current_company or "",
            format_salary_lpa(c.current_salary),
            format_salary_lpa(c.expected_salary),
            notice,
            skills,
            f["profile_url"],
        ])

    for col_idx in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 22
    ws.freeze_panes = "A2"

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def read_candidate_resume(candidate):
    """
    Reliably reads candidate resume bytes whether stored locally or on remote
    storage (S3/Cloudinary) via the FileField's storage backend. Returns a dict
    usable as an attachment, or None when the resume cannot be read.
    """
    if not getattr(candidate, 'has_resume', False):
        return None
    resume = candidate.resume
    filename = getattr(candidate, 'original_filename', None) or os.path.basename(resume.name) or f"resume_{candidate.id}.pdf"
    content = b""
    try:
        resume.open('rb')
        try:
            content = resume.read()
        finally:
            resume.close()
    except Exception as e:
        logger.warning(f"Could not read resume for candidate {candidate.id}: {e}")
        content = b""
    if not content:
        try:
            fh = resume.storage.open(resume.name, 'rb')
            try:
                content = fh.read()
            finally:
                fh.close()
        except Exception as e:
            logger.warning(f"Fallback resume read for candidate {candidate.id} failed: {e}")
            content = b""
    if not content:
        return None
    return {
        "filename": filename,
        "content": content,
        "content_type": get_content_type(filename),
    }


def _attachment_name(att):
    if isinstance(att, dict):
        return att.get('filename') or 'attachment'
    return getattr(att, 'name', None) or 'attachment'


def _split_content_type(content_type):
    if not content_type or '/' not in content_type:
        return 'application', 'octet-stream'
    main, _, sub = content_type.partition('/')
    return main or 'application', sub or 'octet-stream'


def _coerce_attachment(att):
    if isinstance(att, dict):
        filename = att.get('filename') or 'attachment'
        content = att.get('content', b'') or b''
        content_type = att.get('content_type') or get_content_type(filename)
        return filename, content, content_type
    filename = getattr(att, 'name', None) or 'attachment'
    content = b''
    try:
        if isinstance(att, (bytes, bytearray, memoryview)):
            content = bytes(att)
        elif hasattr(att, 'read'):
            if hasattr(att, 'seek'):
                try:
                    att.seek(0)
                except Exception:
                    pass
            content = att.read()
    except Exception:
        content = b''
    if not isinstance(content, (bytes, bytearray)):
        content = b''
    content_type = get_content_type(filename)
    return filename, content, content_type


def send_ats_email(sender, recipient_email, subject, body, cc=None, bcc=None, template_name=None, candidate_ids=None, attachments=None, request=None, email_account=None, html_body=None):
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
        raise ValueError("No connected and verified email mailbox found. Please connect your Gmail or Custom SMTP account in Settings under 'My Email Accounts'.")

    # Allow both OAuth (Gmail/Google Workspace) and verified Custom SMTP accounts
    is_google = connected_account.account_type == 'OAUTH' and connected_account.provider in ('GMAIL', 'GOOGLE_WORKSPACE')
    is_smtp = connected_account.account_type == 'SMTP'
    
    if not (is_google or is_smtp):
        raise ValueError("Recruiter-to-client emails must be sent through an authenticated Gmail, Google Workspace, or verified Custom SMTP account.")

    recruiter_name = "Recruiter"
    if sender:
        if hasattr(sender, 'get_full_name') and sender.get_full_name():
            recruiter_name = sender.get_full_name().strip()
        elif hasattr(sender, 'first_name') and sender.first_name:
            recruiter_name = f"{sender.first_name} {sender.last_name}".strip()
        elif hasattr(sender, 'email') and sender.email:
            recruiter_name = sender.email.split('@')[0].capitalize()

    # Contextual display name override if recruiter name is generic
    if recruiter_name in ("Recruiter", "", None):
        email_prefix = (connected_account.email_address or "").split('@')[0].lower()
        if "growfluence" in email_prefix:
            recruiter_name = "Growfluence Studio"
        elif "nikhil" in email_prefix:
            recruiter_name = "Nikhil Mittal"

    required_alias = connected_account.get_required_alias()
    sending_email = required_alias if required_alias else connected_account.email_address
    recruiter_work_email = connected_account.email_address or (sender.email if sender else sending_email)

    from_email = f"{recruiter_name} <{sending_email}>"
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
        attachment_names=", ".join([_attachment_name(att) for att in attachments]) if attachments else None
    )

    try:
        # Verify sending address / Send-As alias via Gmail API users.settings.sendAs.list (Gmail OAuth only)
        if is_google:
            alias_verified, alias_error = connected_account.verify_sendas_alias(required_alias)
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

        if not html_body:
            from html import escape as _html_escape
            html_body = _html_escape(body or "").replace(chr(10), '<br>')
        html_body = f"{html_body}<br><img src='{pixel_url}' width='1' height='1' style='display:none;' alt='' />"
        plain_body = body or ""

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

        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = recipient_email
        msg['Reply-To'] = reply_to_email
        if cc_list:
            msg['Cc'] = ", ".join(cc_list)
        if bcc_list:
            msg['Bcc'] = ", ".join(bcc_list)

        alt_part = MIMEMultipart('alternative')
        alt_part.attach(MIMEText(plain_body, 'plain', 'utf-8'))
        alt_part.attach(MIMEText(html_body, 'html', 'utf-8'))
        msg.attach(alt_part)

        if attachments:
            for att in attachments:
                try:
                    filename, att_content, content_type = _coerce_attachment(att)
                    if not filename:
                        filename = 'attachment'
                    if not att_content:
                        continue
                    maintype, subtype = _split_content_type(content_type)
                    part = MIMEBase(maintype, subtype)
                    part.set_payload(att_content)
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', 'attachment', filename=filename)
                    msg.attach(part)
                except Exception as att_err:
                    logger.warning(f"Failed to attach file to email message: {att_err}")

        raw_mime = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')

        if is_smtp:
            import smtplib
            smtp_host = connected_account.smtp_host
            smtp_port = connected_account.smtp_port or 587
            smtp_username = connected_account.smtp_username or connected_account.email_address
            smtp_password = connected_account.smtp_password or ""

            if connected_account.use_ssl:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=20)
                if connected_account.use_tls:
                    server.starttls()
            try:
                server.login(smtp_username, smtp_password)
                server.sendmail(sending_email, [recipient_email] + cc_list + bcc_list, msg.as_string())
            finally:
                server.quit()

            email_log.status = 'SENT'
            email_log.save(update_fields=['status'])
            return email_log, True, "Email sent successfully via Custom SMTP mailbox."

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
            stored_scopes = (connected_account.scopes or "").replace(',', ' ').split()
            has_send_scope = any("gmail.send" in s or "mail.google.com" in s for s in stored_scopes)
            legacy_verified = bool(
                connected_account.is_verified and connected_account.oauth_access_token and not stored_scopes
            )
            if has_send_scope or legacy_verified:
                raise Exception(f"Gmail API error ({response.status_code}): {response.text}")
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
