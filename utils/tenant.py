from django.db.models import Q
from apps.accounts.models import User
from apps.jobs.models import Job
from apps.clients.models import Client
from apps.applications.models import Application
from apps.candidates.models import CandidateProfile
from apps.interviews.models import Interview

def get_user_company(user):
    """Returns company for recruiter/company_admin user or None (cached per request/user instance)."""
    if not user or not user.is_authenticated:
        return None
    if hasattr(user, '_cached_company'):
        return user._cached_company
    try:
        cm = user.company_affiliations.select_related('company').first()
        user._cached_company = cm.company if cm else None
    except Exception:
        user._cached_company = None
    return user._cached_company

def is_admin_user(user):
    """Returns True when the user belongs to the Admin portal (Super Admin / staff / superuser)."""
    if not user or not user.is_authenticated:
        return False
    return (
        getattr(user, 'role', None) == User.Role.SUPER_ADMIN
        or getattr(user, 'is_superuser', False)
        or getattr(user, 'is_staff', False)
    )


def admin_created_jobs_q():
    """
    Q object matching jobs created by an Admin portal user or unassigned/system jobs.
    Admin-created jobs must never be visible to External Recruiters.
    """
    return (
        Q(created_by__role=User.Role.SUPER_ADMIN) |
        Q(created_by__is_superuser=True) |
        Q(created_by__is_staff=True) |
        Q(created_by__isnull=True)
    )


def get_tenant_jobs_qs(user):
    """
    Returns tenant-scoped Job queryset.

    Visibility rules:
    - Admin users see every job (including external-recruiter-created jobs).
    - Candidates/guests see active jobs only.
    - External Recruiters/Company Admins see jobs owned by them or shared through
      their existing company relationship (if in an established company, not Default Company),
      but never jobs created by Admin users or unassigned/system jobs.
    """
    if not user or not user.is_authenticated:
        return Job.objects.none()
    if is_admin_user(user):
        return Job.objects.all()
    if user.role == User.Role.CANDIDATE:
        return Job.objects.filter(status='ACTIVE')
    company = get_user_company(user)
    if company and company.slug not in ['default-company', ''] and company.name.lower() not in ['default company', 'default']:
        qs = Job.objects.filter(
            Q(created_by=user) |
            Q(created_by__company_affiliations__company=company)
        )
    else:
        qs = Job.objects.filter(created_by=user)
    # Admin-created jobs must stay hidden from the external recruiter portal.
    return qs.exclude(admin_created_jobs_q()).distinct()

def get_tenant_clients_qs(user):
    """Returns tenant-scoped Client queryset."""
    if not user or not user.is_authenticated:
        return Client.objects.none()
    if user.role == User.Role.SUPER_ADMIN or getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
        return Client.objects.all()
    company = get_user_company(user)
    if company:
        return Client.objects.filter(
            Q(created_by__company_affiliations__company=company) |
            Q(jobs__company=company) |
            Q(created_by=user) |
            Q(created_by__isnull=True)
        ).distinct()
    return Client.objects.filter(Q(created_by=user) | Q(created_by__isnull=True))

def get_tenant_applications_qs(user):
    """Returns tenant-scoped Application queryset."""
    if not user or not user.is_authenticated:
        return Application.objects.none()
    if user.role == User.Role.SUPER_ADMIN or getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
        return Application.objects.all()
    if user.role == User.Role.CANDIDATE:
        return Application.objects.filter(candidate__user=user)
    
    recruiter_jobs = get_tenant_jobs_qs(user)
    return Application.objects.filter(
        Q(job__in=recruiter_jobs) | Q(created_by=user)
    ).exclude(
        job__in=Job.objects.filter(admin_created_jobs_q())
    ).distinct()

def get_tenant_candidates_qs(user):
    """Returns tenant-scoped CandidateProfile queryset."""
    if not user or not user.is_authenticated:
        return CandidateProfile.objects.none()
    if is_admin_user(user):
        return CandidateProfile.objects.all()
    if user.role == User.Role.CANDIDATE:
        return CandidateProfile.objects.filter(user=user)
    
    company = get_user_company(user)
    if company:
        return CandidateProfile.objects.filter(
            Q(created_by__company_affiliations__company=company) |
            Q(created_by__company_affiliations__company__isnull=True) |
            Q(created_by__isnull=True)
        ).distinct()
    
    return CandidateProfile.objects.all()


def candidate_owner_user(candidate):
    """
    Returns the canonical owner of a candidate profile using the existing
    uploader/creator attribution, or None when the candidate is unattributed.
    """
    if candidate is None:
        return None
    return candidate.uploaded_by or candidate.created_by


def can_edit_candidate(user, candidate):
    """
    Whether `user` may edit / structured-edit a candidate profile.

    - Admin portal users (Super Admin / staff / superuser) may edit any candidate.
    - A candidate may edit their own profile.
    - External Recruiters / Company Admins may edit only candidates they
      uploaded or created themselves.
    """
    if not user or not user.is_authenticated:
        return False
    if is_admin_user(user):
        return True
    if candidate is None:
        return False
    if getattr(candidate, 'user_id', None) == user.id:
        return True
    return (
        getattr(candidate, 'uploaded_by_id', None) == user.id
        or getattr(candidate, 'created_by_id', None) == user.id
    )


def get_editable_candidates_qs(user):
    """CandidateProfile queryset the user may edit / structured-edit."""
    if not user or not user.is_authenticated:
        return CandidateProfile.objects.none()
    if is_admin_user(user):
        return CandidateProfile.objects.all()
    if user.role == User.Role.CANDIDATE:
        return CandidateProfile.objects.filter(user=user)
    return get_tenant_candidates_qs(user).filter(
        Q(uploaded_by=user) | Q(created_by=user) | Q(user=user)
    ).distinct()


def get_deletable_candidates_qs(user):
    """
    CandidateProfile queryset the user may delete.
    Only Admin portal users can delete candidates; external recruiters never can.
    """
    if not user or not user.is_authenticated:
        return CandidateProfile.objects.none()
    if is_admin_user(user):
        return CandidateProfile.objects.all()
    return CandidateProfile.objects.none()


def get_deletable_jobs_qs(user):
    """
    Job queryset the user may delete.
    Only Admin portal users can delete jobs; external recruiters never can.
    """
    if not user or not user.is_authenticated:
        return Job.objects.none()
    if is_admin_user(user):
        return Job.objects.all()
    return Job.objects.none()


def get_tenant_interviews_qs(user):
    """Returns tenant-scoped Interview queryset."""
    if not user or not user.is_authenticated:
        return Interview.objects.none()
    if is_admin_user(user):
        return Interview.objects.all()
    if user.role == User.Role.CANDIDATE:
        return Interview.objects.filter(application__candidate__user=user)
    
    recruiter_jobs = get_tenant_jobs_qs(user)
    return Interview.objects.filter(
        Q(application__job__in=recruiter_jobs) | Q(created_by=user)
    ).exclude(
        application__job__in=Job.objects.filter(admin_created_jobs_q())
    ).distinct()
