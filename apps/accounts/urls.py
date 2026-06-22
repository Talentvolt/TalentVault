from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import (
    RegisterView, 
    SignupView,
    UserProfileView, 
    ChangePasswordView,
    ResetPasswordRequestView,
    ResetPasswordConfirmView
)

app_name = 'accounts'

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register_api'),
    path('signup/', SignupView.as_view(), name='register'),
    path('login/', TokenObtainPairView.as_view(), name='login_api'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', UserProfileView.as_view(), name='user_profile'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('reset-password/', ResetPasswordRequestView.as_view(), name='reset_password_request'),
    path('reset-password/confirm/', ResetPasswordConfirmView.as_view(), name='reset_password_confirm'),
]
