from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from django.conf import settings
from django.views.static import serve

from apps.companies.views import CompanyViewSet, CompanyMemberViewSet
from apps.jobs.views import JobViewSet
from apps.jobs.matching_views import MatchingCandidatesView
from apps.candidates.views import (
    CandidateProfileViewSet, 
    CandidateSkillViewSet, 
    ExperienceViewSet, 
    EducationViewSet,
    ProjectViewSet,
    CertificationViewSet
)
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
router.register(r'candidates/projects', ProjectViewSet, basename='candidate-project')
router.register(r'candidates/certifications', CertificationViewSet, basename='candidate-certification')
router.register(r'applications', ApplicationViewSet, basename='application')
router.register(r'interviews', InterviewViewSet, basename='interview')

from allauth.socialaccount.providers.google.views import oauth2_login as google_allauth_login, oauth2_callback as google_allauth_callback

from apps.accounts.views import (
    CustomLoginView, 
    CustomLogoutView, 
    SignupView,
    LoginSelectView,
    SignupSelectView,
    CandidateLoginView,
    CandidateSignupView,
    EmployerLoginView,
    EmployerSignupView,
    AdminLoginView,
    CandidateForgotPasswordView,
    CandidateOTPVerificationView,
    CandidateResetPasswordView,
    GoogleLoginRedirectView,
    GoogleLoginCallbackView,
    SendEmailOTPView,
    VerifyEmailOTPView,
    ResendEmailOTPView
)

urlpatterns = [
    # Frontend Dashboard UI
    path('', include('apps.core.urls', namespace='frontend')),
    path('clients/', include('apps.clients.urls', namespace='clients')),
    path('accounts/logout/', CustomLogoutView.as_view(), name='account_logout'),
    path("accounts/", include("allauth.urls")),
    
    # Candidate Auth & Selects
    path('accounts/login/', CandidateLoginView.as_view(), name='account_login'),
    path('accounts/login/select/', LoginSelectView.as_view(), name='login_select'),
    path('accounts/signup/', SignupSelectView.as_view(), name='account_signup'),
    path('accounts/login/candidate/', CandidateLoginView.as_view(), name='candidate_login'),
    path('accounts/signup/candidate/', CandidateSignupView.as_view(), name='candidate_signup'),
    path('accounts/forgot-password/', CandidateForgotPasswordView.as_view(), name='candidate_forgot_password'),
    path('accounts/verify-otp/', CandidateOTPVerificationView.as_view(), name='candidate_verify_otp'),
    path('accounts/resend-email-otp/', ResendEmailOTPView.as_view(), name='resend_email_otp_web'),
    path('accounts/send-email-otp/', SendEmailOTPView.as_view(), name='send_email_otp_web'),
    path('accounts/verify-email-otp/', VerifyEmailOTPView.as_view(), name='verify_email_otp_web'),
    path('accounts/reset-password/', CandidateResetPasswordView.as_view(), name='candidate_reset_password'),



    
    # OAuth Routes
    path('accounts/login/google/', google_allauth_login, name='google_login'),
    path('accounts/login/google/callback/', google_allauth_callback, name='google_callback'),
    path('accounts/login/google/callback/alias/', google_allauth_callback, name='google_login_callback'),
    
    # Employer Auth
    path('accounts/login/employer/', EmployerLoginView.as_view(), name='employer_login'),
    path('accounts/signup/employer/', EmployerSignupView.as_view(), name='employer_signup'),
    
    # Admin Auth
    path('accounts/login/admin/', AdminLoginView.as_view(), name='admin_login'),

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
