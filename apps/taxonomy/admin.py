from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from apps.taxonomy.models import (
    Industry, Department, JobFunction, JobRole, Specialization,
    SkillCategory, Skill, Technology, Tool, Certification, Qualification,
    TaxonomyAlias, RoleSkill, RoleRelation, RoleHierarchy, IndustryRole,
    TaxonomyImportLog, TaxonomyStatus
)


@admin.action(description=_("Soft-delete selected items (Set INACTIVE)"))
def make_inactive(modeladmin, request, queryset):
    queryset.update(status=TaxonomyStatus.INACTIVE)


@admin.action(description=_("Activate selected items (Set ACTIVE)"))
def make_active(modeladmin, request, queryset):
    queryset.update(status=TaxonomyStatus.ACTIVE)


class RoleSkillInline(admin.TabularInline):
    model = RoleSkill
    extra = 1
    fk_name = 'role'
    autocomplete_fields = ['skill', 'technology', 'tool']
    fields = ['skill', 'technology', 'tool', 'relation_type', 'weight', 'status']


class TaxonomyAliasInline(admin.TabularInline):
    model = TaxonomyAlias
    extra = 1
    fk_name = 'job_role'
    fields = ['alias', 'alias_type', 'confidence', 'status']


class OutgoingRoleRelationInline(admin.TabularInline):
    model = RoleRelation
    extra = 1
    fk_name = 'source_role'
    autocomplete_fields = ['target_role']
    fields = ['target_role', 'relation_type', 'weight', 'is_bidirectional', 'status']


@admin.register(Industry)
class IndustryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'status_badge', 'source', 'created_at']
    search_fields = ['name', 'normalized_name', 'code']
    list_filter = ['status', 'source']
    actions = [make_active, make_inactive]

    def status_badge(self, obj):
        color = "green" if obj.status == TaxonomyStatus.ACTIVE else "gray"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())
    status_badge.short_description = _("Status")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'status_badge', 'source', 'created_at']
    search_fields = ['name', 'normalized_name', 'code']
    list_filter = ['status', 'source']
    actions = [make_active, make_inactive]

    def status_badge(self, obj):
        color = "green" if obj.status == TaxonomyStatus.ACTIVE else "gray"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())
    status_badge.short_description = _("Status")


@admin.register(JobFunction)
class JobFunctionAdmin(admin.ModelAdmin):
    list_display = ['name', 'department', 'status_badge', 'source', 'created_at']
    search_fields = ['name', 'normalized_name', 'department__name']
    list_filter = ['status', 'department', 'source']
    actions = [make_active, make_inactive]

    def status_badge(self, obj):
        color = "green" if obj.status == TaxonomyStatus.ACTIVE else "gray"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())
    status_badge.short_description = _("Status")


@admin.register(JobRole)
class JobRoleAdmin(admin.ModelAdmin):
    list_display = ['canonical_name', 'seniority', 'industry', 'department', 'weight', 'status_badge', 'source']
    search_fields = ['name', 'canonical_name', 'normalized_name', 'aliases__alias']
    list_filter = ['status', 'seniority', 'typical_experience', 'industry', 'department', 'source']
    inlines = [TaxonomyAliasInline, RoleSkillInline, OutgoingRoleRelationInline]
    actions = [make_active, make_inactive]

    def status_badge(self, obj):
        color = "green" if obj.status == TaxonomyStatus.ACTIVE else "gray"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())
    status_badge.short_description = _("Status")


@admin.register(SkillCategory)
class SkillCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'category_type', 'status_badge', 'created_at']
    search_fields = ['name', 'normalized_name']
    list_filter = ['category_type', 'status']
    actions = [make_active, make_inactive]

    def status_badge(self, obj):
        color = "green" if obj.status == TaxonomyStatus.ACTIVE else "gray"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())
    status_badge.short_description = _("Status")


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ['canonical_name', 'category', 'skill_type', 'is_popular', 'status_badge', 'source']
    search_fields = ['name', 'canonical_name', 'normalized_name', 'aliases__alias']
    list_filter = ['status', 'skill_type', 'is_popular', 'category', 'source']
    actions = [make_active, make_inactive]

    def status_badge(self, obj):
        color = "green" if obj.status == TaxonomyStatus.ACTIVE else "gray"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())
    status_badge.short_description = _("Status")


@admin.register(Technology)
class TechnologyAdmin(admin.ModelAdmin):
    list_display = ['canonical_name', 'tech_category', 'vendor', 'status_badge', 'source']
    search_fields = ['name', 'canonical_name', 'normalized_name', 'vendor']
    list_filter = ['tech_category', 'status', 'source']
    actions = [make_active, make_inactive]

    def status_badge(self, obj):
        color = "green" if obj.status == TaxonomyStatus.ACTIVE else "gray"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())
    status_badge.short_description = _("Status")


@admin.register(Tool)
class ToolAdmin(admin.ModelAdmin):
    list_display = ['canonical_name', 'tool_type', 'vendor', 'status_badge', 'source']
    search_fields = ['name', 'canonical_name', 'normalized_name', 'vendor']
    list_filter = ['tool_type', 'status', 'source']
    actions = [make_active, make_inactive]

    def status_badge(self, obj):
        color = "green" if obj.status == TaxonomyStatus.ACTIVE else "gray"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())
    status_badge.short_description = _("Status")


@admin.register(Certification)
class CertificationAdmin(admin.ModelAdmin):
    list_display = ['canonical_name', 'issuing_organization', 'industry', 'status_badge']
    search_fields = ['name', 'canonical_name', 'issuing_organization']
    list_filter = ['industry', 'status']
    actions = [make_active, make_inactive]

    def status_badge(self, obj):
        color = "green" if obj.status == TaxonomyStatus.ACTIVE else "gray"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())
    status_badge.short_description = _("Status")


@admin.register(Qualification)
class QualificationAdmin(admin.ModelAdmin):
    list_display = ['canonical_name', 'degree_level', 'discipline', 'status_badge']
    search_fields = ['name', 'canonical_name', 'discipline']
    list_filter = ['degree_level', 'status']
    actions = [make_active, make_inactive]

    def status_badge(self, obj):
        color = "green" if obj.status == TaxonomyStatus.ACTIVE else "gray"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())
    status_badge.short_description = _("Status")


@admin.register(TaxonomyAlias)
class TaxonomyAliasAdmin(admin.ModelAdmin):
    list_display = ['alias', 'canonical_name', 'entity_type', 'alias_type', 'confidence', 'status_badge']
    search_fields = ['alias', 'normalized_alias', 'canonical_name']
    list_filter = ['entity_type', 'alias_type', 'status', 'source']
    actions = [make_active, make_inactive]

    def status_badge(self, obj):
        color = "green" if obj.status == TaxonomyStatus.ACTIVE else "gray"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())
    status_badge.short_description = _("Status")


@admin.register(RoleSkill)
class RoleSkillAdmin(admin.ModelAdmin):
    list_display = ['role', 'get_target', 'relation_type', 'weight', 'status_badge']
    search_fields = ['role__canonical_name', 'skill__canonical_name', 'technology__canonical_name', 'tool__canonical_name']
    list_filter = ['relation_type', 'status', 'source']
    autocomplete_fields = ['role', 'skill', 'technology', 'tool']
    actions = [make_active, make_inactive]

    def get_target(self, obj):
        return obj.skill or obj.technology or obj.tool or "N/A"
    get_target.short_description = _("Skill / Tool")

    def status_badge(self, obj):
        color = "green" if obj.status == TaxonomyStatus.ACTIVE else "gray"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())
    status_badge.short_description = _("Status")


@admin.register(RoleRelation)
class RoleRelationAdmin(admin.ModelAdmin):
    list_display = ['source_role', 'target_role', 'relation_type', 'weight', 'is_bidirectional', 'status_badge']
    search_fields = ['source_role__canonical_name', 'target_role__canonical_name']
    list_filter = ['relation_type', 'is_bidirectional', 'status', 'source']
    autocomplete_fields = ['source_role', 'target_role']
    actions = [make_active, make_inactive]

    def status_badge(self, obj):
        color = "green" if obj.status == TaxonomyStatus.ACTIVE else "gray"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())
    status_badge.short_description = _("Status")


@admin.register(TaxonomyImportLog)
class TaxonomyImportLogAdmin(admin.ModelAdmin):
    list_display = ['source_name', 'version', 'records_processed', 'records_created', 'status_badge', 'created_at']
    list_filter = ['status', 'source_name']
    readonly_fields = ['created_at', 'updated_at', 'statistics', 'error_details']

    def status_badge(self, obj):
        color = "green" if obj.status == TaxonomyImportLog.ImportStatus.SUCCESS else "red"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())
    status_badge.short_description = _("Status")
