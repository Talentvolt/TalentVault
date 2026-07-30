from django.contrib import admin
from .models import Interview, InterviewFeedback

@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ('application', 'interview_type', 'start_time', 'end_time', 'status', 'created_at')
    list_filter = ('status', 'interview_type', 'start_time')
    search_fields = ('application__candidate__full_name', 'application__candidate__user__email', 'application__job__title')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(InterviewFeedback)
class InterviewFeedbackAdmin(admin.ModelAdmin):
    list_display = ('interview', 'interviewer', 'rating', 'recommendation', 'created_at')
    list_filter = ('rating', 'recommendation', 'created_at')
    search_fields = ('interviewer__email', 'comments')
    readonly_fields = ('created_at', 'updated_at')
