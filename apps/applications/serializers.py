from rest_framework import serializers
from apps.applications.models import Application, ApplicationHistory
from apps.jobs.serializers import JobSerializer
from apps.candidates.serializers import CandidateProfileSerializer

class ApplicationHistorySerializer(serializers.ModelSerializer):
    created_by_email = serializers.CharField(source='created_by.email', read_only=True)

    class Meta:
        model = ApplicationHistory
        fields = ('id', 'from_stage', 'to_stage', 'notes', 'created_by_email', 'created_at')
        read_only_fields = ('id', 'created_at')

class ApplicationSerializer(serializers.ModelSerializer):
    job_details = JobSerializer(source='job', read_only=True)
    candidate_details = CandidateProfileSerializer(source='candidate', read_only=True)
    history = ApplicationHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Application
        fields = (
            'id', 'job', 'job_details', 'candidate', 'candidate_details', 
            'stage', 'match_score', 'cover_letter', 'rejection_reason', 
            'is_active', 'history', 'created_at'
        )
        read_only_fields = ('id', 'stage', 'match_score', 'is_active', 'created_at')

class ApplicationApplySerializer(serializers.Serializer):
    job_id = serializers.UUIDField(required=True)
    cover_letter = serializers.CharField(required=False, allow_blank=True)

class ApplicationTransitionSerializer(serializers.Serializer):
    to_stage = serializers.ChoiceField(choices=Application.ApplicationStage.choices)
    notes = serializers.CharField(required=False, allow_blank=True)
