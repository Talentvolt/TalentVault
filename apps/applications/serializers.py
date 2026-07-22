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
    mobile_number = serializers.CharField(required=True)
    current_ctc = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    expected_ctc = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    notice_period = serializers.IntegerField(required=True)
    current_location = serializers.CharField(required=True)
    preferred_locations = serializers.JSONField(required=True)
    key_skills = serializers.JSONField(required=True)
    date_of_birth = serializers.DateField(required=True)
    linkedin_url = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    portfolio_url = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    note_to_recruiter = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=500)
    cover_letter = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def to_internal_value(self, data):
        data = data.copy()
        for field in ['linkedin_url', 'portfolio_url']:
            val = data.get(field)
            if isinstance(val, str) and val.strip():
                v = val.strip()
                if not v.startswith(('http://', 'https://')):
                    v = f"https://{v}"
                data[field] = v
            elif val == '':
                data[field] = None
        return super().to_internal_value(data)

    def validate_mobile_number(self, value):
        import re
        val = str(value).strip()
        if not re.match(r'^[6-9]\d{9}$', val):
            raise serializers.ValidationError("Please enter a valid 10-digit Indian mobile number.")
        return val

    def validate_current_location(self, value):
        val = str(value).strip()
        if not val:
            raise serializers.ValidationError("Please enter your current city.")
        return val

    def validate_preferred_locations(self, value):
        if isinstance(value, str):
            value = [loc.strip() for loc in value.split(',') if loc.strip()]
        if not value or not isinstance(value, list) or len(value) == 0:
            raise serializers.ValidationError("Please select at least one preferred location.")
        return value

    def validate_key_skills(self, value):
        if isinstance(value, str):
            value = [skill.strip() for skill in value.split(',') if skill.strip()]
        if not value or not isinstance(value, list) or len(value) == 0:
            raise serializers.ValidationError("Please select at least one key skill.")
        return value

class ApplicationTransitionSerializer(serializers.Serializer):
    to_stage = serializers.ChoiceField(choices=Application.ApplicationStage.choices)
    notes = serializers.CharField(required=False, allow_blank=True)
