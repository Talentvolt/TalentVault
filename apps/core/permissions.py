from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from apps.accounts.models import User

class RoleRequiredMixin(LoginRequiredMixin):
    """
    Base mixin to check if the authenticated user has the required role.
    Redirects unauthorized users to the main dashboard router instead of raising 403.
    """
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
            
        if request.user.role not in self.allowed_roles:
            return redirect('frontend:dashboard')
            
        return super().dispatch(request, *args, **kwargs)

class SuperAdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = [User.Role.SUPER_ADMIN]

class RecruiterRequiredMixin(RoleRequiredMixin):
    allowed_roles = [User.Role.RECRUITER, User.Role.COMPANY_ADMIN, User.Role.SUPER_ADMIN]

class CandidateRequiredMixin(RoleRequiredMixin):
    allowed_roles = [User.Role.CANDIDATE]
