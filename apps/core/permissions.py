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

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
            
        if request.user.role not in self.allowed_roles:
            if request.user.role == User.Role.CANDIDATE:
                return redirect('frontend:candidate_dashboard')
            elif request.user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN, User.Role.SUPER_ADMIN]:
                return redirect('frontend:recruiter_dashboard')
            return redirect('frontend:dashboard')
            
        return super().dispatch(request, *args, **kwargs)

class SuperAdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = [User.Role.SUPER_ADMIN]
    login_url = reverse_lazy('admin_login')

class RecruiterRequiredMixin(RoleRequiredMixin):
    allowed_roles = [User.Role.RECRUITER, User.Role.COMPANY_ADMIN, User.Role.SUPER_ADMIN]
    login_url = reverse_lazy('employer_login')

class CandidateRequiredMixin(RoleRequiredMixin):
    allowed_roles = [User.Role.CANDIDATE]
    login_url = reverse_lazy('candidate_login')
