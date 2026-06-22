from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from apps.applications.models import Application
from .serializers import (
    ApplicationSerializer, 
    ApplicationApplySerializer, 
    ApplicationTransitionSerializer
)
from services.application_service import ApplicationService
from permissions.roles import IsRecruiter, IsCandidate
from utils.pagination import StandardResultsSetPagination

class ApplicationViewSet(viewsets.ModelViewSet):
    """
    Applicant Tracking System (ATS) Endpoints.
    """
    queryset = Application.objects.all()
    serializer_class = ApplicationSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    filterset_fields = ['job', 'stage', 'is_active']
    search_fields = ['candidate__user__email', 'job__title']
    ordering_fields = ['match_score', 'created_at']
    ordering = ['-match_score']

    def get_permissions(self):
        if self.action == 'apply':
            permission_classes = [IsCandidate]
        elif self.action in ['transition_stage', 'shortlist', 'reject']:
            permission_classes = [IsRecruiter]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'CANDIDATE':
            return Application.objects.filter(candidate__user=user)
        # Recruiters can see all applications for their company's jobs
        return super().get_queryset()

    @action(detail=False, methods=['post'], serializer_class=ApplicationApplySerializer)
    def apply(self, request):
        """Candidate applies for a job."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        job_id = serializer.validated_data['job_id']
        cover_letter = serializer.validated_data.get('cover_letter', '')
        candidate_id = request.user.candidate_profile.id
        
        try:
            application = ApplicationService.apply_for_job(job_id, candidate_id, cover_letter)
            return Response(ApplicationSerializer(application).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], serializer_class=ApplicationTransitionSerializer)
    def transition_stage(self, request, pk=None):
        """Recruiter moves candidate to a different ATS stage."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            application = ApplicationService.transition_stage(
                application_id=pk,
                to_stage=serializer.validated_data['to_stage'],
                notes=serializer.validated_data.get('notes', ''),
                user=request.user
            )
            return Response(ApplicationSerializer(application).data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Quick action to reject a candidate."""
        notes = request.data.get('notes', 'Candidate rejected after review.')
        application = ApplicationService.transition_stage(pk, Application.ApplicationStage.SYSTEM_REJECTED, notes, request.user)
        application.is_active = False
        application.rejection_reason = notes
        application.save()
        return Response({'status': 'Candidate rejected'})
