import random
import json
from decimal import Decimal
from datetime import datetime
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.generic import TemplateView, ListView, DetailView, View, CreateView, UpdateView, DeleteView
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.db.models import Count, Q, Avg
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

from apps.core.models import Location

class LocationSearchView(View):
    def get(self, request, *args, **kwargs):
        q = request.GET.get('q', '')
        locations = Location.objects.filter(
            Q(name__icontains=q) | Q(state__icontains=q)
        ).distinct()[:20]
        
        results = []
        for loc in locations:
            text = f"{loc.name}"
            if loc.state:
                text += f", {loc.state}"
            results.append({'id': text, 'text': text})
            
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

class RoleRedirectView(LoginRequiredMixin, View):
    """
    Redirect users to their respective dashboards based on their role.
    """
    def get(self, request, *args, **kwargs):
        role = request.user.role
        if role == User.Role.SUPER_ADMIN:
            return redirect('frontend:admin_dashboard')
        elif role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN]:
            return redirect('frontend:recruiter_dashboard')
        elif role == User.Role.CANDIDATE:
            return redirect('frontend:candidate_dashboard')
        return redirect('frontend:dashboard')

class CandidateDashboardView(CandidateRequiredMixin, TemplateView):
    template_name = 'candidate_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add candidate specific data
        context['applications_count'] = Application.objects.filter(candidate__user=self.request.user).count()
        context['interviews_count'] = Interview.objects.filter(application__candidate__user=self.request.user).count()
        return context

class RecruiterDashboardView(RecruiterRequiredMixin, TemplateView):
    template_name = 'recruiter_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Current Database counts/objects
        context['timezone_now'] = timezone.now()
        from apps.candidates.models import CandidateProfile
        from apps.applications.models import Application
        from apps.notifications.models import EmailLog
        from django.utils import timezone as django_timezone
        
        context['total_candidates_count'] = CandidateProfile.objects.count()
        context['open_jobs_count'] = Job.objects.filter(status='ACTIVE').count()
        context['total_emails_count'] = EmailLog.objects.count()
        
        # New applications count (last 7 days)
        seven_days_ago = django_timezone.now() - django_timezone.timedelta(days=7)
        context['new_applications_count'] = Application.objects.filter(created_at__gte=seven_days_ago).count()
        
        # Interviews scheduled for today
        today_date = django_timezone.now().date()
        context['interviews_today_count'] = Interview.objects.filter(start_time__date=today_date).count()
        
        # Recent Job Openings
        context['recent_jobs'] = Job.objects.filter(status='ACTIVE').order_by('-created_at')[:5]
        
        # Candidates added over last 7 days (for line chart)
        candidates_by_day = []
        for i in range(6, -1, -1):
            day = today_date - django_timezone.timedelta(days=i)
            count = CandidateProfile.objects.filter(created_at__date=day).count()
            candidates_by_day.append({
                'day': day.strftime("%a"),
                'count': count
            })
        context['candidates_by_day'] = candidates_by_day
        
        # 1. Total Interviews (Scheduled Interviews)
        context['upcoming_interviews'] = Interview.objects.filter(
            status='SCHEDULED'
        ).select_related('application__candidate__user', 'application__job').order_by('start_time')[:10]
        context['total_interviews_count'] = Interview.objects.filter(status='SCHEDULED').count()
        
        # 2. My Tasks (Recruiter Actionable Items from database records)
        tasks = []
        # Task type 1: Screen new applicants
        pending_screening = Application.objects.filter(stage='APPLIED').select_related('candidate__user', 'job')
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
        # Task type 2: Conduct scheduled interviews
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
        
        # 4. Applicant Status (Pipeline stats counts)
        pipeline_counts = []
        for stage_val, stage_label in Application.ApplicationStage.choices:
            count = Application.objects.filter(stage=stage_val).count()
            
            # Map stages to CSS classes based on the requested colors:
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
        context['job_applicants'] = Job.objects.filter(status='ACTIVE').annotate(
            applicant_count=Count('applications'),
            avg_ats_score=Avg('applications__match_score')
        ).order_by('-applicant_count')[:10]
        
        # 6. Referrals Count (Database-driven)
        context['referrals_count'] = 0  # No referral tracking model in the database yet
        
        return context

class AdminDashboardView(SuperAdminRequiredMixin, TemplateView):
    template_name = 'admin_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        context['open_jobs'] = Job.objects.filter(status='ACTIVE').count()
        context['candidates_added'] = CandidateProfile.objects.count()
        context['interviews_scheduled'] = Interview.objects.count()
        context['placements'] = Application.objects.filter(stage='HIRED').count()
        context['duplicates_found'] = DuplicateResumeLog.objects.count()
        context['resumes_uploaded_today'] = CandidateProfile.objects.filter(created_at__date=today).count()
        context['recent_applicants'] = Application.objects.select_related('candidate__user', 'job').order_by('-created_at')[:10]
        context['total_users'] = User.objects.count()
        context['total_recruiters'] = User.objects.filter(role__in=[User.Role.RECRUITER, User.Role.COMPANY_ADMIN]).count()
        return context

class JobActionView(View):
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
        elif action == 'clone':
            new_job = job
            new_job.pk = None
            new_job.title = f"Copy of {job.title}"
            new_job.status = 'DRAFT'
            new_job.save()
            return redirect('frontend:job_edit', pk=new_job.pk)
        job.save()
        return redirect('frontend:jobs')

class JobsView(LoginRequiredMixin, ListView):
    model = Job
    template_name = 'jobs.html'
    context_object_name = 'jobs'
    paginate_by = 10

    def get_queryset(self):
        queryset = Job.objects.annotate(
            app_count=Count('applications'),
            interview_count=Count('applications__interviews')
        )
        
        # Search
        q = self.request.GET.get('q', '')
        if q:
            queryset = queryset.filter(Q(title__icontains=q) | Q(description__icontains=q))
            
        # Filters
        status = self.request.GET.get('status', '')
        if status:
            queryset = queryset.filter(status=status)
            
        job_type = self.request.GET.get('job_type', '')
        if job_type:
            queryset = queryset.filter(job_type=job_type)
            
        # Sorting
        sort_by = self.request.GET.get('sort_by', '-created_at')
        if sort_by in ['title', '-title', 'created_at', '-created_at', 'app_count', '-app_count']:
            queryset = queryset.order_by(sort_by)
        else:
            queryset = queryset.order_by('-created_at')
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_count'] = Job.objects.filter(status='ACTIVE').count()
        context['draft_count'] = Job.objects.filter(status='DRAFT').count()
        context['on_hold_count'] = Job.objects.filter(status='ON_HOLD').count()
        context['closed_count'] = Job.objects.filter(status='CLOSED').count()
        
        # Preserve search, filter and sort inputs in template
        context['q'] = self.request.GET.get('q', '')
        context['selected_status'] = self.request.GET.get('status', '')
        context['selected_job_type'] = self.request.GET.get('job_type', '')
        context['selected_sort'] = self.request.GET.get('sort_by', '-created_at')
        
        context['job_types'] = [
            ('FULL_TIME', 'Full Time'),
            ('PART_TIME', 'Part Time'),
            ('CONTRACT', 'Contract'),
            ('FREELANCE', 'Freelance'),
            ('REMOTE', 'Remote'),
        ]
        context['statuses'] = Job.JobStatus.choices

        # Pre-generate absolute share URLs using request.build_absolute_uri()
        for job in context.get('jobs', []):
            job.share_url = self.request.build_absolute_uri(
                reverse('frontend:public_job_share', kwargs={'pk': job.pk})
            )
        
        return context

from apps.jobs.models import Job, JobSkill

class JobCreateView(LoginRequiredMixin, CreateView):
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
        member = CompanyMember.objects.filter(user=self.request.user).first()
        if member:
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

class JobUpdateView(LoginRequiredMixin, UpdateView):
    model = Job
    form_class = JobForm
    template_name = 'job_create.html'
    success_url = reverse_lazy('frontend:jobs')

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

class JobDeleteView(LoginRequiredMixin, DeleteView):
    model = Job
    success_url = reverse_lazy('frontend:jobs')
    template_name = 'job_confirm_delete.html'

    def form_valid(self, form):
        messages.success(self.request, "Job deleted successfully.")
        return super().form_valid(form)


class CandidateSearchView(LoginRequiredMixin, ListView):
    model = CandidateProfile
    template_name = 'candidate_search.html'
    context_object_name = 'candidates'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = CandidateProfile.objects.select_related('user').prefetch_related('skills').all()
        
        # Get Filter Params
        q = self.request.GET.get('q')
        skills = self.request.GET.get('skills')
        location = self.request.GET.get('location')
        min_exp = self.request.GET.get('min_exp')
        max_exp = self.request.GET.get('max_exp')
        company = self.request.GET.get('company')
        designation = self.request.GET.get('designation')
        max_ctc = self.request.GET.get('max_ctc')
        max_np = self.request.GET.get('max_np')
        
        min_ats = self.request.GET.get('min_ats')
        max_ats = self.request.GET.get('max_ats')
        sort_by = self.request.GET.get('sort_by')
        job_id = self.request.GET.get('job_id')

        if q:
            queryset = queryset.filter(
                Q(user__email__icontains=q) | 
                Q(user__first_name__icontains=q) |
                Q(user__last_name__icontains=q) |
                Q(summary__icontains=q)
            )
        
        if skills:
            skill_list = [s.strip() for s in skills.split(',') if s.strip()]
            for s in skill_list:
                queryset = queryset.filter(skills__skill_name__icontains=s)
        
        if location:
            queryset = queryset.filter(location__icontains=location)
            
        if min_exp:
            queryset = queryset.filter(total_experience__gte=float(min_exp))
        if max_exp:
            queryset = queryset.filter(total_experience__lte=float(max_exp))
            
        if company:
            queryset = queryset.filter(current_company__icontains=company)
        if designation:
            queryset = queryset.filter(current_designation__icontains=designation)
            
        if max_ctc:
            queryset = queryset.filter(current_salary__lte=float(max_ctc))
            
        if max_np:
            queryset = queryset.filter(notice_period__lte=int(max_np))
            
        selected_job = None
        if job_id:
            from apps.jobs.models import Job
            selected_job = Job.objects.filter(id=job_id).first()

        # If a job is selected, calculate dynamic scores and filter/sort list in python
        if selected_job:
            from services.candidate_matching_service import CandidateMatchingService
            candidate_list = list(queryset)
            # Precompute scores against selected job
            for c in candidate_list:
                c.temp_score = CandidateMatchingService.calculate_job_ats_score(c, selected_job)['total_score']
            
            # Apply Min/Max ATS filters on the list
            if min_ats and min_ats.strip():
                candidate_list = [c for c in candidate_list if c.temp_score >= int(min_ats)]
            if max_ats and max_ats.strip():
                candidate_list = [c for c in candidate_list if c.temp_score <= int(max_ats)]
                
            # Sort candidate_list
            if sort_by == 'ats_desc':
                candidate_list.sort(key=lambda x: x.temp_score, reverse=True)
            elif sort_by == 'ats_asc':
                candidate_list.sort(key=lambda x: x.temp_score, reverse=False)
            else:
                candidate_list.sort(key=lambda x: (x.temp_score, x.created_at), reverse=True)
                
            return candidate_list
        else:
            # No job selected: filter by general ats_score field
            if min_ats and min_ats.strip():
                queryset = queryset.filter(ats_score__gte=int(min_ats))
            if max_ats and max_ats.strip():
                queryset = queryset.filter(ats_score__lte=int(max_ats))
                
            queryset = queryset.distinct()
            if sort_by == 'ats_desc':
                queryset = queryset.order_by('-ats_score', '-created_at')
            elif sort_by == 'ats_asc':
                queryset = queryset.order_by('ats_score', '-created_at')
            else:
                queryset = queryset.order_by('-created_at')
                
            return queryset

    def get_context_data(self, **kwargs):
        from apps.jobs.models import Job
        context = super().get_context_data(**kwargs)
        job_id = self.request.GET.get('job_id')
        selected_job = None
        if job_id:
            selected_job = Job.objects.filter(id=job_id).first()
            
        context['selected_job'] = selected_job
        context['filters'] = self.request.GET
        context['active_jobs'] = Job.objects.filter(status='ACTIVE')
        
        # Attach match details dynamically for page display
        from services.candidate_matching_service import CandidateMatchingService
        candidates_list = list(context.get('candidates') or context.get('object_list') or [])
        for candidate in candidates_list:
            if selected_job:
                candidate.match_details = CandidateMatchingService.calculate_job_ats_score(candidate, selected_job)
            else:
                candidate.match_details = None
                
        context['candidates'] = candidates_list
        context['object_list'] = candidates_list
        return context

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

class CandidateDetailView(LoginRequiredMixin, DetailView):
    model = CandidateProfile
    template_name = 'candidate_detail.html'
    context_object_name = 'candidate'

    def get_context_data(self, **kwargs):
        from apps.jobs.models import Job
        from datetime import datetime, date
        
        context = super().get_context_data(**kwargs)
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[DETAIL_VIEW] Recruiter {self.request.user.email} accessed candidate profile: {self.object.id} ({self.object.full_name})")
        context['active_jobs'] = Job.objects.filter(status='ACTIVE')
        context['stage_choices'] = Application.ApplicationStage.choices
        
        job_id = self.request.GET.get('job_id')
        selected_job = None
        match_details = None
        
        if job_id:
            selected_job = Job.objects.filter(id=job_id).first()
            if selected_job:
                from services.candidate_matching_service import CandidateMatchingService
                match_details = CandidateMatchingService.calculate_job_ats_score(self.object, selected_job)
                
        context['selected_job'] = selected_job
        context['match_details'] = match_details
        
        # Check for duplicates
        from services.resume_intelligence import ResumeIntelligenceService
        duplicates = []
        other_candidates = CandidateProfile.objects.exclude(id=self.object.id)
        for c in other_candidates:
            res = ResumeIntelligenceService.calculate_duplicate_similarity(self.object, c)
            if res["is_duplicate"]:
                duplicates.append(res)
        context['duplicates'] = duplicates
        
        # Determine which version to preview (default to 1)
        version_param = self.request.GET.get('version')
        selected_version_id = 1
        if version_param:
            try:
                selected_version_id = int(version_param)
            except ValueError:
                selected_version_id = 1
                
        version_str = str(selected_version_id)
        if self.object.resume_versions and version_str in self.object.resume_versions:
            version_data = self.object.resume_versions[version_str]["data"]
        else:
            if self.object.resume_versions and "1" in self.object.resume_versions:
                version_data = self.object.resume_versions["1"]["data"]
                selected_version_id = 1
            else:
                # Reconstruct version data from database fields if versions are empty
                version_data = {
                    "personal_info": {
                        "name": self.object.full_name,
                        "current_company": self.object.current_company,
                        "current_designation": self.object.current_designation,
                        "total_experience": float(self.object.total_experience),
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
                selected_version_id = 1

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
        
        resume_exists = False
        resume_missing = False
        if self.object.resume:
            try:
                if self.object.resume.name and os.path.exists(self.object.resume.path):
                    resume_exists = True
                else:
                    resume_missing = True
            except (ValueError, AssertionError):
                resume_missing = True
        context['resume_exists'] = resume_exists
        context['resume_missing'] = resume_missing
        
        from django.urls import reverse
        context['public_share_url'] = self.request.build_absolute_uri(
            reverse('frontend:public_candidate_profile', kwargs={'pk': self.object.pk})
        )
        
        return context

class CandidateUpdateView(LoginRequiredMixin, UpdateView):
    model = CandidateProfile
    template_name = 'candidate_form.html'
    fields = [
        'full_name', 'summary', 'location', 'total_experience', 
        'current_company', 'current_designation',
        'current_salary', 'expected_salary', 'notice_period',
        'linkedin_url', 'portfolio_url'
    ]
    success_url = reverse_lazy('frontend:candidate_search')

    def get_success_url(self):
        return reverse_lazy('frontend:candidate_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        from services.candidate_matching_service import CandidateMatchingService
        CandidateMatchingService.update_ats_scores(candidate_id=self.object.id)
        return response

class CandidateDeleteView(LoginRequiredMixin, View):
    def post(self, request, id, *args, **kwargs):
        candidate = get_object_or_404(CandidateProfile, id=id)
        user = candidate.user
        candidate.delete()
        if user and user.role == 'CANDIDATE':
            user.delete()
        messages.success(request, "Candidate deleted successfully.")
        return redirect('frontend:candidate_search')

class CandidateRejectView(LoginRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        candidate = get_object_or_404(CandidateProfile, pk=pk)
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
            
        return redirect('frontend:candidate_detail', pk=pk)

class UpdateApplicationStageDirectView(LoginRequiredMixin, View):
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        import os
        context['resume_filename'] = os.path.basename(self.object.resume.name) if self.object.resume else ""
        context['resume_extension'] = os.path.splitext(self.object.resume.name)[1].lower().replace('.', '') if self.object.resume else ""
        
        resume_exists = False
        resume_missing = False
        if self.object.resume:
            try:
                if self.object.resume.name and os.path.exists(self.object.resume.path):
                    resume_exists = True
                else:
                    resume_missing = True
            except (ValueError, AssertionError):
                resume_missing = True
        context['resume_exists'] = resume_exists
        context['resume_missing'] = resume_missing
        return context

class PublicJobShareView(DetailView):
    model = Job
    template_name = 'public_job_share.html'
    context_object_name = 'job'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        share_url = self.request.build_absolute_uri(
            reverse('frontend:public_job_share', kwargs={'pk': self.object.pk})
        )
        context['share_url'] = share_url
        return context

class AddToPipelineView(RecruiterRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        candidate = get_object_or_404(CandidateProfile, pk=pk)
        job_id = request.POST.get('job_id')
        
        if not job_id:
            messages.error(request, "Please select a job.")
            return redirect('frontend:candidate_detail', pk=pk)
            
        job = get_object_or_404(Job, id=job_id)
        
        # Prevent duplicate applications
        application, created = Application.objects.get_or_create(
            candidate=candidate,
            job=job,
            defaults={'stage': 'OPEN'}
        )
        
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
            
        return redirect('frontend:ats_pipeline')

import json

class UpdateApplicationStageView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            app_id = data.get('application_id')
            new_stage = data.get('new_stage')
            
            application = get_object_or_404(Application, id=app_id)
            old_stage = application.stage
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

class CompleteTaskView(LoginRequiredMixin, View):
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

class ATSPipelineView(LoginRequiredMixin, TemplateView):
    template_name = 'ats_pipeline.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        job_id = self.request.GET.get('job_id')
        if not job_id:
            job = Job.objects.filter(status='ACTIVE').first()
        else:
            job = Job.objects.filter(id=job_id).first()
        
        context['selected_job'] = job
        context['all_jobs'] = Job.objects.filter(status='ACTIVE')
        
        if job:
            apps = Application.objects.filter(job=job).select_related('candidate__user')
            pipeline_data = []
            stage_colors = {
                'OPEN': '#3b82f6', # blue
                'SCREENING_SELECT': '#198754', # green
                'SCREENING_REJECT': '#dc3545', # red
                'INTERVIEW_SCHEDULE': '#ffc107', # yellow
                'INTERVIEW_SELECT': '#198754', # green
                'INTERVIEW_REJECT': '#dc3545', # red
                'OFFER_STAGE': '#6f42c1', # purple
                'ACCEPTED': '#20c997', # teal
                'JOINED': '#0f5132', # dark green
                'DROPOUT': '#6c757d', # gray
            }
            for stage_val, stage_label in Application.ApplicationStage.choices:
                color = stage_colors.get(stage_val, '#cbd5e1')
                pipeline_data.append({
                    'stage': stage_val,
                    'label': stage_label,
                    'apps': apps.filter(stage=stage_val),
                    'color': color
                })
            context['pipeline'] = pipeline_data
        return context

class InterviewsView(LoginRequiredMixin, ListView):
    model = Interview
    template_name = 'interviews.html'
    context_object_name = 'interviews'
    
    def get_queryset(self):
        return Interview.objects.all().order_by('start_time')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN]:
            context['applications'] = Application.objects.select_related('candidate__user', 'job').all()
            context['recruiters'] = User.objects.filter(role__in=[User.Role.RECRUITER, User.Role.COMPANY_ADMIN])
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

class InterviewCalendarEventsView(LoginRequiredMixin, View):
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
        for c in CandidateProfile.objects.select_related('user').all():
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
        for j in Job.objects.select_related('company').all():
            writer.writerow([j.title, j.company.name, j.location, j.job_type, j.experience_level, j.min_salary, j.max_salary, j.status])
        return response

class ExportInterviewsView(RecruiterRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="interviews.csv"'
        writer = csv.writer(response)
        writer.writerow(['Candidate', 'Job', 'Start Time', 'End Time', 'Round', 'Status', 'Meeting Link'])
        for i in Interview.objects.select_related('application__candidate__user', 'application__job').all():
            writer.writerow([
                i.application.candidate.user.email,
                i.application.job.title,
                i.start_time,
                i.end_time,
                i.round,
                i.status,
                i.meeting_link
            ])
        return response

from apps.candidates.models import CandidateSkill

class AnalyticsView(LoginRequiredMixin, TemplateView):
    template_name = 'analytics.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Hiring Funnel Data
        funnel_data = Application.objects.values('stage').annotate(count=Count('id'))
        context['funnel_labels'] = [s[1] for s in Application.ApplicationStage.choices]
        context['funnel_values'] = []
        for stage_code, stage_label in Application.ApplicationStage.choices:
            count = next((item['count'] for item in funnel_data if item['stage'] == stage_code), 0)
            context['funnel_values'].append(count)
            
        # Top Skills Data
        top_skills = CandidateSkill.objects.values('skill_name').annotate(count=Count('id')).order_by('-count')[:5]
        context['skill_labels'] = [item['skill_name'] for item in top_skills]
        context['skill_values'] = [item['count'] for item in top_skills]
        
        # Source Data (Mocked as we don't have source field yet, but I'll use random for now or just 0s)
        context['source_labels'] = ['LinkedIn', 'Indeed', 'Naukri', 'Referral']
        context['source_values'] = [45, 30, 20, 5]
        
        return context

class SettingsView(LoginRequiredMixin, TemplateView):
    template_name = 'settings.html'

from apps.candidates.utils import handle_resume_upload
from django.contrib import messages

class ResumeParserView(RecruiterRequiredMixin, TemplateView):
    template_name = 'resume_parser.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        context['duplicates_found_today'] = DuplicateResumeLog.objects.filter(created_at__date=today).count()
        return context

    def post(self, request, *args, **kwargs):
        overwrite = request.POST.get('overwrite') == 'on'
        total_created = 0
        total_duplicates = 0
        
        if 'resume' in request.FILES:
            results = handle_resume_upload(request.FILES['resume'], overwrite=overwrite)
            total_created += len(results['created'])
            total_duplicates += results['duplicates']
            
        if 'resumes_zip' in request.FILES:
            results = handle_resume_upload(request.FILES['resumes_zip'], overwrite=overwrite)
            total_created += len(results['created'])
            total_duplicates += results['duplicates']
            
        if total_created > 0 or total_duplicates > 0:
            msg = f'Import complete. {total_created} profiles created.'
            if total_duplicates > 0:
                msg += f' {total_duplicates} duplicates found ({"updated" if overwrite else "skipped"}).'
            messages.success(request, msg)
            # Create recruiter notification
            Notification.objects.create(
                recipient=request.user,
                title="Resume Parsing Complete",
                message=msg,
                notification_type='SYSTEM'
            )
        else:
            messages.error(request, 'No valid resumes were parsed.')
            
        return redirect('frontend:candidate_search')

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
        profile.full_name = info.get("name", profile.full_name)
        profile.summary = data.get("summary", profile.summary)
        profile.location = info.get("location", profile.location)
        profile.current_company = info.get("current_company", profile.current_company)
        profile.current_designation = info.get("current_designation", profile.current_designation)
        
        try:
            profile.total_experience = Decimal(str(info.get("total_experience", profile.total_experience)))
        except Exception:
            pass
            
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
            CandidateSkill.objects.get_or_create(profile=profile, skill_name=sk.strip().title())
            
        # Sync Experiences relation
        profile.experiences.all().delete()
        for exp in data.get("experience", []):
            try:
                s_date = datetime.strptime(exp.get("start_date"), "%Y-%m-%d").date() if exp.get("start_date") else None
                e_date = datetime.strptime(exp.get("end_date"), "%Y-%m-%d").date() if exp.get("end_date") else None
            except Exception:
                s_date, e_date = None, None
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
                description=proj.get("description", ""),
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
                name=cert.get("name", "Certification")[:255],
                issuing_organization=cert.get("issuing_organization", "")[:255],
                issue_date=i_date
            )
            
        # Recalculate ATS Scores
        CandidateMatchingService.update_ats_scores(candidate_id=profile.id)
        
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
            profile.full_name = info.get("name", profile.full_name)
            profile.summary = improved_data.get("summary", profile.summary)
            profile.current_company = info.get("current_company", profile.current_company)
            profile.current_designation = info.get("current_designation", profile.current_designation)
            
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
                CandidateSkill.objects.get_or_create(profile=profile, skill_name=sk.strip().title())
                
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
        profile.full_name = info.get("name", profile.full_name)
        profile.summary = data.get("summary", profile.summary)
        profile.location = info.get("location", profile.location)
        profile.current_company = info.get("current_company", profile.current_company)
        profile.current_designation = info.get("current_designation", profile.current_designation)
        
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
            CandidateSkill.objects.get_or_create(profile=profile, skill_name=sk.strip().title())
            
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
    Renders inline candidate resume in browser for PDF, JPG, PNG previews.
    """
    def get(self, request, pk, *args, **kwargs):
        import os
        import mimetypes
        candidate = get_object_or_404(CandidateProfile, pk=pk)
        if not candidate.resume:
            return HttpResponse("No resume file found.", status=404)
            
        file_path = candidate.resume.path
        if not os.path.exists(file_path):
            return HttpResponse("File does not exist on disk.", status=404)
            
        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            content_type = 'application/octet-stream'
            
        try:
            f = open(file_path, 'rb')
            response = FileResponse(f, content_type=content_type)
            response['Content-Disposition'] = f'inline; filename="{os.path.basename(file_path)}"'
            return response
        except Exception as e:
            return HttpResponse(f"Error loading resume file: {str(e)}", status=500)


class CandidateResumeDownloadView(LoginRequiredMixin, View):
    """
    Forces download of the original candidate resume file, preserving filename.
    """
    def get(self, request, pk, *args, **kwargs):
        import os
        candidate = get_object_or_404(CandidateProfile, pk=pk)
        if not candidate.resume:
            return HttpResponse("No resume file found.", status=404)
            
        file_path = candidate.resume.path
        if not os.path.exists(file_path):
            return HttpResponse("File does not exist on disk.", status=404)
            
        filename = os.path.basename(file_path)
        try:
            f = open(file_path, 'rb')
            response = FileResponse(f, as_attachment=True, filename=filename)
            return response
        except Exception as e:
            return HttpResponse(f"Error downloading file: {str(e)}", status=500)


@method_decorator(xframe_options_sameorigin, name='dispatch')
class PublicCandidateResumePreviewView(View):
    """
    Renders inline candidate resume publicly in browser for PDF, JPG, PNG previews.
    """
    def get(self, request, pk, *args, **kwargs):
        import os
        import mimetypes
        candidate = get_object_or_404(CandidateProfile, pk=pk)
        if not candidate.resume:
            return HttpResponse("No resume file found.", status=404)
            
        file_path = candidate.resume.path
        if not os.path.exists(file_path):
            return HttpResponse("File does not exist on disk.", status=404)
            
        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            content_type = 'application/octet-stream'
            
        try:
            f = open(file_path, 'rb')
            response = FileResponse(f, content_type=content_type)
            response['Content-Disposition'] = f'inline; filename="{os.path.basename(file_path)}"'
            return response
        except Exception as e:
            return HttpResponse(f"Error loading resume file: {str(e)}", status=500)


class PublicCandidateResumeDownloadView(View):
    """
    Forces public download of the original candidate resume file, preserving filename.
    """
    def get(self, request, pk, *args, **kwargs):
        import os
        candidate = get_object_or_404(CandidateProfile, pk=pk)
        if not candidate.resume:
            return HttpResponse("No resume file found.", status=404)
            
        file_path = candidate.resume.path
        if not os.path.exists(file_path):
            return HttpResponse("File does not exist on disk.", status=404)
            
        filename = os.path.basename(file_path)
        try:
            f = open(file_path, 'rb')
            response = FileResponse(f, as_attachment=True, filename=filename)
            return response
        except Exception as e:
            return HttpResponse(f"Error downloading file: {str(e)}", status=500)
