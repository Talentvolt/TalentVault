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

from django.views import View
from django.views.generic import CreateView
from django.urls import reverse_lazy
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django import forms
from .models import User

class LoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={
        'class': 'form-control',
        'placeholder': 'name@company.com',
        'autocomplete': 'email',
    }))
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'form-control',
        'placeholder': '••••••••',
        'autocomplete': 'current-password',
    }))
    remember_me = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={
        'class': 'form-check-input',
    }))

class SignupForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'First Name'
    }))
    last_name = forms.CharField(max_length=30, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Last Name'
    }))
    email = forms.EmailField(widget=forms.EmailInput(attrs={
        'class': 'form-control',
        'placeholder': 'name@company.com'
    }))
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'form-control',
        'placeholder': '••••••••'
    }))
    role = forms.ChoiceField(choices=User.Role.choices, widget=forms.Select(attrs={
        'class': 'form-select'
    }), initial=User.Role.RECRUITER)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'role', 'password']

class CustomLoginView(View):
    template_name = 'registration/login.html'

    @method_decorator(never_cache)
    @method_decorator(csrf_protect)
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('frontend:dashboard')
        form = LoginForm()
        return render(request, self.template_name, {'form': form})

    @method_decorator(never_cache)
    @method_decorator(csrf_protect)
    def post(self, request, *args, **kwargs):
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data.get('email')
            password = form.cleaned_data.get('password')
            remember_me = form.cleaned_data.get('remember_me')

            # Authenticate the user
            user = authenticate(request, username=email, password=password)
            if user is not None:
                if user.is_active:
                    login(request, user)
                    
                    # Apply remember me logic (set session expiry to 2 weeks or 0 if not checked)
                    if remember_me:
                        request.session.set_expiry(1209600)  # 2 weeks
                    else:
                        request.session.set_expiry(0)  # Browser close
                        
                    return redirect('frontend:dashboard')
                else:
                    form.add_error(None, "This account is disabled.")
            else:
                form.add_error(None, "Invalid email or password.")
        
        return render(request, self.template_name, {'form': form})

class CustomLogoutView(View):
    def get(self, request, *args, **kwargs):
        logout(request)
        return redirect('account_login')

    def post(self, request, *args, **kwargs):
        logout(request)
        return redirect('account_login')

class SignupView(CreateView):
    model = User
    form_class = SignupForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('frontend:dashboard')

    def form_valid(self, form):
        user = form.save(commit=False)
        user.set_password(form.cleaned_data['password'])
        user.is_active = True
        user.is_verified = True
        user.save()
        
        # Ensure default company association exists for dashboard integrity
        from apps.companies.models import Company, CompanyMember
        try:
            company, _ = Company.objects.get_or_create(
                name="TalentVault Technologies",
                defaults={
                    'slug': 'talentvault-technologies',
                    'industry': 'Software Product',
                    'description': 'Default organization created during user signup.',
                    'location': 'Remote'
                }
            )
            # Associate user to this company
            CompanyMember.objects.get_or_create(
                company=company,
                user=user,
                defaults={
                    'designation': 'Recruiter' if user.role == User.Role.RECRUITER else 'Staff',
                    'role': CompanyMember.MemberRole.ADMIN if user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN] else CompanyMember.MemberRole.MEMBER
                }
            )
        except Exception as company_err:
            print(f"Error associating company in signup: {company_err}")
            
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
