import os
import random
import json
import logging
from decimal import Decimal
from datetime import datetime
from django.http import JsonResponse, HttpResponse, FileResponse, Http404
from django.views.generic import TemplateView, ListView, DetailView, View, CreateView, UpdateView, DeleteView
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.db import transaction
from django.db.models import Count, Q, Avg, Prefetch
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from apps.accounts.models import User
from apps.jobs.models import Job
from apps.jobs.forms import JobForm
from apps.candidates.models import (
    CandidateProfile, DuplicateResumeLog, CandidateSkill, Experience, Education, Project, Certification
)
from apps.applications.models import Application
from apps.interviews.models import Interview
from apps.notifications.models import Notification
from apps.companies.models import CompanyMember, Company
from .permissions import SuperAdminRequiredMixin, RecruiterRequiredMixin, CandidateRequiredMixin
from services.resume_intelligence import ResumeIntelligenceService
from services.candidate_matching_service import CandidateMatchingService
from utils.tenant import (
    get_user_company,
    get_tenant_jobs_qs,
    get_tenant_clients_qs,
    get_tenant_applications_qs,
    get_tenant_candidates_qs,
    get_tenant_interviews_qs,
)

from apps.core.models import Location
from services.location_service import LocationService

logger = logging.getLogger(__name__)

class LocationSearchView(View):
    def get(self, request, *args, **kwargs):
        q = request.GET.get('q', '').strip()
        
        # Fetch real distinct locations from published/active jobs in database
        db_locations = Job.objects.filter(status='ACTIVE') \
            .exclude(location__isnull=True) \
            .exclude(location='') \
            .values_list('location', flat=True) \
            .distinct()
            
        results = []
        seen = set()
        
        for loc in db_locations:
            clean_loc = loc.strip()
            if not clean_loc:
                continue
                
            if clean_loc.islower():
                clean_loc = clean_loc.title()
                
            base_city = clean_loc.split(',')[0].strip()
            
            if not q or q.lower() in clean_loc.lower() or q.lower() in base_city.lower():
                norm_key = base_city.lower()
                if norm_key not in seen:
                    seen.add(norm_key)
                    results.append({
                        'id': clean_loc,
                        'name': clean_loc,
                        'text': clean_loc
                    })
                    
        return JsonResponse({'results': results})

class DashboardView(TemplateView):
    template_name = 'dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_jobs_count'] = Job.objects.filter(status='ACTIVE').count()
        context['total_applications_count'] = Application.objects.count()
        context['interviews_today_count'] = Interview.objects.filter(start_time__date=timezone.now().date()).count()
        context['hires_this_month_count'] = Application.objects.filter(stage='HIRED', updated_at__month=timezone.now().month).count()
        context['recent_activity'] = Notification.objects.all()[:5]
        return context

class LandingPageView(TemplateView):
    template_name = 'landing.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if request.user.role == User.Role.CANDIDATE:
                return redirect('frontend:candidate_dashboard')
            elif request.user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN, User.Role.SUPER_ADMIN]:
                return redirect('frontend:recruiter_dashboard')
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from collections import Counter
        
        # Generate Popular Searches dynamically from REAL active jobs in database
        active_jobs = Job.objects.filter(status='ACTIVE').prefetch_related('skills')
        terms_counter = Counter()
        
        for job in active_jobs:
            if job.title and job.title.strip():
                t = job.title.strip()
                terms_counter[t.title() if t.islower() else t] += 3
            if job.department and job.department.strip():
                d = job.department.strip()
                terms_counter[d.title() if d.islower() else d] += 2
            for sk in job.skills.all():
                if sk.skill_name and sk.skill_name.strip():
                    s = sk.skill_name.strip()
                    terms_counter[s.title() if s.islower() else s] += 2
                    
        popular_chips = []
        for term, _count in terms_counter.most_common(8):
            popular_chips.append({
                'label': term,
                'query': term
            })
            
        context['popular_searches'] = popular_chips
        
        # Deduplicated company dataset with 1 card per company identity
        trusted_dataset = [
            {"name": "ShipGlobal", "industry": "Logistics", "logo": "images/client_logos/shipglobal.png", "website": "https://shipglobal.in/"},
            {"name": "Lumax", "industry": "Automotive", "logo": "images/client_logos/lumax-group.png", "website": "https://www.lumaxworld.in/"},
            {"name": "CARS24", "industry": "Automotive", "logo": "images/client_logos/cars24.png", "website": "https://www.cars24.com/", "sub_label": "FINANCIAL"},
            {"name": "CARS24 Australia", "industry": "Internationally", "logo": "images/client_logos/cars24.png", "website": "https://www.cars24.com/au/", "sub_label": "AUSTRALIA"},
            {"name": "ExpertPanel", "industry": "Internet", "logo": "images/client_logos/expertpanel.svg", "website": "https://www.expertpanel.in/"},
            {"name": "Murugappa", "industry": "Manufacturing", "logo": "images/client_logos/murugappa-group.svg", "website": "https://www.murugappa.com/"},
            {"name": "Vame", "industry": "Internationally", "logo": "images/client_logos/vame.svg", "website": "https://www.vame.in/"},
            {"name": "Scaler Academy", "industry": "Edtech", "logo": "images/client_logos/scaler-academy.svg", "website": "https://www.scaler.com/"},
            {"name": "OYO", "industry": "Hospitality", "logo": "images/client_logos/oyo.png", "website": "https://www.oyorooms.com/"},
            {"name": "Gumlet", "industry": "SaaS", "logo": "images/client_logos/gumlet.svg", "website": "https://www.gumlet.com/"},
            {"name": "Meshr", "industry": "FMCG", "logo": "images/client_logos/meshr.png", "website": "https://www.meshr.in/"},
            {"name": "Alyfy Freight System", "industry": "Logistics", "logo": "images/client_logos/alyf.svg", "website": "https://alyfy.com/"},
            {"name": "Ambak", "industry": "Fintech", "logo": "images/client_logos/ambak.png", "website": "https://ambak.com/"},
            {"name": "ACT Fibernet", "industry": "Internet", "logo": "images/client_logos/act-fibernet.svg", "website": "https://www.actcorp.in/"},
            {"name": "Entri", "industry": "Edtech", "logo": "images/client_logos/entri.svg", "website": "https://entri.app/"},
            {"name": "Zingbus", "industry": "Internet", "logo": "images/client_logos/zingbus.svg", "website": "https://www.zingbus.com/"},
            {"name": "magicpin", "industry": "SaaS", "logo": "images/client_logos/magicpin.svg", "website": "https://magicpin.in/"},
            {"name": "NoBroker Vanguard", "industry": "Real Estate", "logo": "images/client_logos/nobroker.svg", "website": "https://www.nobroker.in/"},
            {"name": "Spinny", "industry": "Automotive", "logo": "images/client_logos/spinny.svg", "website": "https://www.spinny.com/"},
            {"name": "Aye Finance", "industry": "Fintech", "logo": "images/client_logos/ayefinance.svg", "website": "https://www.ayefin.com/"},
            {"name": "Hero Group", "industry": "Automotive", "logo": "images/client_logos/hero-group.svg", "website": "https://www.herogroup.com/"},
            {"name": "Suraasa", "industry": "Edtech", "logo": "images/client_logos/suraasa.svg", "website": "https://www.suraasa.com/"},
            {"name": "redBus", "industry": "Internet", "logo": "images/client_logos/redbus.svg", "website": "https://www.redbus.in/"},
            {"name": "apna", "industry": "Internet", "logo": "images/client_logos/apna.svg", "website": "https://apna.co/"},
            {"name": "QuickShift", "industry": "Logistics", "logo": "images/client_logos/quickshift.svg", "website": "https://quickshift.in/"},
            {"name": "Rane", "industry": "Automotive", "logo": "images/client_logos/rane-group.svg", "website": "https://www.rane.co.in/"},
            {"name": "Truck Loans", "industry": "Fintech", "logo": "images/client_logos/truck-loans.svg", "website": "https://www.truckloans.in/"},
            {"name": "Wired", "industry": "Internet", "logo": "images/client_logos/wired.svg", "website": "https://www.wired.com/"},
            {"name": "CloudFuze", "industry": "SaaS", "logo": "images/client_logos/cloudfuze.svg", "website": "https://www.cloudfuze.com/"},
            {"name": "WheelsEye", "industry": "Logistics", "logo": "images/client_logos/wheelseye.svg", "website": "https://wheelseye.com/"},
            {"name": "DriveX", "industry": "Automotive", "logo": "images/client_logos/drivex.svg", "website": "https://www.drivex.in/"},
            {"name": "IndusInd Bank", "industry": "Fintech", "logo": "images/client_logos/indusind-bank.jpg", "website": "https://www.indusind.com/"},
            {"name": "Justdial", "industry": "Internet", "logo": "images/client_logos/justdial.svg", "website": "https://www.justdial.com/"},
            {"name": "BuyY Commodity", "industry": "Manufacturing", "logo": "images/client_logos/buy-commodity.svg", "website": "https://buyy.com/"},
            {"name": "Netcore", "industry": "SaaS", "logo": "images/client_logos/netcore-software.svg", "website": "https://netcorecloud.com/"},
            {"name": "FleetX.io", "industry": "Logistics", "logo": "images/client_logos/fleetx-io.svg", "website": "https://fleetx.com/"},
            {"name": "Motilal Oswal", "industry": "Fintech", "logo": "images/client_logos/motilal-oswal.svg", "website": "https://www.motilaloswal.com/"},
            {"name": "Unicorn DenMart", "industry": "Internet", "logo": "images/client_logos/unicorn-denmart.svg", "website": "https://unicorndenmart.com/"},
            {"name": "CUMI", "industry": "Manufacturing", "logo": "images/client_logos/cumi.svg", "website": "https://www.cumi-murugappa.com/"},
            {"name": "SmartWinnr", "industry": "SaaS", "logo": "images/client_logos/smartwinnr.svg", "website": "https://smartwinnr.com/"},
            {"name": "TVS", "industry": "Automotive", "logo": "images/client_logos/tvs-group.png", "website": "https://www.tvsmotor.com/"},
            {"name": "Bonanza", "industry": "Fintech", "logo": "images/client_logos/bonanza.svg", "website": "https://www.bonanzaonline.com/"},
            {"name": "Vutto", "industry": "Automotive", "logo": "images/client_logos/vutto.svg", "website": "https://vutto.in/"},
            {"name": "Insurity", "industry": "Fintech", "logo": "images/client_logos/onsurity.svg", "website": "https://insurity.com/"},
            {"name": "TECHXR", "industry": "Internet", "logo": "images/client_logos/techxr.png", "website": "https://techxr.co/"},
            {"name": "91TRUCKS", "industry": "Automotive", "logo": "images/client_logos/91-trucks.svg", "website": "https://www.91trucks.com/"},
            {"name": "EchoVME", "industry": "Internet", "logo": "images/client_logos/echovme.svg", "website": "https://echovme.in/"},
            {"name": "ATI Motors", "industry": "Automotive", "logo": "images/client_logos/ati-motors.svg", "website": "https://atimotors.com/"},
            {"name": "MG / Morris Garages", "industry": "Automotive", "logo": "images/client_logos/mg.svg", "website": "https://www.mgmotor.co.in/"},
            {"name": "Lenskart", "industry": "Retail", "logo": "images/client_logos/lenskart.jpg", "website": "https://www.lenskart.com/"}
        ]
        
        import json
        context['trusted_employers'] = trusted_dataset
        context['trusted_employers_json'] = json.dumps(trusted_dataset)
        
        # Unique ordered list of categories for UI filters
        categories = []
        seen_cats = set()
        for item in trusted_dataset:
            cat = item['industry']
            if cat not in seen_cats:
                seen_cats.add(cat)
                categories.append(cat)
        context['trusted_categories'] = categories
        

        return context



class EmployerLandingView(TemplateView):
    template_name = 'landing_employer.html'

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class RoleRedirectView(LoginRequiredMixin, View):
    """
    Redirect users to their respective dashboards based on their role.
    This is used after login (LOGIN_REDIRECT_URL) to route to the correct dashboard.
    """
    def handle_no_permission(self):
        return redirect('/')

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            user = request.user
            if user.role == User.Role.SUPER_ADMIN or getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
                return redirect('frontend:admin_dashboard')
            elif user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN]:
                return redirect('frontend:recruiter_dashboard')
            elif user.role == User.Role.CANDIDATE:
                return redirect('frontend:candidate_dashboard')
        return redirect('/')

class ShortcutRouteView(View):
    """
    Handles shortcuts like /candidate/, /recruiter/, /admin/.
    If not authenticated, redirects to homepage /.
    If authenticated, redirects to appropriate dashboard.
    """
    def get(self, request, target=None, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/')
        user = request.user
        if user.role == User.Role.SUPER_ADMIN or getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
            return redirect('frontend:admin_dashboard')
        elif user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN]:
            return redirect('frontend:recruiter_dashboard')
        elif user.role == User.Role.CANDIDATE:
            return redirect('frontend:candidate_dashboard')
        return redirect('/')

class CandidateDashboardView(CandidateRequiredMixin, TemplateView):
    template_name = 'candidate_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        from apps.candidates.models import CandidateProfile
        candidate_profile = CandidateProfile.objects.filter(user=user).prefetch_related('skills', 'educations', 'experiences', 'job_applications', 'saved_jobs').first()
        
        if candidate_profile:
            context['candidate_profile'] = candidate_profile
            context['profile_completion_percentage'] = candidate_profile.profile_completion_percentage
            context['has_resume'] = candidate_profile.has_resume
            context['resume_url'] = candidate_profile.resume_file_url
            context['applications_count'] = Application.objects.filter(candidate=candidate_profile).count()
            from apps.candidates.models import SavedJob
            context['saved_jobs_count'] = SavedJob.objects.filter(candidate=candidate_profile).count()
            context['interviews_count'] = Interview.objects.filter(application__candidate=candidate_profile).count()
            
            context['recent_activity'] = list(Notification.objects.filter(recipient=user).order_by('-created_at')[:5])
            context['upcoming_interviews'] = list(Interview.objects.filter(
                application__candidate=candidate_profile, 
                start_time__gte=timezone.now()
            ).select_related('application__job', 'application__job__company').order_by('start_time')[:3])
            
            from services.candidate_matching_service import CandidateMatchingService
            context['recommended_jobs'] = CandidateMatchingService.get_recommended_jobs(candidate_profile, limit=5)
            
            context['applied_job_ids'] = list(candidate_profile.job_applications.values_list('job_id', flat=True))
            context['saved_job_ids'] = list(candidate_profile.saved_jobs.values_list('job_id', flat=True))
        else:
            context['candidate_profile'] = None
            context['profile_completion_percentage'] = 0
            context['has_resume'] = False
            context['resume_url'] = '#'
            context['applications_count'] = 0
            context['saved_jobs_count'] = 0
            context['interviews_count'] = 0
            context['recent_activity'] = []
            context['upcoming_interviews'] = []
            context['recommended_jobs'] = []
            context['applied_job_ids'] = []
            context['saved_job_ids'] = []
            
        context['recruiter_views_count'] = 0
        return context

class RecruiterDashboardView(RecruiterRequiredMixin, TemplateView):
    template_name = 'recruiter_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Detect logged in user role
        is_super_admin = (user.role == User.Role.SUPER_ADMIN) or getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False)
        is_company_admin = (user.role == User.Role.COMPANY_ADMIN)
        is_recruiter = (user.role == User.Role.RECRUITER)
        
        context['is_super_admin'] = is_super_admin
        context['is_company_admin'] = is_company_admin
        context['is_recruiter'] = is_recruiter
        context['user_role'] = user.role
        context['user_role_display'] = "Super Admin" if is_super_admin else ("Company Admin" if is_company_admin else "Recruiter")
        
        context['timezone_now'] = timezone.now()
        from apps.candidates.models import CandidateProfile
        from apps.applications.models import Application
        from apps.notifications.models import EmailLog
        from apps.interviews.models import Interview
        from django.utils import timezone as django_timezone
        from django.db.models import Count, Q, Avg, Prefetch
        
        company_member = user.company_affiliations.select_related('company').first()
        company = company_member.company if company_member else None
        context['company'] = company
        
        jobs_qs = get_tenant_jobs_qs(user)
        apps_qs = get_tenant_applications_qs(user)
        interviews_qs = get_tenant_interviews_qs(user)
        candidates_qs = get_tenant_candidates_qs(user)
        
        context['total_candidates_count'] = candidates_qs.count()
        context['open_jobs_count'] = jobs_qs.filter(status='ACTIVE').count()
        context['open_positions_count'] = context['open_jobs_count']
        context['total_emails_count'] = EmailLog.objects.count()
        
        # New applications count (last 7 days)
        seven_days_ago = django_timezone.now() - django_timezone.timedelta(days=7)
        context['new_applications_count'] = apps_qs.filter(created_at__gte=seven_days_ago).count()
        
        # New applications today count
        today_start = django_timezone.localtime(django_timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0)
        context['applications_today_count'] = apps_qs.filter(created_at__gte=today_start).count()
        context['total_pipeline_count'] = apps_qs.count()
        
        # Interviews scheduled for today
        today_date = django_timezone.now().date()
        context['interviews_today_count'] = interviews_qs.filter(start_time__date=today_date).count()
        
        # Recent Job Openings
        context['recent_jobs'] = jobs_qs.filter(status='ACTIVE').order_by('-created_at')[:5]
        
        # Candidates added over last 7 days (Single aggregated query)
        candidates_by_day = []
        six_days_ago = today_date - django_timezone.timedelta(days=6)
        cand_counts_dict = dict(
            candidates_qs.filter(created_at__date__gte=six_days_ago)
            .values('created_at__date')
            .annotate(cnt=Count('id'))
            .values_list('created_at__date', 'cnt')
        )
        for i in range(6, -1, -1):
            day = today_date - django_timezone.timedelta(days=i)
            count = cand_counts_dict.get(day, 0)
            candidates_by_day.append({
                'day': day.strftime("%a"),
                'count': count
            })
        context['candidates_by_day'] = candidates_by_day
        
        # 1. Total Interviews (Scheduled Interviews)
        context['upcoming_interviews'] = interviews_qs.filter(
            status='SCHEDULED'
        ).select_related('application__candidate__user', 'application__job').order_by('start_time')[:10]
        context['total_interviews_count'] = interviews_qs.filter(status='SCHEDULED').count()
        
        # 2. My Tasks (Recruiter Actionable Items + Admin pending approvals)
        tasks = []
        if is_super_admin:
            pending_rec_count = User.objects.filter(role__in=[User.Role.RECRUITER, User.Role.COMPANY_ADMIN], recruiter_status='PENDING').count()
            if pending_rec_count > 0:
                tasks.append({
                    'title': f"Verify {pending_rec_count} Recruiter Account Registration{'s' if pending_rec_count > 1 else ''}",
                    'subtitle': "Company Verification Pending",
                    'due': "Today",
                    'badge': "Admin Priority",
                    'badge_class': "bg-danger-subtle text-danger",
                    'task_type': 'admin_approval',
                    'object_id': 'pending_recruiters'
                })

        pending_screening = apps_qs.filter(stage__in=['OPEN', 'SYSTEM_SUBMITTED', 'SCREENING_FEEDBACK_PENDING']).select_related('candidate__user', 'job')
        for app in pending_screening:
            tasks.append({
                'title': f"Screen {app.candidate.full_name or app.candidate.user.email}",
                'subtitle': f"For Job: {app.job.title}",
                'due': app.created_at.strftime("%b %d"),
                'badge': "Pending Screen",
                'badge_class': "bg-warning-subtle text-warning",
                'task_type': 'screen',
                'object_id': str(app.id)
            })
            
        for interview in context['upcoming_interviews']:
            tasks.append({
                'title': f"Conduct {interview.round or 'Interview'} with {interview.application.candidate.full_name or interview.application.candidate.user.email}",
                'subtitle': f"Job: {interview.application.job.title}",
                'due': interview.start_time.strftime("%b %d"),
                'badge': "Interview",
                'badge_class': "bg-primary-subtle text-primary",
                'task_type': 'interview',
                'object_id': str(interview.id)
            })
        context['recruiter_tasks'] = tasks
        context['total_tasks_count'] = len(tasks)
        
        # 3. Mails From Candidates (Latest Candidate messages/logs)
        context['candidate_mails'] = EmailLog.objects.all().order_by('-created_at')[:10]
        
        # 4. Applicant Status (Single aggregated query for pipeline stats counts)
        stage_counts_dict = dict(
            apps_qs.values('stage').annotate(cnt=Count('id')).values_list('stage', 'cnt')
        )
        pipeline_counts = []
        for stage_val, stage_label in Application.ApplicationStage.choices:
            count = stage_counts_dict.get(stage_val, 0)
            
            if stage_val == 'OPEN':
                badge_class = 'bg-primary text-white' # blue
            elif stage_val in ['SCREENING_SELECT', 'INTERVIEW_SELECT']:
                badge_class = 'bg-success text-white' # green
            elif stage_val in ['SCREENING_REJECT', 'INTERVIEW_REJECT', 'SYSTEM_REJECTED']:
                badge_class = 'bg-danger text-white' # red
            elif stage_val == 'INTERVIEW_SCHEDULE':
                badge_class = 'bg-warning text-dark' # yellow
            elif stage_val == 'OFFER_STAGE':
                badge_class = 'bg-purple text-white' # purple
            elif stage_val == 'ACCEPTED':
                badge_class = 'bg-teal text-white' # teal
            elif stage_val == 'JOINED':
                badge_class = 'bg-dark-green text-white' # dark green
            elif stage_val == 'DROPOUT':
                badge_class = 'bg-secondary text-white' # gray
            elif stage_val in ['SYSTEM_SELECTED', 'SYSTEM_SUBMITTED', 'INTERVIEW_IN_PROCESS', 'DOCUMENTATION_STAGE', 'NEGOTIATION_STAGE', 'JOINING_CONFIRMATION_REQUESTED', 'JOINING_CONFIRMATION_RECEIVED']:
                badge_class = 'bg-info text-dark'
            else:
                badge_class = 'bg-secondary text-white'
                
            pipeline_counts.append({
                'value': stage_val,
                'label': stage_label,
                'count': count,
                'badge_class': badge_class
            })
        context['pipeline_counts'] = pipeline_counts
        
        # 5. Job Applicants (Active jobs and their applicant counts)
        context['job_applicants'] = jobs_qs.filter(status='ACTIVE').annotate(
            applicant_count=Count('applications'),
            avg_ats_score=Avg('applications__match_score')
        ).order_by('-applicant_count')[:10]
        
        # 6. Candidate Signup Overview Analytics (Single aggregated DB query)
        from utils.date_helpers import format_relative_time, format_registration_date

        now = django_timezone.now()
        local_now = django_timezone.localtime(now)
        today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - django_timezone.timedelta(days=1)
        start_of_week = today_start - django_timezone.timedelta(days=local_now.weekday())
        start_of_month = today_start.replace(day=1)

        signup_stats = candidates_qs.aggregate(
            total=Count('id'),
            today=Count('id', filter=Q(created_at__gte=today_start)),
            yesterday=Count('id', filter=Q(created_at__gte=yesterday_start, created_at__lt=today_start)),
            this_week=Count('id', filter=Q(created_at__gte=start_of_week)),
            mtd=Count('id', filter=Q(created_at__gte=start_of_month))
        )
        context['candidate_signup_stats'] = signup_stats

        # 7. Recent Candidate Activity
        raw_candidates = candidates_qs.select_related('user').prefetch_related(
            Prefetch('job_applications', queryset=apps_qs.select_related('job').order_by('-created_at'), to_attr='latest_applications')
        ).order_by('-created_at')[:10]

        recent_candidate_activity = []
        for candidate in raw_candidates:
            latest_apps = getattr(candidate, 'latest_applications', [])
            latest_app = latest_apps[0] if latest_apps else None
            job_obj = latest_app.job if latest_app else None

            recent_candidate_activity.append({
                'id': candidate.id,
                'name': candidate.full_name or candidate.user.email,
                'email': candidate.user.email,
                'applied_job': job_obj,
                'registered_date_formatted': format_registration_date(candidate.created_at),
                'last_login_formatted': format_relative_time(candidate.user.last_login or candidate.created_at)
            })
        context['recent_candidate_activity'] = recent_candidate_activity

        # Dynamic Greeting based on Asia/Kolkata local time
        import zoneinfo
        kolkata_tz = zoneinfo.ZoneInfo('Asia/Kolkata')
        now_local = django_timezone.localtime(django_timezone.now(), kolkata_tz)
        hour = now_local.hour

        if 5 <= hour < 12:
            greeting_prefix = "Good Morning"
            greeting_emoji = "👋"
        elif 12 <= hour < 17:
            greeting_prefix = "Good Afternoon"
            greeting_emoji = "☀️"
        elif 17 <= hour < 21:
            greeting_prefix = "Good Evening"
            greeting_emoji = "🌇"
        else:
            greeting_prefix = "Good Night"
            greeting_emoji = "🌙"

        first_name = (user.first_name or "").strip()
        if first_name and "@" not in first_name and "talentvault" not in first_name.lower():
            greeting_text = f"{greeting_prefix}, {first_name} {greeting_emoji}"
        else:
            greeting_text = f"{greeting_prefix} {greeting_emoji}"

        context['dynamic_greeting'] = greeting_text

        # 8. Recent Job Applications
        context['recent_applications'] = apps_qs.select_related('candidate__user', 'job').order_by('-created_at')[:10]
        
        # 9. Super Admin specific data
        if is_super_admin:
            context['pending_recruiters_count'] = User.objects.filter(role__in=[User.Role.RECRUITER, User.Role.COMPANY_ADMIN], recruiter_status='PENDING').count()
            
        return context


class RecruiterJobsView(RecruiterRequiredMixin, TemplateView):
    template_name = 'recruiter_jobs.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        company_member = user.company_affiliations.select_related('company').first()
        company = company_member.company if company_member else None

        status_filter = self.request.GET.get('status', 'ALL').upper()

        jobs_qs = get_tenant_jobs_qs(user)

        if status_filter in ['ACTIVE', 'DRAFT', 'PAUSED', 'ON_HOLD', 'CLOSED']:
            jobs_qs = jobs_qs.filter(status=status_filter)

        context['jobs'] = jobs_qs.order_by('-created_at')
        context['company'] = company
        context['status_filter'] = status_filter
        context['active_count'] = get_tenant_jobs_qs(user).filter(status='ACTIVE').count()
        context['closed_count'] = get_tenant_jobs_qs(user).filter(status='CLOSED').count()
        return context

    def post(self, request, *args, **kwargs):
        user = request.user
        action = request.POST.get('action')
        company_member = user.company_affiliations.select_related('company').first()
        company = company_member.company if company_member else None

        if not company:
            from apps.companies.models import Company, CompanyMember
            from django.utils.text import slugify
            comp_name = f"{user.first_name or 'Recruiter'} Organization"
            company, _ = Company.objects.get_or_create(
                name=comp_name,
                defaults={'slug': slugify(f"{comp_name}-{user.id}")}
            )
            CompanyMember.objects.get_or_create(company=company, user=user, defaults={'designation': 'Recruiter'})

        if action == 'create':
            title = request.POST.get('title', '').strip()
            department = request.POST.get('department', '').strip()
            job_type = request.POST.get('job_type', 'FULL_TIME')
            location = request.POST.get('location', '').strip()
            min_exp = int(request.POST.get('min_experience') or 0)
            max_exp = int(request.POST.get('max_experience') or 1)
            min_sal = request.POST.get('min_salary') or None
            max_sal = request.POST.get('max_salary') or None
            req_skills = request.POST.get('required_skills', '').strip()
            pref_skills = request.POST.get('preferred_skills', '').strip()
            education = request.POST.get('education', '').strip()
            notice_period = int(request.POST.get('notice_period') or 30)
            description = request.POST.get('description', '').strip()
            ai_matching_enabled = request.POST.get('ai_matching_enabled') == 'on' or request.POST.get('ai_matching_enabled') == 'true'

            new_job = Job.objects.create(
                company=company,
                created_by=user,
                title=title,
                department=department,
                job_type=job_type,
                location=location,
                min_experience=min_exp,
                max_experience=max_exp,
                min_salary=min_sal if min_sal else None,
                max_salary=max_sal if max_sal else None,
                required_skills_text=req_skills,
                preferred_skills_text=pref_skills,
                education=education,
                notice_period=notice_period,
                description=description,
                ai_matching_enabled=ai_matching_enabled,
                status='ACTIVE'
            )

            from apps.jobs.models import JobSkill
            if req_skills:
                for sname in req_skills.split(','):
                    sname_clean = sname.strip()
                    if sname_clean:
                        JobSkill.objects.get_or_create(job=new_job, skill_name=sname_clean, defaults={'is_mandatory': True})
            if pref_skills:
                for sname in pref_skills.split(','):
                    sname_clean = sname.strip()
                    if sname_clean:
                        JobSkill.objects.get_or_create(job=new_job, skill_name=sname_clean, defaults={'is_mandatory': False})

            messages.success(request, f"Job '{title}' has been created and published successfully!")
            return redirect('frontend:recruiter_jobs')

        return redirect('frontend:recruiter_jobs')


class ParseJobDescriptionView(RecruiterRequiredMixin, View):
    """
    AJAX endpoint for uploading and parsing a Job Description document (PDF, DOC, DOCX).
    Returns extracted fields to auto-fill the Create Job Posting modal.
    """
    def post(self, request, *args, **kwargs):
        if 'jd_file' not in request.FILES:
            return JsonResponse({
                'success': False,
                'error': 'No file uploaded. Please select a PDF, DOC, or DOCX file.'
            }, status=400)

        uploaded_file = request.FILES['jd_file']
        filename = uploaded_file.name
        ext = os.path.splitext(filename)[1].lower().replace('.', '')

        if ext not in ['pdf', 'doc', 'docx']:
            return JsonResponse({
                'success': False,
                'error': 'Invalid file format. Supported formats: PDF, DOC, DOCX.'
            }, status=400)

        if uploaded_file.size > 10 * 1024 * 1024:
            return JsonResponse({
                'success': False,
                'error': 'File size exceeds maximum limit of 10 MB.'
            }, status=400)

        try:
            from apps.jobs.services import JobDescriptionParserService
            file_bytes = uploaded_file.read()
            raw_text = JobDescriptionParserService.extract_text(file_bytes, filename)

            if not raw_text or len(raw_text.strip()) < 10:
                return JsonResponse({
                    'success': False,
                    'error': 'Unable to extract automatically. Please fill the remaining fields manually.'
                })

            parsed_result = JobDescriptionParserService.parse_jd(raw_text)
            return JsonResponse(parsed_result)

        except Exception as e:
            logger.error(f"[JD PARSE ERROR] Exception parsing JD file {filename}: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Unable to extract automatically. Please fill the remaining fields manually.'
            })


class RecruiterCandidatesView(RecruiterRequiredMixin, TemplateView):
    template_name = 'recruiter_candidates.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        import re

        recruiter_jobs = get_tenant_jobs_qs(user).filter(status='ACTIVE').order_by('-created_at')

        job_id_param = self.request.GET.get('job_id')
        selected_job = None
        if job_id_param:
            selected_job = recruiter_jobs.filter(id=job_id_param).first()
        if not selected_job and recruiter_jobs.exists():
            selected_job = recruiter_jobs.first()

        search_query = self.request.GET.get('q', '').strip().lower()
        min_exp_param = self.request.GET.get('min_exp')
        location_param = self.request.GET.get('location', '').strip().lower()
        sort_by = self.request.GET.get('sort', 'match_desc')

        all_candidates = get_tenant_candidates_qs(user).select_related('user').prefetch_related('skills', 'educations', 'experiences')[:50]
        matched_candidates = []

        if selected_job:
            job_required_skills = {s.strip().lower() for s in selected_job.get_required_skills_list if s.strip()}
            TITLE_STOP_WORDS = {'senior', 'junior', 'lead', 'manager', 'associate', 'director', 'intern', 'staff', 'principal', 'vp', 'head', 'executive', 'assistant'}
            job_title_words = set(re.findall(r'\w+', (selected_job.title or '').lower())) - TITLE_STOP_WORDS

            for cand in all_candidates:
                cand_skills = {s.skill_name.strip().lower() for s in cand.skills.all() if s.skill_name and s.skill_name.strip()}
                matched_skill_names = [s for s in selected_job.get_required_skills_list if s.strip().lower() in cand_skills]
                missing_skill_names = [s for s in selected_job.get_required_skills_list if s.strip().lower() not in cand_skills]

                cand_title_words = set(re.findall(r'\w+', (cand.current_designation or '').lower())) - TITLE_STOP_WORDS
                title_overlap = bool(job_title_words.intersection(cand_title_words))

                # Exclude unrelated candidates: candidate must have at least 1 matching skill OR title overlap
                if len(matched_skill_names) == 0 and not title_overlap and selected_job.get_required_skills_list:
                    continue

                if search_query:
                    c_text = f"{(cand.full_name or '')} {(cand.user.email or '')} {(cand.current_designation or '')} {(cand.location or '')} {' '.join(cand_skills)}".lower()
                    if search_query not in c_text:
                        continue

                if min_exp_param:
                    try:
                        if cand.total_experience < float(min_exp_param):
                            continue
                    except ValueError:
                        pass

                if location_param and location_param not in (cand.location or '').lower():
                    continue

                total_req = len(selected_job.get_required_skills_list)
                if total_req > 0:
                    base_calc = int((len(matched_skill_names) / total_req) * 80)
                    score = min(100, base_calc + (20 if title_overlap else 0))
                else:
                    score = cand.ats_score or 75

                if score >= 80:
                    match_label = 'Excellent Match'
                    badge_class = 'bg-success text-white'
                elif score >= 60:
                    match_label = 'Good Match'
                    badge_class = 'bg-warning text-dark'
                else:
                    match_label = 'Moderate Match'
                    badge_class = 'bg-secondary text-white'

                matched_candidates.append({
                    'candidate': cand,
                    'job': selected_job,
                    'match_score': score,
                    'matched_skills': matched_skill_names,
                    'missing_skills': missing_skill_names,
                    'match_label': match_label,
                    'badge_class': badge_class,
                })

        if sort_by == 'match_desc':
            matched_candidates.sort(key=lambda x: x['match_score'], reverse=True)
        elif sort_by == 'match_asc':
            matched_candidates.sort(key=lambda x: x['match_score'])
        elif sort_by == 'exp_desc':
            matched_candidates.sort(key=lambda x: float(x['candidate'].total_experience or 0), reverse=True)

        context['recruiter_jobs'] = recruiter_jobs
        context['selected_job'] = selected_job
        context['candidates'] = matched_candidates
        context['search_query'] = search_query
        context['selected_job_id'] = str(selected_job.id) if selected_job else ''
        return context

class AdminDashboardView(SuperAdminRequiredMixin, TemplateView):
    template_name = 'recruiter_dashboard.html'
    
    def get(self, request, *args, **kwargs):
        return redirect('frontend:recruiter_dashboard')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        context['open_jobs'] = Job.objects.filter(status='ACTIVE').count()
        context['candidates_added'] = CandidateProfile.objects.count()
        context['interviews_scheduled'] = Interview.objects.count()
        context['placements'] = Application.objects.filter(stage__in=['ACCEPTED', 'JOINED', 'HIRED', 'OFFER_STAGE']).count()
        context['duplicates_found'] = DuplicateResumeLog.objects.count()
        context['resumes_uploaded_today'] = CandidateProfile.objects.filter(created_at__date=today).count()
        context['recent_applicants'] = Application.objects.select_related('candidate__user', 'job').order_by('-created_at')[:10]
        context['total_users'] = User.objects.count()
        context['total_recruiters'] = User.objects.filter(role__in=[User.Role.RECRUITER, User.Role.COMPANY_ADMIN]).count()
        context['pending_recruiters_count'] = User.objects.filter(role__in=[User.Role.RECRUITER, User.Role.COMPANY_ADMIN], recruiter_status='PENDING').count()
        
        pending_qs = User.objects.filter(role__in=[User.Role.RECRUITER, User.Role.COMPANY_ADMIN], recruiter_status='PENDING').order_by('-created_at')[:5]
        pending_list = []
        for u in pending_qs:
            cm = u.company_affiliations.select_related('company').first()
            comp = cm.company if cm else None
            pending_list.append({
                'user': u,
                'company_name': comp.name if comp else "Company",
                'company_industry': comp.industry if comp else "Technology"
            })
        context['pending_recruiters'] = pending_list
        return context


class AdminRecruiterApprovalsView(SuperAdminRequiredMixin, TemplateView):
    template_name = 'admin_recruiter_approvals.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status_filter = self.request.GET.get('status', 'PENDING').upper()
        if status_filter not in ['PENDING', 'ACTIVE', 'REJECTED', 'SUSPENDED', 'ALL']:
            status_filter = 'PENDING'

        recruiter_qs = User.objects.filter(role__in=[User.Role.RECRUITER, User.Role.COMPANY_ADMIN]).order_by('-created_at')
        if status_filter != 'ALL':
            recruiter_qs = recruiter_qs.filter(recruiter_status=status_filter)

        recruiter_list = []
        for u in recruiter_qs:
            cm = u.company_affiliations.select_related('company').first()
            comp = cm.company if cm else None
            recruiter_list.append({
                'user': u,
                'company_name': comp.name if comp else (u.first_name + " Company" if u.first_name else "Company"),
                'company_website': comp.website if comp else '',
                'company_industry': comp.industry if comp else '',
                'company_size': comp.employee_count if comp else ''
            })

        context['recruiters'] = recruiter_list
        context['status_filter'] = status_filter
        context['pending_count'] = User.objects.filter(role__in=[User.Role.RECRUITER, User.Role.COMPANY_ADMIN], recruiter_status='PENDING').count()
        return context

    def post(self, request, *args, **kwargs):
        user_id = request.POST.get('user_id')
        action = request.POST.get('action')

        if not user_id or not action:
            messages.error(request, "Invalid request parameters.")
            return redirect('frontend:admin_recruiter_approvals')

        target_user = get_object_or_404(User, pk=user_id, role__in=[User.Role.RECRUITER, User.Role.COMPANY_ADMIN])

        from django.urls import reverse

        if action in ['approve', 'reactivate']:
            target_user.recruiter_status = User.RecruiterStatus.ACTIVE
            target_user.is_active = True
            target_user.save()
            msg_action = "Reactivated" if action == 'reactivate' else "Approved"
            messages.success(request, f"{msg_action} recruiter {target_user.email} successfully. Account is now ACTIVE.")

            if action == 'approve':
                try:
                    from django.utils import timezone
                    from apps.accounts.services.email_service import send_recruiter_approval_emails

                    cm = target_user.company_affiliations.select_related('company').first()
                    comp_name = cm.company.name if cm else "your company"
                    login_url = request.build_absolute_uri('/accounts/login/employer/')
                    appr_time = timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')

                    send_recruiter_approval_emails(
                        recruiter_email=target_user.email,
                        company_name=comp_name,
                        approval_timestamp=appr_time,
                        login_url=login_url
                    )
                except Exception as e:
                    logger.error(f"Error sending approval email to {target_user.email}: {e}")

            return redirect(f"{reverse('frontend:admin_recruiter_approvals')}?status=ACTIVE")

        elif action == 'reject':
            target_user.recruiter_status = User.RecruiterStatus.REJECTED
            target_user.is_active = False
            target_user.save()
            messages.warning(request, f"Rejected recruiter {target_user.email}. Verification status set to REJECTED.")

            try:
                from django.utils import timezone
                from apps.accounts.services.email_service import send_recruiter_rejection_emails

                cm = target_user.company_affiliations.select_related('company').first()
                comp_name = cm.company.name if cm else "your company"
                rej_time = timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')

                send_recruiter_rejection_emails(
                    recruiter_email=target_user.email,
                    company_name=comp_name,
                    rejection_timestamp=rej_time
                )
            except Exception as e:
                logger.error(f"Error sending rejection email to {target_user.email}: {e}")

            return redirect(f"{reverse('frontend:admin_recruiter_approvals')}?status=REJECTED")

        elif action == 'suspend':
            target_user.recruiter_status = User.RecruiterStatus.SUSPENDED
            target_user.is_active = False
            target_user.save()
            messages.info(request, f"Suspended recruiter {target_user.email}. Account status set to SUSPENDED.")
            return redirect(f"{reverse('frontend:admin_recruiter_approvals')}?status=SUSPENDED")

        return redirect('frontend:admin_recruiter_approvals')

class JobActionView(RecruiterRequiredMixin, View):
    def post(self, request, pk, action):
        job = get_object_or_404(Job, pk=pk)
        if action == 'publish':
            job.status = 'ACTIVE'
        elif action == 'pause':
            job.status = 'PAUSED'
        elif action == 'on_hold':
            job.status = 'ON_HOLD'
        elif action == 'close':
            job.status = 'CLOSED'
            from django.utils import timezone
            job.closed_at = timezone.now()
            job.closed_by = request.user
        elif action == 'reopen':
            job.status = 'ACTIVE'
            job.closed_at = None
            job.closed_by = None
        elif action == 'clone':
            # Need to clone without mutating original job's PK
            new_job = Job.objects.get(pk=pk)
            new_job.pk = None
            new_job.title = f"Copy of {job.title}"
            new_job.status = 'DRAFT'
            new_job.closed_at = None
            new_job.closed_by = None
            new_job.save()
            return redirect('frontend:job_edit', pk=new_job.pk)
        job.save()
        return redirect('frontend:jobs')

class JobsView(ListView):
    model = Job
    context_object_name = 'jobs'
    paginate_by = 10

    def get_template_names(self):
        if not self.request.user.is_authenticated or getattr(self.request.user, 'role', None) == 'CANDIDATE':
            return ['candidate_jobs.html']
        return ['jobs.html']

    def get(self, request, *args, **kwargs):
        # Handle invalid page numbers gracefully (Redirect instead of 404)
        page_raw = request.GET.get(self.page_kwarg)
        if page_raw is not None:
            try:
                page_num = int(page_raw)
                if page_num < 1:
                    params = request.GET.copy()
                    params[self.page_kwarg] = 1
                    return redirect(f"{request.path}?{params.urlencode()}")
            except (TypeError, ValueError):
                params = request.GET.copy()
                params[self.page_kwarg] = 1
                return redirect(f"{request.path}?{params.urlencode()}")

        try:
            return super().get(request, *args, **kwargs)
        except Http404:
            self.object_list = self.get_queryset()
            paginator = self.get_paginator(self.object_list, self.paginate_by)
            max_pages = paginator.num_pages if paginator.num_pages > 0 else 1
            params = request.GET.copy()
            params[self.page_kwarg] = max_pages
            return redirect(f"{request.path}?{params.urlencode()}")

    def get_queryset(self):
        is_candidate_or_guest = not self.request.user.is_authenticated or getattr(self.request.user, 'role', None) == 'CANDIDATE'
        
        if is_candidate_or_guest:
            queryset = Job.objects.filter(status='ACTIVE').select_related('company', 'client').prefetch_related('skills')
            
            # 1. Search by Keyword (q, search, keyword)
            q = self.request.GET.get('q', '') or self.request.GET.get('search', '') or self.request.GET.get('keyword', '')
            q = q.strip()
            if q:
                queryset = queryset.filter(
                    Q(title__icontains=q) |
                    Q(description__icontains=q) |
                    Q(department__icontains=q) |
                    Q(required_skills_text__icontains=q) |
                    Q(preferred_skills_text__icontains=q) |
                    Q(company__name__icontains=q) |
                    Q(client__company_name__icontains=q) |
                    Q(location__icontains=q) |
                    Q(skills__skill_name__icontains=q)
                )
            
            # 2. Search by Location (location, city, preferred_location, state)
            loc = self.request.GET.get('location', '') or self.request.GET.get('preferred_location', '') or self.request.GET.get('city', '') or self.request.GET.get('state', '')
            loc = loc.strip()
            if loc:
                queryset = queryset.filter(location__icontains=loc)
                
            # 3. Search by Company
            company = self.request.GET.get('company', '').strip()
            if company:
                queryset = queryset.filter(Q(company__name__icontains=company) | Q(client__company_name__icontains=company))
                
            # 4. Search by Skills
            skills = self.request.GET.get('skills', '').strip()
            if skills:
                queryset = queryset.filter(skills__skill_name__icontains=skills)
                
            # 5. Experience Filter
            experience = self.request.GET.get('experience', '')
            if experience:
                try:
                    exp_val = int(experience)
                    queryset = queryset.filter(min_experience__lte=exp_val)
                except ValueError:
                    pass
                    
            # 6. Salary Filter
            salary = self.request.GET.get('salary', '')
            if salary:
                try:
                    salary_clean = salary.upper().replace('LPA', '').strip()
                    sal_val = float(salary_clean) * 100000
                    queryset = queryset.filter(Q(max_salary__gte=sal_val) | Q(min_salary__gte=sal_val))
                except ValueError:
                    pass
                    
            # 7. Job Type Filter
            job_type = self.request.GET.get('job_type', '')
            if job_type:
                queryset = queryset.filter(job_type=job_type)
                
            # 8. Work Mode Filter
            work_mode = self.request.GET.get('work_mode', '')
            if work_mode:
                queryset = queryset.filter(work_mode=work_mode)

            queryset = queryset.distinct()
                
            # 9. Sorting
            sort_by = self.request.GET.get('sort_by', 'newest')
            if sort_by == 'relevance' and q:
                from django.db.models import Case, When, Value, IntegerField
                queryset = queryset.annotate(
                    relevance=Case(
                        When(title__icontains=q, then=Value(3)),
                        When(description__icontains=q, then=Value(1)),
                        default=Value(0),
                        output_field=IntegerField(),
                    )
                ).order_by('-relevance', '-created_at')
            else:
                queryset = queryset.order_by('-created_at')
                
            return queryset
        else:
            queryset = get_tenant_jobs_qs(self.request.user).select_related('company', 'client').prefetch_related('skills').annotate(
                app_count=Count('applications'),
                interview_count=Count('applications__interviews')
            )
            
            # Search
            q = self.request.GET.get('q', '') or self.request.GET.get('search', '') or self.request.GET.get('keyword', '')
            q = q.strip()
            if q:
                queryset = queryset.filter(
                    Q(title__icontains=q) |
                    Q(description__icontains=q) |
                    Q(department__icontains=q) |
                    Q(location__icontains=q) |
                    Q(company__name__icontains=q) |
                    Q(client__company_name__icontains=q)
                )
                
            # Filters
            status = self.request.GET.get('status', '').strip()
            if status:
                queryset = queryset.filter(status=status)
            else:
                queryset = queryset.exclude(status='CLOSED')
                
            job_type = self.request.GET.get('job_type', '').strip()
            if job_type:
                queryset = queryset.filter(job_type=job_type)
                
            # Company / Client filter (Supports UUID, name, and slugified name)
            company_filter = self.request.GET.get('company', '').strip() or self.request.GET.get('client', '').strip()
            if company_filter:
                import uuid
                try:
                    comp_uuid = uuid.UUID(company_filter)
                    queryset = queryset.filter(Q(company_id=comp_uuid) | Q(client_id=comp_uuid))
                except ValueError:
                    clean_name = company_filter.replace('-', ' ').strip()
                    queryset = queryset.filter(
                        Q(company__name__icontains=company_filter) |
                        Q(company__name__icontains=clean_name) |
                        Q(client__company_name__icontains=company_filter) |
                        Q(client__company_name__icontains=clean_name)
                    )
                
            # Sorting
            sort_by = self.request.GET.get('sort_by', '-created_at').strip()
            if sort_by in ['title', '-title', 'created_at', '-created_at', 'app_count', '-app_count']:
                queryset = queryset.order_by(sort_by)
            else:
                queryset = queryset.order_by('-created_at')
                
            return queryset.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Build encoded filter parameters query string (excluding 'page') for pagination links
        get_params = self.request.GET.copy()
        if 'page' in get_params:
            del get_params['page']
        encoded_filters = get_params.urlencode()
        context['filter_params'] = f"&{encoded_filters}" if encoded_filters else ""

        # Pre-generate absolute share URLs using request.build_absolute_uri()
        jobs_list = context.get('jobs', [])
        for job in jobs_list:
            job.share_url = self.request.build_absolute_uri(
                reverse('frontend:public_job_share', kwargs={'pk': job.pk})
            )
            
        is_candidate_or_guest = not self.request.user.is_authenticated or getattr(self.request.user, 'role', None) == 'CANDIDATE'
        if is_candidate_or_guest:
            candidate_profile = getattr(self.request.user, 'candidate_profile', None) if self.request.user.is_authenticated else None
            if candidate_profile:
                context['applied_job_ids'] = list(candidate_profile.job_applications.values_list('job_id', flat=True))
                context['saved_job_ids'] = list(candidate_profile.saved_jobs.values_list('job_id', flat=True))
            else:
                context['applied_job_ids'] = []
                context['saved_job_ids'] = []
                
            q_val = self.request.GET.get('q', '') or self.request.GET.get('search', '') or self.request.GET.get('keyword', '')
            loc_val = self.request.GET.get('location', '') or self.request.GET.get('preferred_location', '') or self.request.GET.get('city', '') or self.request.GET.get('state', '')
            
            context['q'] = q_val
            context['search'] = q_val
            context['company'] = self.request.GET.get('company', '')
            context['skills'] = self.request.GET.get('skills', '')
            context['city'] = self.request.GET.get('city', '')
            context['state'] = self.request.GET.get('state', '')
            context['preferred_location'] = loc_val
            context['location'] = loc_val
            context['experience'] = self.request.GET.get('experience', '')
            context['salary'] = self.request.GET.get('salary', '')
            context['selected_job_type'] = self.request.GET.get('job_type', '')
            context['selected_work_mode'] = self.request.GET.get('work_mode', '')
            context['selected_sort'] = self.request.GET.get('sort_by', 'newest')
            
            context['unique_locations'] = sorted(list(set(
                Job.objects.filter(status='ACTIVE').exclude(location=None).exclude(location='').values_list('location', flat=True)
            )))
        else:
            status_counts = Job.objects.aggregate(
                active=Count('id', filter=Q(status='ACTIVE')),
                draft=Count('id', filter=Q(status='DRAFT')),
                on_hold=Count('id', filter=Q(status='ON_HOLD')),
                closed=Count('id', filter=Q(status='CLOSED'))
            )
            context['active_count'] = status_counts['active']
            context['draft_count'] = status_counts['draft']
            context['on_hold_count'] = status_counts['on_hold']
            context['closed_count'] = status_counts['closed']
            
            # Preserve search, filter and sort inputs in template
            context['q'] = self.request.GET.get('q', '')
            context['selected_status'] = self.request.GET.get('status', '')
            context['selected_job_type'] = self.request.GET.get('job_type', '')
            context['selected_sort'] = self.request.GET.get('sort_by', '-created_at')
            
            from apps.companies.models import Company
            from apps.clients.models import Client

            active_companies = list(Company.objects.filter(jobs__status='ACTIVE').distinct())
            if not active_companies:
                active_companies = list(Company.objects.filter(is_active=True).order_by('name'))

            client_list = list(Client.objects.filter(status='ACTIVE'))

            company_options = []
            seen_names = set()
            for c in active_companies:
                if c.name and c.name not in seen_names:
                    company_options.append({'id': str(c.id), 'name': c.name})
                    seen_names.add(c.name)
            for cl in client_list:
                if cl.company_name and cl.company_name not in seen_names:
                    company_options.append({'id': str(cl.id), 'name': cl.company_name})
                    seen_names.add(cl.company_name)

            context['companies'] = company_options
            context['selected_company'] = self.request.GET.get('company', '') or self.request.GET.get('client', '')

            context['clients'] = Client.objects.filter(status='ACTIVE')
            context['selected_client'] = self.request.GET.get('client', '') or self.request.GET.get('company', '')
            
            context['job_types'] = [
                ('FULL_TIME', 'Full Time'),
                ('PART_TIME', 'Part Time'),
                ('CONTRACT', 'Contract'),
                ('FREELANCE', 'Freelance'),
                ('ON_SITE', 'On Site'),
                ('HYBRID', 'Hybrid'),
                ('WORK_FROM_HOME', 'Work From Home'),
            ]
            context['statuses'] = Job.JobStatus.choices
        
        return context

from apps.jobs.models import Job, JobSkill

class JobCreateView(RecruiterRequiredMixin, CreateView):
    model = Job
    form_class = JobForm
    template_name = 'job_create.html'
    success_url = reverse_lazy('frontend:jobs')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Generate salary choices: 0, 1.0 to 100.0 in 0.5 increments
        salaries = [{'value': 0, 'label': '0 LPA'}]
        for i in range(2, 201): # 1.0, 1.5 ... 100.0
            val = i / 2.0
            label = f"{val:g} LPA" if val < 100 else "1 Crore"
            salaries.append({'value': int(val * 100000), 'label': label})
        context['salary_choices'] = salaries
        return context

    def form_valid(self, form):
        client = form.cleaned_data.get('client') or getattr(form.instance, 'client', None)
        if client:
            from apps.companies.models import Company
            from django.utils.text import slugify
            comp_name = client.company_name.strip()
            company = Company.objects.filter(name__iexact=comp_name).first()
            if not company:
                base_slug = slugify(comp_name) or 'company'
                slug = base_slug
                counter = 1
                while Company.objects.filter(slug=slug).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                company = Company.objects.create(
                    name=comp_name,
                    slug=slug,
                    industry=getattr(client, 'industry', '') or 'General',
                    location=client.city or 'India'
                )
            form.instance.company = company
            form.instance.client = client
        else:
            member = CompanyMember.objects.filter(user=self.request.user).first()
            if member and member.company:
                form.instance.company = member.company
            else:
                company, _ = Company.objects.get_or_create(name="Default Company", slug="default-company")
                form.instance.company = company
            
        if 'draft' in self.request.POST:
            form.instance.status = 'DRAFT'
        else:
            form.instance.status = 'ACTIVE'
            
        response = super().form_valid(form)
        
        # Handle Skills Tags
        skills_tags = form.cleaned_data.get('skills_tags')
        if skills_tags:
            skill_list = [s.strip() for s in skills_tags.split(',') if s.strip()]
            for skill_name in skill_list:
                JobSkill.objects.get_or_create(job=self.object, skill_name=skill_name)
                
        messages.success(self.request, f"Job '{self.object.title}' created successfully!")
        return response

class JobUpdateView(RecruiterRequiredMixin, UpdateView):
    model = Job
    form_class = JobForm
    template_name = 'job_create.html'
    success_url = reverse_lazy('frontend:jobs')

    def get_queryset(self):
        return get_tenant_jobs_qs(self.request.user)

    def get_initial(self):
        initial = super().get_initial()
        initial['skills_tags'] = ", ".join(self.object.skills.values_list('skill_name', flat=True))
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Generate salary choices: 0, 1.0 to 100.0 in 0.5 increments
        salaries = [{'value': 0, 'label': '0 LPA'}]
        for i in range(2, 201): # 1.0, 1.5 ... 100.0
            val = i / 2.0
            label = f"{val:g} LPA" if val < 100 else "1 Crore"
            salaries.append({'value': int(val * 100000), 'label': label})
        context['salary_choices'] = salaries
        return context

    def form_valid(self, form):
        client = form.cleaned_data.get('client') or getattr(form.instance, 'client', None)
        if client:
            from apps.companies.models import Company
            from django.utils.text import slugify
            comp_name = client.company_name.strip()
            company = Company.objects.filter(name__iexact=comp_name).first()
            if not company:
                base_slug = slugify(comp_name) or 'company'
                slug = base_slug
                counter = 1
                while Company.objects.filter(slug=slug).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                company = Company.objects.create(
                    name=comp_name,
                    slug=slug,
                    industry=getattr(client, 'industry', '') or 'General',
                    location=client.city or 'India'
                )
            form.instance.company = company
            form.instance.client = client

        if 'draft' in self.request.POST:
            form.instance.status = 'DRAFT'
        else:
            form.instance.status = 'ACTIVE'
            
        response = super().form_valid(form)
        
        # Update Skills Tags
        skills_tags = form.cleaned_data.get('skills_tags')
        if skills_tags:
            self.object.skills.all().delete()
            skill_list = [s.strip() for s in skills_tags.split(',') if s.strip()]
            for skill_name in skill_list:
                JobSkill.objects.get_or_create(job=self.object, skill_name=skill_name)
                
        # Recalculate ATS scores for all candidates applied to this job
        from services.candidate_matching_service import CandidateMatchingService
        CandidateMatchingService.update_ats_scores(job_id=self.object.id)
        
        return response

class JobDeleteView(RecruiterRequiredMixin, DeleteView):
    model = Job
    success_url = reverse_lazy('frontend:jobs')
    template_name = 'job_confirm_delete.html'

    def get_queryset(self):
        return get_tenant_jobs_qs(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "Job deleted successfully.")
        return super().form_valid(form)


class CandidateSearchView(RecruiterRequiredMixin, ListView):
    model = CandidateProfile
    template_name = 'candidate_search.html'
    context_object_name = 'candidates'
    paginate_by = 20

    def paginate_queryset(self, queryset, page_size):
        """
        Safe pagination that gracefully falls back to the nearest valid page
        or page 1 (with empty list) instead of raising a Django Http404 on invalid/out-of-range pages.
        """
        from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage, InvalidPage

        paginator = self.get_paginator(
            queryset,
            page_size,
            orphans=self.get_paginate_orphans(),
            allow_empty_first_page=self.get_allow_empty(),
        )
        page_kwarg = self.page_kwarg
        page = self.kwargs.get(page_kwarg) or self.request.GET.get(page_kwarg) or 1

        if paginator.count == 0:
            page_obj = paginator.page(1)
            return (paginator, page_obj, page_obj.object_list, False)

        try:
            page_number = int(page)
        except (ValueError, TypeError):
            if str(page).lower() == "last":
                page_number = paginator.num_pages
            else:
                page_number = 1

        if page_number < 1:
            page_number = 1

        try:
            page_obj = paginator.page(page_number)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            if page_number > paginator.num_pages:
                page_obj = paginator.page(paginator.num_pages)
            else:
                page_obj = paginator.page(1)
        except InvalidPage:
            page_obj = paginator.page(1)

        return (paginator, page_obj, page_obj.object_list, page_obj.has_other_pages())
    
    def get_queryset(self):
        from django.db.models import Prefetch, Q
        from services.universal_candidate_search_service import UniversalCandidateSearchService
        from apps.candidates.models import RecentCandidateSearch
        
        user = self.request.user
        base_qs = get_tenant_candidates_qs(user).order_by('-created_at').prefetch_related(
            Prefetch(
                'job_applications',
                queryset=get_tenant_applications_qs(user).select_related('job', 'job__company', 'job__client', 'created_by').order_by('-created_at')
            )
        )
        
        # 1. Extract query & tag inputs
        q = (self.request.GET.get('q') or self.request.GET.get('name') or '').strip()
        tags_raw = self.request.GET.getlist('tags')
        if not tags_raw and self.request.GET.get('tags'):
            tags_raw = [t.strip() for t in self.request.GET.get('tags').split(',') if t.strip()]

        selected_tags = []
        for t in tags_raw:
            if t and t.strip():
                selected_tags.append({"label": t.strip(), "type": "tag"})

        exclude_keywords = self.request.GET.get('exclude_keywords') or self.request.GET.get('excluded_keywords') or ''
        skills_param = (self.request.GET.get('skills') or '').strip()
        it_skills_param = (self.request.GET.get('it_skills') or '').strip()
        min_exp_param = self.request.GET.get('min_exp') or self.request.GET.get('min_experience')
        max_exp_param = self.request.GET.get('max_exp') or self.request.GET.get('max_experience')
        location_param = (self.request.GET.get('location') or '').strip()
        preferred_location_param = (self.request.GET.get('preferred_location') or '').strip()
        willing_to_relocate_param = True if self.request.GET.get('willing_to_relocate') in ['1', 'true', 'True', True] else (False if self.request.GET.get('willing_to_relocate') in ['0', 'false', 'False', False] else None)
        work_mode_param = (self.request.GET.get('work_mode') or '').strip()
        min_salary_param = self.request.GET.get('min_salary')
        max_salary_param = self.request.GET.get('max_salary')
        currency_param = self.request.GET.get('currency', 'INR')
        department_param = (self.request.GET.get('department') or '').strip()
        role_name_param = (self.request.GET.get('role') or self.request.GET.get('role_name') or '').strip()
        title_param = (self.request.GET.get('title') or self.request.GET.get('designation') or '').strip()
        prev_designation_param = (self.request.GET.get('previous_designation') or '').strip()
        industry_param = (self.request.GET.get('industry') or '').strip()
        company_param = (self.request.GET.get('company') or '').strip()
        prev_company_param = (self.request.GET.get('previous_company') or '').strip()
        excluded_company_param = (self.request.GET.get('excluded_company') or '').strip()
        company_type_param = (self.request.GET.get('company_type') or '').strip()
        employment_type_param = (self.request.GET.get('employment_type') or '').strip()
        notice_period_param = self.request.GET.get('notice_period')
        
        # Education parameters
        ug_degree = (self.request.GET.get('ug_degree') or '').strip()
        ug_specialization = (self.request.GET.get('ug_specialization') or '').strip()
        ug_education_type = (self.request.GET.get('ug_education_type') or '').strip()
        ug_passing_year_from = self.request.GET.get('ug_passing_year_from')
        ug_passing_year_to = self.request.GET.get('ug_passing_year_to')
        ug_institute = (self.request.GET.get('ug_institute') or '').strip()
        pg_degree = (self.request.GET.get('pg_degree') or '').strip()
        pg_specialization = (self.request.GET.get('pg_specialization') or '').strip()
        pg_education_type = (self.request.GET.get('pg_education_type') or '').strip()
        pg_passing_year_from = self.request.GET.get('pg_passing_year_from')
        pg_passing_year_to = self.request.GET.get('pg_passing_year_to')
        pg_institute = (self.request.GET.get('pg_institute') or '').strip()
        doctorate_degree = (self.request.GET.get('doctorate_degree') or '').strip()
        doctorate_specialization = (self.request.GET.get('doctorate_specialization') or '').strip()
        doctorate_institute = (self.request.GET.get('doctorate_institute') or '').strip()
        education_type = (self.request.GET.get('education_type') or '').strip()
        passing_year_from = self.request.GET.get('passing_year_from')
        passing_year_to = self.request.GET.get('passing_year_to')
        institute_param = (self.request.GET.get('institute') or '').strip()
        is_pursuing = True if self.request.GET.get('is_pursuing') in ['1', 'true', 'True'] else None

        # Diversity & Candidate attributes (explicit self-declared candidate data only)
        cand_name_param = (self.request.GET.get('candidate_name') or '').strip()
        cand_email_param = (self.request.GET.get('candidate_email') or '').strip()
        cand_phone_param = (self.request.GET.get('candidate_phone') or '').strip()
        gender_param = (self.request.GET.get('gender') or '').strip()
        has_career_break = True if self.request.GET.get('has_career_break') in ['1', 'true', 'True'] else None
        is_differently_abled = True if self.request.GET.get('is_differently_abled') in ['1', 'true', 'True'] else None
        disability_category = (self.request.GET.get('disability_category') or '').strip()
        has_defence_background = True if self.request.GET.get('has_defence_background') in ['1', 'true', 'True'] else None
        defence_branch = (self.request.GET.get('defence_branch') or '').strip()
        work_permit_country = (self.request.GET.get('work_permit_country') or '').strip()

        # Status & Freshness
        candidate_status_param = (self.request.GET.get('candidate_status') or self.request.GET.get('status') or '').strip()
        freshness_days = self.request.GET.get('freshness_days') or self.request.GET.get('activity_days')
        has_resume = True if self.request.GET.get('has_resume') in ['1', 'true', 'True'] else None
        has_verified_mobile = True if self.request.GET.get('has_verified_mobile') in ['1', 'true', 'True'] else None
        has_verified_email = True if self.request.GET.get('has_verified_email') in ['1', 'true', 'True'] else None
        search_within_results = (self.request.GET.get('search_within_results') or '').strip()

        job_id_param = (self.request.GET.get('job_id') or '').strip()
        stage_param = (self.request.GET.get('stage') or '').strip()
        mandatory_keywords_param = self.request.GET.getlist('mandatory_keywords')
        if not mandatory_keywords_param and self.request.GET.get('mandatory_keywords'):
            mandatory_keywords_param = [k.strip() for k in self.request.GET.get('mandatory_keywords').split(',') if k.strip()]
        boolean_query_param = (self.request.GET.get('boolean_query') or '').strip()
        sort_by = (self.request.GET.get('sort_by') or self.request.GET.get('sort') or 'newest').strip()

        # Tab routing (e.g. shortlisted, saved_for_later, new, modified)
        tab_param = self.request.GET.get('tab', '').strip().lower()
        if tab_param == 'shortlisted':
            candidate_status_param = 'SHORTLISTED'
        elif tab_param == 'saved_for_later':
            candidate_status_param = 'SAVED_FOR_LATER'
        elif tab_param == 'new':
            candidate_status_param = 'NEW_CANDIDATE'
        elif tab_param == 'modified':
            candidate_status_param = 'MODIFIED'

        # Record Recent Search if any search term is entered
        if q or selected_tags or title_param or skills_param or boolean_query_param:
            try:
                RecentCandidateSearch.objects.create(
                    user=user,
                    search_query=q or title_param or boolean_query_param or (selected_tags[0]["label"] if selected_tags else "Filtered Search"),
                    selected_tags=selected_tags,
                    filters_payload={
                        "title": title_param,
                        "location": location_param,
                        "skills": skills_param,
                        "department": department_param,
                        "industry": industry_param,
                        "min_exp": min_exp_param,
                        "max_exp": max_exp_param,
                        "boolean_query": boolean_query_param
                    }
                )
                rec_ids = list(RecentCandidateSearch.objects.filter(user=user).order_by('-created_at').values_list('id', flat=True)[:15])
                RecentCandidateSearch.objects.filter(user=user).exclude(id__in=rec_ids).delete()
            except Exception:
                pass

        # Execute universal hybrid relevance search with 41 structured filters
        scored_results = UniversalCandidateSearchService.search_candidates(
            base_queryset=base_qs,
            query=q,
            selected_tags=selected_tags,
            exclude_keywords=exclude_keywords,
            skills=skills_param,
            it_skills=it_skills_param,
            min_experience=float(min_exp_param) if min_exp_param else None,
            max_experience=float(max_exp_param) if max_exp_param else None,
            location=location_param,
            preferred_location=preferred_location_param,
            willing_to_relocate=willing_to_relocate_param,
            work_mode=work_mode_param,
            min_salary=float(min_salary_param) if min_salary_param else None,
            max_salary=float(max_salary_param) if max_salary_param else None,
            currency=currency_param,
            department=department_param,
            role_name=role_name_param,
            designation=title_param,
            previous_designation=prev_designation_param,
            industry=industry_param,
            company=company_param,
            previous_company=prev_company_param,
            excluded_company=excluded_company_param,
            company_type=company_type_param,
            employment_type=employment_type_param,
            notice_period=notice_period_param,
            ug_degree=ug_degree,
            ug_specialization=ug_specialization,
            ug_education_type=ug_education_type,
            ug_passing_year_from=int(ug_passing_year_from) if ug_passing_year_from else None,
            ug_passing_year_to=int(ug_passing_year_to) if ug_passing_year_to else None,
            ug_institute=ug_institute,
            pg_degree=pg_degree,
            pg_specialization=pg_specialization,
            pg_education_type=pg_education_type,
            pg_passing_year_from=int(pg_passing_year_from) if pg_passing_year_from else None,
            pg_passing_year_to=int(pg_passing_year_to) if pg_passing_year_to else None,
            pg_institute=pg_institute,
            doctorate_degree=doctorate_degree,
            doctorate_specialization=doctorate_specialization,
            doctorate_institute=doctorate_institute,
            education_type=education_type,
            passing_year_from=int(passing_year_from) if passing_year_from else None,
            passing_year_to=int(passing_year_to) if passing_year_to else None,
            institute=institute_param,
            is_pursuing=is_pursuing,
            candidate_name=cand_name_param,
            candidate_email=cand_email_param,
            candidate_phone=cand_phone_param,
            gender=gender_param,
            has_career_break=has_career_break,
            is_differently_abled=is_differently_abled,
            disability_category=disability_category,
            has_defence_background=has_defence_background,
            defence_branch=defence_branch,
            work_permit_country=work_permit_country,
            candidate_status=candidate_status_param,
            freshness_days=int(freshness_days) if freshness_days else None,
            has_resume=has_resume,
            has_verified_mobile=has_verified_mobile,
            has_verified_email=has_verified_email,
            search_within_results=search_within_results,
            mandatory_keywords=mandatory_keywords_param,
            boolean_query=boolean_query_param,
            stage=stage_param,
            job_id=job_id_param,
            sort_by=sort_by
        )

        candidates_list = []
        for item in scored_results:
            cand = item["candidate"]
            cand.relevance_score = item["relevance_score"]
            cand.match_quality = item["match_quality"]
            cand.matched_tags_list = item["matched_tags"]
            cand.why_matched_reasons = item["why_matched"]
            
            # Application snapshot
            apps_list = list(cand.job_applications.all())
            cand.latest_application = apps_list[0] if apps_list else None

            # Resolve effective uploader user name
            cand.effective_uploader_name = cand.uploader_name or "System Import"

            candidates_list.append(cand)

        return candidates_list

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        job_id = (self.request.GET.get('job_id') or '').strip()
        selected_job = None
        if job_id:
            selected_job = get_tenant_jobs_qs(user).filter(id=job_id).first()
            
        context['selected_job'] = selected_job
        
        q = (self.request.GET.get('q') or self.request.GET.get('name') or '').strip()
        tags_raw = self.request.GET.getlist('tags')
        if not tags_raw and self.request.GET.get('tags'):
            tags_raw = [t.strip() for t in self.request.GET.get('tags').split(',') if t.strip()]

        selected_tags_list = [{"label": t.strip(), "type": "tag"} for t in tags_raw if t.strip()]

        context['current_tab'] = self.request.GET.get('tab', 'search').strip().lower()
        context['filters'] = {
            'q': q,
            'name': q,
            'title': (self.request.GET.get('title') or self.request.GET.get('designation') or '').strip(),
            'role': (self.request.GET.get('role') or self.request.GET.get('role_name') or '').strip(),
            'location': (self.request.GET.get('location') or '').strip(),
            'preferred_location': (self.request.GET.get('preferred_location') or '').strip(),
            'willing_to_relocate': self.request.GET.get('willing_to_relocate', ''),
            'work_mode': (self.request.GET.get('work_mode') or '').strip(),
            'skills': (self.request.GET.get('skills') or '').strip(),
            'it_skills': (self.request.GET.get('it_skills') or '').strip(),
            'exclude_keywords': (self.request.GET.get('exclude_keywords') or '').strip(),
            'department': (self.request.GET.get('department') or '').strip(),
            'industry': (self.request.GET.get('industry') or '').strip(),
            'company': (self.request.GET.get('company') or '').strip(),
            'previous_company': (self.request.GET.get('previous_company') or '').strip(),
            'excluded_company': (self.request.GET.get('excluded_company') or '').strip(),
            'company_type': (self.request.GET.get('company_type') or '').strip(),
            'employment_type': (self.request.GET.get('employment_type') or '').strip(),
            'job_id': job_id,
            'stage': (self.request.GET.get('stage') or '').strip(),
            'tags': tags_raw,
            'min_exp': (self.request.GET.get('min_exp') or '').strip(),
            'max_exp': (self.request.GET.get('max_exp') or '').strip(),
            'min_salary': (self.request.GET.get('min_salary') or '').strip(),
            'max_salary': (self.request.GET.get('max_salary') or '').strip(),
            'currency': (self.request.GET.get('currency') or 'INR').strip(),
            'notice_period': (self.request.GET.get('notice_period') or '').strip(),
            'ug_degree': (self.request.GET.get('ug_degree') or '').strip(),
            'ug_specialization': (self.request.GET.get('ug_specialization') or '').strip(),
            'ug_education_type': (self.request.GET.get('ug_education_type') or '').strip(),
            'ug_passing_year_from': (self.request.GET.get('ug_passing_year_from') or '').strip(),
            'ug_passing_year_to': (self.request.GET.get('ug_passing_year_to') or '').strip(),
            'ug_institute': (self.request.GET.get('ug_institute') or '').strip(),
            'pg_degree': (self.request.GET.get('pg_degree') or '').strip(),
            'pg_specialization': (self.request.GET.get('pg_specialization') or '').strip(),
            'pg_education_type': (self.request.GET.get('pg_education_type') or '').strip(),
            'pg_passing_year_from': (self.request.GET.get('pg_passing_year_from') or '').strip(),
            'pg_passing_year_to': (self.request.GET.get('pg_passing_year_to') or '').strip(),
            'pg_institute': (self.request.GET.get('pg_institute') or '').strip(),
            'doctorate_degree': (self.request.GET.get('doctorate_degree') or '').strip(),
            'doctorate_specialization': (self.request.GET.get('doctorate_specialization') or '').strip(),
            'doctorate_institute': (self.request.GET.get('doctorate_institute') or '').strip(),
            'education_type': (self.request.GET.get('education_type') or '').strip(),
            'passing_year_from': (self.request.GET.get('passing_year_from') or '').strip(),
            'passing_year_to': (self.request.GET.get('passing_year_to') or '').strip(),
            'institute': (self.request.GET.get('institute') or '').strip(),
            'gender': (self.request.GET.get('gender') or '').strip(),
            'has_career_break': (self.request.GET.get('has_career_break') or '').strip(),
            'is_differently_abled': (self.request.GET.get('is_differently_abled') or '').strip(),
            'disability_category': (self.request.GET.get('disability_category') or '').strip(),
            'has_defence_background': (self.request.GET.get('has_defence_background') or '').strip(),
            'defence_branch': (self.request.GET.get('defence_branch') or '').strip(),
            'work_permit_country': (self.request.GET.get('work_permit_country') or '').strip(),
            'candidate_status': (self.request.GET.get('candidate_status') or '').strip(),
            'freshness_days': (self.request.GET.get('freshness_days') or '').strip(),
            'has_resume': (self.request.GET.get('has_resume') or '').strip(),
            'has_verified_email': (self.request.GET.get('has_verified_email') or '').strip(),
            'search_within_results': (self.request.GET.get('search_within_results') or '').strip(),
            'mandatory_keywords': (self.request.GET.get('mandatory_keywords') or '').strip(),
            'boolean_query': (self.request.GET.get('boolean_query') or '').strip(),
            'sort_by': (self.request.GET.get('sort_by') or self.request.GET.get('sort') or 'newest').strip(),
        }
        context['selected_tags'] = selected_tags_list
        context['selected_tags_json'] = json.dumps([t["label"] for t in selected_tags_list])
        context['active_jobs'] = get_tenant_jobs_qs(user).filter(status='ACTIVE')
        
        # Taxonomy Autocomplete & Smart Suggestions based on active search terms
        if q or selected_tags_list or self.request.GET.get('title'):
            from apps.taxonomy.services.taxonomy_engine import TaxonomyEngine
            TaxonomyEngine.ensure_seeded()
            suggestions_res = TaxonomyEngine.get_smart_suggestions(
                query=q or (self.request.GET.get('title') or ''),
                active_tags=[t["label"] for t in selected_tags_list],
                limit=15
            )
            context['smart_suggestions'] = suggestions_res.get('suggestions', [])
        else:
            context['smart_suggestions'] = []

        # User's Saved & Recent Searches
        from apps.candidates.models import SavedCandidateSearch, RecentCandidateSearch
        context['saved_searches'] = SavedCandidateSearch.objects.filter(user=user).order_by('-created_at')[:10]
        context['recent_searches'] = RecentCandidateSearch.objects.filter(user=user).order_by('-created_at')[:8]

        # Counts for tabs
        base_all = get_tenant_candidates_qs(user)
        from django.utils import timezone
        import datetime
        week_ago = timezone.now() - datetime.timedelta(days=7)
        context['tab_counts'] = {
            'all': base_all.count(),
            'shortlisted': base_all.filter(Q(is_shortlisted=True) | Q(candidate_status='SHORTLISTED')).count(),
            'saved_for_later': base_all.filter(Q(is_saved_for_later=True) | Q(candidate_status='SAVED_FOR_LATER')).count(),
            'new': base_all.filter(created_at__gte=week_ago).count(),
            'modified': base_all.filter(updated_at__gte=week_ago).count(),
        }

        candidates_list = list(context.get('candidates') or context.get('object_list') or [])
        for candidate in candidates_list:
            if selected_job:
                cand_skills = {s.skill_name.strip().lower() for s in candidate.skills.all() if s.skill_name and s.skill_name.strip()}
                matched_skill_names = [s for s in selected_job.get_required_skills_list if s.strip().lower() in cand_skills]
                total_req = len(selected_job.get_required_skills_list)
                if total_req > 0:
                    score = min(100, int((len(matched_skill_names) / total_req) * 100))
                else:
                    score = getattr(candidate, 'relevance_score', candidate.ats_score or 75)
                candidate.match_details = {'total_score': score, 'matched_skills': matched_skill_names}
            else:
                score = getattr(candidate, 'relevance_score', candidate.ats_score or 75)
                candidate.match_details = {'total_score': score, 'matched_skills': getattr(candidate, 'matched_tags_list', [])}
                
        context['candidates'] = candidates_list
        context['object_list'] = candidates_list
        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest' or self.request.GET.get('ajax') == '1':
            from django.template.loader import render_to_string
            html = render_to_string('includes/candidate_search_list.html', context, request=self.request)
            count = context['page_obj'].paginator.count if context.get('page_obj') else len(context.get('candidates', []))
            return JsonResponse({
                'html': html,
                'count': count,
                'smart_suggestions': context.get('smart_suggestions', [])
            })
        return super().render_to_response(context, **response_kwargs)


class TalentSearchView(CandidateSearchView):
    """
    Dedicated Talent Search workspace for recruiter talent discovery, multi-domain taxonomy filters, 
    deterministic matching, and relevance ranking.
    """
    template_name = 'talent_search.html'


class CandidateSuggestionsAPIView(RecruiterRequiredMixin, View):
    """
    API endpoint returning dynamic AI & Taxonomy suggested keywords.
    """
    def get(self, request, *args, **kwargs):
        from apps.taxonomy.services.taxonomy_engine import TaxonomyEngine
        q = request.GET.get('q', '').strip()
        tags_raw = request.GET.getlist('tags')
        if not tags_raw and request.GET.get('tags'):
            tags_raw = [t.strip() for t in request.GET.get('tags').split(',') if t.strip()]

        data = TaxonomyEngine.get_smart_suggestions(query=q, active_tags=tags_raw, limit=15)
        return JsonResponse(data)


class CandidateSavedSearchesAPIView(RecruiterRequiredMixin, View):
    """
    CRUD API for recruiter Saved Searches.
    """
    def get(self, request, *args, **kwargs):
        from apps.candidates.models import SavedCandidateSearch
        searches = SavedCandidateSearch.objects.filter(user=request.user).order_by('-created_at')[:20]
        results = []
        for s in searches:
            results.append({
                "id": str(s.id),
                "name": s.name,
                "search_query": s.search_query,
                "selected_tags": s.selected_tags,
                "filters": s.filters_payload,
                "results_count": s.results_count,
                "created_at": s.created_at.strftime("%b %d, %Y")
            })
        return JsonResponse({"saved_searches": results})

    def post(self, request, *args, **kwargs):
        from apps.candidates.models import SavedCandidateSearch
        try:
            body = json.loads(request.body)
        except Exception:
            body = request.POST

        name = body.get('name', '').strip()
        if not name:
            name = f"Search - {timezone.now().strftime('%b %d, %H:%M')}"

        search_query = body.get('q', '').strip()
        selected_tags = body.get('tags', [])
        if isinstance(selected_tags, str):
            selected_tags = [t.strip() for t in selected_tags.split(',') if t.strip()]

        filters_payload = body.get('filters', {})
        results_count = int(body.get('count', 0))

        saved = SavedCandidateSearch.objects.create(
            user=request.user,
            name=name,
            search_query=search_query,
            selected_tags=selected_tags,
            filters_payload=filters_payload,
            results_count=results_count
        )

        return JsonResponse({
            "status": "success",
            "success": True,
            "message": "Search criteria saved successfully.",
            "saved_search": {
                "id": str(saved.id),
                "name": saved.name,
                "search_query": saved.search_query,
                "selected_tags": saved.selected_tags,
                "filters": saved.filters_payload,
                "results_count": saved.results_count
            }
        })

    def delete(self, request, *args, **kwargs):
        from apps.candidates.models import SavedCandidateSearch
        search_id = kwargs.get('pk') or request.GET.get('id')
        if not search_id:
            return JsonResponse({"status": "error", "message": "Search ID required."}, status=400)

        deleted, _ = SavedCandidateSearch.objects.filter(user=request.user, id=search_id).delete()
        return JsonResponse({"status": "success", "deleted": bool(deleted)})


class CandidateRecentSearchesAPIView(RecruiterRequiredMixin, View):
    """
    API endpoint returning recent searches for recruiter.
    """
    def get(self, request, *args, **kwargs):
        from apps.candidates.models import RecentCandidateSearch
        recent = RecentCandidateSearch.objects.filter(user=request.user).order_by('-created_at')[:10]
        results = []
        for r in recent:
            results.append({
                "id": str(r.id),
                "search_query": r.search_query,
                "selected_tags": r.selected_tags,
                "filters": r.filters_payload,
                "results_count": r.results_count,
                "created_at": r.created_at.strftime("%b %d, %H:%M")
            })
        return JsonResponse({"recent_searches": results})


class CandidateAutocompleteView(RecruiterRequiredMixin, View):
    """
    Universal Dynamic candidate & taxonomy autocomplete suggestions.
    Fast, debounced, indexed/multi-field partial search with rank ordering.
    Supports candidate name, email, phone, designation, company, skills, and location.
    """
    def get(self, request, *args, **kwargs):
        import urllib.parse
        from django.db.models import Q
        stype = request.GET.get('type', 'all').strip().lower()
        q = request.GET.get('q', '').strip()

        if not q or len(q) < 2:
            return JsonResponse({'query': q, 'count': 0, 'results': [], 'candidates': [], 'suggestions': []})

        user = request.user
        q_lower = q.lower()

        if stype == 'taxonomy':
            from apps.taxonomy.services.taxonomy_engine import TaxonomyEngine
            taxonomy_data = TaxonomyEngine.get_smart_suggestions(query=q, limit=12)
            results = []
            for s in taxonomy_data.get('results', []):
                results.append({
                    'id': s.get('id', ''),
                    'value': s['label'],
                    'name': s['label'],
                    'label': s['label'],
                    'title': s['label'],
                    'type': s.get('type', 'designation'),
                    'category': s.get('category', ''),
                    'score': s.get('score', 0.8),
                    'subtitle': f"{s.get('type', 'Keyword').title()} &bull; {s.get('category', '')}"
                })
            return JsonResponse({'query': q, 'count': len(results), 'results': results, 'suggestions': results})

        # Multi-field Candidate Directory Autocomplete Search
        candidates_qs = get_tenant_candidates_qs(user).select_related('user').prefetch_related('skills').filter(
            Q(full_name__icontains=q) |
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q) |
            Q(user__email__icontains=q) |
            Q(user__phone_number__icontains=q) |
            Q(current_designation__icontains=q) |
            Q(current_company__icontains=q) |
            Q(skills__skill_name__icontains=q) |
            Q(location__icontains=q)
        ).distinct()[:20]

        results = []
        seen_ids = set()

        for cand in candidates_qs:
            if cand.id in seen_ids:
                continue
            seen_ids.add(cand.id)

            cand_name = cand.full_name or (cand.user.get_full_name().strip() if cand.user else '') or (cand.user.email if cand.user else 'Candidate')
            cand_name_lower = cand_name.lower()
            desig = cand.current_designation or ""
            desig_lower = desig.lower()
            comp = cand.current_company or ""
            comp_lower = comp.lower()
            skills = [s.skill_name for s in cand.skills.all()[:5] if s.skill_name]
            skills_lower = [s.lower() for s in skills]

            # Determine match relevance rank
            if cand_name_lower == q_lower:
                rank = 1
            elif cand_name_lower.startswith(q_lower):
                rank = 2
            elif q_lower in cand_name_lower:
                rank = 3
            elif desig_lower.startswith(q_lower) or q_lower in desig_lower:
                rank = 4
            elif any(q_lower in sk for sk in skills_lower):
                rank = 5
            elif q_lower in comp_lower:
                rank = 6
            else:
                rank = 7

            subtitle_parts = []
            if desig:
                subtitle_parts.append(desig)
            if comp:
                subtitle_parts.append(comp)
            subtitle = " · ".join(subtitle_parts) if subtitle_parts else (cand.location or "Candidate Profile")

            matched_skill = ""
            for sk in skills:
                if q_lower in sk.lower():
                    matched_skill = sk
                    break

            results.append({
                'id': str(cand.id),
                'value': cand_name,
                'name': cand_name,
                'title': desig or "Candidate",
                'designation': desig,
                'company': comp,
                'subtitle': subtitle,
                'location': cand.location or "",
                'skills': skills,
                'matched_skill': matched_skill,
                'rank': rank,
                'avatar': cand_name[0].upper() if cand_name else "C",
                'url': reverse('frontend:candidate_detail', kwargs={'pk': cand.id}),
            })

        results.sort(key=lambda x: (x['rank'], x['name'].lower()))
        top_results = results[:8]

        # If general search and no candidate profiles match, enrich with taxonomy suggestions
        if not top_results and stype in ['all', '']:
            from apps.taxonomy.services.taxonomy_engine import TaxonomyEngine
            taxonomy_data = TaxonomyEngine.get_smart_suggestions(query=q, limit=12)
            tax_results = []
            for s in taxonomy_data.get('results', []):
                tax_results.append({
                    'id': s.get('id', ''),
                    'value': s['label'],
                    'name': s['label'],
                    'label': s['label'],
                    'title': s['label'],
                    'type': s.get('type', 'designation'),
                    'category': s.get('category', ''),
                    'score': s.get('score', 0.8),
                    'subtitle': f"{s.get('type', 'Keyword').title()} &bull; {s.get('category', '')}"
                })
            return JsonResponse({
                'query': q,
                'count': len(tax_results),
                'total_matches': len(tax_results),
                'results': tax_results,
                'candidates': [],
                'suggestions': tax_results,
                'view_all_url': f"{reverse('frontend:candidate_search')}?q={urllib.parse.quote(q)}"
            })

        return JsonResponse({
            'query': q,
            'count': len(top_results),
            'total_matches': len(results),
            'results': top_results,
            'candidates': top_results,
            'suggestions': top_results,
            'view_all_url': f"{reverse('frontend:candidate_search')}?q={urllib.parse.quote(q)}"
        })


class JobCandidatesView(RecruiterRequiredMixin, ListView):
    model = Application
    template_name = 'job_candidates.html'
    context_object_name = 'applications'
    paginate_by = 10

    def get_queryset(self):
        self.job = get_object_or_404(get_tenant_jobs_qs(self.request.user), id=self.kwargs['job_id'])
        queryset = get_tenant_applications_qs(self.request.user).filter(job=self.job).select_related('candidate__user').prefetch_related('candidate__skills', 'candidate__educations')
        
        # Sync ATS scores for applications under this job
        from services.candidate_matching_service import CandidateMatchingService
        for app in queryset:
            if app.match_score == 0.0:
                CandidateMatchingService.update_ats_scores(candidate_id=app.candidate.id, job_id=self.job.id)
                
        # Refetch
        queryset = Application.objects.filter(job=self.job).select_related('candidate__user').prefetch_related('candidate__skills', 'candidate__educations')

        # Search
        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(
                Q(candidate__full_name__icontains=q) | 
                Q(candidate__user__email__icontains=q) |
                Q(candidate__current_company__icontains=q) |
                Q(candidate__current_designation__icontains=q)
            )
            
        # Filters:
        # Experience
        exp = self.request.GET.get('experience', '').strip()
        if exp:
            if exp == 'fresher':
                queryset = queryset.filter(candidate__total_experience=0)
            elif exp == '1-3':
                queryset = queryset.filter(candidate__total_experience__gte=1, candidate__total_experience__lte=3)
            elif exp == '3-5':
                queryset = queryset.filter(candidate__total_experience__gte=3, candidate__total_experience__lte=5)
            elif exp == '5-10':
                queryset = queryset.filter(candidate__total_experience__gte=5, candidate__total_experience__lte=10)
            elif exp == '10+':
                queryset = queryset.filter(candidate__total_experience__gt=10)

        # Location
        location = self.request.GET.get('location', '').strip()
        if location:
            queryset = queryset.filter(candidate__location__icontains=location)
            
        # Education
        education = self.request.GET.get('education', '').strip()
        if education:
            queryset = queryset.filter(candidate__educations__degree__icontains=education).distinct()
            
        # ATS Score
        ats_score = self.request.GET.get('ats_score', '').strip()
        if ats_score:
            if ats_score == '90+':
                queryset = queryset.filter(match_score__gte=90)
            elif ats_score == '75-90':
                queryset = queryset.filter(match_score__gte=75, match_score__lt=90)
            elif ats_score == '60-75':
                queryset = queryset.filter(match_score__gte=60, match_score__lt=75)
            elif ats_score == 'below-60':
                queryset = queryset.filter(match_score__lt=60)
                
        # Status
        status = self.request.GET.get('status', '').strip()
        if status:
            queryset = queryset.filter(stage=status)
            
        # Sorting
        sort_by = self.request.GET.get('sort_by', 'newest').strip()
        if sort_by == 'highest_ats' or sort_by == 'ats':
            queryset = queryset.order_by('-match_score', '-created_at')
        elif sort_by == 'highest_experience' or sort_by == 'experience':
            queryset = queryset.order_by('-candidate__total_experience', '-created_at')
        elif sort_by == 'highest_match' or sort_by == 'match':
            queryset = queryset.order_by('-match_score', '-created_at')
        else: # newest
            queryset = queryset.order_by('-created_at')

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['job'] = self.job
        context['total_applications_count'] = Application.objects.filter(job=self.job).count()
        
        # Get stages lists for filters
        context['stage_choices'] = Application.ApplicationStage.choices
        
        # Capture filter inputs for form persistent state
        context['q'] = self.request.GET.get('q', '')
        context['selected_experience'] = self.request.GET.get('experience', '')
        context['selected_sort_by'] = self.request.GET.get('sort_by', 'newest')
        context['selected_location'] = self.request.GET.get('location', '')
        context['selected_education'] = self.request.GET.get('education', '')
        context['selected_ats_score'] = self.request.GET.get('ats_score', '')
        context['selected_status'] = self.request.GET.get('status', '')
        
        return context


class SaveCandidateNotesView(RecruiterRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        profile = get_object_or_404(CandidateProfile, pk=pk)
        notes = request.POST.get('notes', '').strip()
        profile.recruiter_notes = notes
        profile.save()
        
        # Add to audit log
        profile.audit_logs.append({
            "action": "Updated recruiter notes",
            "timestamp": timezone.now().isoformat(),
            "user": request.user.email
        })
        profile.save()
        
        messages.success(request, "Recruiter notes saved successfully.")
        
        next_url = request.POST.get('next') or request.GET.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('frontend:candidate_detail', pk=pk)


class MockQuerySet:
    def __init__(self, items):
        self.items = items
    def all(self):
        return self.items
    def exists(self):
        return len(self.items) > 0
    def count(self):
        return len(self.items)

class CandidateProfileWrapper:
    def __init__(self, original, data_overrides, rel_overrides):
        self._original = original
        self._data_overrides = data_overrides
        self._rel_overrides = rel_overrides

    def __getattr__(self, name):
        if name in self._rel_overrides:
            return self._rel_overrides[name]
        if name in self._data_overrides:
            return self._data_overrides[name]
        return getattr(self._original, name)

    def __str__(self):
        return str(self._original)

class CandidateDetailView(RecruiterRequiredMixin, DetailView):
    model = CandidateProfile
    template_name = 'candidate_detail.html'
    context_object_name = 'candidate'

    def get_queryset(self):
        return get_tenant_candidates_qs(self.request.user)

    def get_context_data(self, **kwargs):
        from apps.jobs.models import Job
        from apps.applications.models import Application
        from datetime import datetime, date
        
        context = super().get_context_data(**kwargs)
        
        logger.info(f"[DETAIL_VIEW] Recruiter {self.request.user.email} accessed candidate profile: {self.object.id} ({self.object.full_name})")
        context['active_jobs'] = get_tenant_jobs_qs(self.request.user).filter(status='ACTIVE')
        context['stage_choices'] = Application.ApplicationStage.choices
        
        job_id = self.request.GET.get('job_id')
        selected_job = None
        match_details = None
        is_in_pipeline = False
        application_id = None
        
        if job_id:
            selected_job = Job.objects.filter(id=job_id).first()
            if selected_job:
                from services.candidate_matching_service import CandidateMatchingService
                match_details = CandidateMatchingService.calculate_job_ats_score(self.object, selected_job)
                app = Application.objects.filter(candidate=self.object, job=selected_job).first()
                if app:
                    is_in_pipeline = app.in_pipeline
                    application_id = app.id
                
        context['selected_job'] = selected_job
        context['match_details'] = match_details
        context['is_in_pipeline'] = is_in_pipeline
        context['application_id'] = application_id
        
        # Check for duplicates
        from services.resume_intelligence import ResumeIntelligenceService
        duplicates = []
        other_candidates = CandidateProfile.objects.exclude(id=self.object.id)
        for c in other_candidates:
            res = ResumeIntelligenceService.calculate_duplicate_similarity(self.object, c)
            if res["is_duplicate"]:
                duplicates.append(res)
        context['duplicates'] = duplicates
        
        # Determine which version to preview (default to self.object.current_version or latest available)
        version_param = self.request.GET.get('version')
        selected_version_id = None
        if version_param:
            try:
                selected_version_id = int(version_param)
            except ValueError:
                selected_version_id = None
                
        if selected_version_id is None:
            selected_version_id = self.object.current_version or 1

        version_str = str(selected_version_id)
        if self.object.resume_versions and version_str in self.object.resume_versions:
            version_data = self.object.resume_versions[version_str]["data"]
        else:
            current_ver_str = str(self.object.current_version) if self.object.current_version else "1"
            if self.object.resume_versions and current_ver_str in self.object.resume_versions:
                version_data = self.object.resume_versions[current_ver_str]["data"]
                selected_version_id = self.object.current_version
            elif self.object.resume_versions:
                available_keys = [int(k) for k in self.object.resume_versions.keys() if str(k).isdigit()]
                if available_keys:
                    latest_key = str(max(available_keys))
                    version_data = self.object.resume_versions[latest_key]["data"]
                    selected_version_id = int(latest_key)
                else:
                    version_data = {}
                    selected_version_id = self.object.current_version or 1
            else:
                # Reconstruct version data from database fields if versions are empty
                version_data = {
                    "personal_info": {
                        "name": self.object.full_name,
                        "current_company": self.object.current_company,
                        "current_designation": self.object.current_designation,
                        "total_experience": float(self.object.total_experience) if self.object.total_experience is not None else 0.0,
                        "location": self.object.location,
                    },
                    "summary": self.object.summary,
                    "skills": [s.skill_name for s in self.object.skills.all()],
                    "experience": [
                        {
                            "company": e.company_name,
                            "designation": e.designation,
                            "start_date": e.start_date.strftime("%Y-%m-%d") if e.start_date else "",
                            "end_date": e.end_date.strftime("%Y-%m-%d") if e.end_date else ("Present" if e.is_current else ""),
                            "description": e.description,
                        } for e in self.object.experiences.all()
                    ],
                    "education": [
                        {
                            "institution": ed.institution,
                            "degree": ed.degree,
                            "field_of_study": ed.field_of_study,
                            "start_date": ed.start_date.strftime("%Y-%m-%d") if ed.start_date else "",
                            "end_date": ed.end_date.strftime("%Y-%m-%d") if ed.end_date else "",
                        } for ed in self.object.educations.all()
                    ],
                    "projects": [
                        {
                            "title": p.title,
                            "description": p.description,
                            "link": p.link,
                        } for p in self.object.projects.all()
                    ],
                    "certifications": [
                        {
                            "name": c.name,
                            "issuing_organization": c.issuing_organization,
                            "issue_date": c.issue_date.strftime("%Y-%m-%d") if c.issue_date else "",
                        } for c in self.object.certifications.all()
                    ]
                }
                selected_version_id = self.object.current_version or 1

        context['selected_version_id'] = selected_version_id

        def str_to_date(date_str):
            if not date_str:
                return None
            if isinstance(date_str, date):
                return date_str
            if isinstance(date_str, datetime):
                return date_str.date()
            try:
                return datetime.strptime(date_str, "%Y-%m-%d").date()
            except Exception:
                from apps.candidates.utils import parse_date_robust
                return parse_date_robust(date_str, None)

        display_experiences = []
        for exp in version_data.get('experience', []):
            s_date = str_to_date(exp.get('start_date'))
            e_date = str_to_date(exp.get('end_date'))
            is_curr = exp.get('end_date') == 'Present' or e_date is None
            display_experiences.append({
                'company_name': exp.get('company') or exp.get('company_name') or '',
                'designation': exp.get('designation') or exp.get('title') or '',
                'description': exp.get('description') or '',
                'start_date': s_date,
                'end_date': e_date,
                'is_current': is_curr,
            })

        display_educations = []
        for edu in version_data.get('education', []):
            s_date = str_to_date(edu.get('start_date'))
            e_date = str_to_date(edu.get('end_date'))
            display_educations.append({
                'institution': edu.get('institution') or '',
                'degree': edu.get('degree') or '',
                'field_of_study': edu.get('field_of_study') or '',
                'start_date': s_date,
                'end_date': e_date,
            })

        class MockSkillObj:
            def __init__(self, name):
                self.skill_name = name

        display_skills = []
        for sk in version_data.get('skills', []):
            if isinstance(sk, dict):
                display_skills.append(MockSkillObj(sk.get('skill_name') or sk.get('name') or ''))
            else:
                display_skills.append(MockSkillObj(sk))

        display_projects = []
        for proj in version_data.get('projects', []):
            display_projects.append({
                'title': proj.get('title') or '',
                'description': proj.get('description') or '',
                'link': proj.get('link') or '',
            })

        display_certifications = []
        for cert in version_data.get('certifications', []):
            i_date = str_to_date(cert.get('issue_date'))
            display_certifications.append({
                'name': cert.get('name') or '',
                'issuing_organization': cert.get('issuing_organization') or '',
                'issue_date': i_date,
            })

        info = version_data.get('personal_info', {})
        display_full_name = info.get('name') or self.object.full_name
        display_summary = version_data.get('summary') or self.object.summary
        display_current_company = info.get('current_company') or self.object.current_company
        display_current_designation = info.get('current_designation') or self.object.current_designation
        display_total_experience = info.get('total_experience') or self.object.total_experience
        display_location = info.get('location') or self.object.location

        rel_overrides = {
            'experiences': MockQuerySet(display_experiences),
            'educations': MockQuerySet(display_educations),
            'projects': MockQuerySet(display_projects),
            'certifications': MockQuerySet(display_certifications),
            'skills': MockQuerySet(display_skills),
        }
        data_overrides = {
            'full_name': display_full_name,
            'summary': display_summary,
            'current_company': display_current_company,
            'current_designation': display_current_designation,
            'total_experience': display_total_experience,
            'location': display_location,
            'parsed_json': version_data,
        }
        wrapped_candidate = CandidateProfileWrapper(self.object, data_overrides, rel_overrides)
        context['candidate'] = wrapped_candidate
        
        # Version control timeline variables
        versions_list = sorted(list(self.object.resume_versions.values()), key=lambda x: x["version"])
        context['versions_list'] = versions_list
        context['has_undo'] = str(self.object.current_version - 1) in self.object.resume_versions
        context['has_redo'] = str(self.object.current_version + 1) in self.object.resume_versions
        context['prev_version'] = self.object.current_version - 1
        context['next_version'] = self.object.current_version + 1
        
        import os
        context['resume_filename'] = os.path.basename(self.object.resume.name) if self.object.resume else ""
        context['resume_extension'] = os.path.splitext(self.object.resume.name)[1].lower().replace('.', '') if self.object.resume else ""
        
        has_ocr_data = bool(self.object.raw_resume_text.strip()) or bool(self.object.parsed_json) or self.object.experiences.exists()
        file_physically_exists = False
        if self.object.resume:
            try:
                if self.object.resume.name and self.object.resume.storage.exists(self.object.resume.name):
                    file_physically_exists = True
            except Exception:
                pass
                
        if file_physically_exists:
            resume_exists = True
            resume_missing = False
        else:
            resume_exists = False
            resume_missing = bool(self.object.resume)
        context['resume_exists'] = resume_exists
        context['resume_missing'] = resume_missing
        
        from django.urls import reverse
        context['public_share_url'] = self.request.build_absolute_uri(
            reverse('frontend:public_candidate_profile', kwargs={'pk': self.object.pk})
        )
        
        # Fetch candidate's active/latest Job Application
        latest_app = None
        if selected_job:
            latest_app = Application.objects.filter(candidate_id=self.object.id, job=selected_job).select_related('job', 'created_by').first()
        if not latest_app:
            latest_app = Application.objects.filter(candidate_id=self.object.id).select_related('job', 'created_by').order_by('-created_at').first()
        context['latest_application'] = latest_app
        
        return context

from apps.candidates.forms import CandidateProfileForm

class CandidateUpdateView(RecruiterRequiredMixin, UpdateView):
    model = CandidateProfile
    template_name = 'candidate_form.html'
    form_class = CandidateProfileForm
    success_url = reverse_lazy('frontend:candidate_search')

    def get_queryset(self):
        return get_tenant_candidates_qs(self.request.user)

    def get_success_url(self):
        return reverse_lazy('frontend:candidate_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        from services.candidate_matching_service import CandidateMatchingService
        CandidateMatchingService.update_ats_scores(candidate_id=self.object.id)
        return response

class CandidateDeleteView(RecruiterRequiredMixin, View):
    def post(self, request, id, *args, **kwargs):
        try:
            with transaction.atomic():
                queryset = get_tenant_candidates_qs(request.user).select_for_update()
                candidate = get_object_or_404(queryset, id=id)
                user = candidate.user
                if user and user.role == 'CANDIDATE':
                    user.delete()
                else:
                    candidate.delete()
            messages.success(request, "Candidate deleted successfully.")
        except (Http404, CandidateProfile.DoesNotExist):
            messages.info(request, "Candidate already deleted.")
        except Exception as e:
            messages.error(request, "An unexpected error occurred while deleting the candidate.")
        return redirect('frontend:candidate_search')

class CandidateRejectView(RecruiterRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        candidate = get_object_or_404(get_tenant_candidates_qs(request.user), pk=pk)
        job_id = request.POST.get('job_id') or request.GET.get('job_id')
        if job_id:
            applications = Application.objects.filter(candidate=candidate, job_id=job_id)
        else:
            applications = Application.objects.filter(candidate=candidate)
            
        if applications.exists():
            for app in applications:
                old_stage = app.stage
                app.stage = 'SYSTEM_REJECTED'
                app.save()
                
                # Notify Recruiter
                Notification.objects.create(
                    recipient=request.user,
                    title="Candidate Rejected",
                    message=f"Candidate {candidate.full_name or candidate.user.email} was rejected for job {app.job.title}.",
                    notification_type='APPLICATION_STATUS'
                )
                # Notify Candidate
                if candidate.user:
                    Notification.objects.create(
                        recipient=candidate.user,
                        title="Application Status Updated",
                        message=f"Your application status for '{app.job.title}' has been updated to Rejected.",
                        notification_type='APPLICATION_STATUS'
                    )
            messages.success(request, f"Candidate {candidate.full_name or candidate.user.email} has been rejected.")
        else:
            messages.warning(request, "Candidate has no active applications to reject.")
            
        next_url = request.POST.get('next') or request.GET.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('frontend:candidate_detail', pk=pk)

class UpdateApplicationStageDirectView(RecruiterRequiredMixin, View):
    def post(self, request, app_id, *args, **kwargs):
        application = get_object_or_404(Application, id=app_id)
        old_stage = application.stage
        new_stage = request.POST.get('stage')
        
        if new_stage in dict(Application.ApplicationStage.choices):
            application.stage = new_stage
            application.save()
            
            if new_stage != old_stage:
                # Notify Recruiter
                Notification.objects.create(
                    recipient=request.user,
                    title="Application Stage Updated",
                    message=f"Candidate {application.candidate.full_name or application.candidate.user.email} was moved from {old_stage} to {new_stage} for job {application.job.title}.",
                    notification_type='APPLICATION_STATUS'
                )
                # Trigger notifications on INTERVIEW_SCHEDULE, OFFER_STAGE, JOINED
                if application.candidate.user and new_stage in ['INTERVIEW_SCHEDULE', 'OFFER_STAGE', 'JOINED']:
                    Notification.objects.create(
                        recipient=application.candidate.user,
                        title=f"Application Stage: {application.get_stage_display()}",
                        message=f"Your application status for the job '{application.job.title}' has been moved to {application.get_stage_display()}.",
                        notification_type='APPLICATION_STATUS'
                    )
                messages.success(request, f"Successfully updated stage for {application.candidate.full_name or application.candidate.user.email} to {application.get_stage_display()}.")
        else:
            messages.error(request, "Invalid stage choice.")
            
        return redirect('frontend:candidate_detail', pk=application.candidate.id)

class PublicCandidateProfileView(DetailView):
    model = CandidateProfile
    template_name = 'public_candidate_profile.html'
    context_object_name = 'candidate'

    def get_queryset(self):
        return CandidateProfile.objects.select_related('user').prefetch_related(
            'skills', 'experiences', 'educations', 'projects', 'certifications'
        )

    def get(self, request, *args, **kwargs):
        try:
            self.object = self.get_object()
        except (Http404, CandidateProfile.DoesNotExist):
            return render(request, '404.html', {'message': 'Candidate profile no longer available.'}, status=404)
        except Exception as e:
            logger.error(f"Error loading public candidate profile view {kwargs.get('pk')}: {e}")
            return render(request, '404.html', {'message': 'Candidate profile no longer available.'}, status=404)
        
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        import os
        candidate = self.object
        try:
            context['resume_filename'] = os.path.basename(candidate.resume.name) if candidate.resume else ""
            context['resume_extension'] = os.path.splitext(candidate.resume.name)[1].lower().replace('.', '') if candidate.resume else ""
        except Exception:
            context['resume_filename'] = ""
            context['resume_extension'] = ""
        
        file_physically_exists = False
        if candidate.resume:
            try:
                if candidate.resume.name and candidate.resume.storage.exists(candidate.resume.name):
                    file_physically_exists = True
            except Exception:
                pass
                
        if file_physically_exists:
            resume_exists = True
            resume_missing = False
        else:
            resume_exists = False
            resume_missing = bool(candidate.resume)
        context['resume_exists'] = resume_exists
        context['resume_missing'] = resume_missing
        return context

class PublicJobShareView(DetailView):
    model = Job
    template_name = 'public_job_share.html'
    context_object_name = 'job'

    def get_queryset(self):
        return Job.objects.select_related('company', 'client').prefetch_related('skills')

    def get(self, request, *args, **kwargs):
        try:
            self.object = self.get_object()
        except (Http404, Job.DoesNotExist):
            return render(request, '404.html', {'message': 'Job no longer available.'}, status=404)
        except Exception as e:
            logger.error(f"Error loading public job share view {kwargs.get('pk')}: {e}")
            return render(request, '404.html', {'message': 'Job no longer available.'}, status=404)
        
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        job = self.object
        try:
            share_url = self.request.build_absolute_uri(
                reverse('frontend:public_job_share', kwargs={'pk': job.pk})
            )
        except Exception:
            share_url = ""
        context['share_url'] = share_url
        
        jd_file = job.jd_file if job.jd_file else None
        context['jd_file'] = jd_file
        context['job_description_file'] = jd_file
        
        if jd_file:
            import os
            try:
                filename = os.path.basename(jd_file.name)
            except Exception:
                filename = str(jd_file)
            
            ext = os.path.splitext(filename)[1].lower() if '.' in filename else ''
            context['jd_file_name'] = filename
            context['jd_file_ext'] = ext
            context['is_pdf'] = (ext == '.pdf')
            context['is_docx'] = (ext in ['.docx', '.doc'])

            from utils.s3 import get_presigned_url
            jd_preview_url = get_presigned_url(jd_file, expires_in=7200, as_attachment=False, filename=filename)
            if not jd_preview_url:
                try:
                    jd_preview_url = reverse('frontend:share_job_jd_preview', kwargs={'pk': job.pk})
                except Exception:
                    jd_preview_url = ""
            context['jd_preview_url'] = jd_preview_url

            jd_download_url = get_presigned_url(jd_file, expires_in=7200, as_attachment=True, filename=filename)
            if not jd_download_url:
                try:
                    jd_download_url = reverse('frontend:share_job_jd_download', kwargs={'pk': job.pk})
                except Exception:
                    jd_download_url = ""
            context['jd_download_url'] = jd_download_url

            if ext in ['.docx', '.doc']:
                try:
                    import mammoth
                    with jd_file.open('rb') as docx_file:
                        result = mammoth.convert_to_html(docx_file)
                        context['jd_docx_html'] = result.value
                except Exception:
                    try:
                        import docx
                        with jd_file.open('rb') as docx_file:
                            doc = docx.Document(docx_file)
                            paras = [f"<p>{p.text.strip()}</p>" for p in doc.paragraphs if p.text.strip()]
                            context['jd_docx_html'] = "".join(paras)
                    except Exception:
                        context['jd_docx_html'] = None

        return context

class PublicJobApplyView(View):
    """
    Public Endpoint for submitting job applications without requiring candidate login.
    """
    def post(self, request, job_id, *args, **kwargs):
        from apps.jobs.models import Job
        from apps.candidates.models import CandidateProfile, CandidateSkill, Education
        from apps.applications.models import Application, ApplicationHistory
        from apps.accounts.models import User
        from services.candidate_matching_service import CandidateMatchingService
        from apps.notifications.models import Notification
        import logging
        import os

        logger = logging.getLogger(__name__)
        job = get_object_or_404(Job, pk=job_id)
        
        is_ajax = (
            request.headers.get('x-requested-with') == 'XMLHttpRequest' or
            'application/json' in request.headers.get('accept', '') or
            request.POST.get('is_ajax') == '1'
        )

        try:
            full_name = request.POST.get('full_name', '').strip()
            email = request.POST.get('email', '').strip().lower()
            phone_number = request.POST.get('phone_number', '').strip()
            current_location = request.POST.get('current_location', '').strip()
            total_experience_raw = request.POST.get('total_experience', '').strip()
            current_company = request.POST.get('current_company', '').strip()
            current_designation = request.POST.get('current_designation', '').strip()
            current_ctc_raw = request.POST.get('current_ctc', '').strip()
            expected_ctc_raw = request.POST.get('expected_ctc', '').strip()
            notice_period_raw = request.POST.get('notice_period', '').strip()
            preferred_location = request.POST.get('preferred_location', '').strip()
            highest_qualification = request.POST.get('highest_qualification', '').strip()
            skills_raw = request.POST.get('skills', '').strip()
            cover_letter = request.POST.get('cover_letter', '').strip()
            linkedin_url = request.POST.get('linkedin_url', '').strip()
            portfolio_url = request.POST.get('portfolio_url', '').strip()
            
            resume_file = request.FILES.get('resume_file')

            # Validation
            errors = []
            if not full_name:
                errors.append("Full Name is required.")
            if not email:
                errors.append("Email is required.")
            if not phone_number:
                errors.append("Phone Number is required.")
            if not current_location:
                errors.append("Current Location is required.")
            if not total_experience_raw:
                errors.append("Total Experience is required.")
            if not current_company:
                errors.append("Current Company is required.")
            if not current_designation:
                errors.append("Current Designation is required.")
            if not current_ctc_raw:
                errors.append("Current CTC is required.")
            if not expected_ctc_raw:
                errors.append("Expected CTC is required.")
            if not notice_period_raw:
                errors.append("Notice Period is required.")
            if not preferred_location:
                errors.append("Preferred Location is required.")
            if not highest_qualification:
                errors.append("Highest Qualification is required.")
            if not skills_raw:
                errors.append("Skills are required.")
            
            if not resume_file:
                errors.append("Resume upload is required (PDF Only).")
            else:
                filename_str = getattr(resume_file, 'name', '')
                ext = os.path.splitext(filename_str)[1].lower() if '.' in filename_str else ''
                if ext != '.pdf':
                    errors.append("Only PDF resumes are allowed.")
                elif resume_file.size > 10 * 1024 * 1024:
                    errors.append("Maximum file size allowed is 10 MB.")

            if errors:
                err_msg = errors[0] if len(errors) == 1 else " ".join(errors)
                if is_ajax:
                    return JsonResponse({'success': False, 'message': err_msg, 'errors': errors}, status=400)
                messages.error(request, err_msg)
                return redirect('frontend:public_job_share', pk=job.pk)

            # Numerical Parsing
            try:
                total_experience = float(total_experience_raw)
            except ValueError:
                total_experience = 0.0

            try:
                current_ctc = float(current_ctc_raw)
            except ValueError:
                current_ctc = None

            try:
                expected_ctc = float(expected_ctc_raw)
            except ValueError:
                expected_ctc = None

            try:
                notice_period = int(notice_period_raw)
            except ValueError:
                notice_period = 30

            # 1. Create or retrieve Candidate User (No candidate account login required)
            name_parts = full_name.split()
            first_name = name_parts[0] if name_parts else ''
            last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''

            user, user_created = User.objects.get_or_create(
                email=email,
                defaults={
                    'role': User.Role.CANDIDATE,
                    'phone_number': phone_number,
                    'first_name': first_name,
                    'last_name': last_name,
                }
            )
            if user_created:
                user.set_unusable_password()
                user.save()
            elif phone_number and not user.phone_number:
                user.phone_number = phone_number
                user.save(update_fields=['phone_number'])

            # 2. Create Candidate Profile
            profile, _ = CandidateProfile.objects.get_or_create(user=user)

            # 3. Save Profile
            profile.full_name = full_name
            profile.location = current_location
            profile.total_experience = total_experience
            profile.current_company = current_company
            profile.current_designation = current_designation
            profile.current_salary = current_ctc
            profile.expected_salary = expected_ctc
            profile.notice_period = notice_period
            profile.preferred_location = preferred_location
            if linkedin_url:
                profile.linkedin_url = linkedin_url
            if portfolio_url:
                profile.portfolio_url = portfolio_url

            # 4. Save Resume File (No OCR/parsing - purely manual entry)
            if resume_file:
                from services.resume_storage_service import upload_and_verify_resume, copy_and_verify_original_resume
                orig_fn = getattr(resume_file, 'name', 'resume.pdf')
                saved_key, _ = upload_and_verify_resume(resume_file, orig_fn)
                profile.resume.name = saved_key
                profile.original_filename = orig_fn
                orig_key = copy_and_verify_original_resume(saved_key, orig_fn)
                if orig_key:
                    profile.original_file.name = orig_key
            profile.save()

            # 5. Save Skills
            skill_list = [s.strip() for s in skills_raw.split(',') if s.strip()]
            for sk_name in skill_list:
                CandidateSkill.objects.get_or_create(profile=profile, skill_name=sk_name)

            # 6. Save Experience
            if current_company or current_designation:
                from apps.candidates.models import Experience
                Experience.objects.get_or_create(
                    profile=profile,
                    company_name=current_company or "N/A",
                    designation=current_designation or "N/A",
                    defaults={'is_current': True}
                )

            # 7. Save Education
            if highest_qualification:
                Education.objects.get_or_create(
                    profile=profile,
                    degree=highest_qualification,
                    defaults={'institution': 'N/A'}
                )

            # Determine Recruiter User
            recruiter_user = job.created_by
            if not recruiter_user and job.company:
                member = job.company.members.first()
                if member:
                    recruiter_user = member.user

            # 8. Create or Update Application
            app, app_created = Application.objects.get_or_create(
                job=job,
                candidate=profile,
                defaults={
                    'recruiter': recruiter_user,
                    'stage': Application.ApplicationStage.OPEN,
                    'in_pipeline': True,
                    'cover_letter': cover_letter,
                    'current_company': current_company,
                    'current_designation': current_designation,
                    'total_experience': total_experience,
                    'current_ctc': current_ctc,
                    'expected_ctc': expected_ctc,
                    'notice_period': notice_period,
                    'preferred_location': preferred_location,
                    'current_location': current_location,
                    'mobile_number': phone_number,
                    'linkedin_url': linkedin_url,
                    'portfolio_url': portfolio_url,
                    'resume': profile.resume or resume_file,
                    'key_skills': skill_list,
                }
            )

            if not app_created:
                app.in_pipeline = True
                app.is_active = True
                app.stage = Application.ApplicationStage.OPEN
                app.cover_letter = cover_letter or app.cover_letter
                app.resume = profile.resume or resume_file or app.resume
                app.current_company = current_company
                app.current_designation = current_designation
                app.total_experience = total_experience
                app.current_ctc = current_ctc
                app.expected_ctc = expected_ctc
                app.notice_period = notice_period
                app.preferred_location = preferred_location
                app.current_location = current_location
                app.mobile_number = phone_number
                app.linkedin_url = linkedin_url or app.linkedin_url
                app.portfolio_url = portfolio_url or app.portfolio_url
                app.key_skills = skill_list
                app.save()

            # Create History Entry
            ApplicationHistory.objects.create(
                application=app,
                from_stage=Application.ApplicationStage.OPEN,
                to_stage=Application.ApplicationStage.OPEN,
                notes="Application submitted via Public Job Link."
            )

            # Sync & Store ATS Match Score
            try:
                CandidateMatchingService.update_ats_scores(candidate_id=profile.id, job_id=job.id)
                ats_data = CandidateMatchingService.calculate_job_ats_score(profile, job)
                app.match_score = ats_data.get('total_score', 0.0)
                app.save(update_fields=['match_score'])
            except Exception as ats_err:
                logger.warning(f"ATS score sync warning: {ats_err}")

            # Recruiter Notification
            if recruiter_user:
                try:
                    Notification.objects.create(
                        recipient=recruiter_user,
                        title="New Public Job Application",
                        message=f"{full_name} submitted an application for '{job.title}' via public link.",
                        notification_type='APPLICATION_STATUS'
                    )
                except Exception:
                    pass

            success_msg = "Application Submitted Successfully."

            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': success_msg,
                    'application_id': str(app.id)
                })

            messages.success(request, success_msg)
            return redirect(reverse('frontend:public_job_share', kwargs={'pk': job.pk}) + '?applied=true')

        except Exception as e:
            logger.exception("Error processing public job application")
            error_message = str(e)
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': f"Application Error: {error_message}",
                    'error': error_message
                }, status=400)
            messages.error(request, f"Application Error: {error_message}")
            return redirect('frontend:public_job_share', pk=job_id)

class AddToPipelineView(RecruiterRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        candidate = get_object_or_404(CandidateProfile, pk=pk)
        job_id = request.POST.get('job_id')
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json' or request.META.get('HTTP_ACCEPT') == 'application/json'
        
        if not job_id:
            if is_ajax:
                return JsonResponse({"success": False, "message": "Please select a job."}, status=400)
            messages.error(request, "Please select a job.")
            return redirect('frontend:candidate_detail', pk=pk)
            
        job = get_object_or_404(Job, id=job_id)
        
        # Prevent duplicate applications
        application, created = Application.objects.get_or_create(
            candidate=candidate,
            job=job,
            defaults={'stage': 'OPEN', 'in_pipeline': True}
        )
        if not created:
            application.in_pipeline = True
            application.save()
        
        # Calculate and sync ATS Score for this application
        from services.candidate_matching_service import CandidateMatchingService
        CandidateMatchingService.update_ats_scores(candidate_id=candidate.id, job_id=job.id)
        
        if created:
            messages.success(request, f"{candidate.full_name or candidate.user.email} added to {job.title} pipeline.")
            # Notify Recruiter
            Notification.objects.create(
                recipient=request.user,
                title="Candidate Added to Pipeline",
                message=f"Candidate {candidate.full_name or candidate.user.email} was added to the {job.title} pipeline.",
                notification_type='APPLICATION_STATUS'
            )
            # Notify Candidate
            if candidate.user:
                Notification.objects.create(
                    recipient=candidate.user,
                    title="Added to Recruitment Pipeline",
                    message=f"You have been added to the recruitment pipeline for {job.title}.",
                    notification_type='APPLICATION_STATUS'
                )
        else:
            messages.info(request, "Candidate is already in this job's pipeline.")
            
        if is_ajax:
            return JsonResponse({
                "success": True,
                "created": created,
                "message": "Candidate moved to Pipeline successfully." if created else "Candidate is already in Pipeline.",
                "in_pipeline": True
            })
            
        next_url = request.POST.get('next') or request.GET.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('frontend:ats_pipeline')


class BulkAddToPipelineView(RecruiterRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        import json
        candidate_ids = request.POST.getlist('candidate_ids') or request.POST.getlist('candidate_ids[]')
        job_id = request.POST.get('job_id')

        if not candidate_ids and request.POST.get('candidate_ids'):
            candidate_ids = [c.strip() for c in request.POST.get('candidate_ids').split(',') if c.strip()]

        if not candidate_ids and request.content_type == 'application/json':
            try:
                body = json.loads(request.body)
                job_id = job_id or body.get('job_id')
                candidate_ids = body.get('candidate_ids', [])
            except Exception:
                pass

        if not candidate_ids:
            return JsonResponse({
                "success": False,
                "message": "Please select at least one candidate."
            }, status=400)

        if not job_id:
            return JsonResponse({
                "success": False,
                "message": "Please select a job opening."
            }, status=400)

        job = get_object_or_404(Job, id=job_id)

        from django.db import transaction
        added_count = 0
        skipped_count = 0

        with transaction.atomic():
            candidates = CandidateProfile.objects.filter(id__in=candidate_ids)
            for candidate in candidates:
                application, created = Application.objects.get_or_create(
                    candidate=candidate,
                    job=job,
                    defaults={'stage': 'OPEN', 'in_pipeline': True}
                )
                if created:
                    added_count += 1
                    Notification.objects.create(
                        recipient=request.user,
                        title="Candidate Added to Pipeline",
                        message=f"Candidate {candidate.full_name or candidate.user.email} was added to the {job.title} pipeline.",
                        notification_type='APPLICATION_STATUS'
                    )
                else:
                    if not application.in_pipeline:
                        application.in_pipeline = True
                        application.save(update_fields=['in_pipeline'])
                        added_count += 1
                    else:
                        skipped_count += 1

        if added_count > 0 and skipped_count == 0:
            msg = f"{added_count} candidate{'s' if added_count > 1 else ''} added to pipeline successfully."
        elif added_count > 0 and skipped_count > 0:
            msg = f"{added_count} candidate{'s' if added_count > 1 else ''} added ({skipped_count} candidate{'s' if skipped_count > 1 else ''} already in pipeline)."
        else:
            msg = "Candidate is already in this pipeline."

        return JsonResponse({
            "success": True,
            "added_count": added_count,
            "skipped_count": skipped_count,
            "message": msg
        })


class RemoveFromPipelineView(RecruiterRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        candidate = get_object_or_404(CandidateProfile, pk=pk)
        job_id = request.POST.get('job_id')
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json' or request.META.get('HTTP_ACCEPT') == 'application/json'
        
        if not job_id:
            if is_ajax:
                return JsonResponse({"success": False, "message": "Job ID is required."}, status=400)
            messages.error(request, "Job ID is required.")
            return redirect('frontend:candidate_detail', pk=pk)
            
        job = get_object_or_404(Job, id=job_id)
        
        application = Application.objects.filter(candidate=candidate, job=job).first()
        if application:
            application.in_pipeline = False
            application.save()
            
            # Notify Recruiter
            Notification.objects.create(
                recipient=request.user,
                title="Candidate Removed from Pipeline",
                message=f"Candidate {candidate.full_name or candidate.user.email} was removed from the {job.title} pipeline.",
                notification_type='APPLICATION_STATUS'
            )
            
            if is_ajax:
                return JsonResponse({
                    "success": True,
                    "message": "Candidate removed from Pipeline successfully.",
                    "in_pipeline": False
                })
            messages.success(request, f"{candidate.full_name or candidate.user.email} removed from {job.title} pipeline.")
        else:
            if is_ajax:
                return JsonResponse({"success": False, "message": "Application not found or not in pipeline."}, status=404)
            messages.info(request, "Candidate is not in this job's pipeline.")
            
        next_url = request.POST.get('next') or request.GET.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('frontend:ats_pipeline')


import json

class UpdateApplicationStageView(RecruiterRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            app_id = data.get('application_id')
            new_stage = data.get('new_stage')
            
            application = get_object_or_404(Application, id=app_id)
            old_stage = application.stage
            
            # Map frontend stage columns back to DB stage representation if applicable
            stage_mapping = {
                'APPLIED': 'OPEN',
                'SCREENING': 'SCREENING_SELECT',
                'SHORTLISTED': 'SYSTEM_SELECTED',
                'INTERVIEW': 'INTERVIEW_SCHEDULE',
                'TECHNICAL': 'INTERVIEW_SELECT',
                'HR': 'DOCUMENTATION_STAGE',
                'OFFER': 'OFFER_STAGE',
                'HIRED': 'JOINED',
                'REJECTED': 'SYSTEM_REJECTED'
            }
            if new_stage in stage_mapping:
                new_stage = stage_mapping[new_stage]
                
            application.stage = new_stage
            application.save()
            
            # Notify Recruiter
            Notification.objects.create(
                recipient=request.user,
                title="Application Stage Updated",
                message=f"Candidate {application.candidate.full_name or application.candidate.user.email} was moved from {old_stage} to {new_stage} for job {application.job.title}.",
                notification_type='APPLICATION_STATUS'
            )
            # Notify Candidate
            if application.candidate.user:
                if new_stage in ['INTERVIEW_SCHEDULE', 'OFFER_STAGE', 'JOINED']:
                    Notification.objects.create(
                        recipient=application.candidate.user,
                        title=f"Application Stage: {application.get_stage_display()}",
                        message=f"Your application status for '{application.job.title}' has been updated to {application.get_stage_display()}.",
                        notification_type='APPLICATION_STATUS'
                    )
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

class CompleteTaskView(RecruiterRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        task_type = request.POST.get('task_type')
        object_id = request.POST.get('object_id')
        
        if task_type == 'screen':
            app = get_object_or_404(Application, id=object_id)
            app.stage = 'SCREENING_FEEDBACK_PENDING'
            app.save()
            messages.success(request, f"Task complete: Screened {app.candidate.full_name or app.candidate.user.email}.")
        elif task_type == 'interview':
            interview = get_object_or_404(Interview, id=object_id)
            interview.status = 'COMPLETED'
            interview.save()
            messages.success(request, f"Task complete: Conducted interview for {interview.application.candidate.full_name or interview.application.candidate.user.email}.")
            
        return redirect('frontend:recruiter_dashboard')

class ATSPipelineView(RecruiterRequiredMixin, TemplateView):
    template_name = 'ats_pipeline.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        job_id = self.request.GET.get('job_id')
        tenant_jobs = get_tenant_jobs_qs(self.request.user)
        if not job_id:
            job = tenant_jobs.filter(status='ACTIVE').first()
        else:
            job = tenant_jobs.filter(id=job_id).first()
        
        context['selected_job'] = job
        context['all_jobs'] = tenant_jobs.filter(status='ACTIVE')
        
        if job:
            apps = Application.objects.filter(job=job, in_pipeline=True).select_related('candidate__user')
            
            pipeline_columns = [
                {
                    'stage': 'APPLIED',
                    'label': 'Applied',
                    'color': '#3b82f6',
                    'db_stages': ['OPEN', 'SYSTEM_SUBMITTED']
                },
                {
                    'stage': 'SCREENING',
                    'label': 'Screening',
                    'color': '#f59e0b',
                    'db_stages': ['SCREENING_FEEDBACK_PENDING', 'SCREENING_SELECT']
                },
                {
                    'stage': 'SHORTLISTED',
                    'label': 'Shortlisted',
                    'color': '#10b981',
                    'db_stages': ['SYSTEM_SELECTED', 'AUTOMATION_SKIPPED']
                },
                {
                    'stage': 'INTERVIEW',
                    'label': 'Interview',
                    'color': '#8b5cf6',
                    'db_stages': ['INTERVIEW_SCHEDULE', 'INTERVIEW_IN_PROCESS']
                },
                {
                    'stage': 'TECHNICAL',
                    'label': 'Technical',
                    'color': '#6366f1',
                    'db_stages': ['INTERVIEW_SELECT']
                },
                {
                    'stage': 'HR',
                    'label': 'HR',
                    'color': '#ec4899',
                    'db_stages': ['DOCUMENTATION_STAGE', 'NEGOTIATION_STAGE']
                },
                {
                    'stage': 'OFFER',
                    'label': 'Offer',
                    'color': '#a855f7',
                    'db_stages': ['OFFER_STAGE', 'ACCEPTED', 'JOINING_CONFIRMATION_REQUESTED', 'JOINING_CONFIRMATION_RECEIVED']
                },
                {
                    'stage': 'HIRED',
                    'label': 'Hired',
                    'color': '#059669',
                    'db_stages': ['JOINED']
                },
                {
                    'stage': 'REJECTED',
                    'label': 'Rejected',
                    'color': '#ef4444',
                    'db_stages': ['SCREENING_REJECT', 'INTERVIEW_REJECT', 'SYSTEM_REJECTED', 'DROPOUT']
                }
            ]
            
            pipeline_data = []
            for col in pipeline_columns:
                pipeline_data.append({
                    'stage': col['stage'],
                    'label': col['label'],
                    'apps': apps.filter(stage__in=col['db_stages']),
                    'color': col['color']
                })
            context['pipeline'] = pipeline_data
        return context

class InterviewsView(LoginRequiredMixin, ListView):
    model = Interview
    template_name = 'interviews.html'
    context_object_name = 'interviews'
    
    def get_queryset(self):
        return get_tenant_interviews_qs(self.request.user).order_by('start_time')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.role == 'CANDIDATE':
            context['base_template'] = 'layouts/candidate_base.html'
        else:
            context['base_template'] = 'layouts/recruiter_base.html'
            context['applications'] = get_tenant_applications_qs(self.request.user).select_related('candidate__user', 'job')
            company = get_user_company(self.request.user)
            if company:
                context['recruiters'] = User.objects.filter(company_affiliations__company=company)
            else:
                context['recruiters'] = User.objects.filter(id=self.request.user.id)
        return context

    def post(self, request, *args, **kwargs):
        app_id = request.POST.get('application_id')
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        interview_type = request.POST.get('interview_type', 'TECHNICAL')
        meeting_link = request.POST.get('meeting_link', '')
        interviewer_id = request.POST.get('interviewer_id')
        round_name = request.POST.get('round', '')
        notes = request.POST.get('notes', '')
        
        try:
            application = Application.objects.get(id=app_id)
            interview = Interview.objects.create(
                application=application,
                start_time=start_time,
                end_time=end_time,
                interview_type=interview_type,
                meeting_link=meeting_link,
                round=round_name,
                notes=notes,
                status='SCHEDULED'
            )
            if interviewer_id:
                interviewer = User.objects.get(id=interviewer_id)
                interview.interviewers.add(interviewer)
                # Notify Interviewer
                Notification.objects.create(
                    recipient=interviewer,
                    title="Interview Assigned",
                    message=f"You have been assigned to interview {application.candidate.full_name or application.candidate.user.email} for '{application.job.title}' on {start_time}.",
                    notification_type='INTERVIEW_SCHEDULED'
                )
                
            # Notify Recruiter
            Notification.objects.create(
                recipient=request.user,
                title="Interview Scheduled",
                message=f"Interview scheduled with {application.candidate.full_name or application.candidate.user.email} for '{application.job.title}' on {start_time}.",
                notification_type='INTERVIEW_SCHEDULED'
            )
            # Notify Candidate
            if application.candidate.user:
                Notification.objects.create(
                    recipient=application.candidate.user,
                    title="Interview Scheduled",
                    message=f"An interview for the job '{application.job.title}' has been scheduled on {start_time}.",
                    notification_type='INTERVIEW_SCHEDULED'
                )
                
            messages.success(request, 'Interview scheduled successfully.')
        except Exception as e:
            messages.error(request, f'Failed to schedule interview: {e}')
            
        return redirect('frontend:interviews')

class InterviewCalendarEventsView(RecruiterRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        events = []
        interviews = Interview.objects.select_related('application__candidate__user', 'application__job').all()
        for i in interviews:
            events.append({
                'title': f"{i.application.candidate.user.get_full_name() or i.application.candidate.user.email} - {i.application.job.title}",
                'start': i.start_time.isoformat(),
                'end': i.end_time.isoformat(),
                'url': reverse_lazy('frontend:candidate_detail', kwargs={'pk': i.application.candidate.id}),
                'color': '#3b82f6' if i.status == 'SCHEDULED' else '#10b981'
            })
        return JsonResponse(events, safe=False)

import csv
from django.http import HttpResponse

class ExportCandidatesView(RecruiterRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="candidates.csv"'
        writer = csv.writer(response)
        writer.writerow(['Name', 'Email', 'Phone', 'Location', 'Experience', 'Current Company', 'Designation', 'Current CTC', 'Expected CTC', 'Notice Period'])
        for c in get_tenant_candidates_qs(request.user).select_related('user'):
            writer.writerow([
                c.user.get_full_name() or c.user.email,
                c.user.email,
                c.user.phone_number,
                c.location,
                c.total_experience,
                c.current_company,
                c.current_designation,
                c.current_salary,
                c.expected_salary,
                c.notice_period
            ])
        return response

class ExportJobsView(RecruiterRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="jobs.csv"'
        writer = csv.writer(response)
        writer.writerow(['Title', 'Company', 'Location', 'Job Type', 'Experience Level', 'Salary Min', 'Salary Max', 'Status'])
        for j in get_tenant_jobs_qs(request.user).select_related('company'):
            writer.writerow([j.title, j.company.name if j.company else '', j.location, j.job_type, f"{j.min_experience}-{j.max_experience} Years", j.min_salary, j.max_salary, j.status])
        return response

class ExportInterviewsView(RecruiterRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="interviews.csv"'
        writer = csv.writer(response)
        writer.writerow(['Candidate', 'Job', 'Start Time', 'End Time', 'Round', 'Status', 'Meeting Link'])
        for i in get_tenant_interviews_qs(request.user).select_related('application__candidate__user', 'application__job'):
            writer.writerow([
                i.application.candidate.user.email if i.application and i.application.candidate and i.application.candidate.user else '',
                i.application.job.title if i.application and i.application.job else '',
                i.start_time,
                i.end_time,
                i.round,
                i.status,
                i.meeting_link
            ])
        return response

from apps.candidates.models import CandidateSkill

class AnalyticsView(RecruiterRequiredMixin, TemplateView):
    template_name = 'analytics.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Hiring Funnel Data
        funnel_data = get_tenant_applications_qs(self.request.user).values('stage').annotate(count=Count('id'))
        context['funnel_labels'] = [s[1] for s in Application.ApplicationStage.choices]
        context['funnel_values'] = []
        for stage_code, stage_label in Application.ApplicationStage.choices:
            count = next((item['count'] for item in funnel_data if item['stage'] == stage_code), 0)
            context['funnel_values'].append(count)
            
        # Top Skills Data
        top_skills = CandidateSkill.objects.filter(profile__in=get_tenant_candidates_qs(self.request.user)).values('skill_name').annotate(count=Count('id')).order_by('-count')[:5]
        context['skill_labels'] = [item['skill_name'] for item in top_skills]
        context['skill_values'] = [item['count'] for item in top_skills]
        
        # Source Data
        context['source_labels'] = ['LinkedIn', 'Indeed', 'Naukri', 'Referral']
        context['source_values'] = [45, 30, 20, 5]
        
        return context

class SettingsView(LoginRequiredMixin, TemplateView):
    def get_template_names(self):
        if self.request.user.role == 'CANDIDATE':
            return ['candidate_settings.html']
        return ['settings.html']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        cm = user.company_affiliations.select_related('company').first()
        context['company_name'] = cm.company.name if cm and cm.company else ""
        context['designation'] = cm.designation if cm else ""
        return context

    def post(self, request, *args, **kwargs):
        view = ProfileSettingsUpdateView.as_view()
        response = view(request, *args, **kwargs)
        if isinstance(response, JsonResponse):
            import json
            data = json.loads(response.content)
            if data.get('success'):
                from django.contrib import messages
                messages.success(request, data.get('message', 'Profile settings saved successfully!'))
            else:
                from django.contrib import messages
                messages.error(request, data.get('error', 'Failed to update profile settings.'))
            return redirect('frontend:settings')
        return response


class ProfileSettingsUpdateView(LoginRequiredMixin, View):
    """
    AJAX endpoint to validate, save profile settings (photo, names, company, designation, phone, email).
    """
    def post(self, request, *args, **kwargs):
        user = request.user
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone_number = request.POST.get('phone_number') or request.POST.get('phone', '')
        company_name = request.POST.get('company_name', '').strip()
        designation = request.POST.get('designation', '').strip()

        if not email or '@' not in email:
            return JsonResponse({'success': False, 'error': 'Please enter a valid email address.'}, status=400)

        if User.objects.filter(email__iexact=email).exclude(id=user.id).exists():
            return JsonResponse({'success': False, 'error': 'This email address is already in use by another account.'}, status=400)

        user.first_name = first_name
        user.last_name = last_name
        user.email = email
        if phone_number is not None:
            user.phone_number = phone_number.strip()

        if 'profile_picture' in request.FILES:
            photo_file = request.FILES['profile_picture']
            from django.core.files.storage import FileSystemStorage
            fs = FileSystemStorage()
            filename = fs.save(f"profile_photos/{user.id}_{photo_file.name}", photo_file)
            user.profile_picture = fs.url(filename)
        elif request.POST.get('profile_picture_url'):
            user.profile_picture = request.POST.get('profile_picture_url').strip()

        user.save()

        if company_name:
            from apps.companies.models import Company, CompanyMember
            from django.utils.text import slugify
            company, _ = Company.objects.get_or_create(
                name=company_name,
                defaults={'slug': slugify(company_name) or str(user.id)[:8]}
            )
            cm = user.company_affiliations.first()
            if cm:
                cm.company = company
                if designation:
                    cm.designation = designation
                cm.save()
            else:
                CompanyMember.objects.create(
                    company=company,
                    user=user,
                    designation=designation or "Recruiter",
                    role=CompanyMember.MemberRole.RECRUITER
                )

        from django.contrib import messages
        messages.success(request, "Profile settings updated successfully!")

        return JsonResponse({
            'success': True,
            'message': 'Profile settings updated successfully!',
            'user': {
                'first_name': user.first_name,
                'last_name': user.last_name,
                'full_name': user.get_full_name() or user.first_name or "Recruiter",
                'email': user.email,
                'phone_number': user.phone_number or '',
                'profile_picture': user.profile_picture or '',
                'company_name': company_name,
                'designation': designation
            }
        })


class CandidateMessageAPIView(LoginRequiredMixin, View):
    """
    AJAX Endpoint for Candidate Messaging (Inbox, Chat Thread, Send Message, Emoji, Attachment, Read Status).
    """
    def get(self, request, *args, **kwargs):
        user = request.user
        candidate_id = request.GET.get('candidate_id')
        recipient_user_id = request.GET.get('recipient_user_id')
        search_query = request.GET.get('q', '').strip()

        from apps.notifications.models import CandidateMessage
        from apps.candidates.models import CandidateProfile
        from django.utils import timezone as django_timezone

        total_unread_count = CandidateMessage.objects.filter(
            recipient=user,
            is_read=False
        ).count()

        if candidate_id or recipient_user_id:
            cand_profile = None
            target_user = None

            if recipient_user_id and recipient_user_id not in ['undefined', 'null', 'None']:
                try:
                    target_user = User.objects.get(id=recipient_user_id)
                except Exception:
                    target_user = None
                if not target_user:
                    try:
                        cand_profile = CandidateProfile.objects.get(id=recipient_user_id)
                        target_user = cand_profile.user
                    except Exception:
                        pass

            if not target_user and candidate_id and candidate_id not in ['undefined', 'null', 'None']:
                try:
                    cand_profile = CandidateProfile.objects.get(id=candidate_id)
                    target_user = cand_profile.user
                except Exception:
                    pass

            if target_user and not cand_profile:
                try:
                    cand_profile = target_user.candidate_profile
                except Exception:
                    cand_profile = None

            if not target_user:
                return JsonResponse({'success': False, 'error': 'Candidate user not found.'}, status=404)

            messages_qs = CandidateMessage.objects.filter(
                Q(sender=user, recipient=target_user) | Q(sender=target_user, recipient=user)
            ).order_by('created_at')

            unread_incoming = messages_qs.filter(recipient=user, is_read=False)
            if unread_incoming.exists():
                unread_incoming.update(is_read=True, read_at=django_timezone.now())

            messages_list = []
            for msg in messages_qs:
                messages_list.append({
                    'id': str(msg.id),
                    'sender_id': str(msg.sender.id),
                    'is_me': msg.sender.id == user.id,
                    'text': msg.message_text,
                    'attachment_url': msg.attachment.url if msg.attachment else None,
                    'attachment_name': msg.attachment_name or (os.path.basename(msg.attachment.name) if msg.attachment else None),
                    'timestamp': django_timezone.localtime(msg.created_at).strftime("%I:%M %p, %b %d"),
                    'is_read': msg.is_read
                })

            cand_name = cand_profile.full_name if cand_profile and cand_profile.full_name else (target_user.get_full_name() or target_user.email)

            return JsonResponse({
                'success': True,
                'candidate': {
                    'id': str(cand_profile.id) if cand_profile else '',
                    'user_id': str(target_user.id),
                    'name': cand_name,
                    'email': target_user.email,
                    'avatar': target_user.profile_picture or f"https://ui-avatars.com/api/?background=2563eb&color=fff&name={cand_name}"
                },
                'messages': messages_list,
                'total_unread_count': total_unread_count
            })

        # Search or list conversations
        candidates_qs = get_tenant_candidates_qs(user).select_related('user')
        if search_query:
            candidates_qs = candidates_qs.filter(
                Q(full_name__icontains=search_query) | Q(user__email__icontains=search_query)
            )

        conversations = []
        for cand in candidates_qs[:30]:
            last_msg = CandidateMessage.objects.filter(
                Q(sender=user, recipient=cand.user) | Q(sender=cand.user, recipient=user)
            ).order_by('-created_at').first()

            unread_count = CandidateMessage.objects.filter(
                sender=cand.user,
                recipient=user,
                is_read=False
            ).count()

            cand_name = cand.full_name or cand.user.email
            last_text = last_msg.message_text if last_msg else "Click to start chatting"
            if last_msg and last_msg.attachment and not last_text:
                last_text = "📎 Attachment"

            conversations.append({
                'candidate_id': str(cand.id),
                'recipient_user_id': str(cand.user.id),
                'candidate_name': cand_name,
                'candidate_email': cand.user.email,
                'avatar': cand.user.profile_picture or f"https://ui-avatars.com/api/?background=2563eb&color=fff&name={cand_name}",
                'last_message': last_text,
                'last_time': django_timezone.localtime(last_msg.created_at).strftime("%b %d, %I:%M %p") if last_msg else '',
                'unread_count': unread_count
            })

        return JsonResponse({
            'success': True,
            'conversations': conversations,
            'total_unread_count': total_unread_count
        })

    def post(self, request, *args, **kwargs):
        user = request.user
        
        recipient_id = request.POST.get('recipient_id') or request.POST.get('recipient_user_id')
        candidate_id = request.POST.get('candidate_id')
        message_text = request.POST.get('message_text', '').strip()
        attachment_file = request.FILES.get('attachment')

        if request.content_type and 'application/json' in request.content_type:
            import json
            try:
                data = json.loads(request.body.decode('utf-8'))
                recipient_id = recipient_id or data.get('recipient_id') or data.get('recipient_user_id')
                candidate_id = candidate_id or data.get('candidate_id')
                message_text = message_text or str(data.get('message_text') or data.get('message') or '').strip()
            except Exception:
                pass

        from apps.notifications.models import CandidateMessage
        from apps.candidates.models import CandidateProfile
        from django.utils import timezone as django_timezone

        target_user = None
        cand_profile = None

        if recipient_id in ['undefined', 'null', 'None']:
            recipient_id = None
        if candidate_id in ['undefined', 'null', 'None']:
            candidate_id = None

        if recipient_id:
            try:
                target_user = User.objects.get(id=recipient_id)
            except Exception:
                target_user = None

            if not target_user:
                try:
                    cand_profile = CandidateProfile.objects.get(id=recipient_id)
                    target_user = cand_profile.user
                except Exception:
                    pass

        if not target_user and candidate_id:
            try:
                cand_profile = CandidateProfile.objects.get(id=candidate_id)
                target_user = cand_profile.user
            except Exception:
                pass

        if target_user and not cand_profile:
            try:
                cand_profile = target_user.candidate_profile
            except Exception:
                cand_profile = None

        if not target_user:
            return JsonResponse({'success': False, 'error': 'Recipient candidate not found.'}, status=400)

        if not message_text and not attachment_file:
            return JsonResponse({'success': False, 'error': 'Message text or attachment is required.'}, status=400)

        try:
            msg = CandidateMessage.objects.create(
                sender=user,
                recipient=target_user,
                candidate=cand_profile,
                message_text=message_text,
                attachment=attachment_file,
                attachment_name=attachment_file.name if attachment_file else None
            )
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Failed to save message: {str(e)}'}, status=500)

        return JsonResponse({
            'success': True,
            'message': {
                'id': str(msg.id),
                'sender_id': str(user.id),
                'is_me': True,
                'text': msg.message_text,
                'attachment_url': msg.attachment.url if msg.attachment else None,
                'attachment_name': msg.attachment_name,
                'timestamp': django_timezone.localtime(msg.created_at).strftime("%I:%M %p, %b %d")
            }
        })


from apps.candidates.utils import handle_resume_upload
from django.contrib import messages

class ResumeParserView(RecruiterRequiredMixin, TemplateView):
    template_name = 'resume_parser.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        context['duplicates_found_today'] = DuplicateResumeLog.objects.filter(created_at__date=today).count()
        from apps.candidates.forms import ManualCandidateForm
        
        from apps.jobs.models import Job
        job_id = self.request.GET.get('job_id') or self.request.POST.get('job_id')
        if job_id:
            try:
                context['job'] = Job.objects.get(id=job_id)
            except Exception:
                pass
        
        candidate_id = self.request.GET.get('candidate_id')
        experiences_json = '[]'
        if candidate_id:
            try:
                profile = CandidateProfile.objects.get(id=candidate_id)
                context['editing_profile'] = profile
                
                # Pre-populate manual form fields
                initial_data = {
                    "full_name": profile.full_name,
                    "email": profile.user.email,
                    "phone_number": profile.user.phone_number or '',
                    "current_company": profile.current_company,
                    "current_designation": profile.current_designation,
                    "total_experience": profile.total_experience,
                    "location": profile.location,
                    "linkedin_url": profile.linkedin_url,
                    "portfolio_url": profile.portfolio_url,
                    "summary": profile.summary,
                }
                
                # Fetch qualifications/location/etc. from parsed_json
                personal_info = profile.parsed_json.get('personal_info', {}) if profile.parsed_json else {}
                initial_data.update({
                    "relevant_experience": personal_info.get('relevant_experience', 0.0),
                    "preferred_location": personal_info.get('preferred_location', ''),
                    "current_salary": float(profile.current_salary / 100000) if profile.current_salary else None,
                    "expected_salary": float(profile.expected_salary / 100000) if profile.expected_salary else None,
                    "notice_period": profile.notice_period or 30,
                    "highest_qualification": personal_info.get('highest_qualification', ''),
                    "college_university": personal_info.get('college_university', ''),
                    "github_url": personal_info.get('github_url', ''),
                })
                
                skills_list = list(profile.skills.values_list('skill_name', flat=True))
                if skills_list:
                    initial_data["primary_skills"] = ", ".join(skills_list[:len(skills_list)//2])
                    initial_data["secondary_skills"] = ", ".join(skills_list[len(skills_list)//2:])
                    
                context['manual_form'] = ManualCandidateForm(initial=initial_data)
                
                # Gather experiences
                experiences_list = []
                parsed_experiences = profile.parsed_json.get('experience', []) if profile.parsed_json else []
                if parsed_experiences:
                    for exp in parsed_experiences:
                        experiences_list.append({
                            "company": exp.get('company') or exp.get('company_name') or '',
                            "designation": exp.get('designation') or exp.get('job_title') or '',
                            "start_date": exp.get('start_date') or '',
                            "end_date": exp.get('end_date') or '',
                            "is_current": exp.get('is_current') or False,
                            "is_relevant": exp.get('is_relevant') or False,
                            "description": exp.get('description') or '',
                            "employment_type": exp.get('employment_type') or 'Full Time',
                            "location": exp.get('location') or '',
                            "industry": exp.get('industry') or '',
                            "skills_used": exp.get('skills_used') or '',
                            "job_description": exp.get('job_description') or '',
                            "responsibilities": exp.get('responsibilities') or '',
                            "achievements": exp.get('achievements') or ''
                        })
                else:
                    for exp in profile.experiences.all().order_by('-start_date'):
                        experiences_list.append({
                            "company": exp.company_name,
                            "designation": exp.designation,
                            "start_date": exp.start_date.strftime('%Y-%m') if exp.start_date else '',
                            "end_date": exp.end_date.strftime('%Y-%m') if exp.end_date else '',
                            "is_current": exp.is_current,
                            "description": exp.description,
                            "employment_type": "Full Time",
                            "location": "",
                            "industry": "",
                            "skills_used": ""
                        })
                import json as _json
                experiences_json = _json.dumps(experiences_list)
            except Exception:
                pass
        else:
            context['manual_form'] = ManualCandidateForm()
            
        context['experiences_json'] = experiences_json
        return context

    def post(self, request, *args, **kwargs):
        from apps.candidates.forms import ManualCandidateForm
        from django.http import JsonResponse
        from django.db import transaction
        
        # Check if this is a manual save request
        if request.POST.get('action') == 'manual_save':
            form = ManualCandidateForm(request.POST, request.FILES)
            if form.is_valid():
                candidate_id = request.POST.get('candidate_id')
                email = form.cleaned_data['email']
                phone = form.cleaned_data['phone_number']
                
                ignore_duplicate = request.POST.get('ignore_duplicate') == 'true'
                
                # Duplicate email/mobile verification for new candidates
                if not candidate_id and not ignore_duplicate:
                    existing_user = None
                    if phone:
                        existing_user = User.objects.filter(Q(email=email) | Q(phone_number=phone)).first()
                    else:
                        existing_user = User.objects.filter(email=email).first()
                    if existing_user:
                        existing_profile = getattr(existing_user, 'candidate_profile', None)
                        return JsonResponse({
                            "success": False,
                            "stage": "duplicate",
                            "message": "Candidate profile with this email or phone number already exists.",
                            "duplicate_candidate": {
                                "candidate_id": str(existing_profile.id) if existing_profile else "",
                                "name": existing_profile.full_name if existing_profile else "Unknown",
                                "email": existing_user.email,
                                "phone": existing_user.phone_number or "Not specified",
                                "current_company": existing_profile.current_company if existing_profile else "Not specified"
                            }
                        }, status=400)
                
                if not candidate_id and ignore_duplicate:
                    if User.objects.filter(email=email).exists():
                        import time
                        if '@' in email:
                            parts = email.split('@')
                            email = f"{parts[0]}+anyway{int(time.time())}@{parts[1]}"
                        else:
                            email = f"{email}+anyway{int(time.time())}"
                
                try:
                    with transaction.atomic():
                        if candidate_id:
                            profile = CandidateProfile.objects.get(id=candidate_id)
                            user = profile.user
                            user.email = email
                            user.phone_number = phone if phone else None
                            user.save()
                        else:
                            user = User.objects.create(
                                email=email,
                                role=User.Role.CANDIDATE,
                                phone_number=phone if phone else None
                            )
                            user.set_unusable_password()
                            user.save()
                            profile = CandidateProfile.objects.create(user=user)
                        
                        profile.full_name = form.cleaned_data.get('full_name', '')
                        profile.current_company = form.cleaned_data.get('current_company', '')
                        profile.current_designation = form.cleaned_data.get('current_designation', '')
                        profile.total_experience = form.cleaned_data.get('total_experience') or 0.0
                        profile.location = form.cleaned_data.get('location') or "Unknown"
                        
                        curr_sal = form.cleaned_data.get('current_salary')
                        if curr_sal is not None:
                            profile.current_salary = curr_sal * 100000
                        else:
                            profile.current_salary = None
                            
                        exp_sal = form.cleaned_data.get('expected_salary')
                        if exp_sal is not None:
                            profile.expected_salary = exp_sal * 100000
                        else:
                            profile.expected_salary = None
                            
                        profile.notice_period = form.cleaned_data.get('notice_period') or 30
                        profile.linkedin_url = form.cleaned_data.get('linkedin_url', '')
                        profile.portfolio_url = form.cleaned_data.get('portfolio_url', '')
                        profile.summary = form.cleaned_data.get('summary', '') or ""
                        profile.created_by = request.user
                        profile.uploaded_by = request.user
                        
                        # Store customized parsing payload in parsed_json
                        parsed_json = profile.parsed_json or {}
                        parsed_json.update({
                            "personal_info": {
                                "name": profile.full_name,
                                "email": email,
                                "phone": phone,
                                "location": profile.location,
                                "preferred_location": form.cleaned_data.get('preferred_location', ''),
                                "current_company": profile.current_company,
                                "current_designation": profile.current_designation,
                                "total_experience": float(profile.total_experience),
                                "relevant_experience": float(form.cleaned_data.get('relevant_experience') or 0.0),
                                "highest_qualification": form.cleaned_data.get('highest_qualification', ''),
                                "college_university": form.cleaned_data.get('college_university', ''),
                                "linkedin_url": profile.linkedin_url,
                                "github_url": form.cleaned_data.get('github_url', ''),
                                "portfolio_url": profile.portfolio_url,
                            },
                            "skills": [s.strip() for s in (form.cleaned_data.get('primary_skills') or '').split(',') if s.strip()] +
                                      [s.strip() for s in (form.cleaned_data.get('secondary_skills') or '').split(',') if s.strip()],
                            "summary": profile.summary
                        })
                        profile.parsed_json = parsed_json
                        
                        resume_file = request.FILES.get('resume')
                        if resume_file:
                            from services.resume_storage_service import upload_and_verify_resume, copy_and_verify_original_resume
                            saved_key, _ = upload_and_verify_resume(resume_file, resume_file.name)
                            profile.resume.name = saved_key
                            profile.original_filename = resume_file.name
                            profile.secure_filename = resume_file.name
                            profile.parser_status = "SUCCESS"
                            profile.preview_status = "READY"
                            orig_key = copy_and_verify_original_resume(saved_key, resume_file.name)
                            if orig_key:
                                profile.original_file.name = orig_key
                            
                        profile.save()
                        
                        # Save Skills to CandidateSkill model:
                        profile.skills.all().delete()
                        for skill in parsed_json.get('skills', []):
                            CandidateSkill.objects.get_or_create(profile=profile, skill_name=skill.strip().title()[:100])
                            
                        if form.cleaned_data['highest_qualification'] or form.cleaned_data['college_university']:
                            profile.educations.all().delete()
                            Education.objects.create(
                                profile=profile,
                                institution=form.cleaned_data['college_university'] or "Unknown",
                                degree=form.cleaned_data['highest_qualification'] or "Degree",
                                field_of_study="General"
                            )
                            
                        # Save Experiences
                        from apps.candidates.utils import parse_date_robust
                        import json as _json
                        exps_data = []
                        idx = 0
                        while True:
                            company = request.POST.get(f'experience[{idx}][company]')
                            if company is None:
                                break
                            designation = request.POST.get(f'experience[{idx}][designation]')
                            start_date = request.POST.get(f'experience[{idx}][start_date]')
                            end_date = request.POST.get(f'experience[{idx}][end_date]')
                            is_current = request.POST.get(f'experience[{idx}][is_current]') in ('on', 'true', 'checked', True)
                            is_relevant = request.POST.get(f'experience[{idx}][is_relevant]') in ('on', 'true', 'checked', True) or request.POST.get(f'experience[{idx}][is_relevant]') is None
                            employment_type = request.POST.get(f'experience[{idx}][employment_type]', 'Full Time')
                            location = request.POST.get(f'experience[{idx}][location]', '')
                            skills_used = request.POST.get(f'experience[{idx}][skills_used]', '')
                            job_description = request.POST.get(f'experience[{idx}][job_description]', '')
                            responsibilities = request.POST.get(f'experience[{idx}][responsibilities]', '')
                            achievements = request.POST.get(f'experience[{idx}][achievements]', '')
                            
                            desc_parts = []
                            if job_description:
                                desc_parts.append(f"Job Description:\n{job_description}")
                            if responsibilities:
                                desc_parts.append(f"Responsibilities:\n{responsibilities}")
                            if achievements:
                                desc_parts.append(f"Achievements:\n{achievements}")
                            description = "\n\n".join(desc_parts)
                            
                            exps_data.append({
                                "company": company,
                                "designation": designation,
                                "start_date": start_date,
                                "end_date": end_date,
                                "is_current": is_current,
                                "is_relevant": is_relevant,
                                "employment_type": employment_type,
                                "location": location,
                                "skills_used": skills_used,
                                "job_description": job_description,
                                "responsibilities": responsibilities,
                                "achievements": achievements,
                                "description": description
                            })
                            idx += 1
                            
                        if not exps_data:
                            experiences_json = request.POST.get('experiences_json', '[]')
                            try:
                                exps_data = _json.loads(experiences_json)
                            except Exception:
                                exps_data = []
                            
                        from apps.candidates.utils import sanitize_recursive
                        exps_data = sanitize_recursive(exps_data, "manual_save.experiences")
                            
                        profile.experiences.all().delete()
                        for exp in exps_data:
                            description_html = ResumeIntelligenceService.parse_experience_description_to_html(exp.get('description', ''))
                            Experience.objects.create(
                                profile=profile,
                                company_name=(exp.get('company') or '')[:100],
                                designation=(exp.get('designation') or '')[:100],
                                description=description_html,
                                start_date=parse_date_robust(exp.get('start_date'), None),
                                end_date=parse_date_robust(exp.get('end_date'), None),
                                is_current=exp.get('is_current', False)
                            )
                            
                        # Store in parsed_json
                        parsed_json['experience'] = exps_data
                        parsed_json = sanitize_recursive(parsed_json, "manual_save.parsed_json")
                        profile.parsed_json = parsed_json
                        profile.save()
                        
                        # Add job mapping if job_id is present
                        job_id = request.POST.get('job_id')
                        if job_id:
                            from apps.jobs.models import Job
                            from apps.applications.models import Application
                            from services.candidate_matching_service import CandidateMatchingService
                            try:
                                job = Job.objects.get(id=job_id)
                                app, created = Application.objects.get_or_create(job=job, candidate=profile)
                                CandidateMatchingService.update_ats_scores(candidate_id=profile.id, job_id=job.id)
                            except Exception as e_map:
                                logger.error(f"Error mapping manual candidate to job {job_id}: {e_map}", exc_info=True)
                            
                    return JsonResponse({"success": True, "candidate_id": str(profile.id), "job_id": request.POST.get('job_id', ''), "message": "Candidate saved successfully."})
                except Exception as e:
                    logger.error(f"[MANUAL SAVE FAILED] Exception: {str(e)}", exc_info=True)
                    return JsonResponse({"success": False, "message": f"Save failed: {str(e)}"}, status=400)
            else:
                return JsonResponse({"success": False, "errors": form.errors}, status=400)

        # Check if this is a manual merge request
        if request.POST.get('action') == 'manual_merge':
            form = ManualCandidateForm(request.POST, request.FILES)
            if form.is_valid():
                candidate_id = request.POST.get('candidate_id')
                if not candidate_id:
                    return JsonResponse({"success": False, "message": "Candidate ID is required for merge."}, status=400)
                try:
                    profile = CandidateProfile.objects.get(id=candidate_id)
                    from apps.candidates.utils import merge_candidate_profile_data
                    
                    idx = 0
                    exps_data = []
                    while True:
                        company = request.POST.get(f'experience[{idx}][company]')
                        if company is None:
                            break
                        designation = request.POST.get(f'experience[{idx}][designation]')
                        start_date = request.POST.get(f'experience[{idx}][start_date]')
                        end_date = request.POST.get(f'experience[{idx}][end_date]')
                        is_current = request.POST.get(f'experience[{idx}][is_current]') in ('on', 'true', 'checked', True)
                        employment_type = request.POST.get(f'experience[{idx}][employment_type]', 'Full Time')
                        location = request.POST.get(f'experience[{idx}][location]', '')
                        skills_used = request.POST.get(f'experience[{idx}][skills_used]', '')
                        job_description = request.POST.get(f'experience[{idx}][job_description]', '')
                        responsibilities = request.POST.get(f'experience[{idx}][responsibilities]', '')
                        achievements = request.POST.get(f'experience[{idx}][achievements]', '')
                        
                        desc_parts = []
                        if job_description: desc_parts.append(f"Job Description:\n{job_description}")
                        if responsibilities: desc_parts.append(f"Responsibilities:\n{responsibilities}")
                        if achievements: desc_parts.append(f"Achievements:\n{achievements}")
                        description = "\n\n".join(desc_parts)
                        
                        exps_data.append({
                            "company": company,
                            "designation": designation,
                            "start_date": start_date,
                            "end_date": end_date,
                            "is_current": is_current,
                            "description": description
                        })
                        idx += 1
                        
                    manual_parsed_data = {
                        "personal_info": {
                            "name": form.cleaned_data.get('full_name', ''),
                            "email": form.cleaned_data.get('email', ''),
                            "phone": form.cleaned_data.get('phone_number', ''),
                            "location": form.cleaned_data.get('location', ''),
                            "preferred_location": form.cleaned_data.get('preferred_location', ''),
                            "current_company": form.cleaned_data.get('current_company', ''),
                            "current_designation": form.cleaned_data.get('current_designation', ''),
                            "total_experience": float(form.cleaned_data.get('total_experience') or 0.0),
                            "relevant_experience": float(form.cleaned_data.get('relevant_experience') or 0.0),
                            "highest_qualification": form.cleaned_data.get('highest_qualification', ''),
                            "college_university": form.cleaned_data.get('college_university', ''),
                            "linkedin_url": form.cleaned_data.get('linkedin_url', ''),
                            "github_url": form.cleaned_data.get('github_url', ''),
                            "portfolio_url": form.cleaned_data.get('portfolio_url', ''),
                        },
                        "skills": [s.strip() for s in (form.cleaned_data.get('primary_skills') or '').split(',') if s.strip()] +
                                  [s.strip() for s in (form.cleaned_data.get('secondary_skills') or '').split(',') if s.strip()],
                        "summary": form.cleaned_data.get('summary', ''),
                        "experience": exps_data,
                        "education": [
                            {
                                "institution": form.cleaned_data.get('college_university', ''),
                                "degree": form.cleaned_data.get('highest_qualification', ''),
                                "field_of_study": "General"
                            }
                        ] if (form.cleaned_data.get('highest_qualification') or form.cleaned_data.get('college_university')) else []
                    }
                    
                    resume_file = request.FILES.get('resume')
                    file_bytes = resume_file.read() if resume_file else None
                    filename = resume_file.name if resume_file else "manual_entry.pdf"
                    
                    profile = merge_candidate_profile_data(
                        existing_profile=profile,
                        parsed_data=manual_parsed_data,
                        info=manual_parsed_data['personal_info'],
                        file_bytes=file_bytes,
                        filename=filename,
                        uploaded_by=request.user,
                        job_id=request.POST.get('job_id')
                    )
                    return JsonResponse({"success": True, "stage": "completed", "candidate_id": str(profile.id), "job_id": request.POST.get('job_id', ''), "message": "Resume merged successfully into existing candidate."})
                except Exception as e:
                    logger.error(f"[MANUAL MERGE FAILED] Exception: {str(e)}", exc_info=True)
                    return JsonResponse({"success": False, "message": f"Merge failed: {str(e)}"}, status=400)
            else:
                return JsonResponse({"success": False, "errors": form.errors}, status=400)

        # Check if this is a file merge resume request
        if request.POST.get('action') == 'merge_resume':
            candidate_id = request.POST.get('candidate_id')
            uploaded_file = request.FILES.get('resume') or request.FILES.get('resumes_zip')
            if not candidate_id:
                return JsonResponse({"success": False, "message": "Candidate ID is required for merge."}, status=400)
            if not uploaded_file:
                return JsonResponse({"success": False, "message": "Resume file is required for merge."}, status=400)
                
            from apps.candidates.utils import process_and_merge_resume
            try:
                profile = process_and_merge_resume(
                    file_obj=uploaded_file,
                    filename=uploaded_file.name,
                    candidate_profile_id=candidate_id,
                    uploaded_by=request.user,
                    job_id=request.POST.get('job_id') or request.GET.get('job_id')
                )
                
                try:
                    skills_count = profile.skills.count()
                except Exception:
                    skills_count = 0
                try:
                    edu_count = profile.educations.count()
                except Exception:
                    edu_count = 0
                    
                skills_list = list(profile.skills.values_list('skill_name', flat=True))
                education_first = profile.educations.first()
                personal_info = profile.parsed_json.get('personal_info', {}) if profile.parsed_json else {}
                relevant_exp = personal_info.get('relevant_experience', 0.0)
                preferred_loc = personal_info.get('preferred_location', '')
                github_url = personal_info.get('github_url', '')
                
                experiences_list = []
                parsed_experiences = profile.parsed_json.get('experience', []) if profile.parsed_json else []
                if parsed_experiences:
                    for exp in parsed_experiences:
                        co = exp.get('company') or exp.get('company_name') or ''
                        des = exp.get('designation') or exp.get('job_title') or ''
                        sd = exp.get('start_date') or ''
                        ed = exp.get('end_date') or ''
                        isc = exp.get('is_current') or False
                        if not ed and isc:
                            isc = True
                        desc = exp.get('description') or ''
                        loc = exp.get('location') or ''
                        ind = exp.get('industry') or ''
                        emp_type = exp.get('employment_type') or 'Full Time'
                        skills = exp.get('skills_used') or exp.get('key_skills') or ''
                        if isinstance(skills, list):
                            skills = ", ".join(skills)
                        
                        experiences_list.append({
                            "company": co,
                            "designation": des,
                            "start_date": sd,
                            "end_date": ed,
                            "is_current": isc,
                            "description": desc,
                            "employment_type": emp_type,
                            "location": loc,
                            "industry": ind,
                            "skills_used": skills
                        })
                else:
                    for exp in profile.experiences.all().order_by('-start_date'):
                        experiences_list.append({
                            "company": exp.company_name,
                            "designation": exp.designation,
                            "start_date": exp.start_date.strftime('%Y-%m') if exp.start_date else '',
                            "end_date": exp.end_date.strftime('%Y-%m') if exp.end_date else '',
                            "is_current": exp.is_current,
                            "description": exp.description,
                            "employment_type": "Full Time",
                            "location": "",
                            "industry": "",
                            "skills_used": ""
                        })
                
                return JsonResponse({
                    "success": True,
                    "stage": "completed",
                    "message": "Resume merged successfully into existing candidate.",
                    "candidate_id": str(profile.id),
                    "job_id": request.POST.get('job_id', '') or request.GET.get('job_id', ''),
                    "name": profile.full_name or '',
                    "email": profile.user.email or '',
                    "phone": profile.user.phone_number or '',
                    "experience": float(profile.total_experience or 0.0),
                    "relevant_experience": float(relevant_exp),
                    "skills_count": skills_count,
                    "education_count": edu_count,
                    "current_company": profile.current_company or '',
                    "current_designation": profile.current_designation or '',
                    "location": profile.location or '',
                    "preferred_location": preferred_loc or '',
                    "current_salary": float(profile.current_salary / 100000) if profile.current_salary else '',
                    "expected_salary": float(profile.expected_salary / 100000) if profile.expected_salary else '',
                    "notice_period": profile.notice_period or 30,
                    "highest_qualification": education_first.degree if education_first else '',
                    "college_university": education_first.institution if education_first else '',
                    "primary_skills": ", ".join(skills_list[:len(skills_list)//2]) if skills_list else '',
                    "secondary_skills": ", ".join(skills_list[len(skills_list)//2:]) if skills_list else '',
                    "linkedin_url": profile.linkedin_url or '',
                    "github_url": github_url or '',
                    "portfolio_url": profile.portfolio_url or '',
                    "summary": profile.summary or '',
                    "resume_name": profile.original_filename or '',
                    "confidence": float(profile.ocr_confidence or 95.0),
                    "experiences": experiences_list
                })
            except Exception as e_merge:
                logger.error(f"[MERGE RESUME FAILED] Error: {e_merge}", exc_info=True)
                return JsonResponse({"success": False, "message": f"Merge failed: {str(e_merge)}"}, status=400)

        # Standard file/ZIP upload action
        overwrite = request.POST.get('overwrite') == 'on'
        file_uploaded = 'resume' in request.FILES or 'resumes_zip' in request.FILES
        if not file_uploaded:
            return JsonResponse({"stage": "error", "message": "No file was uploaded."}, status=400)
            
        uploaded_file = request.FILES.get('resume') or request.FILES.get('resumes_zip')
        file_bytes = uploaded_file.read()
        file_name = uploaded_file.name
        content_type = getattr(uploaded_file, 'content_type', '')
        
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.http import StreamingHttpResponse
        import threading
        import queue
        import json
        
        in_memory_file = SimpleUploadedFile(file_name, file_bytes, content_type=content_type)
        q = queue.Queue()
        
        def progress_cb(stage, profile=None):
            data = {"stage": stage}
            if stage == "completed" and profile:
                try:
                    skills_count = profile.skills.count()
                except Exception:
                    skills_count = 0
                try:
                    edu_count = profile.educations.count()
                except Exception:
                    edu_count = 0
                
                skills_list = list(profile.skills.values_list('skill_name', flat=True))
                education_first = profile.educations.first()
                personal_info = profile.parsed_json.get('personal_info', {}) if profile.parsed_json else {}
                relevant_exp = personal_info.get('relevant_experience', 0.0)
                preferred_loc = personal_info.get('preferred_location', '')
                github_url = personal_info.get('github_url', '')
                
                # Fetch and format experiences
                experiences_list = []
                parsed_experiences = profile.parsed_json.get('experience', []) if profile.parsed_json else []
                if parsed_experiences:
                    for exp in parsed_experiences:
                        co = exp.get('company') or exp.get('company_name') or ''
                        des = exp.get('designation') or exp.get('job_title') or ''
                        sd = exp.get('start_date') or ''
                        ed = exp.get('end_date') or ''
                        isc = exp.get('is_current') or False
                        if not ed and isc:
                            isc = True
                        desc = exp.get('description') or ''
                        loc = exp.get('location') or ''
                        ind = exp.get('industry') or ''
                        emp_type = exp.get('employment_type') or 'Full Time'
                        skills = exp.get('skills_used') or exp.get('key_skills') or ''
                        if isinstance(skills, list):
                            skills = ", ".join(skills)
                        
                        experiences_list.append({
                            "company": co,
                            "designation": des,
                            "start_date": sd,
                            "end_date": ed,
                            "is_current": isc,
                            "description": desc,
                            "employment_type": emp_type,
                            "location": loc,
                            "industry": ind,
                            "skills_used": skills
                        })
                else:
                    for exp in profile.experiences.all().order_by('-start_date'):
                        experiences_list.append({
                            "company": exp.company_name,
                            "designation": exp.designation,
                            "start_date": exp.start_date.strftime('%Y-%m') if exp.start_date else '',
                            "end_date": exp.end_date.strftime('%Y-%m') if exp.end_date else '',
                            "is_current": exp.is_current,
                            "description": exp.description,
                            "employment_type": "Full Time",
                            "location": "",
                            "industry": "",
                            "skills_used": ""
                        })
                
                data.update({
                    "candidate_id": str(profile.id),
                    "name": profile.full_name or '',
                    "email": profile.user.email or '',
                    "phone": profile.user.phone_number or '',
                    "experience": float(profile.total_experience or 0.0),
                    "relevant_experience": float(relevant_exp),
                    "skills_count": skills_count,
                    "education_count": edu_count,
                    "current_company": profile.current_company or '',
                    "current_designation": profile.current_designation or '',
                    "location": profile.location or '',
                    "preferred_location": preferred_loc or '',
                    "current_salary": float(profile.current_salary / 100000) if profile.current_salary else '',
                    "expected_salary": float(profile.expected_salary / 100000) if profile.expected_salary else '',
                    "notice_period": profile.notice_period or 30,
                    "highest_qualification": education_first.degree if education_first else '',
                    "college_university": education_first.institution if education_first else '',
                    "primary_skills": ", ".join(skills_list[:len(skills_list)//2]) if skills_list else '',
                    "secondary_skills": ", ".join(skills_list[len(skills_list)//2:]) if skills_list else '',
                    "linkedin_url": profile.linkedin_url or '',
                    "github_url": github_url or '',
                    "portfolio_url": profile.portfolio_url or '',
                    "summary": profile.summary or '',
                    "resume_name": profile.original_filename or '',
                    "confidence": float(profile.ocr_confidence or 90.0),
                    "experiences": experiences_list
                })
            q.put(data)
            
        job_id = request.POST.get('job_id') or request.GET.get('job_id')
        
        def run_parser_thread():
            from django.db import connection
            try:
                connection.close()
                results = handle_resume_upload(in_memory_file, overwrite=overwrite, progress_callback=progress_cb, user=request.user)
                created_profiles = results['created']
                
                # Automatically map newly created profiles to Job if job_id is provided
                if job_id and created_profiles:
                    from apps.jobs.models import Job
                    from apps.applications.models import Application
                    from services.candidate_matching_service import CandidateMatchingService
                    try:
                        job = Job.objects.get(id=job_id)
                        for profile in created_profiles:
                            app, created = Application.objects.get_or_create(job=job, candidate=profile)
                            CandidateMatchingService.update_ats_scores(candidate_id=profile.id, job_id=job.id)
                    except Exception as e_map:
                        logger.error(f"Error mapping uploaded candidate to job {job_id}: {e_map}", exc_info=True)
                
                duplicates = results['duplicates']
                error_reasons = results.get('error_reasons', [])
                
                if not created_profiles:
                    if duplicates > 0:
                        dup_profiles = results.get('duplicate_profiles', [])
                        dup_data = None
                        if dup_profiles:
                            dp = dup_profiles[0]
                            dup_data = {
                                "candidate_id": str(dp.id),
                                "name": dp.full_name or "Unknown",
                                "email": dp.user.email,
                                "phone": dp.user.phone_number or "Not specified",
                                "current_company": dp.current_company or "Not specified"
                            }
                        q.put({
                            "stage": "duplicate", 
                            "message": "Candidate profile with this email or phone number already exists.",
                            "duplicate_candidate": dup_data
                        })
                    else:
                        reason = error_reasons[0] if error_reasons else "Resume could not be parsed automatically. Please use Manual Parsing to enter the candidate details."
                        q.put({"stage": "error", "message": reason})
            except Exception as e:
                logger.error(f"[BACKGROUND PARSER THREAD ERROR] Exception: {str(e)}", exc_info=True)
                logger.info(f"[RESUME PARSER] Automatic parsing failed — manual parsing available")
                q.put({"stage": "error", "message": "Resume could not be parsed automatically. Please use Manual Parsing to enter the candidate details."})
            finally:
                connection.close()
                q.put(None)
                
        t = threading.Thread(target=run_parser_thread)
        t.start()
        
        import time
        stream_start_time = time.time()
        max_stream_duration = 90.0

        def stream_generator():
            yield json.dumps({"stage": "upload_complete"}) + " " * 1024 + "\n"
            
            while True:
                if time.time() - stream_start_time > max_stream_duration:
                    logger.warning("[RESUME PARSER] Automatic parsing failed — manual parsing available")
                    yield json.dumps({"stage": "error", "message": "Resume could not be parsed automatically. Please use Manual Parsing to enter the candidate details."}) + " " * 1024 + "\n"
                    break

                try:
                    item = q.get(timeout=1.0)
                except queue.Empty:
                    yield " "
                    continue
                    
                if item is None:
                    break
                    
                yield json.dumps(item) + " " * 1024 + "\n"
                
        response = StreamingHttpResponse(stream_generator(), content_type="application/x-ndjson")
        response['X-Accel-Buffering'] = 'no'
        response['Cache-Control'] = 'no-cache'
        return response


class BulkResumeValidateAPIView(RecruiterRequiredMixin, View):
    """
    Validates ZIP containing resumes (.pdf, .doc, .docx) and optional Excel sheet.
    Safely stages files and returns validation summary without blocking the web server.
    """
    def post(self, request, *args, **kwargs):
        from services.bulk_resume_parser_service import BulkResumeParserService
        from apps.jobs.models import Job

        zip_file = request.FILES.get('resumes_zip')
        if not zip_file:
            return JsonResponse({"success": False, "message": "Please upload a ZIP file containing resumes."}, status=400)

        excel_file = request.FILES.get('candidates_excel')
        overwrite = request.POST.get('overwrite') in ['true', '1', 'on', True]
        
        job_target = None
        job_id = request.POST.get('job_id') or request.GET.get('job_id')
        if job_id:
            try:
                job_target = Job.objects.get(id=job_id)
            except Exception:
                pass

        try:
            summary = BulkResumeParserService.validate_and_stage_upload(
                zip_file=zip_file,
                excel_file=excel_file,
                user=request.user,
                job=job_target,
                overwrite=overwrite
            )
            return JsonResponse(summary)
        except ValueError as ve:
            return JsonResponse({"success": False, "message": str(ve)}, status=400)
        except Exception as e:
            logger.error(f"[BULK VALIDATE ERROR] Exception: {e}", exc_info=True)
            return JsonResponse({"success": False, "message": f"Validation error: {str(e)}"}, status=500)


class BulkResumeStartAPIView(RecruiterRequiredMixin, View):
    """
    Starts asynchronous background parsing for a staged bulk job.
    """
    def post(self, request, *args, **kwargs):
        from services.bulk_resume_parser_service import BulkResumeParserService
        import json

        job_id = request.POST.get('job_id')
        if not job_id and request.body:
            try:
                payload = json.loads(request.body.decode('utf-8'))
                job_id = payload.get('job_id')
                overwrite = payload.get('overwrite')
            except Exception:
                overwrite = None
        else:
            overwrite = request.POST.get('overwrite') in ['true', '1', 'on', True] if request.POST.get('overwrite') is not None else None

        if not job_id:
            return JsonResponse({"success": False, "message": "Missing job_id parameter."}, status=400)

        sync = request.POST.get('sync') in ['true', '1', True] or (request.headers.get('X-Test-Sync') == '1')

        try:
            BulkResumeParserService.start_background_processing(job_id, overwrite=overwrite, sync=sync)
            return JsonResponse({
                "success": True,
                "job_id": job_id,
                "message": "Bulk Parsing Started"
            })
        except Exception as e:
            logger.error(f"[BULK START ERROR] Exception: {e}", exc_info=True)
            return JsonResponse({"success": False, "message": str(e)}, status=400)


class BulkResumeStatusAPIView(RecruiterRequiredMixin, View):
    """
    Polls real-time progress and item statistics for an active or completed bulk job.
    """
    def get(self, request, job_number, *args, **kwargs):
        from apps.candidates.models import BulkResumeJob, BulkResumeItem
        from services.bulk_resume_parser_service import BulkResumeParserService
        job = BulkResumeParserService.get_job(job_number)
        if not job:
            return JsonResponse({"success": False, "message": "Job not found."}, status=404)

        items_qs = job.items.all().order_by('id')
        items_data = []
        for it in items_qs[:200]:  # Limit payload size
            items_data.append({
                "id": str(it.id),
                "filename": it.filename,
                "status": it.status,
                "action": it.action_taken,
                "candidate_id": str(it.candidate_id) if it.candidate_id else "",
                "candidate_name": it.candidate_name,
                "candidate_email": it.candidate_email,
                "candidate_phone": it.candidate_phone,
                "reason": it.reason
            })

        return JsonResponse({
            "success": True,
            "job_number": job.job_number,
            "status": job.status,
            "total_files": job.total_files,
            "processed_files": job.processed_files,
            "percent": job.progress_percentage,
            "successful_count": job.successful_count,
            "updated_count": job.updated_count,
            "skipped_count": job.skipped_count,
            "failed_count": job.failed_count,
            "current_file": job.current_file,
            "validation_summary": job.validation_summary,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "items": items_data
        })


class BulkResumeReportAPIView(RecruiterRequiredMixin, View):
    """
    Generates and downloads a CSV report for a bulk resume parsing job.
    """
    def get(self, request, job_number, *args, **kwargs):
        from django.http import HttpResponse
        from services.bulk_resume_parser_service import BulkResumeParserService

        try:
            csv_content = BulkResumeParserService.generate_csv_report(job_number)
            response = HttpResponse(csv_content, content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="bulk_parsing_report_{job_number}.csv"'
            return response
        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)}, status=400)


from django.core.mail import send_mail
from django.conf import settings
from apps.notifications.models import EmailLog

class EmailCampaignsView(RecruiterRequiredMixin, TemplateView):
    template_name = 'email_campaigns.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['recent_emails'] = EmailLog.objects.filter(sender=self.request.user)[:10]
        context['candidates'] = CandidateProfile.objects.select_related('user').all()
        return context

    def post(self, request, *args, **kwargs):
        subject = request.POST.get('subject')
        body = request.POST.get('body')
        recipients = request.POST.getlist('recipients')
        
        if not subject or not body or not recipients:
            messages.error(request, 'Please fill all required fields.')
            return redirect('frontend:email_campaigns')
            
        success_count = 0
        for rec_id in recipients:
            try:
                candidate = CandidateProfile.objects.get(id=rec_id)
                email = candidate.user.email
                
                # Mock sending email using Django's console backend (or SMTP if configured)
                send_mail(
                    subject,
                    body,
                    settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@talentvault.com',
                    [email],
                    fail_silently=False,
                )
                
                EmailLog.objects.create(
                    sender=request.user,
                    recipient_email=email,
                    subject=subject,
                    body=body,
                    status='SENT'
                )
                success_count += 1
            except Exception as e:
                print(f"Failed to send email to {rec_id}: {e}")
                
        messages.success(request, f'Successfully sent {success_count} emails.')
        return redirect('frontend:email_campaigns')


class CandidateJSONEditView(LoginRequiredMixin, View):
    """
    Saves recruiter manual edits, synchronizing CandidateProfile model,
    relational lists, updating version history, and recalculating ATS scores.
    """
    def post(self, request, pk, *args, **kwargs):
        profile = get_object_or_404(CandidateProfile, pk=pk)
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON body'}, status=400)
            
        # Update parsed_json data
        profile.parsed_json = data
        
        # Sync CandidateProfile
        info = data.get("personal_info", {})
        profile.full_name = info.get("name", profile.full_name)[:255] if info.get("name") else profile.full_name
        profile.summary = data.get("summary", profile.summary)
        profile.location = info.get("location", profile.location)[:100] if info.get("location") is not None else profile.location
        profile.current_company = info.get("current_company", profile.current_company)[:255] if info.get("current_company") is not None else profile.current_company
        profile.current_designation = info.get("current_designation", profile.current_designation)[:255] if info.get("current_designation") is not None else profile.current_designation
        
        try:
            profile.total_experience = Decimal(str(info.get("total_experience", profile.total_experience)))
        except Exception:
            pass
            
        current_sal = info.get("current_salary")
        expected_sal = info.get("expected_salary")
        if current_sal is not None and str(current_sal).strip() != "":
            try:
                profile.current_salary = Decimal(str(current_sal)) * 100000
            except Exception:
                pass
        elif current_sal is None or str(current_sal).strip() == "":
            profile.current_salary = None

        if expected_sal is not None and str(expected_sal).strip() != "":
            try:
                profile.expected_salary = Decimal(str(expected_sal)) * 100000
            except Exception:
                pass
        elif expected_sal is None or str(expected_sal).strip() == "":
            profile.expected_salary = None
            
        # Update user email / phone if provided
        new_email = info.get("email")
        new_phone = info.get("phone")
        if profile.user:
            user_changed = False
            if new_email and new_email.strip() and new_email.strip() != profile.user.email:
                from apps.accounts.models import User
                if not User.objects.filter(email__iexact=new_email.strip()).exclude(id=profile.user.id).exists():
                    profile.user.email = new_email.strip()
                    user_changed = True
            if new_phone is not None and new_phone != profile.user.phone_number:
                profile.user.phone_number = new_phone.strip() if new_phone else ""
                user_changed = True
            if user_changed:
                profile.user.save()
            
        profile.edited_by = request.user
        profile.edited_at = timezone.now()
        
        # Save new version
        new_ver_num = profile.current_version + 1
        v_data = {
            "version": new_ver_num,
            "label": f"Recruiter Edited (v{new_ver_num})",
            "data": data,
            "created_at": timezone.now().isoformat(),
            "created_by": request.user.email
        }
        profile.resume_versions[str(new_ver_num)] = v_data
        profile.current_version = new_ver_num
        
        # Add to audit log
        profile.audit_logs.append({
            "action": f"Manual profile edit by {request.user.email}",
            "timestamp": timezone.now().isoformat(),
            "user": request.user.email
        })
        
        profile.save()
        
        # Sync Skills relation
        profile.skills.all().delete()
        for sk in data.get("skills", []):
            CandidateSkill.objects.get_or_create(profile=profile, skill_name=sk.strip().title()[:100])
            
        # Sync Experiences relation
        profile.experiences.all().delete()
        for exp in data.get("experience", []):
            try:
                s_date = datetime.strptime(exp.get("start_date"), "%Y-%m-%d").date() if exp.get("start_date") else None
                e_date = datetime.strptime(exp.get("end_date"), "%Y-%m-%d").date() if exp.get("end_date") else None
            except Exception:
                s_date, e_date = None, None
            from services.resume_intelligence import ResumeIntelligenceService
            description_html = ResumeIntelligenceService.parse_experience_description_to_html(exp.get("description", ""))
            Experience.objects.create(
                profile=profile,
                company_name=exp.get("company", "Company")[:100],
                designation=exp.get("designation", "Role")[:100],
                description=description_html,
                start_date=s_date,
                end_date=e_date
            )
            
        # Sync Education relation
        profile.educations.all().delete()
        for edu in data.get("education", []):
            try:
                s_date = datetime.strptime(edu.get("start_date"), "%Y-%m-%d").date() if edu.get("start_date") else None
                e_date = datetime.strptime(edu.get("end_date"), "%Y-%m-%d").date() if edu.get("end_date") else None
            except Exception:
                s_date, e_date = None, None
            Education.objects.create(
                profile=profile,
                institution=edu.get("institution", "Institution")[:100],
                degree=edu.get("degree", "Degree")[:100],
                field_of_study=edu.get("field_of_study", "")[:100],
                start_date=s_date,
                end_date=e_date
            )
            
        # Sync Projects relation
        profile.projects.all().delete()
        for proj in data.get("projects", []):
            Project.objects.create(
                profile=profile,
                title=proj.get("title", "Project")[:255],
                description=ResumeIntelligenceService.parse_experience_description_to_html(proj.get("description", "")),
                link=proj.get("link", "")
            )
            
        # Sync Certifications relation
        profile.certifications.all().delete()
        for cert in data.get("certifications", []):
            try:
                i_date = datetime.strptime(cert.get("issue_date"), "%Y-%m-%d").date() if cert.get("issue_date") else None
            except Exception:
                i_date = None
            Certification.objects.create(
                profile=profile,
                name=ResumeIntelligenceService.parse_experience_description_to_html(cert.get("name", "Certification")[:255]),
                issuing_organization=cert.get("issuing_organization", "")[:255],
                issue_date=i_date
            )
            
        # Recalculate ATS Scores & Refresh Candidate Tags
        CandidateMatchingService.update_ats_scores(candidate_id=profile.id)
        try:
            from services.candidate_tagging_service import CandidateTaggingService
            CandidateTaggingService.tag_candidate_profile(profile, source='manual')
        except Exception as e:
            logger.error(f"[TAGGING ERROR] Failed to update candidate tags on manual edit: {e}")
        
        return JsonResponse({'status': 'success', 'current_version': new_ver_num})


class CandidateAIAssistView(LoginRequiredMixin, View):
    """
    AI Assist engine triggering entity normalization, OCR error correction,
    ATS bullet formatting, and suggestion lists.
    """
    def post(self, request, pk, *args, **kwargs):
        from services.candidate_matching_service import CandidateMatchingService
        
        profile = get_object_or_404(CandidateProfile, pk=pk)
        action = request.POST.get("action", "preview") # preview or accept
        
        improved_data = ResumeIntelligenceService.ai_improve_resume_data(profile.parsed_json)
        
        # Determine job for ATS score and match percentage recommendations
        job_id = request.POST.get('job_id') or request.GET.get('job_id')
        job = None
        if job_id:
            job = Job.objects.filter(id=job_id).first()
        if not job:
            app = Application.objects.filter(candidate=profile).first()
            if app:
                job = app.job
        if not job:
            job = Job.objects.filter(status='ACTIVE').first() or Job.objects.first()
            
        if action == 'preview':
            # Calculate mock improved candidate ATS/match score
            improved_ats_analysis = None
            if job:
                # Helper class to mock django managers for in-memory score calculation
                class MockRelatedManager:
                    def __init__(self, items):
                        self.items = items
                    def all(self):
                        return self
                    def exists(self):
                        return len(self.items) > 0
                    def count(self):
                        return len(self.items)
                    def values_list(self, field, flat=False):
                        if flat:
                            return [getattr(x, field) for x in self.items]
                        return [(getattr(x, field),) for x in self.items]
                    def __iter__(self):
                        return iter(self.items)

                class MockSkill:
                    def __init__(self, name):
                        self.skill_name = name

                class MockExperience:
                    def __init__(self, company, designation, description, start_date, end_date):
                        self.company_name = company
                        self.designation = designation
                        self.description = description
                        self.start_date = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
                        self.end_date = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None

                class MockEducation:
                    def __init__(self, institution, degree, field_of_study, start_date, end_date):
                        self.institution = institution
                        self.degree = degree
                        self.field_of_study = field_of_study
                        self.start_date = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
                        self.end_date = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None

                class MockProject:
                    def __init__(self, title, description):
                        self.title = title
                        self.description = description

                class MockCertification:
                    def __init__(self, name, issuing_organization, issue_date):
                        self.name = name
                        self.issuing_organization = issuing_organization
                        self.issue_date = datetime.strptime(issue_date, "%Y-%m-%d").date() if issue_date else None

                class MockCandidate:
                    def __init__(self, data, original_candidate):
                        self.resume = original_candidate.resume
                        self.is_immediate_joiner = original_candidate.is_immediate_joiner
                        self.notice_period = original_candidate.notice_period
                        
                        info = data.get("personal_info", {})
                        self.full_name = info.get("name", "")
                        self.summary = data.get("summary", "")
                        self.location = info.get("location", "Unknown")
                        self.current_company = info.get("current_company", "")
                        self.current_designation = info.get("current_designation", "")
                        try:
                            self.total_experience = Decimal(str(info.get("total_experience", 0)))
                        except Exception:
                            self.total_experience = Decimal('0.0')

                        self.skills = MockRelatedManager([MockSkill(s) for s in data.get("skills", [])])
                        self.experiences = MockRelatedManager([
                            MockExperience(
                                exp.get("company", ""),
                                exp.get("designation", ""),
                                exp.get("description", ""),
                                exp.get("start_date"),
                                exp.get("end_date")
                            ) for exp in data.get("experience", [])
                        ])
                        self.educations = MockRelatedManager([
                            MockEducation(
                                edu.get("institution", ""),
                                edu.get("degree", ""),
                                edu.get("field_of_study", ""),
                                edu.get("start_date"),
                                edu.get("end_date")
                            ) for edu in data.get("education", [])
                        ])
                        self.projects = MockRelatedManager([
                            MockProject(
                                proj.get("title", ""),
                                proj.get("description", "")
                            ) for proj in data.get("projects", [])
                        ])
                        self.certifications = MockRelatedManager([
                            MockCertification(
                                cert.get("name", ""),
                                cert.get("issuing_organization", ""),
                                cert.get("issue_date")
                            ) for cert in data.get("certifications", [])
                        ])

                mock_cand = MockCandidate(improved_data, profile)
                improved_ats_analysis = CandidateMatchingService.calculate_job_ats_score(mock_cand, job)
            
            # Suggest missing skills (skills in improved list but not in current profile)
            current_skills = set(s.skill_name.strip().title() for s in profile.skills.all())
            suggested_skills = [s for s in improved_data.get('skills', []) if s.strip().title() not in current_skills]
            
            # Calculate current candidate ATS/match score for comparison
            current_ats_analysis = None
            if job:
                current_ats_analysis = CandidateMatchingService.calculate_job_ats_score(profile, job)

            ats_score = improved_ats_analysis['total_score'] if improved_ats_analysis else 0
            job_match_percentage = improved_ats_analysis['total_score'] if improved_ats_analysis else 0
            
            return JsonResponse({
                'status': 'success',
                'preview_data': improved_data,
                'current_ats_score': current_ats_analysis['total_score'] if current_ats_analysis else 0,
                'improved_ats_score': ats_score,
                'suggested_skills': suggested_skills,
                'improved_summary': improved_data.get('summary', ''),
                'job_match_percentage': job_match_percentage,
                'job_title': job.title if job else None
            })
            
        elif action == 'accept':
            # Save as V3 or next version
            profile.parsed_json = improved_data
            
            info = improved_data.get("personal_info", {})
            profile.full_name = info.get("name", profile.full_name)[:255] if info.get("name") else profile.full_name
            profile.summary = improved_data.get("summary", profile.summary)
            profile.current_company = info.get("current_company", profile.current_company)[:255] if info.get("current_company") is not None else profile.current_company
            profile.current_designation = info.get("current_designation", profile.current_designation)[:255] if info.get("current_designation") is not None else profile.current_designation
            
            # Save AI Improved fields separately
            profile.ai_summary = improved_data.get("summary", "")
            profile.ai_skills = improved_data.get("skills", [])
            profile.ai_experience_rewrite = improved_data.get("experience", [])
            
            new_ver_num = profile.current_version + 1
            v_data = {
                "version": new_ver_num,
                "label": "AI Improved Resume",
                "data": improved_data,
                "created_at": timezone.now().isoformat(),
                "created_by": "System AI Assistant"
            }
            profile.resume_versions[str(new_ver_num)] = v_data
            profile.current_version = new_ver_num
            
            profile.audit_logs.append({
                "action": "Applied AI Assist improvements",
                "timestamp": timezone.now().isoformat(),
                "user": "System AI"
            })
            profile.save()
            
            from apps.candidates.utils import parse_date_robust
            
            # Sync Skills relation
            profile.skills.all().delete()
            for sk in improved_data.get("skills", []):
                CandidateSkill.objects.get_or_create(profile=profile, skill_name=sk.strip().title()[:100])
                
            # Sync Experiences relation
            profile.experiences.all().delete()
            for exp in improved_data.get("experience", []):
                s_date = parse_date_robust(exp.get("start_date"), None)
                e_date = parse_date_robust(exp.get("end_date"), None)
                Experience.objects.create(
                    profile=profile,
                    company_name=exp.get("company", "Company")[:100],
                    designation=exp.get("designation", "Role")[:100],
                    description=exp.get("description", ""),
                    start_date=s_date,
                    end_date=e_date
                )
                
            # Sync Education relation
            profile.educations.all().delete()
            for edu in improved_data.get("education", []):
                s_date = parse_date_robust(edu.get("start_date"), None)
                e_date = parse_date_robust(edu.get("end_date"), None)
                Education.objects.create(
                    profile=profile,
                    institution=edu.get("institution", "Institution")[:100],
                    degree=edu.get("degree", "Degree")[:100],
                    field_of_study=edu.get("field_of_study", "")[:100],
                    start_date=s_date,
                    end_date=e_date
                )
                
            # Recalculate ATS
            CandidateMatchingService.update_ats_scores(candidate_id=profile.id)
            
            # Generate and save the OCR/AI resume separately
            try:
                from services.resume_intelligence import ResumeIntelligenceService
                from django.core.files.base import ContentFile
                pdf_bytes = ResumeIntelligenceService.generate_ats_friendly_pdf(profile)
                profile.generated_resume.save("generated_resume.pdf", ContentFile(pdf_bytes), save=True)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"[AI ASSIST] Failed to generate/save generated_resume.pdf: {str(e)}", exc_info=True)

            messages.success(request, "AI improvements accepted successfully!")
            return redirect('frontend:candidate_detail', pk=profile.id)
            
        return JsonResponse({'status': 'error', 'message': 'Invalid action'}, status=400)


class CandidateVersionRollbackView(LoginRequiredMixin, View):
    """
    Rollback version tracking supporting Undo, Redo, and selected timeline rollbacks.
    """
    def post(self, request, pk, *args, **kwargs):
        profile = get_object_or_404(CandidateProfile, pk=pk)
        ver_id = request.POST.get("version_id")
        
        if not ver_id or str(ver_id) not in profile.resume_versions:
            messages.error(request, "Selected version does not exist.")
            return redirect('frontend:candidate_detail', pk=profile.id)
            
        version = profile.resume_versions[str(ver_id)]
        data = version["data"]
        
        profile.parsed_json = data
        
        info = data.get("personal_info", {})
        profile.full_name = info.get("name", profile.full_name)[:255] if info.get("name") else profile.full_name
        profile.summary = data.get("summary", profile.summary)
        profile.location = info.get("location", profile.location)[:100] if info.get("location") is not None else profile.location
        profile.current_company = info.get("current_company", profile.current_company)[:255] if info.get("current_company") is not None else profile.current_company
        profile.current_designation = info.get("current_designation", profile.current_designation)[:255] if info.get("current_designation") is not None else profile.current_designation
        
        try:
            profile.total_experience = Decimal(str(info.get("total_experience", profile.total_experience)))
        except Exception:
            pass
            
        profile.current_version = int(ver_id)
        profile.audit_logs.append({
            "action": f"Rolled back to version {ver_id} ({version['label']})",
            "timestamp": timezone.now().isoformat(),
            "user": request.user.email
        })
        profile.save()
        
        # Sync relational models
        profile.skills.all().delete()
        for sk in data.get("skills", []):
            CandidateSkill.objects.get_or_create(profile=profile, skill_name=sk.strip().title()[:100])
            
        from apps.candidates.utils import parse_date_robust

        profile.experiences.all().delete()
        for exp in data.get("experience", []):
            s_date = parse_date_robust(exp.get("start_date"), None)
            e_date = parse_date_robust(exp.get("end_date"), None)
            Experience.objects.create(
                profile=profile,
                company_name=exp.get("company", "Company")[:100],
                designation=exp.get("designation", "Role")[:100],
                description=exp.get("description", ""),
                start_date=s_date,
                end_date=e_date
            )
            
        profile.educations.all().delete()
        for edu in data.get("education", []):
            s_date = parse_date_robust(edu.get("start_date"), None)
            e_date = parse_date_robust(edu.get("end_date"), None)
            Education.objects.create(
                profile=profile,
                institution=edu.get("institution", "Institution")[:100],
                degree=edu.get("degree", "Degree")[:100],
                field_of_study=edu.get("field_of_study", "")[:100],
                start_date=s_date,
                end_date=e_date
            )
            
        profile.projects.all().delete()
        for proj in data.get("projects", []):
            Project.objects.create(
                profile=profile,
                title=proj.get("title", "Project")[:255],
                description=proj.get("description", ""),
                link=proj.get("link", "")
            )
            
        profile.certifications.all().delete()
        for cert in data.get("certifications", []):
            i_date = parse_date_robust(cert.get("issue_date"), None)
            Certification.objects.create(
                profile=profile,
                name=cert.get("name", "Certification")[:255],
                issuing_organization=cert.get("issuing_organization", "")[:255],
                issue_date=i_date
            )
            
        # Recalculate ATS
        CandidateMatchingService.update_ats_scores(candidate_id=profile.id)
        
        # Generate and save the OCR/AI resume separately
        try:
            from services.resume_intelligence import ResumeIntelligenceService
            from django.core.files.base import ContentFile
            pdf_bytes = ResumeIntelligenceService.generate_ats_friendly_pdf(profile)
            profile.generated_resume.save("generated_resume.pdf", ContentFile(pdf_bytes), save=True)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"[ROLLBACK] Failed to generate/save generated_resume.pdf: {str(e)}", exc_info=True)

        messages.success(request, f"Successfully rolled back to version {ver_id} ({version['label']})")
        return redirect('frontend:candidate_detail', pk=profile.id)


class CandidateDuplicateView(LoginRequiredMixin, View):
    """
    Handles similarity check listings, ignores, and candidate merge actions.
    """
    def get(self, request, pk, *args, **kwargs):
        profile = get_object_or_404(CandidateProfile, pk=pk)
        duplicates = []
        
        other_candidates = CandidateProfile.objects.exclude(id=profile.id)
        for c in other_candidates:
            res = ResumeIntelligenceService.calculate_duplicate_similarity(profile, c)
            if res["is_duplicate"]:
                duplicates.append(res)
                
        return JsonResponse({'status': 'success', 'duplicates': duplicates})

    def post(self, request, pk, *args, **kwargs):
        profile = get_object_or_404(CandidateProfile, pk=pk)
        action = request.POST.get("action")
        target_id = request.POST.get("target_id")
        
        if not target_id:
            messages.error(request, "Target candidate ID is required.")
            return redirect('frontend:candidate_detail', pk=profile.id)
            
        target = get_object_or_404(CandidateProfile, pk=target_id)
        
        if action == 'merge':
            # Merge target details into profile
            profile.audit_logs.append({
                "action": f"Merged data from duplicate candidate {target.full_name or target.user.email}",
                "timestamp": timezone.now().isoformat(),
                "user": request.user.email
            })
            
            # Merge skills
            for sk in target.skills.all():
                CandidateSkill.objects.get_or_create(profile=profile, skill_name=sk.skill_name)
            # Merge experiences
            for exp in target.experiences.all():
                Experience.objects.create(
                    profile=profile,
                    company_name=exp.company_name,
                    designation=exp.designation,
                    description=exp.description,
                    start_date=exp.start_date,
                    end_date=exp.end_date
                )
            # Merge educations
            for edu in target.educations.all():
                Education.objects.create(
                    profile=profile,
                    institution=edu.institution,
                    degree=edu.degree,
                    field_of_study=edu.field_of_study,
                    start_date=edu.start_date,
                    end_date=edu.end_date
                )
            
            # Delete duplicate candidate
            t_user = target.user
            target.delete()
            if t_user and t_user.role == 'CANDIDATE':
                t_user.delete()
                
            profile.save()
            messages.success(request, f"Successfully merged candidate profiles and removed duplicate entry.")
            
        elif action == 'ignore':
            # Ignore duplicate alert
            profile.audit_logs.append({
                "action": f"Ignored duplicate warning for candidate {target.full_name or target.user.email}",
                "timestamp": timezone.now().isoformat(),
                "user": request.user.email
            })
            profile.save()
            messages.success(request, "Duplicate candidate alert ignored.")
            
        return redirect('frontend:candidate_detail', pk=profile.id)


class CandidateExportPDFView(LoginRequiredMixin, View):
    """
    Downloads custom generated ATS friendly PDF utilizing ReportLab Flowables.
    """
    def get(self, request, pk, *args, **kwargs):
        candidate = get_object_or_404(CandidateProfile, pk=pk)
        
        pdf_bytes = ResumeIntelligenceService.generate_ats_friendly_pdf(candidate)
        
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        filename = f"{candidate.full_name or 'Resume'}_ATS_Friendly.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Log to audit history
        candidate.audit_logs.append({
            "action": "Exported ATS Friendly PDF",
            "timestamp": timezone.now().isoformat(),
            "user": request.user.email
        })
        candidate.save()
        
        return response


@method_decorator(xframe_options_sameorigin, name='dispatch')
class CandidateResumePreviewView(LoginRequiredMixin, View):
    """
    Renders inline candidate resume in browser for PDF, JPG, PNG, DOC, DOCX, RTF, TXT previews.
    Only displays the original uploaded file stored in CandidateProfile.resume.
    """
    def get(self, request, pk, *args, **kwargs):
        candidate = get_object_or_404(CandidateProfile, pk=pk)
        candidate.preview_status = 'VIEWED'
        candidate.save(update_fields=['preview_status'])
        
        from utils.preview import generate_resume_preview_response
        return generate_resume_preview_response(candidate)


class CandidateResumeDownloadView(LoginRequiredMixin, View):
    """
    Forces download of the original candidate resume file stored in CandidateProfile.resume, preserving filename.
    """
    def get(self, request, pk, *args, **kwargs):
        import os
        import mimetypes
        try:
            candidate = get_object_or_404(CandidateProfile, pk=pk)
            if not candidate.resume or not candidate.resume.name:
                return HttpResponse("No resume file found.", status=404)
                
            resume_file = candidate.resume
            filename = candidate.original_filename or os.path.basename(resume_file.name)
            
            from utils.s3 import get_presigned_url
            presigned_url = get_presigned_url(resume_file, expires_in=3600, as_attachment=True, filename=filename)
            if presigned_url and presigned_url.startswith('http'):
                return redirect(presigned_url)

            if resume_file.storage.exists(resume_file.name):
                try:
                    if hasattr(resume_file.storage, 'path'):
                        f = resume_file.open('rb')
                        content_type, _ = mimetypes.guess_type(resume_file.name)
                        if not content_type:
                            content_type = 'application/octet-stream'
                        return FileResponse(f, as_attachment=True, filename=filename, content_type=content_type)
                except NotImplementedError:
                    pass
                return redirect(resume_file.url)
        except Exception as e:
            logger.error(f"Error downloading candidate resume {pk}: {e}")
            
        return HttpResponse("Resume file is not available.", status=404)


@method_decorator(xframe_options_sameorigin, name='dispatch')
class PublicCandidateResumePreviewView(View):
    """
    Renders inline candidate resume publicly in browser.
    Only displays the original uploaded file stored in CandidateProfile.resume.
    """
    def get(self, request, pk, *args, **kwargs):
        try:
            candidate = CandidateProfile.objects.filter(pk=pk).first()
            if not candidate or not candidate.resume:
                return render(request, '404.html', {'message': 'Candidate profile no longer available.'}, status=404)
            
            candidate.preview_status = 'VIEWED'
            try:
                candidate.save(update_fields=['preview_status'])
            except Exception:
                pass
            
            from utils.preview import generate_resume_preview_response
            return generate_resume_preview_response(candidate)
        except Exception as e:
            logger.error(f"Error in public candidate resume preview {pk}: {e}")
            return render(request, '404.html', {'message': 'Resume preview no longer available.'}, status=404)


class PublicCandidateResumeDownloadView(View):
    """
    Forces public download of candidate resume file stored in CandidateProfile.resume,
    supporting both local media storage and AWS S3 media storage gracefully without error.
    """
    def get(self, request, pk, *args, **kwargs):
        import os
        try:
            candidate = CandidateProfile.objects.filter(pk=pk).first()
            if not candidate or not candidate.resume or not candidate.resume.name:
                return render(request, '404.html', {'message': 'Resume file no longer available.'}, status=404)
            
            resume_file = candidate.resume
            filename = candidate.original_filename or os.path.basename(resume_file.name)
            
            from utils.s3 import get_presigned_url
            presigned_url = get_presigned_url(resume_file, expires_in=3600, as_attachment=True, filename=filename)
            if presigned_url and presigned_url.startswith('http'):
                return redirect(presigned_url)

            if resume_file.storage.exists(resume_file.name):
                return redirect(resume_file.url)

        except Exception as e:
            logger.error(f"Error downloading candidate resume {pk}: {e}")
            
        return render(request, '404.html', {'message': 'Resume file is no longer available in cloud storage.'}, status=404)


@method_decorator(xframe_options_sameorigin, name='dispatch')
class PublicJobJDPreviewView(View):
    """
    Renders/serves inline Job Description file publicly for preview in iframes or browser.
    Generates a secure AWS S3 presigned URL with inline disposition (no AccessDenied) or serves locally.
    """
    def get(self, request, pk, *args, **kwargs):
        import os
        import mimetypes
        try:
            job = get_object_or_404(Job, pk=pk)
            if not job.jd_file or not job.jd_file.name:
                return render(request, '404.html', {'message': 'Job description document is not available.'}, status=404)
            
            jd_file = job.jd_file
            filename = os.path.basename(jd_file.name)
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type:
                content_type = 'application/pdf' if filename.lower().endswith('.pdf') else 'application/octet-stream'

            from utils.s3 import get_presigned_url
            presigned_url = get_presigned_url(jd_file, expires_in=7200, as_attachment=False, filename=filename, content_type=content_type)
            if presigned_url and presigned_url.startswith('http'):
                return redirect(presigned_url)

            # Local storage or streaming fallback
            if jd_file.storage.exists(jd_file.name):
                f = jd_file.open('rb')
                response = FileResponse(f, content_type=content_type)
                response['Content-Disposition'] = f'inline; filename="{filename}"'
                return response

        except Exception as e:
            logger.error(f"Error serving JD preview for job {pk}: {e}")
            
        return render(request, '404.html', {'message': 'Job description preview is not available.'}, status=404)


class PublicJobJDDownloadView(View):
    """
    Forces public download of Job Description document stored in Job.jd_file,
    generating a secure temporary presigned S3 URL or direct stream without AccessDenied.
    """
    def get(self, request, pk, *args, **kwargs):
        import os
        import mimetypes
        try:
            job = get_object_or_404(Job, pk=pk)
            if not job.jd_file or not job.jd_file.name:
                return render(request, '404.html', {'message': 'Job description document is not available.'}, status=404)

            jd_file = job.jd_file
            filename = os.path.basename(jd_file.name)
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type:
                content_type = 'application/octet-stream'

            from utils.s3 import get_presigned_url
            presigned_url = get_presigned_url(jd_file, expires_in=7200, as_attachment=True, filename=filename, content_type=content_type)
            if presigned_url and presigned_url.startswith('http'):
                return redirect(presigned_url)

            # Local storage or streaming fallback
            if jd_file.storage.exists(jd_file.name):
                f = jd_file.open('rb')
                return FileResponse(f, as_attachment=True, filename=filename, content_type=content_type)

        except Exception as e:
            logger.error(f"Error downloading JD file for job {pk}: {e}")

        return render(request, '404.html', {'message': 'Job description file is not available.'}, status=404)


# --- NEW CANDIDATE PORTAL VIEWS ---
from apps.core.permissions import CandidateRequiredMixin

class CandidateProfileView(CandidateRequiredMixin, TemplateView):
    template_name = 'candidate_profile.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['edit_mode'] = self.request.GET.get('edit') == 'true'
        return context

    def post(self, request, *args, **kwargs):
        user = request.user
        profile = getattr(user, 'candidate_profile', None)
        
        if profile:
            # Update user details
            full_name = request.POST.get('full_name', '').strip()
            if full_name:
                parts = full_name.split(' ', 1)
                user.first_name = parts[0]
                user.last_name = parts[1] if len(parts) > 1 else ''
            
            # Email is kept read-only by default, but if allowed:
            # email = request.POST.get('email', '').strip()
            # if email: user.email = email
            
            phone = request.POST.get('phone_number', '').strip()
            if phone:
                user.phone_number = phone
                
            user.save()
            
            # Update profile details
            profile.full_name = full_name
            profile.current_designation = request.POST.get('current_designation', '').strip()
            profile.location = request.POST.get('location', '').strip()
            profile.summary = request.POST.get('summary', '').strip()
            profile.save()
            
        return redirect('frontend:candidate_profile')


class CandidateResumeUploadView(CandidateRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        if 'resume' not in request.FILES:
            return JsonResponse({'success': False, 'message': 'No file uploaded.'}, status=400)
        
        uploaded_file = request.FILES['resume']
        try:
            profile = request.user.candidate_profile
            from services.resume_storage_service import save_candidate_resume_atomic, ResumeUploadError
            save_candidate_resume_atomic(profile, uploaded_file, uploaded_file.name, is_replacement=True, user=request.user)
            
            return JsonResponse({
                'success': True, 
                'message': 'Resume uploaded successfully!',
                'filename': profile.original_filename or uploaded_file.name
            })
        except ResumeUploadError as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Resume upload failed: {str(e)}'}, status=400)

class CandidateResumeDeleteView(CandidateRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            profile = request.user.candidate_profile
            if profile.resume:
                try:
                    profile.resume.delete(save=False)
                except Exception:
                    pass
                profile.resume = None
                profile.original_filename = None
                profile.save()
            return JsonResponse({'success': True, 'message': 'Resume deleted successfully.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)

class CandidateOnboardingUpdateView(CandidateRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            user = request.user
            profile, _ = CandidateProfile.objects.get_or_create(user=user)
            
            if request.content_type == 'application/json':
                import json
                try:
                    data = json.loads(request.body)
                except Exception:
                    data = {}
            else:
                data = request.POST

            first_name = data.get('first_name', '').strip()
            last_name = data.get('last_name', '').strip()
            if first_name: user.first_name = first_name
            if last_name: user.last_name = last_name

            phone = data.get('phone_number', '').strip()
            if phone: user.phone_number = phone
            user.save()

            full_name = f"{user.first_name} {user.last_name}".strip()
            if full_name: profile.full_name = full_name

            if data.get('location'): profile.location = data.get('location').strip()
            if data.get('date_of_birth'): profile.date_of_birth = data.get('date_of_birth').strip()
            if data.get('current_company'): profile.current_company = data.get('current_company').strip()
            if data.get('current_designation'): profile.current_designation = data.get('current_designation').strip()
            if data.get('preferred_job_role'): profile.preferred_job_role = data.get('preferred_job_role').strip()
            if data.get('preferred_location'): profile.preferred_location = data.get('preferred_location').strip()

            if data.get('total_experience') is not None and str(data.get('total_experience')).strip() != '':
                try: profile.total_experience = float(data.get('total_experience'))
                except (ValueError, TypeError): pass

            if data.get('expected_salary') is not None and str(data.get('expected_salary')).strip() != '':
                try: profile.expected_salary = float(data.get('expected_salary'))
                except (ValueError, TypeError): pass

            if data.get('current_salary') is not None and str(data.get('current_salary')).strip() != '':
                try: profile.current_salary = float(data.get('current_salary'))
                except (ValueError, TypeError): pass

            if data.get('notice_period') is not None and str(data.get('notice_period')).strip() != '':
                try: profile.notice_period = int(data.get('notice_period'))
                except (ValueError, TypeError): pass

            if data.get('summary') is not None:
                profile.summary = data.get('summary').strip()

            profile.save()

            # Update Skills
            skills_data = data.get('skills', [])
            if isinstance(skills_data, str):
                skills_data = [s.strip() for s in skills_data.split(',') if s.strip()]
            if isinstance(skills_data, list) and len(skills_data) > 0:
                profile.skills.all().delete()
                for sk_name in skills_data:
                    sk_clean = str(sk_name).strip()
                    if sk_clean:
                        CandidateSkill.objects.create(profile=profile, skill_name=sk_clean)

            # Update Education
            institution = data.get('education_institution', '').strip()
            degree = data.get('education_degree', '').strip()
            if institution or degree:
                edu = profile.educations.first()
                if not edu:
                    Education.objects.create(
                        profile=profile,
                        institution=institution or "University",
                        degree=degree or "Bachelor's Degree",
                        field_of_study=data.get('education_field', '').strip()
                    )
                else:
                    if institution: edu.institution = institution
                    if degree: edu.degree = degree
                    if data.get('education_field'): edu.field_of_study = data.get('education_field').strip()
                    edu.save()

            # Update Experience
            exp_company = data.get('experience_company', '').strip()
            exp_designation = data.get('experience_designation', '').strip()
            if exp_company or exp_designation:
                exp = profile.experiences.first()
                if not exp:
                    Experience.objects.create(
                        profile=profile,
                        company_name=exp_company or "Company",
                        designation=exp_designation or "Role"
                    )
                else:
                    if exp_company: exp.company_name = exp_company
                    if exp_designation: exp.designation = exp_designation
                    exp.save()

            completion_pct = profile.profile_completion_percentage

            return JsonResponse({
                'success': True,
                'message': 'Profile details updated successfully!',
                'completion_percentage': completion_pct,
                'has_resume': profile.has_resume,
                'resume_name': profile.original_filename or (profile.resume.name if profile.resume else '')
            })

        except Exception as err:
            logger.error(f"Error updating candidate onboarding profile: {err}")
            return JsonResponse({'success': False, 'message': str(err)}, status=400)


class CandidateCareerResourcesView(CandidateRequiredMixin, TemplateView):
    template_name = 'career_resources.html'

class CandidateSavedJobsView(CandidateRequiredMixin, TemplateView):
    template_name = 'candidate_saved_jobs.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        candidate_profile = getattr(user, 'candidate_profile', None)
        if candidate_profile:
            saved_items = list(candidate_profile.saved_jobs.select_related('job', 'job__company').all())
            from services.candidate_matching_service import CandidateMatchingService
            for item in saved_items:
                analysis = CandidateMatchingService.calculate_job_ats_score(candidate_profile, item.job)
                item.match_score = analysis['total_score']
            context['saved_jobs'] = saved_items
            context['applied_job_ids'] = list(candidate_profile.job_applications.values_list('job_id', flat=True))
        else:
            context['saved_jobs'] = []
            context['applied_job_ids'] = []
        return context

class CandidateRecommendedJobsView(CandidateRequiredMixin, TemplateView):
    template_name = 'candidate_recommended_jobs.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        candidate_profile = getattr(user, 'candidate_profile', None)
        if candidate_profile:
            from services.candidate_matching_service import CandidateMatchingService
            recommended = CandidateMatchingService.get_recommended_jobs(candidate_profile, limit=10)
            context['recommended_jobs'] = recommended
            
            # Aggregate all unique missing skills across these recommended jobs
            missing_skills_list = []
            seen_skills = set()
            for rec in recommended:
                for skill in rec['missing_skills']:
                    skill_lower = skill.lower()
                    if skill_lower not in seen_skills:
                        seen_skills.add(skill_lower)
                        missing_skills_list.append({
                            'name': skill,
                            'job_title': rec['job'].title,
                            'company_name': rec['job'].company.name,
                            'job_id': rec['job'].id
                        })
            context['missing_skills'] = missing_skills_list[:5] # top 5 missing skills
            
            # Retrieve applied/saved job ids to toggle buttons
            context['applied_job_ids'] = list(candidate_profile.job_applications.values_list('job_id', flat=True))
            context['saved_job_ids'] = list(candidate_profile.saved_jobs.values_list('job_id', flat=True))
        else:
            context['recommended_jobs'] = []
            context['missing_skills'] = []
            context['applied_job_ids'] = []
            context['saved_job_ids'] = []
        return context

class CandidateApplicationsView(CandidateRequiredMixin, TemplateView):
    template_name = 'candidate_applications.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = getattr(self.request.user, 'candidate_profile', None)
        if profile:
            context['applications'] = profile.job_applications.select_related('job', 'job__company').order_by('-created_at')
        else:
            context['applications'] = []
        return context

class JobApplyView(CandidateRequiredMixin, View):
    def get(self, request, job_id, *args, **kwargs):
        from apps.jobs.models import Job
        from apps.applications.models import Application
        from django.contrib import messages
        
        job = get_object_or_404(Job, id=job_id)
        if Application.objects.filter(job=job, candidate=request.user.candidate_profile).exists():
            messages.warning(request, "You have already applied for this job.")
            return redirect('frontend:candidate_applications')
            
        context = {
            'job': job,
            'profile': request.user.candidate_profile
        }
        return render(request, 'candidate_apply.html', context)
        
    def post(self, request, job_id, *args, **kwargs):
        from apps.jobs.models import Job
        from services.application_service import ApplicationService
        from django.contrib import messages
        
        job = get_object_or_404(Job, id=job_id)
        profile = request.user.candidate_profile
        
        try:
            cover_letter = request.POST.get('cover_letter', '')
            current_company = request.POST.get('current_company', '')
            current_designation = request.POST.get('current_designation', '')
            total_experience = request.POST.get('total_experience') or None
            relevant_experience = request.POST.get('relevant_experience') or None
            current_ctc = request.POST.get('current_ctc') or None
            expected_ctc = request.POST.get('expected_ctc') or None
            notice_period = request.POST.get('notice_period') or None
            is_immediate_joiner = request.POST.get('is_immediate_joiner') == 'on'
            preferred_location = request.POST.get('preferred_location', '')
            preferred_work_mode = request.POST.get('preferred_work_mode', '')
            available_joining_date = request.POST.get('available_joining_date') or None
            
            screening_answers = {}
            for i, q in enumerate(job.screening_questions):
                q_id = f"question_{i}"
                screening_answers[q.get('question')] = request.POST.get(q_id, '')
                
            ApplicationService.apply_for_job(
                job_id=str(job.id),
                candidate_id=str(profile.id),
                cover_letter=cover_letter,
                current_company=current_company,
                current_designation=current_designation,
                total_experience=total_experience,
                relevant_experience=relevant_experience,
                current_ctc=current_ctc,
                expected_ctc=expected_ctc,
                notice_period=notice_period,
                is_immediate_joiner=is_immediate_joiner,
                preferred_location=preferred_location,
                preferred_work_mode=preferred_work_mode,
                available_joining_date=available_joining_date,
                screening_answers=screening_answers
            )
            messages.success(request, f"Successfully applied for {job.title} at {job.company.name}")
            return redirect('frontend:candidate_applications')
        except Exception as e:
            messages.error(request, str(e))
            return redirect('frontend:job_apply', job_id=job.id)


class ToggleSaveJobView(CandidateRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        import json
        try:
            data = json.loads(request.body)
            job_id = data.get('job_id')
        except Exception:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
            
        if not job_id:
            return JsonResponse({'error': 'Missing job_id'}, status=400)
            
        candidate_profile = getattr(request.user, 'candidate_profile', None)
        if not candidate_profile:
            return JsonResponse({'error': 'Candidate profile not found'}, status=400)
            
        from apps.candidates.models import SavedJob
        saved_job = SavedJob.objects.filter(candidate=candidate_profile, job_id=job_id)
        
        if saved_job.exists():
            saved_job.delete()
            return JsonResponse({'status': 'removed'})
        else:
            from apps.jobs.models import Job
            job = get_object_or_404(Job, id=job_id)
            SavedJob.objects.create(candidate=candidate_profile, job=job)
            return JsonResponse({'status': 'saved'})


# --- CUSTOM PRODUCTION ERROR HANDLERS ---

def custom_bad_request_view(request, exception=None):
    logger.error(f"400 Bad Request at {request.path}: {exception}")
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
        return JsonResponse({'error': 'Bad Request', 'message': str(exception) if exception else 'Invalid request parameters.'}, status=400)
    return render(request, '400.html', {'message': str(exception) if exception else 'Invalid request.'}, status=400)

def custom_permission_denied_view(request, exception=None):
    logger.warning(f"403 Permission Denied at {request.path}: {exception}")
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
        return JsonResponse({'error': 'Permission Denied', 'message': 'You do not have permission to perform this action.'}, status=403)
    return render(request, '403.html', {'message': 'You do not have permission to access this resource.'}, status=403)

def custom_page_not_found_view(request, exception=None):
    logger.info(f"404 Not Found at {request.path}")
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
        return JsonResponse({'error': 'Not Found', 'message': 'The requested resource was not found.'}, status=404)
    return render(request, '404.html', {'message': 'The page you requested could not be found.'}, status=404)

def custom_server_error_view(request):
    import traceback
    logger.error(f"500 Internal Server Error at {request.path}\n{traceback.format_exc()}")
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
        return JsonResponse({'error': 'Server Error', 'message': 'An internal error occurred. Our team has been notified.'}, status=500)
    return render(request, '500.html', {'message': 'An unexpected error occurred. Please try again later.'}, status=500)

