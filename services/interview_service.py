from datetime import datetime
from typing import List
from django.db import transaction
from apps.interviews.models import Interview, InterviewFeedback
from apps.applications.models import Application
from django.contrib.auth import get_user_model

User = get_user_model()

class InterviewService:
    """
    Service to manage interview scheduling and feedback.
    """

    @staticmethod
    def schedule_interview(
        application_id: str,
        start_time: datetime,
        end_time: datetime,
        interviewer_ids: List[str],
        interview_type: str = Interview.InterviewType.VIDEO,
        meeting_link: str = "",
        location: str = ""
    ) -> Interview:
        
        application = Application.objects.get(id=application_id)
        
        with transaction.atomic():
            interview = Interview.objects.create(
                application=application,
                start_time=start_time,
                end_time=end_time,
                interview_type=interview_type,
                meeting_link=meeting_link,
                location=location
            )
            
            interview.interviewers.set(interviewer_ids)
            
            # Transition application stage to INTERVIEW_SCHEDULE if not already there
            if application.stage != Application.ApplicationStage.INTERVIEW_SCHEDULE:
                application.stage = Application.ApplicationStage.INTERVIEW_SCHEDULE
                application.save()

        return interview

    @staticmethod
    def submit_feedback(
        interview_id: str,
        interviewer_id: str,
        rating: int,
        comments: str,
        recommendation: str
    ) -> InterviewFeedback:
        
        interview = Interview.objects.get(id=interview_id)
        interviewer = User.objects.get(id=interviewer_id)
        
        feedback = InterviewFeedback.objects.create(
            interview=interview,
            interviewer=interviewer,
            rating=rating,
            comments=comments,
            recommendation=recommendation
        )
        
        return feedback
