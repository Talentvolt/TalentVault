import logging
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.text import slugify
from apps.companies.models import Company, CompanyMember
from .serializers import CompanySerializer, CompanyMemberSerializer
from permissions.roles import IsCompanyAdmin, IsRecruiter
from utils.pagination import StandardResultsSetPagination
from utils.tenant import get_user_company

logger = logging.getLogger(__name__)

class CompanyViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for Companies.
    List and Retrieve are public (authenticated).
    Create, Update, Delete are restricted to Company Admins.
    """
    queryset = Company.objects.filter(is_active=True)
    serializer_class = CompanySerializer
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsCompanyAdmin]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        company = serializer.save(slug=slugify(serializer.validated_data['name']))
        # Automatically make the creator a Company Admin
        if self.request.user.role in ['COMPANY_ADMIN', 'SUPER_ADMIN']:
            CompanyMember.objects.create(
                company=company,
                user=self.request.user,
                designation="Founder/Admin",
                role=CompanyMember.MemberRole.ADMIN
            )

class CompanyMemberViewSet(viewsets.ModelViewSet):
    """
    Manage recruiters and admins within a company.
    """
    serializer_class = CompanyMemberSerializer
    permission_classes = [IsCompanyAdmin]

    def get_queryset(self):
        user = self.request.user
        company_id = self.kwargs.get('company_pk')
        if user.role == 'SUPER_ADMIN' or getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
            return CompanyMember.objects.filter(company_id=company_id)
        user_comp = get_user_company(user)
        if user_comp and str(user_comp.id) == str(company_id):
            return CompanyMember.objects.filter(company_id=company_id)
        return CompanyMember.objects.none()

    def perform_create(self, serializer):
        company_id = self.kwargs.get('company_pk')
        company = Company.objects.get(id=company_id)
        serializer.save(company=company)

