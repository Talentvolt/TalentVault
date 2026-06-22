from rest_framework import views, permissions, status
from rest_framework.response import Response
from apps.jobs.models import Job
from apps.candidates.models import CandidateProfile
from services.candidate_matching_service import CandidateMatchingService
from services.candidate_search_service import CandidateSearchService
from permissions.roles import IsRecruiter
from apps.candidates.serializers import CandidateProfileSerializer

class MatchingCandidatesView(views.APIView):
    """
    Returns candidate profiles ranked by match score for a specific job.
    """
    permission_classes = [IsRecruiter]

    def get(self, request, job_pk, format=None):
        try:
            job = Job.objects.get(id=job_pk)
        except Job.DoesNotExist:
            return Response({"error": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

        # Retrieve potential candidates via advanced search using Job's base criteria
        candidates = CandidateSearchService.search_candidates(
            skills=list(job.skills.values_list('skill_name', flat=True)),
            min_experience=job.min_experience,
            location=job.location if not job.is_remote else None
        )

        matches = []
        for candidate in candidates:
            match_data = CandidateMatchingService.calculate_match_score(job, candidate)
            # Rule: Only return qualified candidates (>= 70% skill match and >= min experience)
            if match_data.get('is_qualified'):
                profile_data = CandidateProfileSerializer(candidate).data
                match_data['candidate'] = profile_data
                matches.append(match_data)

        # Sort by highest match score
        matches.sort(key=lambda x: x['match_score'], reverse=True)

        return Response({
            "job_id": job.id,
            "job_title": job.title,
            "count": len(matches),
            "matches": matches
        })
