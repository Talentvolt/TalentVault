from django.contrib import admin
from .models import (
    CandidateProfile, CandidateSkill, Experience, Education, Project, Certification,
    DuplicateResumeLog, SavedJob, TaxonomySkill, TaxonomyDesignation, RoleRelation,
    RoleSkillRelation, CandidateTag, SavedCandidateSearch, RecentCandidateSearch
)

@admin.register(CandidateProfile)
class CandidateProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user', 'location', 'total_experience', 'current_salary', 'ats_score', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('full_name', 'user__email', 'location')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(CandidateSkill)
class CandidateSkillAdmin(admin.ModelAdmin):
    list_display = ('profile', 'skill_name', 'years_of_experience', 'proficiency')
    list_filter = ('proficiency',)
    search_fields = ('profile__full_name', 'skill_name')

@admin.register(Experience)
class ExperienceAdmin(admin.ModelAdmin):
    list_display = ('profile', 'company_name', 'designation', 'start_date', 'end_date', 'is_current')
    list_filter = ('is_current',)
    search_fields = ('profile__full_name', 'company_name', 'designation')

@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    list_display = ('profile', 'institution', 'degree', 'field_of_study', 'end_date')
    search_fields = ('profile__full_name', 'institution', 'degree')

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('profile', 'title')
    search_fields = ('profile__full_name', 'title')

@admin.register(Certification)
class CertificationAdmin(admin.ModelAdmin):
    list_display = ('profile', 'name', 'issuing_organization', 'issue_date')
    search_fields = ('profile__full_name', 'name', 'issuing_organization')

@admin.register(DuplicateResumeLog)
class DuplicateResumeLogAdmin(admin.ModelAdmin):
    list_display = ('email', 'phone', 'filename', 'action_taken', 'created_at')
    list_filter = ('action_taken', 'created_at')
    search_fields = ('email', 'phone', 'filename')

@admin.register(SavedJob)
class SavedJobAdmin(admin.ModelAdmin):
    list_display = ('candidate', 'job', 'created_at')
    search_fields = ('candidate__full_name', 'job__title')

class RoleRelationInline(admin.TabularInline):
    model = RoleRelation
    fk_name = 'source_role'
    extra = 1

class RoleSkillRelationInline(admin.TabularInline):
    model = RoleSkillRelation
    extra = 1

@admin.register(TaxonomyDesignation)
class TaxonomyDesignationAdmin(admin.ModelAdmin):
    list_display = ('canonical_name', 'department', 'industry', 'seniority', 'is_active', 'weight')
    list_filter = ('seniority', 'department', 'industry', 'is_active')
    search_fields = ('name', 'canonical_name', 'normalized_name', 'department', 'industry')
    inlines = [RoleRelationInline, RoleSkillRelationInline]

@admin.register(TaxonomySkill)
class TaxonomySkillAdmin(admin.ModelAdmin):
    list_display = ('canonical_name', 'category', 'domain', 'is_active', 'weight')
    list_filter = ('category', 'domain', 'is_active')
    search_fields = ('name', 'canonical_name', 'normalized_name', 'domain')

@admin.register(RoleRelation)
class RoleRelationAdmin(admin.ModelAdmin):
    list_display = ('source_role', 'target_role', 'relation_type', 'weight', 'is_bidirectional')
    list_filter = ('relation_type', 'is_bidirectional')
    search_fields = ('source_role__canonical_name', 'target_role__canonical_name')

@admin.register(RoleSkillRelation)
class RoleSkillRelationAdmin(admin.ModelAdmin):
    list_display = ('role', 'skill', 'relation_type', 'weight')
    list_filter = ('relation_type',)
    search_fields = ('role__canonical_name', 'skill__canonical_name')

@admin.register(CandidateTag)
class CandidateTagAdmin(admin.ModelAdmin):
    list_display = ('profile', 'name', 'canonical_name', 'tag_type', 'confidence', 'source', 'is_current')
    list_filter = ('tag_type', 'source', 'is_current')
    search_fields = ('profile__full_name', 'name', 'canonical_name')

@admin.register(SavedCandidateSearch)
class SavedCandidateSearchAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'search_query', 'results_count', 'created_at')
    search_fields = ('name', 'user__email', 'search_query')

@admin.register(RecentCandidateSearch)
class RecentCandidateSearchAdmin(admin.ModelAdmin):
    list_display = ('user', 'search_query', 'created_at')
    search_fields = ('user__email', 'search_query')

