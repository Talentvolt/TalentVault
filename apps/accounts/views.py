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
from .models import User, OTPVerification
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
import random
import time
import logging
import json

logger = logging.getLogger(__name__)


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
                    'role': CompanyMember.MemberRole.ADMIN if user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN] else CompanyMember.MemberRole.RECRUITER
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
        email = request.POST.get('email', '').strip().lower()
        
        is_limited, time_remaining = is_rate_limited(request, f"login_{email}")
        if is_limited:
            form = LoginForm(request.POST)
            form.add_error(None, f"Too many failed login attempts. Locked out for {time_remaining}s.")
            return render(request, self.template_name, {'form': form})
            
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data.get('email').strip().lower()
            password = form.cleaned_data.get('password')
            remember_me = form.cleaned_data.get('remember_me')

            user_check = User.objects.filter(email=email).first()
            user_found = bool(user_check)
            u_is_verified = user_check.is_verified if user_check else False
            u_email_verified = user_check.email_verified if user_check else False

            print(f"\n==================================================")
            print(f"[LOGIN DEBUG] DURING LOGIN:")
            print(f"[LOGIN DEBUG] Target Email: '{email}'")
            print(f"[LOGIN DEBUG] User Found in DB: {user_found}")
            print(f"[LOGIN DEBUG] user.is_verified: {u_is_verified}")
            print(f"[LOGIN DEBUG] user.email_verified: {u_email_verified}")
            print(f"==================================================\n")

            if user_check:
                if user_check.role != User.Role.CANDIDATE:
                    form.add_error(None, "This workspace is reserved for Candidates. Please use the Recruiter Portal to sign in.")
                    return render(request, self.template_name, {'form': form})

                # Check if OTP was verified for this email
                if not user_check.is_verified:
                    if OTPVerification.objects.filter(email=email, verified=True).exists():
                        complete_user_verification(user_check)
                        print(f"[LOGIN DEBUG] Fixed unverified user status for '{email}'. user.is_verified set to True!")

                if not user_check.is_verified:
                    form.add_error(None, "Please verify your email before logging in.")
                    return render(request, self.template_name, {'form': form})

            user = authenticate(request, username=email, password=password)
            if user is not None:
                if user.role == User.Role.CANDIDATE:
                    if user.is_active:
                        login(request, user)
                        if remember_me:
                            request.session.set_expiry(1209600)  # 2 weeks
                        else:
                            request.session.set_expiry(0)
                        print(f"[LOGIN DEBUG] LOGIN SUCCESSFUL for '{email}'! Redirecting to candidate dashboard...")
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
            email = form.cleaned_data['email'].strip().lower()
            phone_number = form.cleaned_data['phone_number'].strip()

            user_exists = User.objects.filter(email=email).exists()
            existing_user = User.objects.filter(email=email).first()
            existing_verified = existing_user.is_verified if existing_user else False

            print(f"\n==================================================")
            print(f"[OTP VERIFICATION DEBUG] BEFORE VERIFICATION (SIGNUP):")
            print(f"[OTP VERIFICATION DEBUG] Target Email: '{email}'")
            print(f"[OTP VERIFICATION DEBUG] User Exists in DB: {user_exists}")
            print(f"[OTP VERIFICATION DEBUG] Existing User is_verified: {existing_verified}")
            print(f"==================================================\n")

            # Clean up expired OTP records
            OTPVerification.cleanup_expired()


            from apps.accounts.services.email_service import generate_otp, send_email_otp
            otp = generate_otp()

            now = timezone.now()
            expires_at = now + timedelta(minutes=5)

            # Create or update OTPVerification record by email
            otp_record = OTPVerification.objects.filter(email=email, verified=False).order_by('-created_at').first()
            if not otp_record:
                otp_record = OTPVerification(
                    email=email,
                    phone=phone_number,
                    expires_at=expires_at,
                    attempts=0,
                    resend_count=0,
                    verified=False
                )
            else:
                otp_record.email = email
                otp_record.phone = phone_number
                otp_record.expires_at = expires_at
                otp_record.attempts = 0
                otp_record.verified = False

            otp_record.set_otp(otp)
            otp_record.save()

            # Send Email OTP via Gmail SMTP Service
            success, msg = send_email_otp(email, otp, purpose="signup")
            if not success:
                form.add_error(None, f"Email Verification Delivery Failure: {msg}. Please check your email address and try again.")
                return render(request, self.template_name, {'form': form})

            # Store pending candidate registration data in session until OTP verification succeeds
            request.session['pending_candidate_signup'] = {
                'first_name': form.cleaned_data['first_name'],
                'last_name': form.cleaned_data['last_name'],
                'email': email,
                'password': form.cleaned_data['password'],
                'phone_number': phone_number,
                'location': form.cleaned_data.get('location', ''),
                'experience': form.cleaned_data.get('experience', ''),
            }
            request.session['otp_email'] = email

            messages.info(request, "A 6-digit verification code has been sent to your email address.")
            return redirect('candidate_verify_otp')

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


def complete_user_verification(user, pending_signup=None):
    """
    Ensure user.is_verified, user.email_verified, candidate.is_verified, 
    candidate.email_verified, and allauth EmailAddress are marked True and saved to DB.
    """
    user.is_active = True
    user.is_verified = True
    user.email_verified = True

    if pending_signup:
        if pending_signup.get('first_name'):
            user.first_name = pending_signup['first_name']
        if pending_signup.get('last_name'):
            user.last_name = pending_signup['last_name']
        if pending_signup.get('phone_number'):
            user.phone_number = pending_signup['phone_number']
        if pending_signup.get('password'):
            user.set_password(pending_signup['password'])

    user.save()

    # Create or update CandidateProfile
    from apps.candidates.models import CandidateProfile
    profile, _ = CandidateProfile.objects.get_or_create(user=user)
    if pending_signup:
        profile.full_name = f"{user.first_name} {user.last_name}".strip()
        if pending_signup.get('location'):
            profile.location = pending_signup['location']
        exp_choice = pending_signup.get('experience')
        if exp_choice == 'fresher':
            profile.total_experience = 0.0
        elif exp_choice == 'experienced':
            profile.total_experience = 1.0
    profile.save()

    # Update allauth EmailAddress record if present
    try:
        from allauth.account.models import EmailAddress
        EmailAddress.objects.update_or_create(
            user=user,
            email=user.email,
            defaults={'verified': True, 'primary': True}
        )
    except Exception:
        pass

    c_is_verified = getattr(profile, 'is_verified', None)
    c_email_verified = getattr(profile, 'email_verified', None)

    print(f"\n==================================================")
    print(f"[OTP VERIFICATION DEBUG] AFTER VERIFICATION:")
    print(f"[OTP VERIFICATION DEBUG] Target Email: '{user.email}'")
    print(f"[OTP VERIFICATION DEBUG] user.is_verified: {user.is_verified}")
    print(f"[OTP VERIFICATION DEBUG] user.email_verified: {user.email_verified}")
    print(f"[OTP VERIFICATION DEBUG] candidate.is_verified: {c_is_verified}")
    print(f"[OTP VERIFICATION DEBUG] candidate.email_verified: {c_email_verified}")
    print(f"[OTP VERIFICATION DEBUG] Saved to Database: True")
    print(f"==================================================\n")

    logger.info(f"User {user.email} verified successfully. is_verified=True, email_verified=True.")
    return user, profile


# --- CANDIDATE AUTHENTICATION ---
class CandidateForgotPasswordView(View):
    template_name = 'registration/forgot_password.html'

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name)

    def post(self, request, *args, **kwargs):
        email_input = request.POST.get('email', '').strip().lower()
        if not email_input:
            return render(request, self.template_name, {'error': 'Registered email address is required.'})

        user = User.objects.filter(email=email_input, role=User.Role.CANDIDATE).first()
        if not user:
            return render(request, self.template_name, {
                'error': "No candidate account found with this email address.",
                'email': email_input
            })

        target_email = user.email

        print(f"\n==================================================")
        print(f"[OTP VERIFICATION DEBUG] BEFORE VERIFICATION (FORGOT PASSWORD):")
        print(f"[OTP VERIFICATION DEBUG] Target Email: '{target_email}'")
        print(f"[OTP VERIFICATION DEBUG] User Exists in DB: True")
        print(f"[OTP VERIFICATION DEBUG] Existing User is_verified: {user.is_verified}")
        print(f"==================================================\n")

        # Clean up expired OTPs
        OTPVerification.cleanup_expired()

        from apps.accounts.services.email_service import generate_otp, send_email_otp
        otp = generate_otp()

        now = timezone.now()
        expires_at = now + timedelta(minutes=5)

        otp_record = OTPVerification.objects.filter(email=target_email, verified=False).order_by('-created_at').first()
        if not otp_record:
            otp_record = OTPVerification(
                email=target_email,
                expires_at=expires_at,
                attempts=0,
                resend_count=0,
                verified=False
            )
        else:
            otp_record.expires_at = expires_at
            otp_record.attempts = 0
            otp_record.verified = False

        otp_record.set_otp(otp)
        otp_record.save()

        success, msg = send_email_otp(target_email, otp, purpose="reset_password")
        if not success:
            return render(request, self.template_name, {
                'error': f"Email delivery error: {msg}. Please check your email address and try again.",
                'email': email_input
            })

        # Store session flags for OTP Verification & Password Reset
        request.session['otp_email'] = target_email
        request.session['reset_password_email'] = target_email
        request.session['reset_password_user_id'] = str(user.pk)

        messages.info(request, "A 6-digit verification code has been sent to your email address.")
        return redirect('candidate_verify_otp')


class CandidateOTPVerificationView(View):
    template_name = 'registration/otp_verification.html'

    def get(self, request, *args, **kwargs):
        email = request.session.get('otp_email', '')
        pending_signup = request.session.get('pending_candidate_signup')
        reset_email = request.session.get('reset_password_email')

        if not email and not pending_signup and not reset_email:
            messages.warning(request, "No active OTP verification session found. Please sign up or request a password reset.")
            return redirect('candidate_signup')

        from apps.accounts.services.email_service import mask_email
        masked_email = mask_email(email) if email else ''

        return render(request, self.template_name, {
            'email': email,
            'masked_email': masked_email,
        })

    def post(self, request, *args, **kwargs):
        otp_entered = request.POST.get('otp', '').strip()
        email = request.session.get('otp_email', '')
        pending_signup = request.session.get('pending_candidate_signup')
        reset_email = request.session.get('reset_password_email')
        reset_user_id = request.session.get('reset_password_user_id')

        if not email:
            return render(request, self.template_name, {
                'error': "Verification session expired. Please restart signup or password reset.",
                'email': email
            })

        OTPVerification.cleanup_expired()
        otp_record = OTPVerification.objects.filter(email=email, verified=False).order_by('-created_at').first()

        if not otp_record:
            return render(request, self.template_name, {
                'error': "The OTP code entered has expired or does not exist. Please click Resend OTP.",
                'email': email
            })

        if otp_record.is_expired():
            return render(request, self.template_name, {
                'error': "The verification code has expired (5 minutes limit). Please click Resend OTP.",
                'email': email
            })

        if otp_record.attempts >= 5:
            return render(request, self.template_name, {
                'error': "Maximum verification attempts (5) exceeded. Please click Resend OTP for a new code.",
                'email': email
            })

        if not otp_record.check_otp(otp_entered):
            otp_record.attempts += 1
            otp_record.save()
            remaining = max(0, 5 - otp_record.attempts)
            return render(request, self.template_name, {
                'error': f"Invalid verification code. {remaining} attempt(s) remaining.",
                'email': email
            })

        # OTP is verified! Mark verified in OTPVerification model
        otp_record.verified = True
        otp_record.save()

        # 1. Forgot Password Reset Flow
        if reset_email and reset_user_id:
            request.session['reset_password_otp_verified'] = True
            request.session.pop('otp_email', None)
            user = User.objects.filter(pk=reset_user_id).first()
            if user:
                complete_user_verification(user)
            otp_record.delete()
            return redirect('candidate_reset_password')

        # 2. Candidate Signup Flow
        if pending_signup:
            try:
                target_email = pending_signup['email'].strip().lower()
                user = User.objects.filter(email=target_email).first()
                if not user:
                    user = User.objects.create_user(
                        email=target_email,
                        password=pending_signup['password'],
                        first_name=pending_signup['first_name'],
                        last_name=pending_signup['last_name'],
                        phone_number=pending_signup['phone_number'],
                        role=User.Role.CANDIDATE,
                        is_active=True,
                        is_verified=True
                    )

                complete_user_verification(user, pending_signup)

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
                    CompanyMember.objects.get_or_create(
                        company=company,
                        user=user,
                        defaults={'designation': 'Staff', 'role': CompanyMember.MemberRole.RECRUITER}
                    )
                except Exception as company_err:
                    logger.error(f"Error associating company in signup: {company_err}")

                request.session.pop('pending_candidate_signup', None)
                request.session.pop('otp_email', None)
                otp_record.delete()

                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                messages.success(request, "Email verification successful! Welcome to TalentVault.")
                return redirect('frontend:candidate_dashboard')

            except Exception as err:
                logger.error(f"User creation error in candidate OTP verification: {err}")
                return render(request, self.template_name, {
                    'error': f"Could not complete registration: {str(err)}.",
                    'email': email
                })

        return render(request, self.template_name, {
            'error': "No active signup or password reset session found.",
            'email': email
        })


class SendEmailOTPView(View):
    def post(self, request, *args, **kwargs):
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                data = {}
        else:
            data = request.POST

        email = data.get('email') or request.session.get('otp_email')
        if not email:
            return JsonResponse({'success': False, 'message': 'Email address is required.'}, status=400)

        OTPVerification.cleanup_expired()
        from apps.accounts.services.email_service import generate_otp, send_email_otp
        otp = generate_otp()

        now = timezone.now()
        expires_at = now + timedelta(minutes=5)

        otp_record = OTPVerification.objects.filter(email=email, verified=False).order_by('-created_at').first()
        if not otp_record:
            otp_record = OTPVerification(
                email=email,
                expires_at=expires_at,
                attempts=0,
                resend_count=0,
                verified=False
            )
        else:
            otp_record.expires_at = expires_at
            otp_record.attempts = 0
            otp_record.verified = False

        otp_record.set_otp(otp)
        otp_record.save()

        success, msg = send_email_otp(email, otp)
        if success:
            request.session['otp_email'] = email
            return JsonResponse({'success': True, 'message': 'Email OTP sent successfully.'})
        else:
            return JsonResponse({'success': False, 'message': msg}, status=400)


class VerifyEmailOTPView(View):
    def post(self, request, *args, **kwargs):
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                data = {}
        else:
            data = request.POST

        otp_entered = data.get('otp', '').strip()
        email = data.get('email') or request.session.get('otp_email')

        if not email or not otp_entered:
            return JsonResponse({'success': False, 'message': 'Email address and 6-digit OTP are required.'}, status=400)

        OTPVerification.cleanup_expired()
        otp_record = OTPVerification.objects.filter(email=email, verified=False).order_by('-created_at').first()

        if not otp_record:
            return JsonResponse({'success': False, 'message': 'No active OTP verification session found or code expired.'}, status=400)

        if otp_record.is_expired():
            return JsonResponse({'success': False, 'message': 'The OTP code has expired (5 minutes limit). Please resend.'}, status=400)

        if otp_record.attempts >= 5:
            return JsonResponse({'success': False, 'message': 'Maximum verification attempts (5) exceeded. Please resend.'}, status=400)

        if not otp_record.check_otp(otp_entered):
            otp_record.attempts += 1
            otp_record.save()
            remaining = max(0, 5 - otp_record.attempts)
            return JsonResponse({'success': False, 'message': f'Invalid OTP code. {remaining} attempt(s) remaining.'}, status=400)

        otp_record.verified = True
        otp_record.save()

        reset_email = request.session.get('reset_password_email')
        reset_user_id = request.session.get('reset_password_user_id')
        if reset_email and reset_user_id:
            request.session['reset_password_otp_verified'] = True
            request.session.pop('otp_email', None)
            user = User.objects.filter(pk=reset_user_id).first()
            if user:
                complete_user_verification(user)
            otp_record.delete()
            return JsonResponse({
                'success': True,
                'message': 'Email OTP verification successful!',
                'redirect_url': reverse('candidate_reset_password')
            })

        pending_signup = request.session.get('pending_candidate_signup')
        redirect_url = reverse('frontend:candidate_dashboard')

        if pending_signup:
            try:
                target_email = pending_signup['email'].strip().lower()
                user = User.objects.filter(email=target_email).first()
                if not user:
                    user = User.objects.create_user(
                        email=target_email,
                        password=pending_signup['password'],
                        first_name=pending_signup['first_name'],
                        last_name=pending_signup['last_name'],
                        phone_number=pending_signup['phone_number'],
                        role=User.Role.CANDIDATE,
                        is_active=True,
                        is_verified=True
                    )

                complete_user_verification(user, pending_signup)

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
                    CompanyMember.objects.get_or_create(
                        company=company,
                        user=user,
                        defaults={'designation': 'Staff', 'role': CompanyMember.MemberRole.RECRUITER}
                    )
                except Exception as company_err:
                    logger.error(f"Error associating company in AJAX OTP signup: {company_err}")

                request.session.pop('pending_candidate_signup', None)
                request.session.pop('otp_email', None)
                otp_record.delete()

                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            except Exception as err:
                logger.error(f"AJAX user creation error: {err}")
                return JsonResponse({'success': False, 'message': f'Account creation failed: {str(err)}'}, status=400)

        return JsonResponse({
            'success': True,
            'message': 'Email verification successful!',
            'redirect_url': redirect_url
        })


        return JsonResponse({
            'success': True,
            'message': 'Email verification successful!',
            'redirect_url': redirect_url
        })


class ResendEmailOTPView(View):
    def post(self, request, *args, **kwargs):
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                data = {}
        else:
            data = request.POST

        email = data.get('email') or request.session.get('otp_email')
        if not email:
            return JsonResponse({'success': False, 'message': 'Email address is required to resend OTP.'}, status=400)

        OTPVerification.cleanup_expired()
        otp_record = OTPVerification.objects.filter(email=email, verified=False).order_by('-created_at').first()

        if otp_record and otp_record.resend_count >= 3:
            return JsonResponse({
                'success': False,
                'message': 'Maximum resend limit (3) reached for this verification session. Please restart session.'
            }, status=400)

        from apps.accounts.services.email_service import generate_otp, send_email_otp
        new_otp = generate_otp()
        now = timezone.now()
        expires_at = now + timedelta(minutes=5)

        purpose = "reset_password" if request.session.get('reset_password_email') else "signup"

        if not otp_record:
            otp_record = OTPVerification(
                email=email,
                expires_at=expires_at,
                attempts=0,
                resend_count=1,
                verified=False
            )
        else:
            otp_record.expires_at = expires_at
            otp_record.attempts = 0
            otp_record.resend_count += 1
            otp_record.verified = False

        otp_record.set_otp(new_otp)
        otp_record.save()

        success, msg = send_email_otp(email, new_otp, purpose=purpose)
        if success:
            request.session['otp_email'] = email
            return JsonResponse({
                'success': True,
                'message': 'A new email verification code has been sent.',
                'resend_count': otp_record.resend_count
            })
        else:
            return JsonResponse({'success': False, 'message': msg}, status=400)


class CandidateResetPasswordView(View):
    template_name = 'registration/reset_password.html'

    def get(self, request, *args, **kwargs):
        is_verified = request.session.get('reset_password_otp_verified')
        user_id = request.session.get('reset_password_user_id')

        if not is_verified or not user_id:
            messages.error(request, "Please complete Email OTP verification before setting a new password.")
            return redirect('candidate_forgot_password')

        return render(request, self.template_name, {'valid': True})

    def post(self, request, *args, **kwargs):
        is_verified = request.session.get('reset_password_otp_verified')
        user_id = request.session.get('reset_password_user_id')

        if not is_verified or not user_id:
            return redirect('candidate_forgot_password')

        try:
            user = User.objects.get(pk=user_id, role=User.Role.CANDIDATE)
        except User.DoesNotExist:
            return render(request, self.template_name, {
                'valid': False,
                'error_message': "User account not found for password reset."
            })

        password = request.POST.get('password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()

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

        request.session.pop('reset_password_otp_verified', None)
        request.session.pop('reset_password_user_id', None)
        request.session.pop('reset_password_email', None)

        return render(request, 'registration/candidate_login.html', {
            'success_message': "Password updated successfully! Please sign in with your new password.",
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
            email = "candidate.github@talent-vault.in"
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
            email = "candidate.linkedin@talent-vault.in"
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
