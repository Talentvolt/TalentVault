from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from apps.accounts.models import User

@method_decorator(never_cache, name='dispatch')
class RoleRequiredMixin(LoginRequiredMixin):
    """
    Base mixin to check if the authenticated user has the required role.
    Redirects unauthorized users to their permitted dashboard instead of raising 403.
    """
    allowed_roles = []

    def handle_no_permission(self):
        return redirect('/')

    def dispatch(self, request, *args, **kwargs):
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            print(f"[DASHBOARD PERMISSION CHECK] request.user = {request.user}")
            print(f"[DASHBOARD PERMISSION CHECK] request.user.role = {getattr(request.user, 'role', None)}")
            print(f"[DASHBOARD PERMISSION CHECK] request.user.is_superuser = {getattr(request.user, 'is_superuser', False)}")
            print(f"[DASHBOARD PERMISSION CHECK] request.user.is_staff = {getattr(request.user, 'is_staff', False)}")
        else:
            print(f"[DASHBOARD PERMISSION CHECK] request.user = {user} (unauthenticated)")

        if not request.user.is_authenticated:
            return self.handle_no_permission()

        user = request.user
        role = getattr(user, 'role', None)
        is_admin_user = (role == User.Role.SUPER_ADMIN) or getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False)

        if is_admin_user:
            return super().dispatch(request, *args, **kwargs)

        if role not in self.allowed_roles:
            if role == User.Role.CANDIDATE:
                return redirect('frontend:candidate_dashboard')
            elif role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN, User.Role.SUPER_ADMIN]:
                return redirect('frontend:recruiter_dashboard')
            return redirect('frontend:recruiter_dashboard')

        return super().dispatch(request, *args, **kwargs)

class SuperAdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = [User.Role.SUPER_ADMIN]
    login_url = reverse_lazy('admin_login')

class RecruiterRequiredMixin(RoleRequiredMixin):
    allowed_roles = [User.Role.RECRUITER, User.Role.COMPANY_ADMIN, User.Role.SUPER_ADMIN]
    login_url = reverse_lazy('recruiter_login')

    def dispatch(self, request, *args, **kwargs):
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            print(f"[RECRUITER PERMISSION CHECK] request.user = {request.user}")
            print(f"[RECRUITER PERMISSION CHECK] request.user.role = {getattr(request.user, 'role', None)}")
            print(f"[RECRUITER PERMISSION CHECK] request.user.is_superuser = {getattr(request.user, 'is_superuser', False)}")
            print(f"[RECRUITER PERMISSION CHECK] request.user.is_staff = {getattr(request.user, 'is_staff', False)}")
        else:
            print(f"[RECRUITER PERMISSION CHECK] request.user = {user} (unauthenticated)")

        if not request.user.is_authenticated:
            return self.handle_no_permission()

        user = request.user
        role = getattr(user, 'role', None)
        is_admin_user = (role == User.Role.SUPER_ADMIN) or getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False)

        # Admin users (Super Admin / superuser / staff) bypass recruiter verification status checks
        if not is_admin_user and role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN]:
            rec_status = getattr(user, 'recruiter_status', User.RecruiterStatus.ACTIVE)
            if rec_status != User.RecruiterStatus.ACTIVE:
                from django.contrib.auth import logout
                from django.contrib import messages
                if rec_status == User.RecruiterStatus.PENDING:
                    messages.warning(request, "Your account is currently under verification. Please wait until TalentVault approves your company.")
                elif rec_status == User.RecruiterStatus.REJECTED:
                    messages.error(request, "Your company verification was rejected. Please contact TalentVault Support.")
                elif rec_status == User.RecruiterStatus.SUSPENDED or not user.is_active:
                    messages.error(request, "Your recruiter account has been suspended. Please contact the administrator.")
                logout(request)
                return redirect('employer_login')

        return super().dispatch(request, *args, **kwargs)

class CandidateRequiredMixin(RoleRequiredMixin):
    allowed_roles = [User.Role.CANDIDATE]
    login_url = reverse_lazy('candidate_login')
