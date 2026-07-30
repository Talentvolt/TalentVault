from django.contrib import admin
from .models import Company, CompanyMember

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'industry', 'employee_count', 'is_active', 'created_at')
    list_filter = ('is_active', 'industry', 'created_at')
    search_fields = ('name', 'industry', 'description')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(CompanyMember)
class CompanyMemberAdmin(admin.ModelAdmin):
    list_display = ('company', 'user', 'designation', 'role', 'created_at')
    list_filter = ('role', 'created_at')
    search_fields = ('company__name', 'user__email', 'designation')
    readonly_fields = ('created_at', 'updated_at')
