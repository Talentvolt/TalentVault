import logging
from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from apps.jobs.models import Job
from .serializers import JobSerializer
from permissions.roles import IsRecruiter
from utils.pagination import StandardResultsSetPagination
from utils.tenant import get_tenant_jobs_qs

logger = logging.getLogger(__name__)

class JobViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for Jobs.
    Candidates can view active jobs.
    Recruiters can create, update, and manage jobs.
    """
    queryset = Job.objects.all()
    serializer_class = JobSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    filterset_fields = ['company', 'job_type', 'is_remote', 'status']
    search_fields = ['title', 'description', 'location', 'skills__skill_name']
    ordering_fields = ['created_at', 'min_salary']
    ordering = ['-created_at']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'close_job', 'pause_job']:
            permission_classes = [IsRecruiter]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        return get_tenant_jobs_qs(self.request.user)

    def perform_create(self, serializer):
        client = serializer.validated_data.get('client')
        if client:
            from apps.companies.models import Company
            from django.utils.text import slugify
            comp_name = client.company_name.strip()
            company = Company.objects.filter(name__iexact=comp_name).first()
            if not company:
                base_slug = slugify(comp_name) or 'company'
                slug = base_slug
                counter = 1
                while Company.objects.filter(slug=slug).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                company = Company.objects.create(
                    name=comp_name,
                    slug=slug,
                    industry=getattr(client, 'industry', '') or 'General',
                    location=client.city or 'India'
                )
            serializer.save(created_by=self.request.user, company=company, client=client)
        else:
            from utils.tenant import get_user_company
            company = get_user_company(self.request.user)
            serializer.save(created_by=self.request.user, company=company or serializer.validated_data.get('company'))

    @action(detail=True, methods=['post'], url_path='publish')
    def publish_job(self, request, pk=None):
        """Publish a draft job posting."""
        job = self.get_object()
        job.status = Job.JobStatus.ACTIVE
        job.save()
        return Response({'status': 'Job published successfully'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='close')
    def close_job(self, request, pk=None):
        """Close an active job posting."""
        job = self.get_object()
        job.status = Job.JobStatus.CLOSED
        from django.utils import timezone
        job.closed_at = timezone.now()
        job.closed_by = request.user
        job.save()
        return Response({'status': 'Job closed successfully'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='pause')
    def pause_job(self, request, pk=None):
        """Pause an active job posting."""
        job = self.get_object()
        job.status = Job.JobStatus.PAUSED
        job.save()
        return Response({'status': 'Job paused successfully'}, status=status.HTTP_200_OK)

