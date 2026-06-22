from rest_framework import serializers
from apps.candidates.models import CandidateProfile, CandidateSkill, Experience, Education
from apps.accounts.serializers import UserSerializer

class CandidateSkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = CandidateSkill
        fields = ('id', 'skill_name', 'years_of_experience', 'proficiency')

class ExperienceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Experience
        fields = ('id', 'company_name', 'designation', 'start_date', 'end_date', 'is_current', 'description')

class EducationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Education
        fields = ('id', 'institution', 'degree', 'field_of_study', 'start_date', 'end_date', 'percentage_or_cgpa')

class CandidateProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    skills = CandidateSkillSerializer(many=True, read_only=True)
    experiences = ExperienceSerializer(many=True, read_only=True)
    educations = EducationSerializer(many=True, read_only=True)

    class Meta:
        model = CandidateProfile
        fields = (
            'id', 'user', 'summary', 'resume', 'location', 'total_experience',
            'current_salary', 'expected_salary', 'notice_period', 'is_immediate_joiner',
            'linkedin_url', 'portfolio_url', 'skills', 'experiences', 'educations', 'created_at'
        )
        read_only_fields = ('id', 'created_at')
