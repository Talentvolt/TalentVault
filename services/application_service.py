from django.db import transaction
from apps.applications.models import Application, ApplicationHistory
from apps.jobs.models import Job
from apps.candidates.models import CandidateProfile
from services.candidate_matching_service import CandidateMatchingService
from typing import Optional

class ApplicationService:
    """
    Service to handle job applications and ATS stage transitions.
    """

    @staticmethod
    def apply_for_job(job_id: str, candidate_id: str, cover_letter: Optional[str] = None) -> Application:
        job = Job.objects.get(id=job_id)
        candidate = CandidateProfile.objects.get(id=candidate_id)
        
        # Calculate initial match score
        match_data = CandidateMatchingService.calculate_match_score(job, candidate)
        
        with transaction.atomic():
            application = Application.objects.create(
                job=job,
                candidate=candidate,
                cover_letter=cover_letter,
                match_score=match_data['match_score'],
                stage=Application.ApplicationStage.OPEN
            )
            
            # Create initial history entry
            ApplicationHistory.objects.create(
                application=application,
                from_stage=Application.ApplicationStage.OPEN,
                to_stage=Application.ApplicationStage.OPEN,
                notes="Initial application submitted."
            )
            
        return application

    @staticmethod
    def transition_stage(application_id: str, to_stage: str, notes: str = "", user=None) -> Application:
        application = Application.objects.get(id=application_id)
        from_stage = application.stage
        
        if from_stage == to_stage:
            return application

        with transaction.atomic():
            application.stage = to_stage
            application.save()
            
            ApplicationHistory.objects.create(
                application=application,
                from_stage=from_stage,
                to_stage=to_stage,
                notes=notes,
                created_by=user
            )
            
        return application
