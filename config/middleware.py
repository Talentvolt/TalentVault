from django.shortcuts import redirect
from apps.accounts.models import User

class RoleAccessMiddleware:
    """
    Middleware to ensure users only access dashboards permitted for their role.
    Also adds no-cache headers to protected pages so back button after logout forces re-authentication.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # Bypass static, media and API
        if not (path.startswith('/static/') or path.startswith('/media/') or path.startswith('/api/')):
            if request.user.is_authenticated:
                role = request.user.role
                
                # Restrict Candidate Access
                if role == User.Role.CANDIDATE:
                    candidate_forbidden_prefixes = [
                        '/dashboard/recruiter/',
                        '/dashboard/admin/',
                        '/pipeline/',
                        '/analytics/',
                        '/candidates/',
                        '/resume-parser/',
                        '/email-campaigns/',
                        '/export/',
                        '/jobs/new/',
                        '/clients/',
                        '/employers/'
                    ]
                    is_forbidden = any(path.startswith(prefix) for prefix in candidate_forbidden_prefixes)
                    if path.endswith('/resume/preview/') or path.endswith('/resume/download/'):
                        is_forbidden = False
                    if not is_forbidden and path.startswith('/jobs/'):
                        is_forbidden = any(suffix in path for suffix in ['/edit/', '/delete/', '/candidates/'])
                        
                    if is_forbidden:
                        return redirect('frontend:candidate_dashboard')
                
                # Restrict Recruiter / Admin Access
                elif role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN, User.Role.SUPER_ADMIN]:
                    recruiter_forbidden_prefixes = [
                        '/dashboard/candidate/',
                        '/profile/',
                        '/career-resources/',
                        '/jobs/saved/',
                        '/jobs/recommended/',
                        '/applications/'
                    ]
                    if any(path.startswith(prefix) for prefix in recruiter_forbidden_prefixes):
                        return redirect('frontend:recruiter_dashboard')
                    
        response = self.get_response(request)

        # Add no-cache headers to authenticated HTML pages so browser Back button after logout forces re-authentication
        if request.user.is_authenticated and not (path.startswith('/static/') or path.startswith('/media/')):
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'

        return response
