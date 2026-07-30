import logging
from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from apps.candidates.models import CandidateProfile, CandidateSkill, Experience, Education
from .serializers import (
    CandidateProfileSerializer, 
    CandidateSkillSerializer, 
    ExperienceSerializer, 
    EducationSerializer
)
from permissions.roles import IsRecruiter, IsCandidate
from utils.pagination import StandardResultsSetPagination
from utils.tenant import get_tenant_candidates_qs

logger = logging.getLogger(__name__)

class CandidateProfileViewSet(viewsets.ModelViewSet):
    """
    CRUD for Candidate Profiles.
    Recruiters can list and search tenant profiles. Candidates can only view/edit their own profile.
    """
    queryset = CandidateProfile.objects.all()
    serializer_class = CandidateProfileSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    filterset_fields = ['location', 'is_immediate_joiner']
    search_fields = ['user__email', 'summary', 'skills__skill_name', 'experiences__company_name']
    ordering_fields = ['total_experience', 'expected_salary']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [IsCandidate]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        return get_tenant_candidates_qs(self.request.user)

class CandidateSkillViewSet(viewsets.ModelViewSet):
    serializer_class = CandidateSkillSerializer
    permission_classes = [IsCandidate]

    def get_queryset(self):
        return CandidateSkill.objects.filter(profile__user=self.request.user)

    def perform_create(self, serializer):
        profile = CandidateProfile.objects.get(user=self.request.user)
        serializer.save(profile=profile)

class ExperienceViewSet(viewsets.ModelViewSet):
    serializer_class = ExperienceSerializer
    permission_classes = [IsCandidate]

    def get_queryset(self):
        return Experience.objects.filter(profile__user=self.request.user)

    def perform_create(self, serializer):
        profile = CandidateProfile.objects.get(user=self.request.user)
        serializer.save(profile=profile)

class EducationViewSet(viewsets.ModelViewSet):
    serializer_class = EducationSerializer
    permission_classes = [IsCandidate]

    def get_queryset(self):
        return Education.objects.filter(profile__user=self.request.user)

    def perform_create(self, serializer):
        profile = CandidateProfile.objects.get(user=self.request.user)
        serializer.save(profile=profile)

from apps.candidates.models import Project, Certification
from .serializers import ProjectSerializer, CertificationSerializer

class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [IsCandidate]

    def get_queryset(self):
        return Project.objects.filter(profile__user=self.request.user)

    def perform_create(self, serializer):
        profile = CandidateProfile.objects.get(user=self.request.user)
        serializer.save(profile=profile)

class CertificationViewSet(viewsets.ModelViewSet):
    serializer_class = CertificationSerializer
    permission_classes = [IsCandidate]

    def get_queryset(self):
        return Certification.objects.filter(profile__user=self.request.user)

    def perform_create(self, serializer):
        profile = CandidateProfile.objects.get(user=self.request.user)
        serializer.save(profile=profile)

