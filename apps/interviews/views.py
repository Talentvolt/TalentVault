from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from apps.interviews.models import Interview, InterviewFeedback
from .serializers import InterviewSerializer, InterviewFeedbackSerializer
from services.interview_service import InterviewService
from permissions.roles import IsRecruiter
from utils.pagination import StandardResultsSetPagination

class InterviewViewSet(viewsets.ModelViewSet):
    """
    Manage Interviews.
    """
    queryset = Interview.objects.all()
    serializer_class = InterviewSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    filterset_fields = ['status', 'interview_type', 'application__job']
    search_fields = ['application__candidate__user__email', 'application__job__title']
    ordering_fields = ['start_time', 'created_at']
    ordering = ['start_time']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'cancel']:
            permission_classes = [IsRecruiter]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'CANDIDATE':
            return Interview.objects.filter(application__candidate__user=user)
        elif user.role in ['RECRUITER', 'COMPANY_ADMIN', 'SUPER_ADMIN']:
            return Interview.objects.filter(application__job__company__members__user=user).distinct()
        return super().get_queryset()

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        interview = self.get_object()
        interview.status = Interview.InterviewStatus.CANCELLED
        interview.save()
        return Response({'status': 'Interview cancelled'})

    @action(detail=True, methods=['post'], serializer_class=InterviewFeedbackSerializer)
    def submit_feedback(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            feedback = InterviewService.submit_feedback(
                interview_id=pk,
                interviewer_id=request.user.id,
                rating=serializer.validated_data['rating'],
                comments=serializer.validated_data['comments'],
                recommendation=serializer.validated_data['recommendation']
            )
            return Response(InterviewFeedbackSerializer(feedback).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
