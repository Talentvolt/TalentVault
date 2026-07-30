from django.contrib import admin
from .models import Application

@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ('candidate', 'job', 'stage', 'created_at')
    list_filter = ('stage', 'created_at')
    search_fields = ('candidate__full_name', 'candidate__user__email', 'job__title')
