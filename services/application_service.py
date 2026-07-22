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
    def apply_for_job(job_id: str, candidate_id: str, cover_letter: Optional[str] = None, **kwargs) -> Application:
        job = Job.objects.get(id=job_id)
        candidate = CandidateProfile.objects.get(id=candidate_id)
        
        if not candidate.resume or not candidate.resume.name:
            raise Exception("Please upload your resume in your Profile before applying.")

        if Application.objects.filter(job=job, candidate=candidate).exists():
            raise Exception("You have already applied for this job.")
            
        # Calculate initial match score
        match_data = CandidateMatchingService.calculate_match_score(job, candidate)
        
        pref_locs = kwargs.get('preferred_locations') or []
        if isinstance(pref_locs, str):
            pref_locs = [x.strip() for x in pref_locs.split(',') if x.strip()]
            
        skills = kwargs.get('key_skills') or []
        if isinstance(skills, str):
            skills = [x.strip() for x in skills.split(',') if x.strip()]

        from services.location_service import LocationService

        current_loc = kwargs.get('current_location') or candidate.location or ''
        current_loc_info = LocationService.parse_location_info(current_loc)

        pref_locs_info = [LocationService.parse_location_info(loc) for loc in pref_locs]

        recruiter_user = getattr(job, 'created_by', None)
        if not recruiter_user and job.company:
            member = job.company.members.first()
            if member:
                recruiter_user = member.user

        with transaction.atomic():
            application = Application.objects.create(
                job=job,
                candidate=candidate,
                recruiter=recruiter_user,
                resume=candidate.resume,
                cover_letter=cover_letter,
                match_score=match_data['match_score'],
                stage=Application.ApplicationStage.OPEN,
                current_ctc=kwargs.get('current_ctc'),
                expected_ctc=kwargs.get('expected_ctc'),
                notice_period=kwargs.get('notice_period'),
                mobile_number=kwargs.get('mobile_number'),
                current_location=current_loc,
                current_location_city=current_loc_info.get('city'),
                current_location_state=current_loc_info.get('state'),
                current_location_tier=current_loc_info.get('tier'),
                preferred_locations=pref_locs,
                preferred_locations_info=pref_locs_info,
                preferred_location=", ".join(pref_locs) if pref_locs else current_loc,
                key_skills=skills,
                date_of_birth=kwargs.get('date_of_birth'),
                note_to_recruiter=kwargs.get('note_to_recruiter'),
                linkedin_url=kwargs.get('linkedin_url'),
                portfolio_url=kwargs.get('portfolio_url'),
                current_company=candidate.current_company,
                current_designation=candidate.current_designation,
                total_experience=candidate.total_experience,
            )
            
            # Sync mobile_number, linkedin_url, portfolio_url to profile/user if empty
            profile_updated = False
            if kwargs.get('linkedin_url') and not candidate.linkedin_url:
                candidate.linkedin_url = kwargs.get('linkedin_url')
                profile_updated = True
            if kwargs.get('portfolio_url') and not candidate.portfolio_url:
                candidate.portfolio_url = kwargs.get('portfolio_url')
                profile_updated = True
            if profile_updated:
                candidate.save()

            if kwargs.get('mobile_number') and candidate.user and not candidate.user.phone_number:
                candidate.user.phone_number = kwargs.get('mobile_number')
                candidate.user.save(update_fields=['phone_number'])

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
