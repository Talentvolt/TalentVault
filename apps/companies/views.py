from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.text import slugify
from apps.companies.models import Company, CompanyMember
from .serializers import CompanySerializer, CompanyMemberSerializer
from permissions.roles import IsCompanyAdmin, IsRecruiter
from utils.pagination import StandardResultsSetPagination

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
        company_id = self.kwargs.get('company_pk')
        return CompanyMember.objects.filter(company_id=company_id)

    def perform_create(self, serializer):
        company_id = self.kwargs.get('company_pk')
        company = Company.objects.get(id=company_id)
        serializer.save(company=company)
