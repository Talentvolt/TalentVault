from rest_framework import serializers
from apps.interviews.models import Interview, InterviewFeedback
from apps.applications.serializers import ApplicationSerializer
from apps.accounts.serializers import UserSerializer

class InterviewFeedbackSerializer(serializers.ModelSerializer):
    interviewer = UserSerializer(read_only=True)

    class Meta:
        model = InterviewFeedback
        fields = ('id', 'interview', 'interviewer', 'rating', 'comments', 'recommendation', 'created_at')
        read_only_fields = ('id', 'interview', 'interviewer', 'created_at')

class InterviewSerializer(serializers.ModelSerializer):
    application_details = ApplicationSerializer(source='application', read_only=True)
    interviewers_details = UserSerializer(source='interviewers', many=True, read_only=True)
    feedbacks = InterviewFeedbackSerializer(many=True, read_only=True)

    class Meta:
        model = Interview
        fields = (
            'id', 'application', 'application_details', 'interviewers', 'interviewers_details',
            'start_time', 'end_time', 'interview_type', 'status', 'meeting_link', 
            'location', 'notes', 'feedbacks', 'created_at'
        )
        read_only_fields = ('id', 'status', 'created_at')
