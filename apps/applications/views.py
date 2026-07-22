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
        
        candidate = getattr(request.user, 'candidate_profile', None)
        if not candidate:
            return Response({"error": "Candidate profile not found."}, status=status.HTTP_400_BAD_REQUEST)

        if not candidate.resume or not candidate.resume.name:
            return Response({"error": "Please upload your resume in your Profile before applying."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Pass all validated data to the service
            application = ApplicationService.apply_for_job(
                job_id=serializer.validated_data['job_id'],
                candidate_id=candidate.id,
                mobile_number=serializer.validated_data['mobile_number'],
                current_ctc=serializer.validated_data['current_ctc'],
                expected_ctc=serializer.validated_data['expected_ctc'],
                notice_period=serializer.validated_data['notice_period'],
                current_location=serializer.validated_data['current_location'],
                preferred_locations=serializer.validated_data['preferred_locations'],
                key_skills=serializer.validated_data['key_skills'],
                date_of_birth=serializer.validated_data['date_of_birth'],
                linkedin_url=serializer.validated_data.get('linkedin_url'),
                portfolio_url=serializer.validated_data.get('portfolio_url'),
                note_to_recruiter=serializer.validated_data.get('note_to_recruiter'),
                cover_letter=serializer.validated_data.get('cover_letter', '')
            )
            return Response(ApplicationSerializer(application).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            import logging, traceback
            logger = logging.getLogger(__name__)
            logger.error(f"[JOB_APPLICATION_ERROR] Application submission failed: {str(e)}\n{traceback.format_exc()}")
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
