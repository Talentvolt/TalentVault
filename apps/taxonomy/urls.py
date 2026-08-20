from django.urls import path
from apps.taxonomy.views import (
    TaxonomyDashboardView,
    TaxonomyEntityCreateView,
    TaxonomyEntityEditView,
    TaxonomyEntityStatusToggleView,
    TaxonomyEntityDeleteView,
    TaxonomyEntityDetailAPIView,
    TaxonomyAliasCreateView,
    TaxonomyAliasDeleteView,
    TaxonomyRelationshipCreateView,
    TaxonomyRelationshipDeleteView,
    TaxonomyMergeView,
    TaxonomyImportView,
    TaxonomyExportView,
    TaxonomySeedView,
    TaxonomyTreeView,
    TaxonomyTreeDataAPIView,
    TaxonomyCheckDuplicateAPIView,
    TaxonomySuggestionsAPIView,
    TaxonomyRolesAPIView,
    TaxonomySkillsAPIView,
    TaxonomyJobSuggestionsAPIView,
    TaxonomyStatsAPIView
)

app_name = 'taxonomy'

urlpatterns = [
    # Dashboard & UI
    path('', TaxonomyDashboardView.as_view(), name='taxonomy_dashboard'),
    path('tree/', TaxonomyTreeView.as_view(), name='taxonomy_tree'),

    # Entity CRUD
    path('entities/create/', TaxonomyEntityCreateView.as_view(), name='taxonomy_entity_create'),
    path('entities/<str:entity_type>/<uuid:entity_id>/edit/', TaxonomyEntityEditView.as_view(), name='taxonomy_entity_edit'),
    path('entities/<str:entity_type>/<uuid:entity_id>/toggle-status/', TaxonomyEntityStatusToggleView.as_view(), name='taxonomy_entity_toggle_status'),
    path('entities/<str:entity_type>/<uuid:entity_id>/delete/', TaxonomyEntityDeleteView.as_view(), name='taxonomy_entity_delete'),
    path('entities/<str:entity_type>/<uuid:entity_id>/detail-json/', TaxonomyEntityDetailAPIView.as_view(), name='taxonomy_entity_detail_json'),

    # Aliases & Relationships
    path('aliases/create/', TaxonomyAliasCreateView.as_view(), name='taxonomy_alias_create'),
    path('aliases/<uuid:alias_id>/delete/', TaxonomyAliasDeleteView.as_view(), name='taxonomy_alias_delete'),
    path('relationships/create/', TaxonomyRelationshipCreateView.as_view(), name='taxonomy_relationship_create'),
    path('relationships/<uuid:rel_id>/delete/', TaxonomyRelationshipDeleteView.as_view(), name='taxonomy_relationship_delete'),

    # Merge, Import, Export, Seeding
    path('merge/', TaxonomyMergeView.as_view(), name='taxonomy_merge'),
    path('import/', TaxonomyImportView.as_view(), name='taxonomy_import'),
    path('export/', TaxonomyExportView.as_view(), name='taxonomy_export'),
    path('seed/', TaxonomySeedView.as_view(), name='taxonomy_seed'),

    # AJAX & Autocomplete API endpoints
    path('api/taxonomy/tree-data/', TaxonomyTreeDataAPIView.as_view(), name='api_taxonomy_tree_data'),
    path('api/taxonomy/check-duplicate/', TaxonomyCheckDuplicateAPIView.as_view(), name='api_taxonomy_check_duplicate'),
    path('api/taxonomy/suggestions/', TaxonomySuggestionsAPIView.as_view(), name='api_taxonomy_suggestions'),
    path('api/taxonomy/roles/', TaxonomyRolesAPIView.as_view(), name='api_taxonomy_roles'),
    path('api/taxonomy/skills/', TaxonomySkillsAPIView.as_view(), name='api_taxonomy_skills'),
    path('api/taxonomy/job-suggestions/', TaxonomyJobSuggestionsAPIView.as_view(), name='api_taxonomy_job_suggestions'),
    path('api/taxonomy/stats/', TaxonomyStatsAPIView.as_view(), name='api_taxonomy_stats'),
]
