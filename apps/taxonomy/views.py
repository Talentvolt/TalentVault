import re
import csv
import json
import io
from typing import Dict, Any, List, Optional
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from django.utils.text import slugify

from apps.taxonomy.models import (
    Industry, Department, JobFunction, JobRole, Specialization,
    SkillCategory, Skill, Technology, Tool, Certification, Qualification,
    TaxonomyAlias, RoleSkill, RoleRelation, RoleHierarchy, IndustryRole,
    TaxonomyImportLog, TaxonomyStatus, TaxonomySource
)
from apps.taxonomy.services.taxonomy_engine import TaxonomyEngine
from apps.taxonomy.services.taxonomy_importer import TaxonomyImporter
from apps.taxonomy.services.taxonomy_seeder import TaxonomySeeder


# Map tab key to model class and metadata
ENTITY_TYPE_CONFIG = {
    'roles': {
        'model': JobRole,
        'title': 'Job Titles & Roles',
        'singular': 'Job Role',
        'type_code': 'job_role',
        'icon': 'bi-briefcase-fill'
    },
    'skills': {
        'model': Skill,
        'title': 'Skills & Competencies',
        'singular': 'Skill',
        'type_code': 'skill',
        'icon': 'bi-stars'
    },
    'technologies': {
        'model': Technology,
        'title': 'Technologies & Tech Stacks',
        'singular': 'Technology',
        'type_code': 'technology',
        'icon': 'bi-cpu-fill'
    },
    'tools': {
        'model': Tool,
        'title': 'Tools & Platforms',
        'singular': 'Tool',
        'type_code': 'tool',
        'icon': 'bi-tools'
    },
    'departments': {
        'model': Department,
        'title': 'Departments & Divisions',
        'singular': 'Department',
        'type_code': 'department',
        'icon': 'bi-diagram-3-fill'
    },
    'functions': {
        'model': JobFunction,
        'title': 'Job Functions',
        'singular': 'Job Function',
        'type_code': 'job_function',
        'icon': 'bi-diagram-2-fill'
    },
    'industries': {
        'model': Industry,
        'title': 'Industries & Sectors',
        'singular': 'Industry',
        'type_code': 'industry',
        'icon': 'bi-building-fill'
    },
    'specializations': {
        'model': Specialization,
        'title': 'Specializations',
        'singular': 'Specialization',
        'type_code': 'specialization',
        'icon': 'bi-bullseye'
    },
    'qualifications': {
        'model': Qualification,
        'title': 'Education & Degrees',
        'singular': 'Qualification',
        'type_code': 'qualification',
        'icon': 'bi-mortarboard-fill'
    },
    'certifications': {
        'model': Certification,
        'title': 'Certifications & Accreditations',
        'singular': 'Certification',
        'type_code': 'certification',
        'icon': 'bi-patch-check-fill'
    },
    'aliases': {
        'model': TaxonomyAlias,
        'title': 'Synonyms & Aliases',
        'singular': 'Synonym / Alias',
        'type_code': 'alias',
        'icon': 'bi-arrow-left-right'
    },
    'relations': {
        'model': RoleRelation,
        'title': 'Role Relationships & Ontology',
        'singular': 'Role Relationship',
        'type_code': 'relation',
        'icon': 'bi-share-fill'
    },
    'logs': {
        'model': TaxonomyImportLog,
        'title': 'Import & Audit Logs',
        'singular': 'Import Log',
        'type_code': 'log',
        'icon': 'bi-journal-text'
    }
}


class TaxonomyDashboardView(LoginRequiredMixin, View):
    """
    Main Enterprise Taxonomy & Tagging Dashboard.
    Supports multi-category browsing, search, status filtering, relations, tree view, and live stats.
    """
    template_name = 'taxonomy/taxonomy_dashboard.html'

    def get(self, request, *args, **kwargs):
        # Auto seed if taxonomy is empty
        try:
            if not JobRole.objects.exists():
                TaxonomySeeder.seed_all()
        except Exception:
            pass

        current_tab = request.GET.get('tab', 'roles')
        if current_tab not in ENTITY_TYPE_CONFIG and current_tab != 'tree':
            current_tab = 'roles'

        query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', 'ALL')
        industry_filter = request.GET.get('industry', '')
        dept_filter = request.GET.get('department', '')

        # Global Statistics
        stats = {
            'total_roles': JobRole.objects.count(),
            'total_skills': Skill.objects.count(),
            'total_technologies': Technology.objects.count(),
            'total_tools': Tool.objects.count(),
            'total_departments': Department.objects.count(),
            'total_functions': JobFunction.objects.count(),
            'total_industries': Industry.objects.count(),
            'total_specializations': Specialization.objects.count(),
            'total_qualifications': Qualification.objects.count(),
            'total_certifications': Certification.objects.count(),
            'total_aliases': TaxonomyAlias.objects.count(),
            'total_relations': RoleRelation.objects.count() + RoleSkill.objects.count(),
        }
        stats['total_tags'] = (
            stats['total_roles'] + stats['total_skills'] + stats['total_technologies'] +
            stats['total_tools'] + stats['total_industries'] + stats['total_departments'] +
            stats['total_qualifications'] + stats['total_certifications']
        )

        seven_days_ago = timezone.now() - timezone.timedelta(days=7)
        stats['recently_updated'] = (
            JobRole.objects.filter(updated_at__gte=seven_days_ago).count() +
            Skill.objects.filter(updated_at__gte=seven_days_ago).count() +
            TaxonomyAlias.objects.filter(updated_at__gte=seven_days_ago).count()
        )

        # Tab Specific Queryset
        items = []
        page_obj = None
        current_config = ENTITY_TYPE_CONFIG.get(current_tab, ENTITY_TYPE_CONFIG['roles'])

        if current_tab != 'tree':
            model = current_config['model']
            qs = model.objects.all()

            # Status Filter
            if hasattr(model, 'status') and status_filter and status_filter != 'ALL':
                qs = qs.filter(status=status_filter)

            # Search Query Filter
            if query:
                if current_tab == 'aliases':
                    qs = qs.filter(Q(alias__icontains=query) | Q(canonical_name__icontains=query) | Q(normalized_alias__icontains=query))
                elif current_tab == 'relations':
                    qs = qs.filter(Q(source_role__canonical_name__icontains=query) | Q(target_role__canonical_name__icontains=query))
                elif current_tab == 'logs':
                    qs = qs.filter(Q(source_name__icontains=query) | Q(file_name__icontains=query))
                else:
                    q_filter = Q(name__icontains=query) | Q(normalized_name__icontains=query)
                    if hasattr(model, 'canonical_name'):
                        q_filter |= Q(canonical_name__icontains=query)
                    if hasattr(model, 'code') and model.code:
                        q_filter |= Q(code__icontains=query)
                    qs = qs.filter(q_filter)

            # Extra Filters for Job Roles / Functions
            if current_tab == 'roles':
                if industry_filter:
                    qs = qs.filter(industry_id=industry_filter)
                if dept_filter:
                    qs = qs.filter(department_id=dept_filter)
                qs = qs.select_related('industry', 'department', 'job_function').prefetch_related('aliases', 'role_skills')
            elif current_tab == 'skills':
                qs = qs.select_related('category').prefetch_related('aliases')
            elif current_tab == 'aliases':
                qs = qs.select_related('job_role', 'skill', 'technology', 'tool')
            elif current_tab == 'relations':
                qs = qs.select_related('source_role', 'target_role')

            # Pagination
            paginator = Paginator(qs, 25)
            page_number = request.GET.get('page', 1)
            page_obj = paginator.get_page(page_number)
            items = page_obj.object_list

        # Lookup Lists for Modals & Filters
        industries_list = Industry.objects.filter(status=TaxonomyStatus.ACTIVE).order_by('name')
        departments_list = Department.objects.filter(status=TaxonomyStatus.ACTIVE).order_by('name')
        skill_categories = SkillCategory.objects.filter(status=TaxonomyStatus.ACTIVE).order_by('name')
        job_roles_dropdown = JobRole.objects.filter(status=TaxonomyStatus.ACTIVE).order_by('canonical_name')[:100]

        context = {
            'current_tab': current_tab,
            'current_config': current_config,
            'stats': stats,
            'items': items,
            'page_obj': page_obj,
            'is_paginated': page_obj.has_other_pages() if page_obj else False,
            'query': query,
            'status_filter': status_filter,
            'industry_filter': industry_filter,
            'dept_filter': dept_filter,
            'industries_list': industries_list,
            'departments_list': departments_list,
            'skill_categories': skill_categories,
            'job_roles_dropdown': job_roles_dropdown,
            'entity_configs': ENTITY_TYPE_CONFIG,
        }
        return render(request, self.template_name, context)


class TaxonomyEntityCreateView(LoginRequiredMixin, View):
    """
    POST /taxonomy/entities/create/
    Creates a new taxonomy entity (Role, Skill, Tech, Tool, Dept, Industry, etc.)
    with automatic normalization, duplicate prevention, and optional alias generation.
    """
    def post(self, request, *args, **kwargs):
        entity_type = request.POST.get('entity_type', 'job_role')
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        status = request.POST.get('status', TaxonomyStatus.ACTIVE)
        source = request.POST.get('source', TaxonomySource.MANUAL)
        aliases_raw = request.POST.get('aliases', '').strip()

        if not name:
            messages.error(request, "Name is required.")
            return redirect(f"{request.META.get('HTTP_REFERER', '/taxonomy/')}?tab={entity_type}s")

        normalized = re.sub(r'\s+', ' ', name.lower())

        try:
            created_entity = None
            if entity_type == 'job_role':
                seniority = request.POST.get('seniority', JobRole.SeniorityLevel.MID)
                experience = request.POST.get('typical_experience', JobRole.ExperienceLevel.MID_CAREER)
                industry_id = request.POST.get('industry_id')
                department_id = request.POST.get('department_id')
                weight = float(request.POST.get('weight', 1.0))

                existing = JobRole.objects.filter(normalized_name=normalized).first()
                if existing:
                    messages.warning(request, f"Job Role '{name}' already exists as canonical name '{existing.canonical_name}'.")
                    return redirect(f"/taxonomy/?tab=roles&q={name}")

                created_entity = JobRole.objects.create(
                    name=name,
                    canonical_name=name,
                    normalized_name=normalized,
                    description=description,
                    seniority=seniority,
                    typical_experience=experience,
                    industry_id=industry_id if industry_id else None,
                    department_id=department_id if department_id else None,
                    weight=weight,
                    status=status,
                    source=source
                )

                # Parent Role Link
                parent_role_id = request.POST.get('parent_role_id')
                if parent_role_id:
                    parent_role = JobRole.objects.filter(id=parent_role_id).first()
                    if parent_role:
                        RoleRelation.objects.get_or_create(
                            source_role=parent_role,
                            target_role=created_entity,
                            relation_type=RoleRelation.RelationType.CHILD_ROLE,
                            defaults={'weight': 0.95, 'source': source}
                        )

            elif entity_type == 'skill':
                category_id = request.POST.get('category_id')
                skill_type = request.POST.get('skill_type', Skill.SkillType.HARD_SKILL)
                is_popular = request.POST.get('is_popular') == '1'

                existing = Skill.objects.filter(normalized_name=normalized).first()
                if existing:
                    messages.warning(request, f"Skill '{name}' already exists.")
                    return redirect(f"/taxonomy/?tab=skills&q={name}")

                created_entity = Skill.objects.create(
                    name=name,
                    canonical_name=name,
                    normalized_name=normalized,
                    description=description,
                    category_id=category_id if category_id else None,
                    skill_type=skill_type,
                    is_popular=is_popular,
                    status=status,
                    source=source
                )

            elif entity_type == 'technology':
                tech_category = request.POST.get('tech_category', Technology.TechCategory.FRAMEWORK)
                vendor = request.POST.get('vendor', '').strip()

                created_entity, created = Technology.objects.get_or_create(
                    normalized_name=normalized,
                    defaults={
                        'name': name,
                        'canonical_name': name,
                        'description': description,
                        'tech_category': tech_category,
                        'vendor': vendor,
                        'status': status,
                        'source': source
                    }
                )

            elif entity_type == 'tool':
                tool_type = request.POST.get('tool_type', Tool.ToolType.ANALYTICS)
                vendor = request.POST.get('vendor', '').strip()

                created_entity, created = Tool.objects.get_or_create(
                    normalized_name=normalized,
                    defaults={
                        'name': name,
                        'canonical_name': name,
                        'description': description,
                        'tool_type': tool_type,
                        'vendor': vendor,
                        'status': status,
                        'source': source
                    }
                )

            elif entity_type == 'department':
                created_entity, created = Department.objects.get_or_create(
                    normalized_name=normalized,
                    defaults={'name': name, 'description': description, 'status': status, 'source': source}
                )

            elif entity_type == 'industry':
                created_entity, created = Industry.objects.get_or_create(
                    normalized_name=normalized,
                    defaults={'name': name, 'description': description, 'status': status, 'source': source}
                )

            elif entity_type == 'qualification':
                degree_level = request.POST.get('degree_level', Qualification.DegreeLevel.BACHELORS)
                discipline = request.POST.get('discipline', '').strip()
                created_entity, created = Qualification.objects.get_or_create(
                    normalized_name=normalized,
                    defaults={'name': name, 'canonical_name': name, 'degree_level': degree_level, 'discipline': discipline, 'status': status, 'source': source}
                )

            elif entity_type == 'certification':
                issuing_org = request.POST.get('issuing_organization', '').strip()
                industry_id = request.POST.get('industry_id')
                created_entity, created = Certification.objects.get_or_create(
                    normalized_name=normalized,
                    defaults={'name': name, 'canonical_name': name, 'issuing_organization': issuing_org, 'industry_id': industry_id or None, 'status': status, 'source': source}
                )

            # Process comma-separated aliases if provided
            if created_entity and aliases_raw:
                alias_items = [a.strip() for a in aliases_raw.split(',') if a.strip()]
                for a in alias_items:
                    a_norm = re.sub(r'\s+', ' ', a.lower())
                    if a_norm != normalized:
                        TaxonomyAlias.objects.get_or_create(
                            normalized_alias=a_norm,
                            entity_type=TaxonomyAlias.EntityType.JOB_ROLE if entity_type == 'job_role' else (
                                TaxonomyAlias.EntityType.SKILL if entity_type == 'skill' else TaxonomyAlias.EntityType.TECHNOLOGY
                            ),
                            canonical_name=name,
                            defaults={
                                'alias': a,
                                'job_role': created_entity if entity_type == 'job_role' else None,
                                'skill': created_entity if entity_type == 'skill' else None,
                                'technology': created_entity if entity_type == 'technology' else None,
                                'alias_type': TaxonomyAlias.AliasType.SYNONYM,
                                'confidence': 0.95,
                                'status': TaxonomyStatus.ACTIVE,
                                'source': source
                            }
                        )

            messages.success(request, f"Successfully created {entity_type.replace('_', ' ').title()}: '{name}'")
        except Exception as e:
            messages.error(request, f"Error creating entity: {str(e)}")

        tab_redirect = 'roles' if entity_type == 'job_role' else f"{entity_type}s"
        return redirect(f"/taxonomy/?tab={tab_redirect}")


class TaxonomyEntityEditView(LoginRequiredMixin, View):
    """
    POST /taxonomy/entities/<str:entity_type>/<uuid:entity_id>/edit/
    Updates fields of an existing taxonomy entity.
    """
    def post(self, request, entity_type, entity_id, *args, **kwargs):
        config = ENTITY_TYPE_CONFIG.get(entity_type) or ENTITY_TYPE_CONFIG.get(f"{entity_type}s")
        if not config:
            messages.error(request, "Invalid entity type.")
            return redirect('/taxonomy/')

        model = config['model']
        instance = get_object_or_404(model, id=entity_id)

        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        status = request.POST.get('status', instance.status if hasattr(instance, 'status') else TaxonomyStatus.ACTIVE)

        if name:
            instance.name = name
            if hasattr(instance, 'canonical_name'):
                instance.canonical_name = name
            instance.normalized_name = re.sub(r'\s+', ' ', name.lower())

        if hasattr(instance, 'description'):
            instance.description = description
        if hasattr(instance, 'status'):
            instance.status = status

        # Role specific fields
        if hasattr(instance, 'seniority') and request.POST.get('seniority'):
            instance.seniority = request.POST.get('seniority')
        if hasattr(instance, 'typical_experience') and request.POST.get('typical_experience'):
            instance.typical_experience = request.POST.get('typical_experience')
        if hasattr(instance, 'weight') and request.POST.get('weight'):
            try: instance.weight = float(request.POST.get('weight'))
            except: pass
        if hasattr(instance, 'industry_id') and 'industry_id' in request.POST:
            instance.industry_id = request.POST.get('industry_id') or None
        if hasattr(instance, 'department_id') and 'department_id' in request.POST:
            instance.department_id = request.POST.get('department_id') or None

        instance.save()
        messages.success(request, f"Updated {config['singular']}: '{name or instance}'")
        return redirect(request.META.get('HTTP_REFERER', '/taxonomy/'))


class TaxonomyEntityStatusToggleView(LoginRequiredMixin, View):
    """
    POST /taxonomy/entities/<str:entity_type>/<uuid:entity_id>/toggle-status/
    Toggles status between ACTIVE and INACTIVE.
    """
    def post(self, request, entity_type, entity_id, *args, **kwargs):
        config = ENTITY_TYPE_CONFIG.get(entity_type) or ENTITY_TYPE_CONFIG.get(f"{entity_type}s")
        if not config:
            return JsonResponse({'success': False, 'error': 'Invalid entity type'})

        model = config['model']
        instance = get_object_or_404(model, id=entity_id)

        if hasattr(instance, 'status'):
            instance.status = TaxonomyStatus.INACTIVE if instance.status == TaxonomyStatus.ACTIVE else TaxonomyStatus.ACTIVE
            instance.save()
            messages.success(request, f"Status updated to {instance.status} for '{instance}'")
            return redirect(request.META.get('HTTP_REFERER', '/taxonomy/'))

        return redirect('/taxonomy/')


class TaxonomyEntityDeleteView(LoginRequiredMixin, View):
    """
    POST /taxonomy/entities/<str:entity_type>/<uuid:entity_id>/delete/
    Soft-deletes (sets INACTIVE) or deletes a taxonomy entity.
    """
    def post(self, request, entity_type, entity_id, *args, **kwargs):
        config = ENTITY_TYPE_CONFIG.get(entity_type) or ENTITY_TYPE_CONFIG.get(f"{entity_type}s")
        if not config:
            messages.error(request, "Invalid entity type.")
            return redirect('/taxonomy/')

        model = config['model']
        instance = get_object_or_404(model, id=entity_id)
        name_str = str(instance)

        # Soft delete
        if hasattr(instance, 'status'):
            instance.status = TaxonomyStatus.INACTIVE
            instance.save()
            messages.info(request, f"Deactivated {config['singular']}: '{name_str}'")
        else:
            instance.delete()
            messages.info(request, f"Deleted {config['singular']}: '{name_str}'")

        return redirect(request.META.get('HTTP_REFERER', '/taxonomy/'))


class TaxonomyEntityDetailAPIView(LoginRequiredMixin, View):
    """
    GET /taxonomy/entities/<str:entity_type>/<uuid:entity_id>/detail-json/
    Returns full profile, relationships, aliases, and usage statistics for the slide-over details drawer.
    """
    def get(self, request, entity_type, entity_id, *args, **kwargs):
        config = ENTITY_TYPE_CONFIG.get(entity_type) or ENTITY_TYPE_CONFIG.get(f"{entity_type}s")
        if not config:
            return JsonResponse({'error': 'Invalid entity type'}, status=400)

        model = config['model']
        instance = get_object_or_404(model, id=entity_id)

        data = {
            'id': str(instance.id),
            'name': getattr(instance, 'canonical_name', getattr(instance, 'name', str(instance))),
            'normalized_name': getattr(instance, 'normalized_name', ''),
            'entity_type': config['singular'],
            'type_code': config['type_code'],
            'status': getattr(instance, 'status', 'ACTIVE'),
            'description': getattr(instance, 'description', ''),
            'source': getattr(instance, 'source', 'TV_URT'),
            'created_at': instance.created_at.strftime('%b %d, %Y') if hasattr(instance, 'created_at') else '',
            'updated_at': instance.updated_at.strftime('%b %d, %Y') if hasattr(instance, 'updated_at') else '',
            'aliases': [],
            'related_skills': [],
            'related_roles': [],
            'parent_roles': [],
            'child_roles': [],
            'candidate_usage_count': 0
        }

        # Role specific details
        if isinstance(instance, JobRole):
            data['seniority'] = instance.get_seniority_display()
            data['experience'] = instance.get_typical_experience_display()
            data['industry'] = instance.industry.name if instance.industry else 'Universal / Multi-Industry'
            data['department'] = instance.department.name if instance.department else 'Universal'
            data['weight'] = instance.weight

            # Aliases
            for a in instance.aliases.filter(status=TaxonomyStatus.ACTIVE):
                data['aliases'].append({
                    'id': str(a.id),
                    'alias': a.alias,
                    'type': a.get_alias_type_display(),
                    'confidence': a.confidence
                })

            # Skills
            for rs in instance.role_skills.filter(status=TaxonomyStatus.ACTIVE).select_related('skill', 'technology', 'tool'):
                target_name = rs.skill.canonical_name if rs.skill else (rs.technology.canonical_name if rs.technology else (rs.tool.canonical_name if rs.tool else ''))
                if target_name:
                    data['related_skills'].append({
                        'id': str(rs.id),
                        'name': target_name,
                        'relation_type': rs.get_relation_type_display(),
                        'weight': rs.weight
                    })

            # Role Relations
            for rel in instance.outgoing_role_relations.filter(status=TaxonomyStatus.ACTIVE).select_related('target_role'):
                data['related_roles'].append({
                    'id': str(rel.id),
                    'target_name': rel.target_role.canonical_name,
                    'relation_type': rel.get_relation_type_display(),
                    'weight': rel.weight
                })

            # Candidate usage estimation
            from apps.candidates.models import CandidateProfile
            data['candidate_usage_count'] = CandidateProfile.objects.filter(
                Q(current_designation__icontains=instance.canonical_name) |
                Q(matched_tags__contains=[instance.canonical_name])
            ).count()

        elif isinstance(instance, Skill):
            data['category'] = instance.category.name if instance.category else 'General Skill'
            data['skill_type'] = instance.get_skill_type_display()
            data['is_popular'] = instance.is_popular

            for a in instance.aliases.filter(status=TaxonomyStatus.ACTIVE):
                data['aliases'].append({
                    'id': str(a.id),
                    'alias': a.alias,
                    'type': a.get_alias_type_display(),
                    'confidence': a.confidence
                })

            from apps.candidates.models import CandidateSkill
            data['candidate_usage_count'] = CandidateSkill.objects.filter(skill_name__iexact=instance.canonical_name).count()

        elif isinstance(instance, Technology):
            data['tech_category'] = instance.get_tech_category_display()
            data['vendor'] = instance.vendor

            for a in instance.aliases.filter(status=TaxonomyStatus.ACTIVE):
                data['aliases'].append({
                    'id': str(a.id),
                    'alias': a.alias,
                    'type': a.get_alias_type_display(),
                    'confidence': a.confidence
                })

        return JsonResponse(data)


class TaxonomyAliasCreateView(LoginRequiredMixin, View):
    """
    POST /taxonomy/aliases/create/
    Creates a new synonym/alias mapping.
    """
    def post(self, request, *args, **kwargs):
        alias = request.POST.get('alias', '').strip()
        canonical_name = request.POST.get('canonical_name', '').strip()
        entity_type = request.POST.get('entity_type', TaxonomyAlias.EntityType.JOB_ROLE)
        alias_type = request.POST.get('alias_type', TaxonomyAlias.AliasType.SYNONYM)
        confidence = float(request.POST.get('confidence', 0.95))
        job_role_id = request.POST.get('job_role_id')

        if not alias or not canonical_name:
            messages.error(request, "Both Alias/Original Term and Canonical Name are required.")
            return redirect(request.META.get('HTTP_REFERER', '/taxonomy/?tab=aliases'))

        normalized = re.sub(r'\s+', ' ', alias.lower())
        job_role = JobRole.objects.filter(id=job_role_id).first() if job_role_id else None
        if not job_role:
            job_role = JobRole.objects.filter(canonical_name__iexact=canonical_name).first()

        TaxonomyAlias.objects.get_or_create(
            normalized_alias=normalized,
            entity_type=entity_type,
            canonical_name=canonical_name,
            defaults={
                'alias': alias,
                'job_role': job_role,
                'alias_type': alias_type,
                'confidence': confidence,
                'status': TaxonomyStatus.ACTIVE,
                'source': TaxonomySource.MANUAL
            }
        )

        messages.success(request, f"Mapped alias '{alias}' -> '{canonical_name}' ({alias_type})")
        return redirect(request.META.get('HTTP_REFERER', '/taxonomy/?tab=aliases'))


class TaxonomyAliasDeleteView(LoginRequiredMixin, View):
    """
    POST /taxonomy/aliases/<uuid:alias_id>/delete/
    """
    def post(self, request, alias_id, *args, **kwargs):
        alias = get_object_or_404(TaxonomyAlias, id=alias_id)
        alias_str = str(alias)
        alias.delete()
        messages.info(request, f"Deleted alias: {alias_str}")
        return redirect(request.META.get('HTTP_REFERER', '/taxonomy/?tab=aliases'))


class TaxonomyRelationshipCreateView(LoginRequiredMixin, View):
    """
    POST /taxonomy/relationships/create/
    Creates a Role <-> Role or Role <-> Skill relationship.
    """
    def post(self, request, *args, **kwargs):
        rel_category = request.POST.get('relationship_category', 'role_to_role')
        source_role_id = request.POST.get('source_role_id')
        source_role = get_object_or_404(JobRole, id=source_role_id)

        if rel_category == 'role_to_role':
            target_role_id = request.POST.get('target_role_id')
            relation_type = request.POST.get('relation_type', RoleRelation.RelationType.RELATED_ROLE)
            weight = float(request.POST.get('weight', 0.85))
            target_role = get_object_or_404(JobRole, id=target_role_id)

            RoleRelation.objects.get_or_create(
                source_role=source_role,
                target_role=target_role,
                relation_type=relation_type,
                defaults={'weight': weight, 'source': TaxonomySource.MANUAL}
            )
            messages.success(request, f"Created relation: {source_role.canonical_name} -> {target_role.canonical_name} ({relation_type})")

        elif rel_category == 'role_to_skill':
            skill_name = request.POST.get('skill_name', '').strip()
            relation_type = request.POST.get('skill_relation_type', RoleSkill.RelationType.PRIMARY_SKILL)
            weight = float(request.POST.get('skill_weight', 0.90))

            skill = Skill.objects.filter(canonical_name__iexact=skill_name).first()
            if not skill:
                skill = Skill.objects.create(
                    name=skill_name,
                    canonical_name=skill_name,
                    normalized_name=re.sub(r'\s+', ' ', skill_name.lower()),
                    source=TaxonomySource.MANUAL
                )

            RoleSkill.objects.get_or_create(
                role=source_role,
                skill=skill,
                relation_type=relation_type,
                defaults={'weight': weight, 'source': TaxonomySource.MANUAL}
            )
            messages.success(request, f"Mapped skill '{skill.canonical_name}' to role '{source_role.canonical_name}'")

        return redirect(request.META.get('HTTP_REFERER', '/taxonomy/?tab=relations'))


class TaxonomyRelationshipDeleteView(LoginRequiredMixin, View):
    """
    POST /taxonomy/relationships/<uuid:rel_id>/delete/
    """
    def post(self, request, rel_id, *args, **kwargs):
        rel = RoleRelation.objects.filter(id=rel_id).first()
        if not rel:
            rel = RoleSkill.objects.filter(id=rel_id).first()
        if rel:
            rel_str = str(rel)
            rel.delete()
            messages.info(request, f"Deleted relationship: {rel_str}")
        return redirect(request.META.get('HTTP_REFERER', '/taxonomy/?tab=relations'))


class TaxonomyMergeView(LoginRequiredMixin, View):
    """
    POST /taxonomy/merge/
    Merges duplicate or variant entity into canonical entity.
    """
    def post(self, request, *args, **kwargs):
        entity_type = request.POST.get('entity_type', 'job_role')
        source_id = request.POST.get('source_entity_id')
        target_id = request.POST.get('target_entity_id')

        if not source_id or not target_id or source_id == target_id:
            messages.error(request, "Please select distinct source and target entities to merge.")
            return redirect(request.META.get('HTTP_REFERER', '/taxonomy/'))

        if entity_type == 'job_role':
            source_role = get_object_or_404(JobRole, id=source_id)
            target_role = get_object_or_404(JobRole, id=target_id)

            # Re-map aliases
            TaxonomyAlias.objects.filter(job_role=source_role).update(
                job_role=target_role,
                canonical_name=target_role.canonical_name
            )

            # Convert source role name into an alias for target
            TaxonomyAlias.objects.get_or_create(
                normalized_alias=source_role.normalized_name,
                entity_type=TaxonomyAlias.EntityType.JOB_ROLE,
                canonical_name=target_role.canonical_name,
                defaults={
                    'alias': source_role.canonical_name,
                    'job_role': target_role,
                    'alias_type': TaxonomyAlias.AliasType.SYNONYM,
                    'confidence': 0.95,
                    'status': TaxonomyStatus.ACTIVE,
                    'source': TaxonomySource.MANUAL
                }
            )

            # Re-map role skills
            for rs in source_role.role_skills.all():
                RoleSkill.objects.get_or_create(
                    role=target_role,
                    skill=rs.skill,
                    technology=rs.technology,
                    tool=rs.tool,
                    relation_type=rs.relation_type,
                    defaults={'weight': rs.weight}
                )

            # Deactivate source role
            source_role.status = TaxonomyStatus.INACTIVE
            source_role.description = f"Merged into {target_role.canonical_name} on {timezone.now().strftime('%Y-%m-%d')}"
            source_role.save()

            messages.success(request, f"Successfully merged '{source_role.canonical_name}' into '{target_role.canonical_name}'")

        elif entity_type == 'skill':
            source_skill = get_object_or_404(Skill, id=source_id)
            target_skill = get_object_or_404(Skill, id=target_id)

            TaxonomyAlias.objects.filter(skill=source_skill).update(
                skill=target_skill,
                canonical_name=target_skill.canonical_name
            )

            TaxonomyAlias.objects.get_or_create(
                normalized_alias=source_skill.normalized_name,
                entity_type=TaxonomyAlias.EntityType.SKILL,
                canonical_name=target_skill.canonical_name,
                defaults={
                    'alias': source_skill.canonical_name,
                    'skill': target_skill,
                    'alias_type': TaxonomyAlias.AliasType.SYNONYM,
                    'confidence': 0.95,
                    'status': TaxonomyStatus.ACTIVE
                }
            )

            source_skill.status = TaxonomyStatus.INACTIVE
            source_skill.save()
            messages.success(request, f"Successfully merged skill '{source_skill.canonical_name}' into '{target_skill.canonical_name}'")

        return redirect(request.META.get('HTTP_REFERER', '/taxonomy/'))


class TaxonomyImportView(LoginRequiredMixin, View):
    """
    POST /taxonomy/import/
    CSV / JSON Bulk Taxonomy Importer with dry-run duplicate detection.
    """
    def post(self, request, *args, **kwargs):
        import_file = request.FILES.get('taxonomy_file')
        if not import_file:
            messages.error(request, "Please choose a CSV or JSON taxonomy file to import.")
            return redirect('/taxonomy/?tab=logs')

        file_name = import_file.name
        is_json = file_name.endswith('.json')
        is_csv = file_name.endswith('.csv') or file_name.endswith('.txt')

        if not is_json and not is_csv:
            messages.error(request, "Supported formats are CSV and JSON.")
            return redirect('/taxonomy/?tab=logs')

        created_count = 0
        updated_count = 0
        skipped_count = 0
        errors = []

        try:
            content = import_file.read().decode('utf-8', errors='ignore')

            if is_json:
                data = json.loads(content)
                records = data if isinstance(data, list) else data.get('records', [])
                for r in records:
                    cat = r.get('category', 'job_role').lower()
                    name = r.get('name', '').strip()
                    if not name:
                        skipped_count += 1
                        continue

                    norm = re.sub(r'\s+', ' ', name.lower())
                    if cat in ('job_role', 'role', 'job_title'):
                        obj, created = JobRole.objects.get_or_create(
                            normalized_name=norm,
                            defaults={
                                'name': name,
                                'canonical_name': name,
                                'seniority': r.get('seniority', JobRole.SeniorityLevel.MID),
                                'status': r.get('status', TaxonomyStatus.ACTIVE),
                                'source': TaxonomySource.MANUAL
                            }
                        )
                        if created: created_count += 1
                        else: skipped_count += 1
                    elif cat == 'skill':
                        obj, created = Skill.objects.get_or_create(
                            normalized_name=norm,
                            defaults={'name': name, 'canonical_name': name, 'source': TaxonomySource.MANUAL}
                        )
                        if created: created_count += 1
                        else: skipped_count += 1

            elif is_csv:
                reader = csv.DictReader(io.StringIO(content))
                for row in reader:
                    cat = (row.get('category') or row.get('type') or 'job_role').strip().lower()
                    name = (row.get('name') or row.get('canonical_name') or row.get('title') or '').strip()
                    if not name:
                        skipped_count += 1
                        continue

                    norm = re.sub(r'\s+', ' ', name.lower())
                    aliases = [a.strip() for a in (row.get('aliases') or row.get('synonyms') or '').split('|') if a.strip()]

                    if cat in ('job_role', 'role', 'job_title'):
                        obj, created = JobRole.objects.get_or_create(
                            normalized_name=norm,
                            defaults={
                                'name': name,
                                'canonical_name': name,
                                'seniority': row.get('seniority', JobRole.SeniorityLevel.MID),
                                'source': TaxonomySource.MANUAL
                            }
                        )
                        if created:
                            created_count += 1
                            for al in aliases:
                                TaxonomyAlias.objects.get_or_create(
                                    normalized_alias=re.sub(r'\s+', ' ', al.lower()),
                                    entity_type=TaxonomyAlias.EntityType.JOB_ROLE,
                                    canonical_name=name,
                                    defaults={'alias': al, 'job_role': obj, 'source': TaxonomySource.MANUAL}
                                )
                        else:
                            skipped_count += 1

                    elif cat == 'skill':
                        obj, created = Skill.objects.get_or_create(
                            normalized_name=norm,
                            defaults={'name': name, 'canonical_name': name, 'source': TaxonomySource.MANUAL}
                        )
                        if created: created_count += 1
                        else: skipped_count += 1

            # Log import audit
            TaxonomyImportLog.objects.create(
                source_name="Manual User Import",
                file_name=file_name,
                records_processed=created_count + updated_count + skipped_count,
                records_created=created_count,
                records_updated=updated_count,
                duplicates_skipped=skipped_count,
                status=TaxonomyImportLog.ImportStatus.SUCCESS if not errors else TaxonomyImportLog.ImportStatus.PARTIAL,
                error_details=errors
            )

            messages.success(request, f"Import complete: {created_count} created, {skipped_count} duplicates skipped.")
        except Exception as e:
            messages.error(request, f"Import failed: {str(e)}")

        return redirect('/taxonomy/?tab=logs')


class TaxonomyExportView(LoginRequiredMixin, View):
    """
    GET /taxonomy/export/?category=roles&format=csv
    Exports taxonomy records as downloadable CSV or JSON.
    """
    def get(self, request, *args, **kwargs):
        category = request.GET.get('category', 'roles')
        fmt = request.GET.get('format', 'csv')

        config = ENTITY_TYPE_CONFIG.get(category, ENTITY_TYPE_CONFIG['roles'])
        model = config['model']
        qs = model.objects.filter(status=TaxonomyStatus.ACTIVE) if hasattr(model, 'status') else model.objects.all()

        if fmt == 'json':
            data = []
            for item in qs[:1000]:
                data.append({
                    'id': str(item.id),
                    'name': getattr(item, 'canonical_name', getattr(item, 'name', str(item))),
                    'normalized_name': getattr(item, 'normalized_name', ''),
                    'status': getattr(item, 'status', 'ACTIVE')
                })
            response = HttpResponse(json.dumps(data, indent=2), content_type='application/json')
            response['Content-Disposition'] = f'attachment; filename="talentvault_{category}_export.json"'
            return response

        # Default CSV Export
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="talentvault_{category}_export.csv"'

        writer = csv.writer(response)
        writer.writerow(['Category', 'Name', 'Canonical Name', 'Normalized Name', 'Status', 'Source'])

        for item in qs[:5000]:
            writer.writerow([
                config['singular'],
                getattr(item, 'name', str(item)),
                getattr(item, 'canonical_name', getattr(item, 'name', str(item))),
                getattr(item, 'normalized_name', ''),
                getattr(item, 'status', 'ACTIVE'),
                getattr(item, 'source', 'TV_URT')
            ])

        return response


class TaxonomySeedView(LoginRequiredMixin, View):
    """
    POST /taxonomy/seed/
    Idempotently seeds multi-domain employment taxonomy.
    """
    def post(self, request, *args, **kwargs):
        try:
            TaxonomySeeder.seed_all()
            messages.success(request, "TalentVault Universal Recruitment Taxonomy (TV-URT) seeded successfully across 50+ sectors!")
        except Exception as e:
            messages.error(request, f"Seeding failed: {str(e)}")
        return redirect('/taxonomy/')


class TaxonomyTreeView(LoginRequiredMixin, View):
    """
    Renders visual tree navigation for Job Titles and Seniority Ladders.
    """
    def get(self, request, *args, **kwargs):
        return redirect('/taxonomy/?tab=tree')


class TaxonomyTreeDataAPIView(View):
    """
    GET /taxonomy/api/tree-data/
    Returns hierarchical tree JSON of Industry -> Department -> Roles -> Subordinates.
    """
    def get(self, request, *args, **kwargs):
        tree = []
        departments = Department.objects.filter(status=TaxonomyStatus.ACTIVE).prefetch_related('job_roles')

        for dept in departments:
            dept_node = {
                'id': str(dept.id),
                'name': dept.name,
                'type': 'department',
                'children': []
            }
            # Top-level roles in department
            roles = dept.job_roles.filter(status=TaxonomyStatus.ACTIVE).prefetch_related('outgoing_role_relations__target_role')
            for role in roles:
                sub_roles = [
                    {'id': str(rel.target_role.id), 'name': rel.target_role.canonical_name, 'type': 'sub_role'}
                    for rel in role.outgoing_role_relations.filter(relation_type=RoleRelation.RelationType.CHILD_ROLE, status=TaxonomyStatus.ACTIVE)
                ]
                dept_node['children'].append({
                    'id': str(role.id),
                    'name': role.canonical_name,
                    'seniority': role.get_seniority_display(),
                    'type': 'job_role',
                    'children': sub_roles
                })
            tree.append(dept_node)

        return JsonResponse({'tree': tree})


class TaxonomyCheckDuplicateAPIView(View):
    """
    GET /taxonomy/api/check-duplicate/?name=Sales+Manager&type=job_role
    Checks for exact or partial duplicate entities and aliases.
    """
    def get(self, request, *args, **kwargs):
        name = request.GET.get('name', '').strip()
        entity_type = request.GET.get('type', 'job_role')
        if not name:
            return JsonResponse({'has_duplicate': False, 'matches': []})

        norm = re.sub(r'\s+', ' ', name.lower())
        matches = []

        if entity_type == 'job_role':
            for r in JobRole.objects.filter(Q(normalized_name=norm) | Q(canonical_name__icontains=name))[:5]:
                matches.append({'id': str(r.id), 'name': r.canonical_name, 'type': 'Canonical Role'})
            for a in TaxonomyAlias.objects.filter(normalized_alias=norm, entity_type=TaxonomyAlias.EntityType.JOB_ROLE)[:5]:
                matches.append({'id': str(a.id), 'name': a.alias, 'type': f"Alias -> {a.canonical_name}"})
        elif entity_type == 'skill':
            for s in Skill.objects.filter(Q(normalized_name=norm) | Q(canonical_name__icontains=name))[:5]:
                matches.append({'id': str(s.id), 'name': s.canonical_name, 'type': 'Canonical Skill'})

        return JsonResponse({
            'has_duplicate': len(matches) > 0,
            'matches': matches
        })


# Existing Search Autocomplete APIs
class TaxonomySuggestionsAPIView(View):
    """
    GET /api/taxonomy/suggestions/?q=data&tags=...
    """
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '').strip()
        tags_raw = request.GET.getlist('tags')
        limit = int(request.GET.get('limit', 15))

        data = TaxonomyEngine.get_smart_suggestions(query=query, active_tags=tags_raw, limit=limit)
        return JsonResponse(data, safe=False)


class TaxonomyRolesAPIView(View):
    """
    GET /api/taxonomy/roles/?q=manager
    """
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '').strip()
        limit = int(request.GET.get('limit', 10))
        results = TaxonomyEngine.get_role_autocomplete(query=query, limit=limit)
        return JsonResponse({"query": query, "count": len(results), "results": results})


class TaxonomySkillsAPIView(View):
    """
    GET /api/taxonomy/skills/?q=python
    """
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '').strip()
        limit = int(request.GET.get('limit', 10))
        results = TaxonomyEngine.get_skill_autocomplete(query=query, limit=limit)
        return JsonResponse({"query": query, "count": len(results), "results": results})


class TaxonomyJobSuggestionsAPIView(View):
    """
    GET /api/taxonomy/job-suggestions/?title=React Developer
    """
    def get(self, request, *args, **kwargs):
        title = request.GET.get('title', '').strip()
        limit = int(request.GET.get('limit', 10))
        data = TaxonomyEngine.get_job_posting_suggestions(job_title=title, limit=limit)
        return JsonResponse(data)


class TaxonomyStatsAPIView(View):
    """
    GET /api/taxonomy/stats/
    """
    def get(self, request, *args, **kwargs):
        stats = TaxonomyImporter.get_summary_statistics()
        return JsonResponse(stats)
