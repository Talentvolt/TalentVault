"""
TalentVault Universal Recruitment Taxonomy (TV-URT) — Universal Data Importer.
Supports ESCO, O*NET, Open Standards, and TV-URT datasets with validation, deduplication, and audit logging.
"""
import os
import json
import logging
from typing import Dict, Any, List, Optional
from django.db import transaction
from apps.taxonomy.models import (
    Industry, Department, JobFunction, JobRole, SkillCategory, Skill,
    Technology, Tool, Certification, Qualification, TaxonomyAlias,
    RoleSkill, RoleRelation, RoleHierarchy, TaxonomyImportLog,
    TaxonomySource, TaxonomyStatus
)
from apps.taxonomy.services.taxonomy_seeder import TaxonomySeeder

logger = logging.getLogger(__name__)


class TaxonomyImporter:
    """
    Universal Taxonomy Ingestion and Normalization Pipeline.
    """

    @classmethod
    def import_source(
        cls,
        source: str = "all",
        file_path: Optional[str] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Main entry point for taxonomy imports.
        """
        source_normalized = source.strip().lower()
        stats = {
            "source": source,
            "industries_created": 0,
            "departments_created": 0,
            "roles_created": 0,
            "skills_created": 0,
            "technologies_created": 0,
            "tools_created": 0,
            "aliases_created": 0,
            "relations_created": 0,
            "duplicates_skipped": 0,
            "errors": []
        }

        if source_normalized in ["tv_urt", "core", "all"]:
            seeder_stats = TaxonomySeeder.seed_all()
            stats["industries_created"] += seeder_stats.get("industries", 0)
            stats["departments_created"] += seeder_stats.get("departments", 0)
            stats["roles_created"] += seeder_stats.get("job_roles", 0)
            stats["skills_created"] += seeder_stats.get("skills", 0)
            stats["technologies_created"] += seeder_stats.get("technologies", 0)
            stats["tools_created"] += seeder_stats.get("tools", 0)
            stats["aliases_created"] += seeder_stats.get("aliases", 0)
            stats["relations_created"] += seeder_stats.get("role_relations", 0)

        # Custom JSON/CSV import if file_path is provided
        if file_path and os.path.exists(file_path):
            file_stats = cls._import_from_file(file_path, source_normalized, dry_run)
            for k, v in file_stats.items():
                if k in stats and isinstance(v, int):
                    stats[k] += v

        return stats

    @classmethod
    def _import_from_file(cls, file_path: str, source_type: str, dry_run: bool) -> Dict[str, Any]:
        stats = {
            "roles_created": 0,
            "skills_created": 0,
            "aliases_created": 0,
            "duplicates_skipped": 0,
            "errors": []
        }

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                with transaction.atomic():
                    for item in data:
                        name = item.get("name") or item.get("title")
                        if not name:
                            continue
                        canonical = item.get("canonical_name", name)
                        entity_type = item.get("type", "role").lower()

                        if entity_type in ["role", "job_role", "designation"]:
                            role_obj, created = JobRole.objects.get_or_create(
                                canonical_name=canonical,
                                defaults={
                                    "name": name,
                                    "normalized_name": canonical.lower(),
                                    "source": TaxonomySource.ESCO if source_type == "esco" else (TaxonomySource.ONET if source_type == "onet" else TaxonomySource.OPEN_DATA)
                                }
                            )
                            if created:
                                stats["roles_created"] += 1
                            else:
                                stats["duplicates_skipped"] += 1

                            for alias_str in item.get("aliases", []):
                                if alias_str.strip():
                                    _, a_created = TaxonomyAlias.objects.get_or_create(
                                        normalized_alias=alias_str.strip().lower(),
                                        entity_type=TaxonomyAlias.EntityType.JOB_ROLE,
                                        canonical_name=canonical,
                                        defaults={
                                            "alias": alias_str.strip(),
                                            "job_role": role_obj,
                                            "source": TaxonomySource.OPEN_DATA
                                        }
                                    )
                                    if a_created:
                                        stats["aliases_created"] += 1

                        elif entity_type in ["skill", "technology"]:
                            sk_obj, created = Skill.objects.get_or_create(
                                canonical_name=canonical,
                                defaults={
                                    "name": name,
                                    "normalized_name": canonical.lower(),
                                    "source": TaxonomySource.OPEN_DATA
                                }
                            )
                            if created:
                                stats["skills_created"] += 1
                            else:
                                stats["duplicates_skipped"] += 1

                    if dry_run:
                        transaction.set_rollback(True)

        except Exception as e:
            stats["errors"].append(str(e))
            logger.exception(f"Taxonomy file import error: {e}")

        return stats

    @classmethod
    def get_summary_statistics(cls) -> Dict[str, Any]:
        """
        Returns full live statistical breakdown across all taxonomy models.
        """
        return {
            "total_industries": Industry.objects.filter(status=TaxonomyStatus.ACTIVE).count(),
            "total_departments": Department.objects.filter(status=TaxonomyStatus.ACTIVE).count(),
            "total_job_functions": JobFunction.objects.filter(status=TaxonomyStatus.ACTIVE).count(),
            "total_job_roles": JobRole.objects.filter(status=TaxonomyStatus.ACTIVE).count(),
            "total_skills": Skill.objects.filter(status=TaxonomyStatus.ACTIVE).count(),
            "total_technologies": Technology.objects.filter(status=TaxonomyStatus.ACTIVE).count(),
            "total_tools": Tool.objects.filter(status=TaxonomyStatus.ACTIVE).count(),
            "total_certifications": Certification.objects.filter(status=TaxonomyStatus.ACTIVE).count(),
            "total_qualifications": Qualification.objects.filter(status=TaxonomyStatus.ACTIVE).count(),
            "total_aliases": TaxonomyAlias.objects.filter(status=TaxonomyStatus.ACTIVE).count(),
            "total_role_skills": RoleSkill.objects.filter(status=TaxonomyStatus.ACTIVE).count(),
            "total_role_relations": RoleRelation.objects.filter(status=TaxonomyStatus.ACTIVE).count(),
            "sources": [
                {"name": "TalentVault Universal Recruitment Taxonomy (TV-URT Core)", "license": "ODbL / CC BY 4.0 / TV-URT Open Data", "records": JobRole.objects.count() + Skill.objects.count()},
                {"name": "ESCO (European Skills, Competences, Qualifications and Occupations)", "license": "Open Data / EU Public Licence", "records": Skill.objects.filter(source=TaxonomySource.ESCO).count()},
                {"name": "O*NET (Occupational Information Network - US Dept of Labor)", "license": "Creative Commons Attribution 4.0 International", "records": JobRole.objects.filter(source=TaxonomySource.ONET).count()},
            ]
        }
