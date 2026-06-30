from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from django.conf import settings
from django.views.static import serve

from apps.companies.views import CompanyViewSet, CompanyMemberViewSet
from apps.jobs.views import JobViewSet
from apps.jobs.matching_views import MatchingCandidatesView
from apps.candidates.views import CandidateProfileViewSet, CandidateSkillViewSet, ExperienceViewSet, EducationViewSet
from apps.applications.views import ApplicationViewSet
from apps.interviews.views import InterviewViewSet

# Create a router and register our viewsets with it.
router = DefaultRouter()
router.register(r'companies', CompanyViewSet, basename='company')
router.register(r'jobs', JobViewSet, basename='job')
router.register(r'candidates/profiles', CandidateProfileViewSet, basename='candidate-profile')
router.register(r'candidates/skills', CandidateSkillViewSet, basename='candidate-skill')
router.register(r'candidates/experience', ExperienceViewSet, basename='candidate-experience')
router.register(r'candidates/education', EducationViewSet, basename='candidate-education')
router.register(r'applications', ApplicationViewSet, basename='application')
router.register(r'interviews', InterviewViewSet, basename='interview')

from apps.accounts.views import CustomLoginView, CustomLogoutView, SignupView

import os
import sys
import subprocess
from django.http import JsonResponse
from django.views import View

class DebugDiagnosticsView(View):
    def get(self, request, *args, **kwargs):
        if request.GET.get('secret') != 'audit_2026':
            return JsonResponse({'error': 'Unauthorized'}, status=403)
            
        if request.GET.get('action') == 'parse_test':
            try:
                import os
                from django.conf import settings
                from apps.candidates.utils import process_resume_file
                pdf_path = os.path.join(settings.BASE_DIR, 'scratch', 'harneet_resume.pdf')
                with open(pdf_path, 'rb') as f:
                    profile, status = process_resume_file(f, 'harneet_resume.pdf', overwrite=True)
                
                return JsonResponse({
                    'status': status,
                    'candidate_id': str(profile.id) if profile else None,
                    'full_name': profile.full_name if profile else None,
                    'experiences_count': profile.experiences.count() if profile else 0,
                    'educations_count': profile.educations.count() if profile else 0,
                    'skills_count': profile.skills.count() if profile else 0,
                    'skills': [s.skill_name for s in profile.skills.all()] if profile else []
                })
            except Exception as e:
                import traceback
                return JsonResponse({
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }, status=500)
            
        env_vars = {}
        for k, v in os.environ.items():
            if any(secret in k.lower() for secret in ['password', 'key', 'secret', 'token']):
                env_vars[k] = f"{v[:4]}...{v[-4:]}" if len(v) > 8 else "********"
            else:
                env_vars[k] = v
                
        try:
            pip_freeze = subprocess.check_output([sys.executable, '-m', 'pip', 'freeze']).decode('utf-8')
        except Exception as e:
            pip_freeze = f"Error running pip freeze: {e}"
            
        pkg_versions = {}
        packages = ['pdfplumber', 'fitz', 'paddleocr', 'easyocr', 'pdf2image', 'cv2', 'PIL']
        for p in packages:
            try:
                mod = __import__(p)
                pkg_versions[p] = getattr(mod, '__version__', 'unknown')
            except Exception as e:
                pkg_versions[p] = f"Error: {e}"
                
        latest_cand = None
        try:
            from apps.candidates.models import CandidateProfile
            q_name = request.GET.get('name')
            if q_name:
                latest = CandidateProfile.objects.filter(full_name__icontains=q_name).latest('created_at')
            else:
                latest = CandidateProfile.objects.latest('created_at')
            latest_cand = {
                'id': str(latest.id),
                'full_name': latest.full_name,
                'email': latest.user.email,
                'parsed_json': latest.parsed_json,
                'ocr_engine': latest.ocr_engine,
                'ocr_confidence': str(latest.ocr_confidence) if latest.ocr_confidence is not None else None,
                'audit_logs': latest.audit_logs,
                'raw_text_len': len(latest.raw_resume_text) if latest.raw_resume_text else 0,
                'resume_type': latest.resume_type,
            }
        except Exception as e:
            latest_cand = {'error': str(e)}

        return JsonResponse({
            'python_version': sys.version,
            'env_vars': env_vars,
            'pip_freeze': pip_freeze,
            'pkg_versions': pkg_versions,
            'latest_candidate': latest_cand,
        })

urlpatterns = [
    path('api/v1/debug-diagnostics/', DebugDiagnosticsView.as_view(), name='debug_diagnostics'),
    # Frontend Dashboard UI
    path('', include('apps.core.urls', namespace='frontend')),
    path("clients/", include(("apps.clients.urls", "clients"), namespace="clients")),
    path('accounts/login/', CustomLoginView.as_view(), name='account_login'),
    path('accounts/logout/', CustomLogoutView.as_view(), name='account_logout'),
    path('accounts/signup/', SignupView.as_view(), name='account_signup'),

    path('admin/', admin.site.urls),
    
    # API Version 1
    path('api/v1/auth/', include('apps.accounts.urls')),
    path('api/v1/', include(router.urls)),
    
    # Nested routes for companies -> members
    path('api/v1/companies/<uuid:company_pk>/members/', CompanyMemberViewSet.as_view({'get': 'list', 'post': 'create'}), name='company-members'),
    
    # Matching Engine route for a specific job
    path('api/v1/jobs/<uuid:job_pk>/matching-candidates/', MatchingCandidatesView.as_view(), name='job-matching-candidates'),

    # Swagger OpenAPI documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

urlpatterns += [
    path('media/<path:path>', serve, {'document_root': settings.MEDIA_ROOT}),
]
