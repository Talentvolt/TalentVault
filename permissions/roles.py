from rest_framework.permissions import BasePermission
from apps.accounts.models import User

class IsSuperAdmin(BasePermission):
    """
    Allows access only to Super Admins.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == User.Role.SUPER_ADMIN)

class IsCompanyAdmin(BasePermission):
    """
    Allows access to Company Admins and Super Admins.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            request.user.role in [User.Role.COMPANY_ADMIN, User.Role.SUPER_ADMIN]
        )

class IsRecruiter(BasePermission):
    """
    Allows access to Recruiters, Company Admins, and Super Admins.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            request.user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN, User.Role.SUPER_ADMIN]
        )

class IsCandidate(BasePermission):
    """
    Allows access only to Candidates.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == User.Role.CANDIDATE)
