from django.urls import path
from .views import TrackOpenView, TrackClickView, EmailTemplateAPIView, RecruiterEmailAccountAPIView

app_name = 'notifications'

urlpatterns = [
    path('track/open/<uuid:uuid>/', TrackOpenView.as_view(), name='track_open'),
    path('track/click/<uuid:uuid>/', TrackClickView.as_view(), name='track_click'),
    path('api/templates/', EmailTemplateAPIView.as_view(), name='email_templates_api'),
    path('api/email-accounts/', RecruiterEmailAccountAPIView.as_view(), name='recruiter_email_accounts_api'),
]
