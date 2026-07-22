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
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
import random
import time

def redirect_role_dashboard(user):
    role = user.role
    if role == User.Role.SUPER_ADMIN:
        return redirect('frontend:admin_dashboard')
    elif role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN]:
        return redirect('frontend:recruiter_dashboard')
    elif role == User.Role.CANDIDATE:
        return redirect('frontend:candidate_dashboard')
    return redirect('frontend:dashboard')

def is_rate_limited(request, key, max_attempts=5, period=300):
    attempts_key = f"attempts_{key}"
    lockout_key = f"lockout_{key}"
    
    now = time.time()
    lockout_time = request.session.get(lockout_key, 0)
    if now < lockout_time:
        return True, int(lockout_time - now)
        
    attempts = request.session.get(attempts_key, [])
    attempts = [t for t in attempts if now - t < period]
    
    if len(attempts) >= max_attempts:
        request.session[lockout_key] = now + 60
        request.session[attempts_key] = []
        return True, 60
        
    attempts.append(now)
    request.session[attempts_key] = attempts
    return False, 0

def generate_otp():
    return str(random.randint(100000, 999999))

def send_verification_email(user, request):
    otp = generate_otp()
    request.session['verification_otp'] = otp
    request.session['verification_email'] = user.email
    
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    verification_url = request.build_absolute_uri(
        reverse('candidate_verify_email') + f'?uidb64={uid}&token={token}'
    )
    
    subject = "Verify Your TalentVault.ai Account"
    message = f"Hi {user.first_name},\n\nThank you for registering at TalentVault.ai!\n\nTo verify your email address, please click the secure link below:\n{verification_url}\n\nAlternatively, you can manually enter this 6-digit verification code:\n{otp}\n\nBest regards,\nThe TalentVault Team"
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=True
    )

def send_welcome_email(user):
    subject = "Welcome to TalentVault.ai!"
    message = f"Hi {user.first_name},\n\nWelcome to TalentVault.ai! Your account has been verified, and you can now log in.\n\nComplete your profile to let our AI Match engine connect you with tailored opportunities.\n\nBest regards,\nThe TalentVault Team"
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=True
    )

def send_password_reset_email(user, request):
    otp = generate_otp()
    request.session['reset_otp_code'] = otp
    request.session['reset_otp_email'] = user.email
    
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    reset_url = request.build_absolute_uri(
        reverse('candidate_reset_password') + f'?uidb64={uid}&token={token}'
    )
    
    subject = "Reset Your TalentVault.ai Password"
    message = f"Hi {user.first_name},\n\nWe received a request to reset your password.\n\nClick the link below to create a new password:\n{reset_url}\n\nAlternatively, you can enter the following 6-digit OTP code to verify:\n{otp}\n\nIf you didn't request a password reset, you can safely ignore this email.\n\nBest regards,\nThe TalentVault Team"
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=True
    )

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
    first_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'First Name'
    }))
    last_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={
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
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'form-control',
        'placeholder': '••••••••'
    }), required=True)
    role = forms.ChoiceField(choices=User.Role.choices, widget=forms.Select(attrs={
        'class': 'form-select'
    }), initial=User.Role.CANDIDATE)
    
    # Extra fields for candidate registration
    phone_number = forms.CharField(max_length=15, required=True)
    experience = forms.CharField(max_length=20, required=False)
    location = forms.CharField(max_length=100, required=True)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'role', 'password', 'phone_number']

    def clean_first_name(self):
        first_name = self.cleaned_data.get('first_name')
        if not first_name or not first_name.strip():
            raise forms.ValidationError("First name is required.")
        return first_name.strip()

    def clean_last_name(self):
        last_name = self.cleaned_data.get('last_name')
        if not last_name or not last_name.strip():
            raise forms.ValidationError("Last name is required.")
        return last_name.strip()

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not email:
            raise forms.ValidationError("Email is required.")
        email = email.lower().strip()
        
        # Check disposable domain
        disposable_domains = [
            'mailinator.com', 'tempmail.com', '10minutemail.com', 'guerrillamail.com',
            'yopmail.com', 'trashmail.com', 'throwawaymail.com', 'temp-mail.org',
            'dispostable.com', 'mailinator2.com', 'tempmail.net', 'guerrillamailblock.com',
            'yopmail.fr', 'yopmail.net'
        ]
        domain = email.split('@')[-1] if '@' in email else ''
        if domain in disposable_domains or any(disposable in domain for disposable in ['tempmail', 'mailinator', '10minutemail', 'guerrillamail', 'yopmail', 'trashmail', 'throwawaymail']):
            raise forms.ValidationError("Disposable or fake email addresses are not permitted. Please use a real email provider.")
            
        # Duplicate email check
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
            
        return email

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')
        if not phone_number:
            raise forms.ValidationError("Phone number is required.")
        phone_number = phone_number.strip()
        
        # Format/length validation
        digits_only = ''.join(c for c in phone_number if c.isdigit())
        if len(digits_only) < 10 or len(digits_only) > 15:
            raise forms.ValidationError("Please enter a valid phone number (10 to 15 digits).")
            
        # Duplicate phone check
        if User.objects.filter(phone_number=phone_number).exists():
            raise forms.ValidationError("An account with this phone number already exists.")
            
        return phone_number

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if not password:
            raise forms.ValidationError("Password is required.")
        if len(password) < 8:
            raise forms.ValidationError("Password must be at least 8 characters long.")
        if not any(c.isupper() for c in password):
            raise forms.ValidationError("Password must contain at least one uppercase letter.")
        if not any(c.islower() for c in password):
            raise forms.ValidationError("Password must contain at least one lowercase letter.")
        if not any(c.isdigit() for c in password):
            raise forms.ValidationError("Password must contain at least one number.")
        if not any(c in "!@#$%^&*()-_=+[]{}|;:',.<>?/`~" for c in password):
            raise forms.ValidationError("Password must contain at least one special character.")
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match.")
        return cleaned_data

class CustomLoginView(View):
    template_name = 'registration/login.html'

    @method_decorator(never_cache)
    @method_decorator(csrf_protect)
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect_role_dashboard(request.user)
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
                        
                    return redirect_role_dashboard(request.user)
                else:
                    form.add_error(None, "This account is disabled.")
            else:
                form.add_error(None, "Invalid email or password.")
        
        return render(request, self.template_name, {'form': form})

class CustomLogoutView(View):
    def get(self, request, *args, **kwargs):
        role = request.user.role if request.user.is_authenticated else None
        logout(request)
        if role == User.Role.CANDIDATE:
            return redirect('candidate_login')
        elif role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN, User.Role.SUPER_ADMIN]:
            return redirect('employer_login')
        return redirect('candidate_login')

    def post(self, request, *args, **kwargs):
        role = request.user.role if request.user.is_authenticated else None
        logout(request)
        if role == User.Role.CANDIDATE:
            return redirect('candidate_login')
        elif role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN, User.Role.SUPER_ADMIN]:
            return redirect('employer_login')
        return redirect('candidate_login')

class SignupView(CreateView):
    model = User
    form_class = SignupForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('frontend:dashboard')

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            logout(request)
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save(commit=False)
        user.set_password(form.cleaned_data['password'])
        user.is_active = True
        user.is_verified = True
        user.save()
        
        # If user is a Candidate, create and populate CandidateProfile
        if user.role == User.Role.CANDIDATE:
            from apps.candidates.models import CandidateProfile
            profile, _ = CandidateProfile.objects.get_or_create(user=user)
            profile.full_name = f"{user.first_name} {user.last_name}".strip()
            if form.cleaned_data.get('location'):
                profile.location = form.cleaned_data['location']
            exp_choice = form.cleaned_data.get('experience')
            if exp_choice == 'fresher':
                profile.total_experience = 0.0
            elif exp_choice == 'experienced':
                profile.total_experience = 1.0
            profile.save()
        
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
            
        from django.contrib import messages
        messages.success(self.request, "Account created successfully! Please log in.")
        return redirect('account_login')

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


# --- CUSTOM AUTHENTICATION VIEWS & FORMS ---

class EmployerLoginForm(forms.Form):
    email = forms.EmailField(
        label="Official Work Email",
        widget=forms.EmailInput(attrs={
            'class': 'form-control-custom',
            'placeholder': 'official@company.com',
            'autocomplete': 'email',
        })
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control-custom',
            'placeholder': '••••••••',
            'autocomplete': 'current-password',
        })
    )
    remember_me = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
        })
    )


class EmployerSignupForm(forms.ModelForm):
    email = forms.EmailField(required=True)
    password = forms.CharField(widget=forms.PasswordInput(), required=True)
    phone_number = forms.CharField(max_length=15, required=True)
    
    # Employer specific fields
    org_name = forms.CharField(max_length=255, required=True)
    hiring_type = forms.ChoiceField(
        choices=[('organization', 'Organization'), ('independent', 'Independent Recruiter')],
        initial='organization',
        required=True
    )
    website = forms.URLField(required=False)
    company_size = forms.CharField(max_length=50, required=False)
    industry = forms.CharField(max_length=100, required=False)

    class Meta:
        model = User
        fields = ['email', 'password', 'phone_number']


class LoginSelectView(View):
    template_name = 'registration/login_select.html'

    @method_decorator(never_cache)
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect_role_dashboard(request.user)
        return render(request, self.template_name)


class SignupSelectView(View):
    template_name = 'registration/signup_select.html'

    @method_decorator(never_cache)
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            logout(request)
        return render(request, self.template_name)


class CandidateLoginView(View):
    template_name = 'registration/candidate_login.html'

    @method_decorator(never_cache)
    @method_decorator(csrf_protect)
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if request.user.role == User.Role.CANDIDATE:
                return redirect('frontend:candidate_dashboard')
            else:
                return redirect('frontend:recruiter_dashboard')
        form = LoginForm()
        return render(request, self.template_name, {'form': form})

    @method_decorator(never_cache)
    @method_decorator(csrf_protect)
    def post(self, request, *args, **kwargs):
        email = request.POST.get('email', '').strip()
        
        is_limited, time_remaining = is_rate_limited(request, f"login_{email}")
        if is_limited:
            form = LoginForm(request.POST)
            form.add_error(None, f"Too many failed login attempts. Locked out for {time_remaining}s.")
            return render(request, self.template_name, {'form': form})
            
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data.get('email')
            password = form.cleaned_data.get('password')
            remember_me = form.cleaned_data.get('remember_me')

            try:
                user_check = User.objects.get(email=email)
                if user_check.role != User.Role.CANDIDATE:
                    form.add_error(None, "This workspace is reserved for Candidates. Please use the Recruiter Portal to sign in.")
                    return render(request, self.template_name, {'form': form})
                if not user_check.is_verified:
                    form.add_error(None, "Please verify your email before logging in.")
                    return render(request, self.template_name, {'form': form})
            except User.DoesNotExist:
                pass

            user = authenticate(request, username=email, password=password)
            if user is not None:
                if user.role == User.Role.CANDIDATE:
                    if user.is_active:
                        login(request, user)
                        if remember_me:
                            request.session.set_expiry(1209600)  # 2 weeks
                        else:
                            request.session.set_expiry(0)
                        return redirect('frontend:candidate_dashboard')
                    else:
                        form.add_error(None, "This account is disabled.")
                else:
                    form.add_error(None, "This workspace is reserved for Candidates.")
            else:
                form.add_error(None, "Invalid email or password.")
        
        return render(request, self.template_name, {'form': form})


class CandidateSignupView(View):
    template_name = 'registration/signup.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            logout(request)
        form = SignupForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request, *args, **kwargs):
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.role = User.Role.CANDIDATE
            user.is_active = False
            user.is_verified = False
            user.save()
            
            from apps.candidates.models import CandidateProfile
            profile, _ = CandidateProfile.objects.get_or_create(user=user)
            profile.full_name = f"{user.first_name} {user.last_name}".strip()
            if form.cleaned_data.get('location'):
                profile.location = form.cleaned_data['location']
            exp_choice = form.cleaned_data.get('experience')
            if exp_choice == 'fresher':
                profile.total_experience = 0.0
            elif exp_choice == 'experienced':
                profile.total_experience = 1.0
            profile.save()
            
            send_verification_email(user, request)
            return redirect('candidate_verify_email')
            
        return render(request, self.template_name, {'form': form})


class EmployerLoginView(View):
    template_name = 'registration/employer_login.html'

    @method_decorator(never_cache)
    @method_decorator(csrf_protect)
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if request.user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN, User.Role.SUPER_ADMIN]:
                return redirect('frontend:recruiter_dashboard')
            else:
                return redirect('frontend:candidate_dashboard')
        form = EmployerLoginForm()
        return render(request, self.template_name, {'form': form})

    @method_decorator(never_cache)
    @method_decorator(csrf_protect)
    def post(self, request, *args, **kwargs):
        form = EmployerLoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data.get('email')
            password = form.cleaned_data.get('password')
            remember_me = form.cleaned_data.get('remember_me')

            try:
                user_check = User.objects.get(email=email)
                if user_check.role == User.Role.CANDIDATE:
                    form.add_error(None, "This workspace is reserved for Recruiters/Employers. Please use the Candidate Portal to sign in.")
                    return render(request, self.template_name, {'form': form})
            except User.DoesNotExist:
                pass

            user = authenticate(request, username=email, password=password)
            if user is not None:
                if user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN, User.Role.SUPER_ADMIN]:
                    if user.is_active:
                        login(request, user)
                        if remember_me:
                            request.session.set_expiry(1209600)  # 2 weeks
                        else:
                            request.session.set_expiry(0)
                        return redirect('frontend:recruiter_dashboard')
                    else:
                        form.add_error(None, "This account is disabled.")
                else:
                    form.add_error(None, "This workspace is reserved for Recruiters/Employers.")
            else:
                form.add_error(None, "Invalid email or password.")

        return render(request, self.template_name, {'form': form})


class EmployerSignupView(View):
    template_name = 'registration/employer_signup.html'

    def get(self, request, *args, **kwargs):
        form = EmployerSignupForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request, *args, **kwargs):
        form = EmployerSignupForm(request.POST)
        return render(request, self.template_name, {'form': form})


class AdminLoginView(View):
    template_name = 'registration/admin_login.html'

    @method_decorator(never_cache)
    @method_decorator(csrf_protect)
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect_role_dashboard(request.user)
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

            user = authenticate(request, username=email, password=password)
            if user is not None:
                if user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN, User.Role.SUPER_ADMIN]:
                    if user.is_active:
                        login(request, user)
                        if remember_me:
                            request.session.set_expiry(1209600)  # 2 weeks
                        else:
                            request.session.set_expiry(0)
                        return redirect('frontend:recruiter_dashboard')
                    else:
                        form.add_error(None, "This account is disabled.")
                else:
                    form.add_error(None, "This workspace is reserved for Recruiters/Employers.")
            else:
                form.add_error(None, "Invalid email or password.")
        
        return render(request, self.template_name, {'form': form})


# --- CANDIDATE AUTHENTICATION & OAUTH FLOW VIEWS ---
import urllib.parse
import requests

class CandidateForgotPasswordView(View):
    template_name = 'registration/forgot_password.html'

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name)

    def post(self, request, *args, **kwargs):
        email = request.POST.get('email', '').strip().lower()
        if not email:
            return render(request, self.template_name, {'error': 'Email address is required.'})
            
        try:
            user = User.objects.get(email=email, role=User.Role.CANDIDATE)
            send_password_reset_email(user, request)
            return render(request, self.template_name, {
                'success': True,
                'email': email
            })
        except User.DoesNotExist:
            return render(request, self.template_name, {
                'error': "No candidate account found with this email address."
            })


class CandidateEmailVerificationView(View):
    template_name = 'registration/email_verification.html'

    def get(self, request, *args, **kwargs):
        uidb64 = request.GET.get('uidb64')
        token = request.GET.get('token')
        
        if uidb64 and token:
            try:
                uid = force_str(urlsafe_base64_decode(uidb64))
                user = User.objects.get(pk=uid)
                if default_token_generator.check_token(user, token):
                    user.is_verified = True
                    user.is_active = True
                    user.save()
                    send_welcome_email(user)
                    return render(request, self.template_name, {
                        'success': True,
                        'message': "Your email has been successfully verified! You can now log in."
                    })
                else:
                    return render(request, self.template_name, {
                        'success': False,
                        'message': "The verification link is invalid or has expired."
                    })
            except (TypeError, ValueError, OverflowError, User.DoesNotExist):
                return render(request, self.template_name, {
                    'success': False,
                    'message': "The verification link is invalid."
                })
        
        return render(request, self.template_name, {
            'success': None
        })


class CandidateOTPVerificationView(View):
    template_name = 'registration/otp_verification.html'

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name)

    def post(self, request, *args, **kwargs):
        otp_entered = request.POST.get('otp', '').strip()
        
        reset_otp = request.session.get('reset_otp_code')
        reset_email = request.session.get('reset_otp_email')
        
        verify_otp = request.session.get('verification_otp')
        verify_email = request.session.get('verification_email')
        
        if reset_otp and otp_entered == reset_otp:
            request.session['otp_verified_reset_email'] = reset_email
            request.session.pop('reset_otp_code', None)
            return redirect('candidate_reset_password')
            
        elif verify_otp and otp_entered == verify_otp:
            try:
                user = User.objects.get(email=verify_email)
                user.is_verified = True
                user.is_active = True
                user.save()
                send_welcome_email(user)
                
                request.session.pop('verification_otp', None)
                request.session.pop('verification_email', None)
                
                return render(request, 'registration/email_verification.html', {
                    'success': True,
                    'message': "Your email has been successfully verified via OTP! You can now log in."
                })
            except User.DoesNotExist:
                pass
                
        return render(request, self.template_name, {
            'error': "The OTP code entered is incorrect or expired. Please check your email and try again."
        })


class CandidateResetPasswordView(View):
    template_name = 'registration/reset_password.html'

    def get(self, request, *args, **kwargs):
        uidb64 = request.GET.get('uidb64')
        token = request.GET.get('token')
        
        if uidb64 and token:
            try:
                uid = force_str(urlsafe_base64_decode(uidb64))
                user = User.objects.get(pk=uid)
                if default_token_generator.check_token(user, token):
                    return render(request, self.template_name, {
                        'uidb64': uidb64,
                        'token': token,
                        'valid': True
                    })
                else:
                    return render(request, self.template_name, {
                        'valid': False,
                        'error_message': "The password reset link is invalid or has expired."
                    })
            except (TypeError, ValueError, OverflowError, User.DoesNotExist):
                return render(request, self.template_name, {
                    'valid': False,
                    'error_message': "The password reset link is invalid."
                })
                
        reset_email = request.session.get('otp_verified_reset_email')
        if reset_email:
            return render(request, self.template_name, {
                'valid': True
            })
            
        return redirect('candidate_forgot_password')

    def post(self, request, *args, **kwargs):
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        
        uidb64 = request.POST.get('uidb64')
        token = request.POST.get('token')
        
        user = None
        
        if uidb64 and token:
            try:
                uid = force_str(urlsafe_base64_decode(uidb64))
                user = User.objects.get(pk=uid)
                if not default_token_generator.check_token(user, token):
                    user = None
            except Exception:
                pass
        else:
            reset_email = request.session.get('otp_verified_reset_email')
            if reset_email:
                try:
                    user = User.objects.get(email=reset_email)
                except User.DoesNotExist:
                    pass
                    
        if not user:
            return render(request, self.template_name, {
                'valid': False,
                'error_message': "Invalid authorization. Please request a new password reset link."
            })
            
        if not password or len(password) < 8:
            return render(request, self.template_name, {'valid': True, 'error_message': "Password must be at least 8 characters long."})
        if not any(c.isupper() for c in password):
            return render(request, self.template_name, {'valid': True, 'error_message': "Password must contain at least one uppercase letter."})
        if not any(c.islower() for c in password):
            return render(request, self.template_name, {'valid': True, 'error_message': "Password must contain at least one lowercase letter."})
        if not any(c.isdigit() for c in password):
            return render(request, self.template_name, {'valid': True, 'error_message': "Password must contain at least one number."})
        if not any(c in "!@#$%^&*()-_=+[]{}|;:',.<>?/`~" for c in password):
            return render(request, self.template_name, {'valid': True, 'error_message': "Password must contain at least one special character."})
            
        if password != confirm_password:
            return render(request, self.template_name, {
                'valid': True,
                'error_message': "Passwords do not match."
            })
            
        user.set_password(password)
        user.save()
        
        request.session.pop('otp_verified_reset_email', None)
        
        return render(request, 'registration/candidate_login.html', {
            'success_message': "Password reset successful! You can now sign in with your new password.",
            'form': LoginForm()
        })


from allauth.socialaccount.providers.google.views import (
    oauth2_login as google_allauth_login,
    oauth2_callback as google_allauth_callback,
)

class GoogleLoginRedirectView(View):
    def get(self, request, *args, **kwargs):
        return google_allauth_login(request, *args, **kwargs)


class GoogleLoginCallbackView(View):
    def get(self, request, *args, **kwargs):
        return google_allauth_callback(request, *args, **kwargs)


class GitHubLoginRedirectView(View):
    def get(self, request, *args, **kwargs):
        client_id = getattr(settings, 'GITHUB_CLIENT_ID', None)
        if not client_id:
            # Fallback to auto-created candidate for localhost testing
            email = "candidate.github@talentvault.ai"
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': "GitHub",
                    'last_name': "User",
                    'role': User.Role.CANDIDATE,
                    'is_verified': True,
                    'is_active': True,
                    'profile_picture': "https://ui-avatars.com/api/?name=GitHub+User&background=24292e&color=fff"
                }
            )
            if created:
                from apps.candidates.models import CandidateProfile
                CandidateProfile.objects.get_or_create(user=user, defaults={'full_name': "GitHub User", 'location': "Mumbai, India"})
            login(request, user)
            return redirect('frontend:candidate_dashboard')

        redirect_uri = request.build_absolute_uri(reverse('github_login_callback'))
        params = {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'scope': 'user:email',
            'state': 'github-oauth-state'
        }
        url = "https://github.com/login/oauth/authorize?" + urllib.parse.urlencode(params)
        return redirect(url)


class GitHubLoginCallbackView(View):
    def get(self, request, *args, **kwargs):
        code = request.GET.get('code')
        if not code:
            return redirect('candidate_login')
            
        client_id = getattr(settings, 'GITHUB_CLIENT_ID', None)
        client_secret = getattr(settings, 'GITHUB_CLIENT_SECRET', None)
        
        token_url = "https://github.com/login/oauth/access_token"
        headers = {'Accept': 'application/json'}
        data = {
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code
        }
        r = requests.post(token_url, headers=headers, data=data)
        if r.status_code != 200:
            return render(request, 'registration/candidate_login.html', {'error_message': 'Failed to authenticate with GitHub.', 'form': LoginForm()})
            
        tokens = r.json()
        access_token = tokens.get('access_token')
        
        profile_url = "https://api.github.com/user"
        headers = {'Authorization': f'token {access_token}'}
        profile_r = requests.get(profile_url, headers=headers)
        if profile_r.status_code != 200:
            return render(request, 'registration/candidate_login.html', {'error_message': 'Failed to fetch GitHub profile.', 'form': LoginForm()})
            
        profile = profile_r.json()
        username = profile.get('login')
        email = profile.get('email')
        name = profile.get('name') or username
        avatar_url = profile.get('avatar_url')
        
        if not email:
            email_url = "https://api.github.com/user/emails"
            email_r = requests.get(email_url, headers=headers)
            if email_r.status_code == 200:
                emails = email_r.json()
                primary_emails = [e for e in emails if e.get('primary')]
                if primary_emails:
                    email = primary_emails[0].get('email')
                elif emails:
                    email = emails[0].get('email')
                    
        if not email:
            email = f"{username}@github-oauth.demo"
            
        first_name = name.split(' ')[0] if ' ' in name else name
        last_name = name.split(' ')[1] if ' ' in name else ''
        
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'first_name': first_name,
                'last_name': last_name,
                'role': User.Role.CANDIDATE,
                'is_verified': True,
                'is_active': True,
                'profile_picture': avatar_url
            }
        )
        if created:
            from apps.candidates.models import CandidateProfile
            CandidateProfile.objects.get_or_create(user=user, defaults={'full_name': name, 'location': "Mumbai, India"})
            
        login(request, user)
        return redirect('frontend:candidate_dashboard')


class LinkedInLoginRedirectView(View):
    def get(self, request, *args, **kwargs):
        client_id = getattr(settings, 'LINKEDIN_CLIENT_ID', None)
        if not client_id:
            # Fallback to auto-created candidate for localhost testing
            email = "candidate.linkedin@talentvault.ai"
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': "LinkedIn",
                    'last_name': "User",
                    'role': User.Role.CANDIDATE,
                    'is_verified': True,
                    'is_active': True,
                    'profile_picture': "https://ui-avatars.com/api/?name=LinkedIn+User&background=0A66C2&color=fff"
                }
            )
            if created:
                from apps.candidates.models import CandidateProfile
                CandidateProfile.objects.get_or_create(user=user, defaults={'full_name': "LinkedIn User", 'location': "Delhi, India"})
            login(request, user)
            return redirect('frontend:candidate_dashboard')

        redirect_uri = request.build_absolute_uri(reverse('linkedin_login_callback'))
        params = {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': 'r_liteprofile r_emailaddress',
            'state': 'linkedin-oauth-state'
        }
        url = "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode(params)
        return redirect(url)


class LinkedInLoginCallbackView(View):
    def get(self, request, *args, **kwargs):
        code = request.GET.get('code')
        if not code:
            return redirect('candidate_login')
            
        client_id = getattr(settings, 'LINKEDIN_CLIENT_ID', None)
        client_secret = getattr(settings, 'LINKEDIN_CLIENT_SECRET', None)
        redirect_uri = request.build_absolute_uri(reverse('linkedin_login_callback'))
        
        token_url = "https://www.linkedin.com/oauth/v2/accessToken"
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'client_id': client_id,
            'client_secret': client_secret
        }
        r = requests.post(token_url, data=data)
        if r.status_code != 200:
            return render(request, 'registration/candidate_login.html', {'error_message': 'Failed to authenticate with LinkedIn.', 'form': LoginForm()})
            
        tokens = r.json()
        access_token = tokens.get('access_token')
        
        profile_url = "https://api.linkedin.com/v2/me"
        headers = {'Authorization': f'Bearer {access_token}'}
        profile_r = requests.get(profile_url, headers=headers)
        
        email_url = "https://api.linkedin.com/v2/emailAddress?q=members&projection=(elements*(handle~))"
        email_r = requests.get(email_url, headers=headers)
        
        email = None
        if email_r.status_code == 200:
            email_data = email_r.json()
            try:
                email = email_data['elements'][0]['handle~']['emailAddress']
            except Exception:
                pass
                
        first_name = "LinkedIn"
        last_name = "User"
        if profile_r.status_code == 200:
            profile_data = profile_r.json()
            first_name = profile_data.get('localizedFirstName', 'LinkedIn')
            last_name = profile_data.get('localizedLastName', 'User')
            
        if not email:
            email = f"linkedin-{profile_data.get('id', 'user')}@linkedin-oauth.demo"
            
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'first_name': first_name,
                'last_name': last_name,
                'role': User.Role.CANDIDATE,
                'is_verified': True,
                'is_active': True,
                'profile_picture': "https://ui-avatars.com/api/?name=LinkedIn+User&background=0A66C2&color=fff"
            }
        )
        if created:
            from apps.candidates.models import CandidateProfile
            CandidateProfile.objects.get_or_create(user=user, defaults={'full_name': f"{first_name} {last_name}".strip(), 'location': "Delhi, India"})
            
        login(request, user)
        return redirect('frontend:candidate_dashboard')
