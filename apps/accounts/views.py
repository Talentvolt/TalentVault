from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model
from utils.throttling import AuthRateThrottle
from .serializers import (
    RegisterSerializer, 
    UserSerializer, 
    ChangePasswordSerializer,
    ResetPasswordRequestSerializer,
    ResetPasswordConfirmSerializer
)

User = get_user_model()

from django.views.generic import CreateView
from django.urls import reverse_lazy
from django.contrib.auth import login
from .models import User
from django import forms

class SignupForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'role', 'password']

class SignupView(CreateView):
    model = User
    form_class = SignupForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('frontend:dashboard')

    def form_valid(self, form):
        user = form.save(commit=False)
        user.set_password(form.cleaned_data['password'])
        user.save()
        login(self.request, user)
        return super().form_valid(form)

class RegisterView(generics.CreateAPIView):
    """
    Register a new user (Candidate, Recruiter, or Company Admin).
    """
    queryset = User.objects.all()
    permission_classes = (permissions.AllowAny,)
    serializer_class = RegisterSerializer
    throttle_classes = [AuthRateThrottle]

class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    Get or update the current authenticated user's profile.
    """
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

class ChangePasswordView(generics.UpdateAPIView):
    """
    Change password for the authenticated user.
    """
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = ChangePasswordSerializer

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        
        if not user.check_password(serializer.validated_data.get("old_password")):
            return Response({"old_password": ["Wrong password."]}, status=status.HTTP_400_BAD_REQUEST)
            
        user.set_password(serializer.validated_data.get("new_password"))
        user.save()
        return Response({"detail": "Password updated successfully."}, status=status.HTTP_200_OK)

class ResetPasswordRequestView(generics.GenericAPIView):
    """
    Request a password reset email.
    """
    permission_classes = (permissions.AllowAny,)
    serializer_class = ResetPasswordRequestSerializer
    throttle_classes = [AuthRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # TODO: Implement token generation and email sending logic here
        return Response({"detail": "If an account with this email exists, a password reset link has been sent."}, status=status.HTTP_200_OK)

class ResetPasswordConfirmView(generics.GenericAPIView):
    """
    Confirm password reset via token.
    """
    permission_classes = (permissions.AllowAny,)
    serializer_class = ResetPasswordConfirmSerializer
    throttle_classes = [AuthRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # TODO: Implement token verification and password reset logic here
        return Response({"detail": "Password has been reset successfully."}, status=status.HTTP_200_OK)
