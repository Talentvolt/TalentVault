from typing import List, Optional
from django.db.models import Q, QuerySet
from apps.candidates.models import CandidateProfile

class CandidateSearchService:
    """
    Service for advanced candidate search using PostgreSQL optimized queries.
    """

    @staticmethod
    def search_candidates(
        skills: List[str] = None,
        min_experience: Optional[float] = None,
        location: Optional[str] = None,
        max_salary: Optional[float] = None,
        max_notice_period: Optional[int] = None,
        education_degree: Optional[str] = None
    ) -> QuerySet:
        
        # Start with active candidates
        queryset = CandidateProfile.objects.select_related('user').prefetch_related('skills', 'educations')

        filters = Q()

        if skills:
            # Match any of the skills provided
            skill_queries = Q()
            for skill in skills:
                skill_queries |= Q(skills__skill_name__icontains=skill)
            filters &= skill_queries

        if min_experience is not None:
            filters &= Q(total_experience__gte=min_experience)

        if location:
            filters &= Q(location__icontains=location)

        if max_salary is not None:
            filters &= Q(expected_salary__lte=max_salary)

        if max_notice_period is not None:
            filters &= Q(notice_period__lte=max_notice_period)
            
        if education_degree:
            filters &= Q(educations__degree__icontains=education_degree)

        return queryset.filter(filters).distinct()
