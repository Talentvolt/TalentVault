from django.shortcuts import redirect
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
            
            # Bypass static, media and API
            if not (path.startswith('/static/') or path.startswith('/media/') or path.startswith('/api/')):
                # Restrict Candidate Access
                if role == User.Role.CANDIDATE:
                    forbidden_prefixes = [
                        '/dashboard/recruiter/',
                        '/dashboard/admin/',
                        '/pipeline/',
                        '/analytics/',
                        '/candidates/',
                        '/resume-parser/',
                        '/email-campaigns/',
                        '/export/',
                        '/jobs/new/',
                        '/clients/'
                    ]
                    is_forbidden = any(path.startswith(prefix) for prefix in forbidden_prefixes)
                    if not is_forbidden and path.startswith('/jobs/'):
                        is_forbidden = any(suffix in path for suffix in ['/edit/', '/delete/', '/candidates/'])
                        
                    if is_forbidden:
                        return redirect('frontend:candidate_dashboard')
                
                # Restrict Recruiter Access
                elif role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN]:
                    forbidden_prefixes = [
                        '/dashboard/candidate/',
                        '/dashboard/admin/',
                        '/profile/',
                        '/career-resources/',
                        '/jobs/saved/',
                        '/jobs/recommended/',
                        '/applications/'
                    ]
                    if any(path.startswith(prefix) for prefix in forbidden_prefixes):
                        return redirect('frontend:recruiter_dashboard')
                
                # Restrict Admin Access (Admin can access admin only)
                elif role == User.Role.SUPER_ADMIN:
                    allowed_prefixes = [
                        '/dashboard/admin/',
                        '/admin/',
                        '/accounts/logout/',
                    ]
                    if path != '/' and not any(path.startswith(prefix) for prefix in allowed_prefixes):
                        return redirect('frontend:admin_dashboard')
                    
        response = self.get_response(request)
        return response
