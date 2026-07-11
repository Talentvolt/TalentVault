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
    first_name = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'First Name'
    }))
    last_name = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={
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
    
    # Extra fields for candidate registration
    phone_number = forms.CharField(max_length=15, required=False)
    experience = forms.CharField(max_length=20, required=False)
    location = forms.CharField(max_length=100, required=False)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'role', 'password', 'phone_number']

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


class CandidateLoginView(View):
    template_name = 'registration/candidate_login.html'

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

            user = authenticate(request, username=email, password=password)
            if user is not None:
                if user.role == User.Role.CANDIDATE:
                    if user.is_active:
                        login(request, user)
                        if remember_me:
                            request.session.set_expiry(1209600)  # 2 weeks
                        else:
                            request.session.set_expiry(0)
                        return redirect('frontend:dashboard')
                    else:
                        form.add_error(None, "This account is disabled.")
                else:
                    form.add_error(None, "This workspace is reserved for Candidates.")
            else:
                form.add_error(None, "Invalid email or password.")
        
        return render(request, self.template_name, {'form': form})


class CandidateSignupView(CreateView):
    model = User
    form_class = SignupForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('frontend:dashboard')

    def form_valid(self, form):
        user = form.save(commit=False)
        user.set_password(form.cleaned_data['password'])
        user.role = User.Role.CANDIDATE
        user.is_active = True
        user.is_verified = True
        user.save()
        
        # Create and populate CandidateProfile
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
        
        login(self.request, user)
        return super().form_valid(form)


class EmployerLoginView(View):
    template_name = 'registration/employer_login.html'

    @method_decorator(never_cache)
    @method_decorator(csrf_protect)
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('frontend:dashboard')
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

            user = authenticate(request, username=email, password=password)
            if user is not None:
                if user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN]:
                    if user.is_active:
                        login(request, user)
                        if remember_me:
                            request.session.set_expiry(1209600)  # 2 weeks
                        else:
                            request.session.set_expiry(0)
                        return redirect('frontend:dashboard')
                    else:
                        form.add_error(None, "This account is disabled.")
                else:
                    form.add_error(None, "This workspace is reserved for Employers.")
            else:
                form.add_error(None, "Invalid email or password.")
        
        return render(request, self.template_name, {'form': form})


class EmployerSignupView(CreateView):
    model = User
    form_class = EmployerSignupForm
    template_name = 'registration/employer_signup.html'
    success_url = reverse_lazy('frontend:dashboard')

    def form_valid(self, form):
        user = form.save(commit=False)
        user.set_password(form.cleaned_data['password'])
        user.role = User.Role.RECRUITER
        user.is_active = True
        user.is_verified = True
        user.save()
        
        # Create and associate Company
        from apps.companies.models import Company, CompanyMember
        from django.utils.text import slugify
        import uuid
        
        org_name = form.cleaned_data['org_name']
        hiring_type = form.cleaned_data['hiring_type']
        website = form.cleaned_data.get('website')
        company_size = form.cleaned_data.get('company_size')
        industry = form.cleaned_data.get('industry') or "Hiring"
        
        if hiring_type == 'independent':
            company_name = f"Independent Recruiter - {user.email}"
        else:
            company_name = org_name
            
        slug = slugify(company_name)
        if not slug:
            slug = str(uuid.uuid4())[:8]
            
        # Handle unique slug collision
        base_slug = slug
        counter = 1
        while Company.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
            
        try:
            company, created = Company.objects.get_or_create(
                name=company_name,
                defaults={
                    'slug': slug,
                    'website': website,
                    'industry': industry,
                    'employee_count': company_size,
                    'description': f"Organization account for {company_name}",
                    'location': 'Remote'
                }
            )
            
            CompanyMember.objects.get_or_create(
                company=company,
                user=user,
                defaults={
                    'designation': 'Independent Recruiter' if hiring_type == 'independent' else 'Recruiter',
                    'role': CompanyMember.MemberRole.ADMIN
                }
            )
        except Exception as company_err:
            print(f"Error creating company in employer signup: {company_err}")
            
        login(self.request, user)
        return super().form_valid(form)


class AdminLoginView(View):
    template_name = 'registration/admin_login.html'

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

            user = authenticate(request, username=email, password=password)
            if user is not None:
                if user.role == User.Role.SUPER_ADMIN:
                    if user.is_active:
                        login(request, user)
                        if remember_me:
                            request.session.set_expiry(1209600)  # 2 weeks
                        else:
                            request.session.set_expiry(0)
                        return redirect('frontend:dashboard')
                    else:
                        form.add_error(None, "This account is disabled.")
                else:
                    form.add_error(None, "Access restricted to authorized administrators only.")
            else:
                form.add_error(None, "Invalid email or password.")
        
        return render(request, self.template_name, {'form': form})
