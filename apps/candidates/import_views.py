import logging
import re
import base64
import binascii
import os
from decimal import Decimal
from datetime import date
from django.db import transaction
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.accounts.models import User
from apps.candidates.models import CandidateProfile, CandidateSkill, Experience, Education, Project, Certification
from apps.candidates.utils import make_internal_login_email, parse_date_robust

logger = logging.getLogger(__name__)

def parse_date_range(date_str):
    """
    Parse a date range string like "Jan 2021 - Present" or "Jul 2018 - Dec 2022"
    Returns (start_date_obj, end_date_obj, is_current_bool)
    """
    if not date_str or not isinstance(date_str, str):
        return None, None, False

    clean_str = date_str.strip()
    is_current = "present" in clean_str.lower() or "current" in clean_str.lower()

    # Split by hyphen or en-dash
    parts = [p.strip() for p in clean_str.replace("–", "-").split("-") if p.strip()]
    
    start_date = None
    end_date = None

    if len(parts) >= 1:
        start_date = parse_date_robust(parts[0])

    if len(parts) >= 2:
        end_part = parts[1].split("·")[0].split("•")[0].strip()
        if "present" in end_part.lower() or "current" in end_part.lower():
            is_current = True
            end_date = None
        else:
            end_date = parse_date_robust(end_part)

    return start_date, end_date, is_current

def parse_ctc(val):
    if val is None or val == "":
        return None
    if isinstance(val, (int, float, Decimal)):
        f_val = float(val)
        if f_val <= 0:
            return None
        # Convert LPA to raw INR DB amount if <= 500
        return Decimal(str(int(f_val * 100000))) if f_val <= 500 else Decimal(str(int(f_val)))
    
    clean = re.sub(r'[^\d\.]', '', str(val))
    if not clean:
        return None
    try:
        f_val = float(clean)
        if f_val <= 0:
            return None
        return Decimal(str(int(f_val * 100000))) if f_val <= 500 else Decimal(str(int(f_val)))
    except Exception:
        return None

def parse_notice_period(val):
    if val is None or val == "":
        return 30, False
    if isinstance(val, bool):
        return (0, True) if val else (30, False)
    clean = re.sub(r'[^\d]', '', str(val))
    if not clean:
        return 30, False
    try:
        n = int(clean)
        return (n, n == 0)
    except Exception:
        return 30, False

def parse_total_experience(val, experience_list=None):
    if val is not None and val != "":
        clean = re.sub(r'[^\d\.]', '', str(val))
        if clean:
            try:
                f_val = float(clean)
                if f_val > 0:
                    return Decimal(str(round(f_val, 1)))
            except Exception:
                pass
    
    # Calculate from experience_list if available
    if experience_list and isinstance(experience_list, list):
        total_months = 0
        for exp in experience_list:
            if not isinstance(exp, dict):
                continue
            dur = (exp.get("duration") or exp.get("dates") or "").strip()
            s_dt, e_dt, is_curr = parse_date_range(dur)
            if not s_dt and exp.get("start_date"):
                s_dt = parse_date_robust(str(exp.get("start_date")))
            if not e_dt and exp.get("end_date"):
                e_dt = parse_date_robust(str(exp.get("end_date")))
            
            if s_dt:
                end_check = e_dt or date.today()
                months = (end_check.year - s_dt.year) * 12 + (end_check.month - s_dt.month)
                if months > 0:
                    total_months += months
        if total_months > 0:
            years = round(total_months / 12.0, 1)
            return Decimal(str(years))

    return Decimal("0.0")

EMPLOYMENT_TYPE_MAP = {
    'fulltime': 'Full-time', 'full time': 'Full-time', 'full-time': 'Full-time',
    'permanent': 'Full-time',
    'parttime': 'Part-time', 'part time': 'Part-time', 'part-time': 'Part-time',
    'contract': 'Contract', 'contractual': 'Contract',
    'freelance': 'Freelance', 'selfemployed': 'Freelance', 'self employed': 'Freelance', 'self-employed': 'Freelance',
    'internship': 'Internship', 'intern': 'Internship',
    'temporary': 'Temporary', 'temp': 'Temporary',
    'volunteer': 'Volunteer',
}

def normalize_employment_type(val):
    if not val:
        return ""
    key = re.sub(r'[\s\-]+', '', str(val)).lower()
    return EMPLOYMENT_TYPE_MAP.get(key, str(val).strip()[:50])

RESUME_ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.rtf', '.txt'}

def _save_attached_resume(profile, resume_payload, user):
    """
    Optionally attach a resume that the recruiter chose to include.

    Returns (attached: bool, message: str). Never overwrites an existing resume.
    """
    if not resume_payload or not isinstance(resume_payload, dict):
        return False, ""
    if profile.has_resume:
        return False, "Resume already exists; kept the existing file."

    filename = (resume_payload.get("filename") or resume_payload.get("name") or "").strip()
    ext = os.path.splitext(filename)[1].lower()

    data_b64 = resume_payload.get("data_base64") or resume_payload.get("base64") or resume_payload.get("resume_base64") or ""
    resume_url = (resume_payload.get("resume_url") or resume_payload.get("url") or "").strip()

    # Debug: show exactly what the extension sent so a blob:/data:/oversized URL
    # is immediately visible in the Django terminal (never silently swallowed).
    print(f"RECEIVED RESUME DATA: {resume_url}, BASE64 LENGTH: {len(data_b64) if data_b64 else 0}")
    if resume_url and resume_url.lower().startswith("blob:"):
        print("RESUME URL IS A blob: URL — it is browser-local and CANNOT be saved; skipping resume link.")

    # Fallback: the source portal (e.g. Naukri) blocks scripted download of the
    # resume file, so the extension only has its URL. Store it as a link so the
    # recruiter can still open the resume externally.
    if not data_b64:
        if resume_url:
            # blob:/data: URLs are local to the browser and cannot be opened by
            # anyone else. Never persist them (and never crash on their length).
            if resume_url.lower().startswith(("blob:", "data:")):
                return False, "Resume URL is browser-local (blob:/data:) and cannot be saved as a link."
            try:
                profile.source_resume_url = resume_url
                profile.save(update_fields=["source_resume_url"])
                return True, "Resume saved as a link (file download was blocked by the source portal)."
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Resume URL save failed: %s", exc)
                return False, "Resume link save failed."
        return False, "No resume data provided; skipped attachment."

    if ext not in RESUME_ALLOWED_EXTENSIONS:
        return False, "Unsupported resume file type; skipped attachment."

    try:
        raw = base64.b64decode(data_b64, validate=True)
    except (binascii.Error, ValueError):
        return False, "Invalid resume data; skipped attachment."

    if not raw:
        return False, "Empty resume data; skipped attachment."

    # Reasonable size guard (15 MB).
    if len(raw) > 15 * 1024 * 1024:
        return False, "Resume too large; skipped attachment."

    # Validate the file content matches its declared type. A .pdf file must
    # start with the "%PDF-" signature; trusting only the filename is not enough.
    if ext == ".pdf" and not raw.startswith(b"%PDF-"):
        return False, "Invalid PDF content; skipped attachment."

    if not filename:
        filename = "Candidate_Resume" + (ext or ".pdf")

    from django.core.files.base import ContentFile
    from services.resume_storage_service import save_candidate_resume_atomic, ResumeUploadError

    try:
        save_candidate_resume_atomic(
            profile,
            ContentFile(raw, name=filename),
            original_filename=filename,
            is_replacement=False,
            user=user,
        )
        return True, "Resume attached successfully."
    except ResumeUploadError as exc:
        logger.warning("Resume attachment failed: %s", exc)
        return False, str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Resume attachment failed unexpectedly: %s", exc)
        return False, "Resume attachment failed."

@method_decorator(csrf_exempt, name="dispatch")
class CandidateImportAPIView(APIView):
    """
    API endpoint for candidate import from TalentVault Chrome Extension (LinkedIn, Naukri, Manual).
    Accepts normalized candidate JSON data, checks for existing duplicate candidate profiles by email,
    phone, or profile URL, and creates/updates CandidateProfile, Experience, Education, and CandidateSkill.
    """
    permission_classes = [permissions.AllowAny]
    # This public endpoint is called by the Chrome extension (both the packaged
    # production build and an unpacked local build). We intentionally run NO
    # authentication/session classes here so DRF's SessionAuthentication never
    # triggers its CSRF check against the extension's chrome-extension:// origin
    # (a locally loaded extension has a random ID that cannot be listed in
    # CSRF_TRUSTED_ORIGINS). The view is also marked csrf_exempt above.
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        csrf_token = get_token(request)
        return Response({
            "status": "ok",
            "csrfToken": csrf_token,
            "message": "TalentVault Candidate Importer API is active."
        }, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        data = request.data
        if not data:
            return Response({"error": "Empty payload"}, status=status.HTTP_400_BAD_REQUEST)

        # Support both CRM Structured Resume Editor schema (nested personal_info)
        # and extension flat schema for backward compatibility.
        info = data.get("personal_info") if isinstance(data.get("personal_info"), dict) else {}

        name = (info.get("name") or data.get("full_name") or data.get("name") or "").strip()
        headline = (info.get("current_designation") or data.get("current_designation") or data.get("headline") or "").strip()
        current_company_in = (info.get("current_company") or data.get("current_company") or "").strip()
        location = (info.get("location") or data.get("location") or "").strip()
        summary = (data.get("summary") or data.get("about") or info.get("summary") or "").strip()
        experience_list = data.get("experience") or []
        education_list = data.get("education") or []
        projects_list = data.get("projects") or []
        certifications_list = data.get("certifications") or []
        skills_list = data.get("skills") or []
        profile_url = (info.get("profile_url") or data.get("linkedin_url") or data.get("profile_url") or "").strip()
        email = (info.get("email") or data.get("email") or "").strip()
        phone = (info.get("phone") or data.get("phone") or "").strip()
        source = (data.get("source") or "").strip()

        # Numeric fields
        raw_total_exp = info.get("total_experience") if "total_experience" in info else data.get("total_experience")
        total_exp = parse_total_experience(raw_total_exp, experience_list)
        raw_current_sal = info.get("current_salary") if "current_salary" in info else (data.get("current_salary") or data.get("current_ctc"))
        current_sal = parse_ctc(raw_current_sal)
        raw_expected_sal = info.get("expected_salary") if "expected_salary" in info else (data.get("expected_salary") or data.get("expected_ctc"))
        expected_sal = parse_ctc(raw_expected_sal)
        raw_notice = info.get("notice_period") if "notice_period" in info else data.get("notice_period")
        notice_period, is_immediate = parse_notice_period(raw_notice)
        if data.get("is_immediate_joiner") is not None:
            is_immediate = bool(data.get("is_immediate_joiner"))

        if not source:
            if "linkedin.com" in profile_url.lower():
                source = "linkedin"
            elif "naukri.com" in profile_url.lower():
                source = "naukri"
            else:
                source = "web_import"

        # Resolve the importing recruiter so "Uploaded By" shows the real person.
        # The extension sends the logged-in recruiter's email; fall back to the
        # (authenticated) request.user, then to None (rendered as "System Import").
        uploaded_by_email = (data.get("uploaded_by_email") or info.get("uploaded_by_email") or "").strip()
        uploaded_by = None
        if uploaded_by_email:
            uploaded_by = User.objects.filter(email__iexact=uploaded_by_email).first()
        if uploaded_by is None and request.user and request.user.is_authenticated:
            uploaded_by = request.user

        # 1. Duplicate detection
        existing_profile = None

        if email:
            existing_user = User.objects.filter(email__iexact=email).first()
            if existing_user and hasattr(existing_user, 'candidate_profile'):
                existing_profile = existing_user.candidate_profile

        if not existing_profile and phone:
            existing_user = User.objects.filter(phone_number=phone).first()
            if existing_user and hasattr(existing_user, 'candidate_profile'):
                existing_profile = existing_user.candidate_profile

        if not existing_profile and profile_url:
            full_url = profile_url.strip()
            # 1. Match the FULL canonical URL first. This is essential for Naukri
            #    Resdex, where the unique candidate id lives in the query string
            #    (e.g. https://resdex.naukri.com/v3/preview?profileId=123). If we
            #    stripped the query there, every Naukri candidate would share the
            #    same "/v3/preview" path and a new candidate would be wrongly
            #    "updated" onto a previously imported profile.
            existing_profile = (
                CandidateProfile.objects.filter(linkedin_url__iexact=full_url).first()
                or CandidateProfile.objects.filter(portfolio_url__iexact=full_url).first()
            )
            # 2. LinkedIn's unique id is in the path (/in/<slug>), so a path-only
            #    fallback is safe there (it ignores tracking query params).
            if not existing_profile and "naukri" not in full_url.lower():
                path_only = full_url.split("?")[0].split("#")[0].rstrip("/")
                existing_profile = (
                    CandidateProfile.objects.filter(linkedin_url__icontains=path_only).first()
                    or CandidateProfile.objects.filter(portfolio_url__icontains=path_only).first()
                )

        action = "created"
        with transaction.atomic():
            if existing_profile:
                profile = existing_profile
                action = "updated"
                if name and not profile.full_name:
                    profile.full_name = name
                if headline and not profile.current_designation:
                    profile.current_designation = headline
                if current_company_in and not profile.current_company:
                    profile.current_company = current_company_in
                if location and (not profile.location or profile.location == "Unknown"):
                    profile.location = location
                if summary and not profile.summary:
                    profile.summary = summary
                if total_exp > 0:
                    profile.total_experience = total_exp
                if current_sal is not None:
                    profile.current_salary = current_sal
                if expected_sal is not None:
                    profile.expected_salary = expected_sal
                if raw_notice is not None:
                    profile.notice_period = notice_period
                    profile.is_immediate_joiner = is_immediate
                if source:
                    profile.source = source
                if profile_url:
                    if "linkedin" in profile_url.lower() and not profile.linkedin_url:
                        profile.linkedin_url = profile_url
                    elif not profile.portfolio_url and "linkedin" not in profile_url.lower():
                        profile.portfolio_url = profile_url
                if uploaded_by and not profile.uploaded_by:
                    profile.uploaded_by = uploaded_by
                profile.save()
            else:
                # Create user & profile
                if email:
                    login_email = email
                else:
                    seed = name or profile_url or "extension_import"
                    login_email = make_internal_login_email(seed)

                user, created_user = User.objects.get_or_create(
                    email=login_email,
                    defaults={
                        'role': User.Role.CANDIDATE,
                        'phone_number': phone if phone else None
                    }
                )
                if created_user:
                    user.set_unusable_password()
                    user.save()

                first_company = current_company_in
                first_designation = headline
                if experience_list and isinstance(experience_list, list) and len(experience_list) > 0:
                    exp_0 = experience_list[0]
                    if isinstance(exp_0, dict):
                        if not first_company:
                            first_company = (exp_0.get("company_name") or exp_0.get("company") or "").strip()
                        if not first_designation:
                            first_designation = (exp_0.get("designation") or exp_0.get("title") or "").strip()

                is_linkedin = "linkedin" in profile_url.lower() or source == "linkedin"
                profile = CandidateProfile.objects.create(
                    user=user,
                    full_name=name or "Imported Candidate",
                    summary=summary,
                    current_designation=first_designation[:255] if first_designation else None,
                    current_company=first_company[:255] if first_company else None,
                    location=location[:100] if location else "Not Specified",
                    total_experience=total_exp,
                    current_salary=current_sal,
                    expected_salary=expected_sal,
                    notice_period=notice_period,
                    is_immediate_joiner=is_immediate,
                    linkedin_url=profile_url[:200] if is_linkedin and profile_url else None,
                    portfolio_url=profile_url[:200] if not is_linkedin and profile_url else None,
                    source=source,
                    uploaded_by=uploaded_by,
                    created_by=uploaded_by,
                )

            # Create/Update Experience records
            if isinstance(experience_list, list):
                for exp in experience_list:
                    if isinstance(exp, dict):
                        c_name = (exp.get("company_name") or exp.get("company") or "").strip()
                        desig = (exp.get("designation") or exp.get("title") or "").strip()
                        desc = (exp.get("description") or "").strip()
                        loc = (exp.get("location") or "").strip()
                        emp_type = normalize_employment_type(exp.get("employment_type") or exp.get("employmentType") or "")
                        dur = (exp.get("duration") or exp.get("dates") or "").strip()

                        start_dt, end_dt, is_curr = parse_date_range(dur)
                        if not start_dt and exp.get("start_date"):
                            start_dt = parse_date_robust(str(exp.get("start_date")))
                        if not end_dt and exp.get("end_date"):
                            end_dt = parse_date_robust(str(exp.get("end_date")))
                        if exp.get("is_current") is not None:
                            is_curr = bool(exp.get("is_current"))

                        if c_name or desig:
                            Experience.objects.update_or_create(
                                profile=profile,
                                company_name=c_name[:255],
                                designation=desig[:255],
                                start_date=start_dt,
                                end_date=end_dt,
                                defaults={
                                    'employment_type': emp_type,
                                    'location': loc[:255],
                                    'description': desc,  # Full description preserved
                                    'is_current': is_curr
                                }
                            )

            # Create/Update Education records
            if isinstance(education_list, list):
                for edu in education_list:
                    if isinstance(edu, dict):
                        inst = (edu.get("institution") or edu.get("school") or "").strip()
                        deg = (edu.get("degree") or "").strip()
                        field = (edu.get("field_of_study") or edu.get("field") or "").strip()
                        dur = (edu.get("dates") or edu.get("duration") or "").strip()

                        start_dt, end_dt, _ = parse_date_range(dur)
                        if not start_dt and edu.get("start_date"):
                            start_dt = parse_date_robust(str(edu.get("start_date")))
                        if not end_dt and edu.get("end_date"):
                            end_dt = parse_date_robust(str(edu.get("end_date")))

                        if inst or deg:
                            Education.objects.update_or_create(
                                profile=profile,
                                institution=inst[:255],
                                degree=deg[:255],
                                start_date=start_dt,
                                end_date=end_dt,
                                defaults={
                                    'field_of_study': field[:255] if field else None,
                                }
                            )

            # Create/Update Project records
            if isinstance(projects_list, list):
                for proj in projects_list:
                    if isinstance(proj, dict):
                        title = (proj.get("title") or proj.get("name") or "").strip()
                        desc = (proj.get("description") or "").strip()
                        link = (proj.get("link") or proj.get("url") or "").strip()
                        role = (proj.get("role") or "").strip()
                        if role and not desc.startswith(f"Role: {role}"):
                            desc = f"Role: {role}\n{desc}".strip() if desc else f"Role: {role}"

                        if title:
                            Project.objects.update_or_create(
                                profile=profile,
                                title=title[:255],
                                defaults={
                                    'description': desc,
                                    'link': link or None,
                                }
                            )

            # Create/Update Certification records
            if isinstance(certifications_list, list):
                for cert in certifications_list:
                    if isinstance(cert, dict):
                        c_name = (cert.get("name") or cert.get("title") or "").strip()
                        org = (cert.get("issuing_organization") or cert.get("issuer") or cert.get("organization") or "").strip()
                        date_raw = cert.get("issue_date") or cert.get("date") or ""
                        issue_dt = parse_date_robust(str(date_raw)) if date_raw else None

                        if c_name:
                            Certification.objects.update_or_create(
                                profile=profile,
                                name=c_name[:255],
                                defaults={
                                    'issuing_organization': org[:255] if org else None,
                                    'issue_date': issue_dt,
                                }
                            )

            # Create/Update Skill records
            if isinstance(skills_list, list):
                for s in skills_list:
                    if isinstance(s, str):
                        s_clean = s.strip()
                    elif isinstance(s, dict):
                        s_clean = (s.get("skill_name") or s.get("name") or "").strip()
                    else:
                        s_clean = ""

                    if s_clean:
                        CandidateSkill.objects.get_or_create(
                            profile=profile,
                            skill_name=s_clean[:100]
                        )

            # Synchronize canonical parsed_json so the Structured Resume Editor displays all data
            canonical_parsed_json = {
                "personal_info": {
                    "name": profile.full_name or name,
                    "email": email or (profile.user.email if profile.user and "@" in profile.user.email and not profile.user.email.endswith("@internal.talentvault.local") else ""),
                    "phone": phone or (profile.user.phone_number if profile.user else ""),
                    "location": profile.location or location,
                    "current_company": profile.current_company or current_company_in,
                    "current_designation": profile.current_designation or headline,
                    "total_experience": float(profile.total_experience) if profile.total_experience is not None else 0.0,
                    "current_salary": float(profile.current_salary / 100000) if profile.current_salary else 0.0,
                    "expected_salary": float(profile.expected_salary / 100000) if profile.expected_salary else 0.0,
                    "notice_period": profile.notice_period,
                    "profile_url": profile.linkedin_url or profile.portfolio_url or profile_url,
                },
                "summary": profile.summary or summary,
                "skills": [s.skill_name for s in profile.skills.all()] if profile.skills.exists() else skills_list,
                "experience": [
                    {
                        "company": exp.company_name,
                        "designation": exp.designation,
                        "employment_type": exp.employment_type or "",
                        "start_date": exp.start_date.isoformat() if exp.start_date else "",
                        "end_date": exp.end_date.isoformat() if exp.end_date else ("Present" if exp.is_current else ""),
                        "duration": (f"{exp.start_date.strftime('%b %Y')} - Present" if exp.is_current and exp.start_date else "") or "",
                        "location": exp.location or "",
                        "description": exp.description or "",
                    }
                    for exp in profile.experiences.all()
                ],
                "education": [
                    {
                        "institution": edu.institution,
                        "degree": edu.degree,
                        "field_of_study": edu.field_of_study or "",
                        "start_date": edu.start_date.isoformat() if edu.start_date else "",
                        "end_date": edu.end_date.isoformat() if edu.end_date else "",
                    }
                    for edu in profile.educations.all()
                ],
                "projects": [
                    {
                        "title": proj.title,
                        "description": proj.description or "",
                        "link": proj.link or "",
                    }
                    for proj in profile.projects.all()
                ],
                "certifications": [
                    {
                        "name": cert.name,
                        "issuing_organization": cert.issuing_organization or "",
                        "issue_date": cert.issue_date.isoformat() if cert.issue_date else "",
                    }
                    for cert in profile.certifications.all()
                ],
            }
            profile.parsed_json = canonical_parsed_json
            profile.save(update_fields=['parsed_json'])

            # Optionally attach a resume chosen by the recruiter. This never
            # overwrites an existing resume and never fails the whole import.
            resume_attached, resume_message = _save_attached_resume(
                profile,
                data.get("resume"),
                user=request.user if request.user.is_authenticated else None,
            )

        return Response({
            "status": "success",
            "action": action,
            "candidate_id": str(profile.id),
            "resume_attached": resume_attached,
            "resume_message": resume_message,
            "candidate": {
                "id": str(profile.id),
                "name": profile.full_name,
                "headline": profile.current_designation,
                "current_company": profile.current_company,
                "location": profile.location,
                "total_experience": float(profile.total_experience),
                "current_salary": float(profile.current_salary) if profile.current_salary else None,
                "expected_salary": float(profile.expected_salary) if profile.expected_salary else None,
                "notice_period": profile.notice_period,
                "source": profile.source,
                "profile_url": profile.linkedin_url or profile.portfolio_url,
                "skills_count": profile.skills.count(),
                "experiences_count": profile.experiences.count(),
                "educations_count": profile.educations.count(),
                "projects_count": profile.projects.count(),
                "certifications_count": profile.certifications.count(),
            }
        }, status=status.HTTP_201_CREATED if action == "created" else status.HTTP_200_OK)
