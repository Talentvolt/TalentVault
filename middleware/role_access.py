from django.shortcuts import redirect
from django.urls import reverse
from apps.accounts.models import User

class RoleAccessMiddleware:
    """
    Middleware to ensure users only access dashboards permitted for their role.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            path = request.path
            role = request.user.role
            
            # Prevent candidates from accessing recruiter or admin areas
            if role == User.Role.CANDIDATE:
                forbidden_paths = ['/dashboard/recruiter/', '/dashboard/admin/', '/pipeline/', '/analytics/']
                if any(path.startswith(p) for p in forbidden_paths):
                    return redirect('frontend:candidate_dashboard')
            
            # Prevent recruiters from accessing admin area
            elif role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN]:
                if path.startswith('/dashboard/admin/'):
                    return redirect('frontend:recruiter_dashboard')
                    
        response = self.get_response(request)
        return response
