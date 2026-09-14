from django.contrib import admin
from .models import Job

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'department', 'job_type', 'status', 'location', 'ai_matching_enabled', 'created_at')
    list_filter = ('status', 'job_type', 'ai_matching_enabled', 'created_at')
    search_fields = ('title', 'department', 'company__name', 'location')
    readonly_fields = ('created_at', 'updated_at')

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
