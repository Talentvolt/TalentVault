from django.urls import path
from apps.taxonomy.views import (
    TaxonomySuggestionsAPIView,
    TaxonomyRolesAPIView,
    TaxonomySkillsAPIView,
    TaxonomyJobSuggestionsAPIView,
    TaxonomyStatsAPIView
)

app_name = 'taxonomy'

urlpatterns = [
    path('api/taxonomy/suggestions/', TaxonomySuggestionsAPIView.as_view(), name='api_taxonomy_suggestions'),
    path('api/taxonomy/roles/', TaxonomyRolesAPIView.as_view(), name='api_taxonomy_roles'),
    path('api/taxonomy/skills/', TaxonomySkillsAPIView.as_view(), name='api_taxonomy_skills'),
    path('api/taxonomy/job-suggestions/', TaxonomyJobSuggestionsAPIView.as_view(), name='api_taxonomy_job_suggestions'),
    path('api/taxonomy/stats/', TaxonomyStatsAPIView.as_view(), name='api_taxonomy_stats'),
]
