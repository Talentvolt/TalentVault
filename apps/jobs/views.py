from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from apps.jobs.models import Job
from .serializers import JobSerializer
from permissions.roles import IsRecruiter
from utils.pagination import StandardResultsSetPagination

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
    
    filterset_fields = ['company', 'job_type', 'experience_level', 'is_remote', 'status']
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
        user = self.request.user
        if user.role == 'CANDIDATE':
            return Job.objects.filter(status=Job.JobStatus.ACTIVE)
        # Recruiters see all jobs (can filter by company)
        return super().get_queryset()

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
        job.save()
        return Response({'status': 'Job closed successfully'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='pause')
    def pause_job(self, request, pk=None):
        """Pause an active job posting."""
        job = self.get_object()
        job.status = Job.JobStatus.PAUSED
        job.save()
        return Response({'status': 'Job paused successfully'}, status=status.HTTP_200_OK)
