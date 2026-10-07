import logging
import re
from decimal import Decimal
from datetime import date
from django.db import transaction
from django.middleware.csrf import get_token
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.accounts.models import User
from apps.candidates.models import CandidateProfile, CandidateSkill, Experience, Education
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

class CandidateImportAPIView(APIView):
    """
    API endpoint for candidate import from TalentVault Chrome Extension (LinkedIn, Naukri, Manual).
    Accepts normalized candidate JSON data, checks for existing duplicate candidate profiles by email,
    phone, or profile URL, and creates/updates CandidateProfile, Experience, Education, and CandidateSkill.
    """
    permission_classes = [permissions.AllowAny]

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

        name = (data.get("full_name") or data.get("name") or "").strip()
        headline = (data.get("current_designation") or data.get("headline") or "").strip()
        current_company_in = (data.get("current_company") or "").strip()
        location = (data.get("location") or "").strip()
        summary = (data.get("summary") or data.get("about") or "").strip()
        experience_list = data.get("experience") or []
        education_list = data.get("education") or []
        skills_list = data.get("skills") or []
        profile_url = (data.get("linkedin_url") or data.get("profile_url") or "").strip()
        email = (data.get("email") or "").strip()
        phone = (data.get("phone") or "").strip()
        source = (data.get("source") or "").strip()

        # Numeric fields
        total_exp = parse_total_experience(data.get("total_experience"), experience_list)
        current_sal = parse_ctc(data.get("current_salary") or data.get("current_ctc"))
        expected_sal = parse_ctc(data.get("expected_salary") or data.get("expected_ctc"))
        notice_period, is_immediate = parse_notice_period(data.get("notice_period"))
        if data.get("is_immediate_joiner") is not None:
            is_immediate = bool(data.get("is_immediate_joiner"))

        if not source:
            if "linkedin.com" in profile_url.lower():
                source = "linkedin"
            elif "naukri.com" in profile_url.lower():
                source = "naukri"
            else:
                source = "web_import"

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
            clean_url = profile_url.split("?")[0].rstrip("/")
            existing_profile = CandidateProfile.objects.filter(
                linkedin_url__icontains=clean_url
            ).first() or CandidateProfile.objects.filter(
                portfolio_url__icontains=clean_url
            ).first()

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
                if data.get("notice_period") is not None:
                    profile.notice_period = notice_period
                    profile.is_immediate_joiner = is_immediate
                if source:
                    profile.source = source
                if profile_url:
                    if "linkedin" in profile_url.lower() and not profile.linkedin_url:
                        profile.linkedin_url = profile_url
                    elif not profile.portfolio_url and "linkedin" not in profile_url.lower():
                        profile.portfolio_url = profile_url
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
                    parsed_json=data
                )

            # Create/Update Experience records
            if isinstance(experience_list, list):
                for exp in experience_list:
                    if isinstance(exp, dict):
                        c_name = (exp.get("company_name") or exp.get("company") or "").strip()
                        desig = (exp.get("designation") or exp.get("title") or "").strip()
                        desc = (exp.get("description") or "").strip()
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
                                company_name=c_name[:255] if c_name else "Not Specified",
                                designation=desig[:255] if desig else "Not Specified",
                                defaults={
                                    'description': desc,  # Full description preserved
                                    'start_date': start_dt,
                                    'end_date': end_dt,
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
                                institution=inst[:255] if inst else "Not Specified",
                                degree=deg[:255] if deg else "Not Specified",
                                defaults={
                                    'field_of_study': field[:255] if field else None,
                                    'start_date': start_dt,
                                    'end_date': end_dt
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

        return Response({
            "status": "success",
            "action": action,
            "candidate_id": str(profile.id),
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
                "educations_count": profile.educations.count()
            }
        }, status=status.HTTP_201_CREATED if action == "created" else status.HTTP_200_OK)
