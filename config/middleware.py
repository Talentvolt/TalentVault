from django.shortcuts import redirect
from apps.accounts.models import User

PUBLIC_EXACT_PATHS = frozenset({'/', '/employers/', '/employers', '/sitemap.xml', '/robots.txt'})
PUBLIC_PREFIXES = (
    '/accounts/',
    '/jobs/share/',
    '/share/job/',
    '/share/candidate/',
    '/sitemap',
    '/robots.txt',
)

ADMIN_FORBIDDEN_PREFIXES = (
    '/dashboard/candidate/',
    '/profile/',
    '/career-resources/',
    '/jobs/saved/',
    '/jobs/recommended/',
)

CANDIDATE_FORBIDDEN_PREFIXES = (
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
)

RECRUITER_FORBIDDEN_PREFIXES = (
    '/dashboard/candidate/',
    '/dashboard/admin/',
    '/profile/',
    '/career-resources/',
    '/jobs/saved/',
    '/jobs/recommended/',
    '/applications/'
)

JOB_FORBIDDEN_SUFFIXES = ('/edit/', '/delete/', '/candidates/')

class RoleAccessMiddleware:
    """
    Middleware to ensure users only access dashboards permitted for their role,
    and unauthenticated users attempting to access protected pages (or refreshing
    /admin/, /candidate/, /recruiter/, /dashboard/...) are automatically redirected to /.
    Also adds no-cache headers to responses so back button after logout forces re-authentication.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def _add_no_cache_headers(self, response):
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response

    def __call__(self, request):
        path = request.path

        # Bypass static, media and API
        if not (path.startswith('/static/') or path.startswith('/media/') or path.startswith('/api/')):
            if not request.user.is_authenticated:
                is_public = path in PUBLIC_EXACT_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES) or '/public-apply/' in path
                if not is_public:
                    res = redirect('/')
                    return self._add_no_cache_headers(res)
            else:
                user = request.user
                role = user.role
                is_admin_user = (role == User.Role.SUPER_ADMIN) or getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False)

                if is_admin_user:
                    if any(path.startswith(prefix) for prefix in ADMIN_FORBIDDEN_PREFIXES):
                        res = redirect('frontend:admin_dashboard')
                        return self._add_no_cache_headers(res)

                # Restrict Candidate Access
                elif role == User.Role.CANDIDATE:
                    is_forbidden = any(path.startswith(prefix) for prefix in CANDIDATE_FORBIDDEN_PREFIXES)
                    if path.endswith('/resume/preview/') or path.endswith('/resume/download/'):
                        is_forbidden = False
                    if not is_forbidden and path.startswith('/jobs/'):
                        is_forbidden = any(suffix in path for suffix in JOB_FORBIDDEN_SUFFIXES)
                        
                    if is_forbidden:
                        res = redirect('frontend:candidate_dashboard')
                        return self._add_no_cache_headers(res)
                
                # Restrict Recruiter Access
                elif role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN]:
                    if any(path.startswith(prefix) for prefix in RECRUITER_FORBIDDEN_PREFIXES):
                        res = redirect('frontend:recruiter_dashboard')
                        return self._add_no_cache_headers(res)
                    
        response = self.get_response(request)

        # Add no-cache headers to non-static/media pages so browser Back button after logout forces re-authentication
        if not (path.startswith('/static/') or path.startswith('/media/')):
            self._add_no_cache_headers(response)

        return response

