from django.contrib import admin
from .models import CandidateProfile, CandidateSkill, Experience, Education, Project, Certification, DuplicateResumeLog, SavedJob

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
