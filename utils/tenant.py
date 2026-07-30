from django.db.models import Q
from apps.accounts.models import User
from apps.jobs.models import Job
from apps.clients.models import Client
from apps.applications.models import Application
from apps.candidates.models import CandidateProfile
from apps.interviews.models import Interview

def get_user_company(user):
    """Returns company for recruiter/company_admin user or None."""
    if not user or not user.is_authenticated:
        return None
    try:
        cm = user.company_affiliations.select_related('company').first()
        return cm.company if cm else None
    except Exception:
        return None

def get_tenant_jobs_qs(user):
    """Returns tenant-scoped Job queryset."""
    if not user or not user.is_authenticated:
        return Job.objects.none()
    if user.role == User.Role.SUPER_ADMIN or getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
        return Job.objects.all()
    if user.role == User.Role.CANDIDATE:
        return Job.objects.filter(status='ACTIVE')
    company = get_user_company(user)
    if company:
        return Job.objects.filter(Q(company=company) | Q(created_by=user)).distinct()
    return Job.objects.filter(created_by=user)

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
            Q(created_by=user)
        ).distinct()
    return Client.objects.filter(created_by=user)

def get_tenant_applications_qs(user):
    """Returns tenant-scoped Application queryset."""
    if not user or not user.is_authenticated:
        return Application.objects.none()
    if user.role == User.Role.SUPER_ADMIN or getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
        return Application.objects.all()
    if user.role == User.Role.CANDIDATE:
        return Application.objects.filter(candidate__user=user)
    company = get_user_company(user)
    if company:
        return Application.objects.filter(
            Q(job__company=company) | Q(job__created_by=user) | Q(created_by=user)
        ).distinct()
    return Application.objects.filter(Q(job__created_by=user) | Q(created_by=user)).distinct()

def get_tenant_candidates_qs(user):
    """Returns tenant-scoped CandidateProfile queryset."""
    if not user or not user.is_authenticated:
        return CandidateProfile.objects.none()
    if user.role == User.Role.SUPER_ADMIN or getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
        return CandidateProfile.objects.all()
    if user.role == User.Role.CANDIDATE:
        return CandidateProfile.objects.filter(user=user)
    
    company = get_user_company(user)
    if company:
        # Exclude candidates created by other companies
        other_company_candidates = CandidateProfile.objects.filter(
            Q(created_by__company_affiliations__company__isnull=False) &
            ~Q(created_by__company_affiliations__company=company)
        )
        return CandidateProfile.objects.exclude(id__in=other_company_candidates.values_list('id', flat=True)).distinct()
    
    return CandidateProfile.objects.all()

def get_tenant_interviews_qs(user):
    """Returns tenant-scoped Interview queryset."""
    if not user or not user.is_authenticated:
        return Interview.objects.none()
    if user.role == User.Role.SUPER_ADMIN or getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
        return Interview.objects.all()
    if user.role == User.Role.CANDIDATE:
        return Interview.objects.filter(application__candidate__user=user)
    company = get_user_company(user)
    if company:
        return Interview.objects.filter(
            Q(application__job__company=company) |
            Q(application__job__created_by=user) |
            Q(created_by=user)
        ).distinct()
    return Interview.objects.filter(
        Q(application__job__created_by=user) | Q(created_by=user)
    ).distinct()
