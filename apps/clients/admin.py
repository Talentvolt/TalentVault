from django.contrib import admin
from .models import Client

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'spoc_name', 'industry', 'email', 'phone_number', 'status', 'created_at')
    list_filter = ('industry', 'status', 'created_at')
    search_fields = ('company_name', 'spoc_name', 'email')
    ordering = ('company_name',)
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Details', {
            'fields': ('company_name', 'spoc_name', 'designation', 'email', 'phone_number', 'website')
        }),
        ('Classification', {
            'fields': ('industry', 'company_size')
        }),
        ('Location', {
            'fields': ('city', 'state', 'country')
        }),
        ('Other Settings', {
            'fields': ('status', 'notes', 'created_by', 'updated_by', 'created_at', 'updated_at')
        })
    )
