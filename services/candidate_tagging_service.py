import logging
import re
from typing import List, Dict, Any, Optional, Set
from django.db import transaction
from django.db.models import Q
from apps.candidates.models import (
    CandidateProfile, CandidateTag, TaxonomyDesignation, TaxonomySkill,
    RoleSkillRelation, RoleRelation
)
from services.recruitment_taxonomy_service import RecruitmentTaxonomyService

logger = logging.getLogger(__name__)


class CandidateTaggingService:
    """
    Universal Candidate Tagging Engine.
    Extracts, normalizes, and indexes candidate attributes into structured CandidateTags
    with provenance (source) and confidence scores.
    """

    @classmethod
    def tag_candidate_profile(cls, profile: CandidateProfile, source: str = 'resume_parser') -> int:
        """
        Extracts all designations, skills, tools, domains, educations, and certifications
        from CandidateProfile, normalizes them against the centralized taxonomy,
        and saves them into CandidateTag model.
        Returns the number of tags created/updated.
        """
        if not profile or not profile.id:
            return 0

        RecruitmentTaxonomyService.ensure_taxonomy_seeded()

        tags_to_create: List[CandidateTag] = []
        seen_tags: Set[Tuple[str, str]] = set() # (normalized_name, tag_type)

        def add_tag(name: str, tag_type: str, confidence: float, src: str = source, is_curr: bool = False, yoe: Optional[float] = None, canonical: Optional[str] = None):
            if not name or not name.strip():
                return
            clean_name = RecruitmentTaxonomyService.normalize_term(name)
            if not clean_name or len(clean_name) < 2:
                return
            norm_name = clean_name.lower()
            key = (norm_name, tag_type)
            if key in seen_tags:
                return
            seen_tags.add(key)

            can_name = canonical or clean_name

            tags_to_create.append(CandidateTag(
                profile=profile,
                name=clean_name[:150],
                canonical_name=can_name[:150],
                normalized_name=norm_name[:150],
                tag_type=tag_type,
                confidence=round(min(1.0, max(0.1, confidence)), 2),
                source=src,
                is_current=is_curr,
                years_of_experience=yoe
            ))

        # 1. Candidate Explicit Skills (High Priority Provenance)
        for sk in profile.skills.all():
            if sk.skill_name and sk.skill_name.strip():
                s_name = sk.skill_name.strip()
                from apps.taxonomy.services.taxonomy_engine import TaxonomyEngine
                can_skill = TaxonomyEngine.resolve_skill_alias(s_name) or s_name
                add_tag(
                    name=s_name,
                    tag_type='SKILL',
                    confidence=0.95,
                    src=source,
                    yoe=float(sk.years_of_experience) if sk.years_of_experience else None,
                    canonical=can_skill
                )

        # 2. Current Designation & Preferred Job Role
        current_des = profile.current_designation or profile.preferred_job_role
        if current_des and current_des.strip():
            from apps.taxonomy.services.taxonomy_engine import TaxonomyEngine
            tv_canonical = TaxonomyEngine.resolve_role_alias(current_des)
            matched_des = RecruitmentTaxonomyService.find_canonical_designation(current_des)
            canonical = tv_canonical or (matched_des.canonical_name if matched_des else current_des.strip())
            add_tag(
                name=current_des.strip(),
                tag_type='DESIGNATION',
                confidence=0.98,
                src=source,
                is_curr=True,
                yoe=float(profile.total_experience) if profile.total_experience else None,
                canonical=canonical
            )

            # Inferred domain / industry from taxonomy designation
            if matched_des:
                if matched_des.department:
                    add_tag(matched_des.department, 'DOMAIN', 0.90, 'taxonomy')
                if matched_des.industry:
                    add_tag(matched_des.industry, 'INDUSTRY', 0.90, 'taxonomy')

                # Inferred core skills for this designation
                for sr in matched_des.skill_relations.select_related('skill'):
                    sk = sr.skill
                    add_tag(sk.canonical_name, 'SKILL', round(float(sr.weight) * 0.85, 2), 'taxonomy')

        # 3. Previous Designations from Experience Records
        for exp in profile.experiences.all():
            if exp.designation and exp.designation.strip():
                des_text = exp.designation.strip()
                from apps.taxonomy.services.taxonomy_engine import TaxonomyEngine
                tv_can = TaxonomyEngine.resolve_role_alias(des_text)
                matched = RecruitmentTaxonomyService.find_canonical_designation(des_text)
                can_title = tv_can or (matched.canonical_name if matched else des_text)
                add_tag(
                    name=des_text,
                    tag_type='PREVIOUS_DESIGNATION' if not exp.is_current else 'DESIGNATION',
                    confidence=0.95 if exp.is_current else 0.90,
                    src=source,
                    is_curr=exp.is_current,
                    canonical=can_title
                )

        # 4. Skills from parsed_json or original_skills / ai_skills
        if profile.original_skills and isinstance(profile.original_skills, list):
            for os_skill in profile.original_skills:
                if isinstance(os_skill, str) and os_skill.strip():
                    add_tag(os_skill.strip(), 'SKILL', 0.92, 'resume_parser')

        if profile.ai_skills and isinstance(profile.ai_skills, list):
            for ais in profile.ai_skills:
                if isinstance(ais, str) and ais.strip():
                    add_tag(ais.strip(), 'SKILL', 0.88, 'AI')

        # 5. Tools & Technologies from Projects
        for proj in profile.projects.all():
            if proj.title and proj.title.strip():
                add_tag(proj.title.strip(), 'TOOL', 0.85, 'resume_parser')

        # 6. Certifications
        for cert in profile.certifications.all():
            if cert.name and cert.name.strip():
                add_tag(cert.name.strip(), 'CERTIFICATION', 0.92, 'resume_parser')

        # 7. Educations / Degrees
        for edu in profile.educations.all():
            if edu.degree and edu.degree.strip():
                add_tag(edu.degree.strip(), 'EDUCATION', 0.90, 'resume_parser')
            if edu.field_of_study and edu.field_of_study.strip():
                add_tag(edu.field_of_study.strip(), 'DOMAIN', 0.88, 'resume_parser')

        # Save tags atomically
        with transaction.atomic():
            CandidateTag.objects.filter(profile=profile).delete()
            if tags_to_create:
                CandidateTag.objects.bulk_create(tags_to_create, ignore_conflicts=True)

        logger.info(f"[TAGGING SUCCESS] Indexed {len(tags_to_create)} candidate tags for profile: {profile.full_name or profile.id}")
        return len(tags_to_create)

    @classmethod
    def re_tag_all_candidates(cls, batch_size: int = 100) -> int:
        """
        Batch tagging utility to index all existing CandidateProfiles in the database.
        """
        RecruitmentTaxonomyService.ensure_taxonomy_seeded()
        total_tagged = 0
        profiles_qs = CandidateProfile.objects.select_related('user').prefetch_related(
            'skills', 'experiences', 'educations', 'projects', 'certifications'
        )

        for profile in profiles_qs.iterator(chunk_size=batch_size):
            try:
                count = cls.tag_candidate_profile(profile)
                total_tagged += count
            except Exception as e:
                logger.error(f"[TAGGING ERROR] Error tagging candidate {profile.id}: {e}")

        return total_tagged
