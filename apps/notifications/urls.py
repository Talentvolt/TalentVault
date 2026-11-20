from django.urls import path
from .views import (
    TrackOpenView,
    TrackClickView,
    EmailTemplateAPIView,
    RecruiterEmailAccountAPIView,
    RecruiterGmailOAuthStartView,
    RecruiterGmailOAuthCallbackView,
    NotificationsPanelView,
    NotificationListAPIView,
    MarkNotificationReadAPIView,
    MarkAllNotificationsReadAPIView
)

app_name = 'notifications'

urlpatterns = [
    path('', NotificationsPanelView.as_view(), name='panel'),
    path('api/list/', NotificationListAPIView.as_view(), name='api_list'),
    path('api/mark-read/<int:pk>/', MarkNotificationReadAPIView.as_view(), name='api_mark_read'),
    path('api/mark-all-read/', MarkAllNotificationsReadAPIView.as_view(), name='api_mark_all_read'),
    path('track/open/<uuid:uuid>/', TrackOpenView.as_view(), name='track_open'),
    path('track/click/<uuid:uuid>/', TrackClickView.as_view(), name='track_click'),
    path('api/templates/', EmailTemplateAPIView.as_view(), name='email_templates_api'),
    path('api/email-accounts/', RecruiterEmailAccountAPIView.as_view(), name='recruiter_email_accounts_api'),
    path('oauth/gmail/start/', RecruiterGmailOAuthStartView.as_view(), name='recruiter_gmail_oauth_start'),
    path('oauth/gmail/callback/', RecruiterGmailOAuthCallbackView.as_view(), name='recruiter_gmail_oauth_callback'),
]
