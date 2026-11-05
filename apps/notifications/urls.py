from django.urls import path
from .views import (
    TrackOpenView,
    TrackClickView,
    EmailTemplateAPIView,
    RecruiterEmailAccountAPIView,
    RecruiterGmailOAuthStartView,
    RecruiterGmailOAuthCallbackView
)

app_name = 'notifications'

urlpatterns = [
    path('track/open/<uuid:uuid>/', TrackOpenView.as_view(), name='track_open'),
    path('track/click/<uuid:uuid>/', TrackClickView.as_view(), name='track_click'),
    path('api/templates/', EmailTemplateAPIView.as_view(), name='email_templates_api'),
    path('api/email-accounts/', RecruiterEmailAccountAPIView.as_view(), name='recruiter_email_accounts_api'),
    path('oauth/gmail/start/', RecruiterGmailOAuthStartView.as_view(), name='recruiter_gmail_oauth_start'),
    path('oauth/gmail/callback/', RecruiterGmailOAuthCallbackView.as_view(), name='recruiter_gmail_oauth_callback'),
]
