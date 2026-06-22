from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

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

urlpatterns = [
    # Frontend Dashboard UI
    path('', include('apps.core.urls', namespace='frontend')),
    path("clients/", include(("apps.clients.urls", "clients"), namespace="clients")),
    path('accounts/', include('django.contrib.auth.urls')),

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
