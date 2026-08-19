"""
TalentVault Universal Recruitment Taxonomy (TV-URT) — Centralized Semantic Search & Normalization Engine.
Provides sub-millisecond autocomplete, alias normalization, ontology graph traversal, and job/resume matching.
"""
import re
from typing import Dict, Any, List, Optional, Tuple, Set
from django.core.cache import cache
from django.db.models import Q
from apps.taxonomy.models import (
    JobRole, Skill, Technology, Tool, TaxonomyAlias,
    RoleSkill, RoleRelation, Industry, Department,
    TaxonomyStatus, TaxonomySource
)
from apps.taxonomy.services.taxonomy_seeder import TaxonomySeeder


# Non-informative role modifiers to filter when searching
GENERIC_STOPWORDS = {
    'and', 'or', 'the', 'in', 'of', 'for', 'with', 'at', 'by', 'to', 'a', 'an', 'is', 'on', 'all', 'any'
}


class TaxonomyEngine:
    """
    Core Runtime Engine for TV-URT.
    """

    @classmethod
    def ensure_seeded(cls):
        """
        Idempotent check ensuring base taxonomy is populated.
        """
        try:
            if not JobRole.objects.filter(status=TaxonomyStatus.ACTIVE).exists():
                TaxonomySeeder.seed_all()
        except Exception:
            pass

    @classmethod
    def normalize_term(cls, term: str) -> str:
        """
        Strips noise, punctuation, and extra whitespace.
        """
        if not term:
            return ""
        clean = re.sub(r'[\r\n\t]+', ' ', str(term))
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    ACTIVITY_TO_ROLE_PATTERNS = [
        (r'\b(inspection|inspecting)\b', 'inspector'),
        (r'\b(development|developing)\b', 'developer'),
        (r'\b(engineering)\b', 'engineer'),
        (r'\b(management|managing)\b', 'manager'),
        (r'\b(analytics|analysis|analysing)\b', 'analyst'),
        (r'\b(accounting)\b', 'accountant'),
        (r'\b(recruitment|recruiting)\b', 'recruiter'),
        (r'\b(consulting)\b', 'consultant'),
        (r'\b(auditing)\b', 'auditor'),
        (r'\b(advisory|advising)\b', 'advisor'),
        (r'\b(supervision|supervising)\b', 'supervisor'),
        (r'\b(testing)\b', 'tester'),
        (r'\b(administration|administering)\b', 'administrator'),
    ]

    @classmethod
    def resolve_role_alias(cls, input_title: str) -> Optional[str]:
        """
        Resolves abbreviations, gerunds, activity phrases, or aliases to canonical Job Role name.
        e.g. 'Car Inspection' -> 'Vehicle Inspector', 'SDE' -> 'Software Engineer', 'Sr. BDE' -> 'Business Development Executive'
        """
        cls.ensure_seeded()
        clean = cls.normalize_term(input_title)
        if not clean:
            return None

        clean_lower = clean.lower()

        # 1. Direct Canonical Check
        direct_role = JobRole.objects.filter(
            Q(canonical_name__iexact=clean) | Q(normalized_name=clean_lower),
            status=TaxonomyStatus.ACTIVE
        ).first()
        if direct_role:
            return direct_role.canonical_name

        # 2. Direct Alias Table Lookup
        alias_match = TaxonomyAlias.objects.filter(
            normalized_alias=clean_lower,
            entity_type=TaxonomyAlias.EntityType.JOB_ROLE,
            status=TaxonomyStatus.ACTIVE
        ).select_related('job_role').first()
        if alias_match:
            if alias_match.job_role:
                return alias_match.job_role.canonical_name
            return alias_match.canonical_name

        # 3. Activity / Gerund to Agent Noun Transformation (e.g. "Car Inspection" -> "Car Inspector")
        transformed = clean_lower
        for pattern, repl in cls.ACTIVITY_TO_ROLE_PATTERNS:
            transformed = re.sub(pattern, repl, transformed, flags=re.IGNORECASE)

        if transformed != clean_lower:
            direct_role = JobRole.objects.filter(
                Q(canonical_name__iexact=transformed) | Q(normalized_name=transformed),
                status=TaxonomyStatus.ACTIVE
            ).first()
            if direct_role:
                return direct_role.canonical_name

            alias_match = TaxonomyAlias.objects.filter(
                normalized_alias=transformed,
                entity_type=TaxonomyAlias.EntityType.JOB_ROLE,
                status=TaxonomyStatus.ACTIVE
            ).select_related('job_role').first()
            if alias_match:
                if alias_match.job_role:
                    return alias_match.job_role.canonical_name
                return alias_match.canonical_name

        # 4. Seniority Prefix Stripping (e.g. "Sr. BDE" -> "BDE", "Junior SDE" -> "SDE")
        stripped = re.sub(
            r'^(sr\.?|senior|jr\.?|junior|lead|principal|associate|trainee|intern|chief|head of|assistant|deputy)\s+',
            '',
            clean_lower
        ).strip()

        if stripped and stripped != clean_lower:
            direct_role = JobRole.objects.filter(
                Q(canonical_name__iexact=stripped) | Q(normalized_name=stripped),
                status=TaxonomyStatus.ACTIVE
            ).first()
            if direct_role:
                return direct_role.canonical_name

            alias_match = TaxonomyAlias.objects.filter(
                normalized_alias=stripped,
                entity_type=TaxonomyAlias.EntityType.JOB_ROLE,
                status=TaxonomyStatus.ACTIVE
            ).select_related('job_role').first()
            if alias_match:
                if alias_match.job_role:
                    return alias_match.job_role.canonical_name
                return alias_match.canonical_name

        return None

    @classmethod
    def get_expanded_role_terms(cls, role_input: str) -> Set[str]:
        """
        Returns all valid normalized designations, synonyms, and related roles for a role input.
        e.g. 'Car Inspection' -> {'Car Inspection', 'Car Inspector', 'Vehicle Inspector', 'Automobile Inspector',
                                  'Vehicle Inspection Officer', 'Car Inspection Executive', ...}
        """
        cls.ensure_seeded()
        clean = cls.normalize_term(role_input)
        if not clean:
            return set()

        canonical = cls.resolve_role_alias(clean) or clean
        expanded: Set[str] = {clean, canonical}

        # Also add transformed term
        transformed = clean.lower()
        for pattern, repl in cls.ACTIVITY_TO_ROLE_PATTERNS:
            transformed = re.sub(pattern, repl, transformed, flags=re.IGNORECASE)
        if transformed:
            expanded.add(transformed.title())

        # Look up role object & aliases in TV-URT
        role_obj = JobRole.objects.filter(
            Q(canonical_name__iexact=canonical) | Q(canonical_name__iexact=clean),
            status=TaxonomyStatus.ACTIVE
        ).first()

        if role_obj:
            expanded.add(role_obj.canonical_name)
            # Add all aliases
            for al in role_obj.aliases.filter(status=TaxonomyStatus.ACTIVE):
                expanded.add(al.alias)

            # Add related roles from graph
            for rel in role_obj.outgoing_role_relations.filter(status=TaxonomyStatus.ACTIVE).select_related('target_role'):
                expanded.add(rel.target_role.canonical_name)

        # Look up any alias matching canonical
        for al in TaxonomyAlias.objects.filter(
            Q(canonical_name__iexact=canonical) | Q(alias__iexact=clean) | Q(normalized_alias=clean.lower()),
            entity_type=TaxonomyAlias.EntityType.JOB_ROLE,
            status=TaxonomyStatus.ACTIVE
        ):
            expanded.add(al.alias)
            expanded.add(al.canonical_name)

        return {t for t in expanded if t and len(t.strip()) > 1}

    @classmethod
    def resolve_skill_alias(cls, input_skill: str) -> Optional[str]:
        """
        Resolves skill synonyms / spelling variants to canonical Skill name.
        e.g. 'ReactJS' -> 'React', 'Postgres' -> 'PostgreSQL'
        """
        cls.ensure_seeded()
        clean = cls.normalize_term(input_skill)
        if not clean:
            return None

        clean_lower = clean.lower()

        # 1. Direct Canonical Check
        direct_skill = Skill.objects.filter(
            Q(canonical_name__iexact=clean) | Q(normalized_name=clean_lower),
            status=TaxonomyStatus.ACTIVE
        ).first()
        if direct_skill:
            return direct_skill.canonical_name

        # 2. Direct Technology Check
        direct_tech = Technology.objects.filter(
            Q(canonical_name__iexact=clean) | Q(normalized_name=clean_lower),
            status=TaxonomyStatus.ACTIVE
        ).first()
        if direct_tech:
            return direct_tech.canonical_name

        # 3. Alias Table Lookup
        alias_match = TaxonomyAlias.objects.filter(
            normalized_alias=clean_lower,
            entity_type__in=[TaxonomyAlias.EntityType.SKILL, TaxonomyAlias.EntityType.TECHNOLOGY, TaxonomyAlias.EntityType.TOOL],
            status=TaxonomyStatus.ACTIVE
        ).first()
        if alias_match:
            return alias_match.canonical_name

        return None

    @classmethod
    def get_smart_suggestions(cls, query: str = "", active_tags: List[str] = None, limit: int = 15) -> Dict[str, Any]:
        """
        Returns structured, weighted keyword suggestions for recruiter searches.
        Includes exact matches, prefix matches, graph-related roles, and core skills.
        """
        cls.ensure_seeded()
        query = cls.normalize_term(query)
        active_tags = [cls.normalize_term(t) for t in (active_tags or []) if cls.normalize_term(t)]

        # Cache key
        cache_str = f"{query.lower()}_{'_'.join(sorted([t.lower() for t in active_tags]))}"
        safe_cache_key = f"tv_urt_sug_{re.sub(r'[^a-zA-Z0-9_]', '_', cache_str)[:100]}"
        cached = cache.get(safe_cache_key)
        if cached:
            return cached

        suggestions_map: Dict[str, Dict[str, Any]] = {}
        all_terms = []
        if query:
            all_terms.append(query)
        all_terms.extend(active_tags)

        # 1. Direct, Prefix & Word Matches from Job Roles
        if query:
            q_lower = query.lower()
            q_tokens = [w for w in re.findall(r'\w+', q_lower) if len(w) >= 2]

            roles_qs = JobRole.objects.filter(
                Q(normalized_name__icontains=q_lower) | Q(canonical_name__icontains=query),
                status=TaxonomyStatus.ACTIVE
            ).select_related('industry', 'department')[:25]

            for role in roles_qs:
                r_lower = role.canonical_name.lower()
                is_exact = r_lower == q_lower
                is_prefix = r_lower.startswith(q_lower)
                # Token match (e.g. "sales" matches "Area Sales Manager", "Regional Sales Manager")
                r_tokens = re.findall(r'\w+', r_lower)
                is_word_match = any(t == q_lower for t in r_tokens) or (q_tokens and all(any(qt in rt for rt in r_tokens) for qt in q_tokens))

                if is_exact:
                    score = 1.00
                    m_type = "exact"
                elif is_prefix:
                    score = 0.95
                    m_type = "prefix"
                elif is_word_match:
                    score = 0.88
                    m_type = "word_match"
                else:
                    score = 0.80
                    m_type = "substring"

                suggestions_map[role.canonical_name] = {
                    "id": str(role.id),
                    "name": role.canonical_name,
                    "label": role.canonical_name,
                    "type": "designation",
                    "category": role.industry.name if role.industry else "Designation",
                    "score": score,
                    "match_type": m_type
                }

            # Direct & Prefix Matches from Skills & Technologies
            skills_qs = Skill.objects.filter(
                Q(normalized_name__icontains=q_lower) | Q(canonical_name__icontains=query),
                status=TaxonomyStatus.ACTIVE
            )[:20]
            for sk in skills_qs:
                sk_lower = sk.canonical_name.lower()
                is_exact = sk_lower == q_lower
                is_prefix = sk_lower.startswith(q_lower)
                sk_tokens = re.findall(r'\w+', sk_lower)
                is_word_match = any(t == q_lower for t in sk_tokens)

                if is_exact:
                    score = 0.98
                    m_type = "exact"
                elif is_prefix:
                    score = 0.92
                    m_type = "prefix"
                elif is_word_match:
                    score = 0.85
                    m_type = "word_match"
                else:
                    score = 0.78
                    m_type = "substring"

                suggestions_map[sk.canonical_name] = {
                    "id": str(sk.id),
                    "name": sk.canonical_name,
                    "label": sk.canonical_name,
                    "type": "skill",
                    "category": "Skill",
                    "score": score,
                    "match_type": m_type
                }

            techs_qs = Technology.objects.filter(
                Q(normalized_name__icontains=q_lower) | Q(canonical_name__icontains=query),
                status=TaxonomyStatus.ACTIVE
            )[:15]
            for tech in techs_qs:
                t_lower = tech.canonical_name.lower()
                is_exact = t_lower == q_lower
                is_prefix = t_lower.startswith(q_lower)
                t_tokens = re.findall(r'\w+', t_lower)
                is_word_match = any(t == q_lower for t in t_tokens)

                if is_exact:
                    score = 0.98
                    m_type = "exact"
                elif is_prefix:
                    score = 0.92
                    m_type = "prefix"
                elif is_word_match:
                    score = 0.85
                    m_type = "word_match"
                else:
                    score = 0.78
                    m_type = "substring"

                suggestions_map[tech.canonical_name] = {
                    "id": str(tech.id),
                    "name": tech.canonical_name,
                    "label": tech.canonical_name,
                    "type": "technology",
                    "category": tech.get_tech_category_display(),
                    "score": score,
                    "match_type": m_type
                }

            # Aliases Match
            aliases_qs = TaxonomyAlias.objects.filter(
                Q(normalized_alias__icontains=q_lower) | Q(alias__icontains=query),
                status=TaxonomyStatus.ACTIVE
            )[:20]
            for al in aliases_qs:
                if al.canonical_name not in suggestions_map:
                    is_exact = al.alias.lower() == q_lower
                    is_prefix = al.alias.lower().startswith(q_lower)
                    score = 0.92 if is_exact else (0.86 if is_prefix else 0.82)
                    display_type = "designation" if al.entity_type == TaxonomyAlias.EntityType.JOB_ROLE else al.entity_type.lower()
                    suggestions_map[al.canonical_name] = {
                        "id": str(al.id),
                        "name": al.canonical_name,
                        "label": al.canonical_name,
                        "type": display_type,
                        "category": f"Alias: {al.alias}",
                        "score": score,
                        "match_type": "alias"
                    }

        # 2. Graph Traversal for All Active Terms (Roles -> Related Roles & Skills)
        for term in all_terms:
            resolved_role_name = cls.resolve_role_alias(term) or term
            role_obj = JobRole.objects.filter(canonical_name__iexact=resolved_role_name, status=TaxonomyStatus.ACTIVE).first()
            if not role_obj:
                continue

            # Outgoing & Incoming Role Relations
            for rel in role_obj.outgoing_role_relations.filter(status=TaxonomyStatus.ACTIVE).select_related('target_role'):
                tgt = rel.target_role
                if tgt.canonical_name not in suggestions_map and tgt.canonical_name.lower() != term.lower():
                    suggestions_map[tgt.canonical_name] = {
                        "id": str(tgt.id),
                        "label": tgt.canonical_name,
                        "type": "job_role",
                        "category": rel.get_relation_type_display(),
                        "score": round(float(rel.weight) * 0.85, 2),
                        "match_type": "graph_relation"
                    }

            # Role Skills & Tools
            for rs in role_obj.role_skills.filter(status=TaxonomyStatus.ACTIVE).select_related('skill', 'technology', 'tool')[:8]:
                target_name = rs.skill.canonical_name if rs.skill else (rs.technology.canonical_name if rs.technology else (rs.tool.canonical_name if rs.tool else None))
                if target_name and target_name not in suggestions_map and target_name.lower() != term.lower():
                    t_type = "skill" if rs.skill else ("technology" if rs.technology else "tool")
                    suggestions_map[target_name] = {
                        "id": str(rs.id),
                        "label": target_name,
                        "type": t_type,
                        "category": rs.get_relation_type_display(),
                        "score": round(float(rs.weight) * 0.80, 2),
                        "match_type": "role_skill"
                    }

        # 3. Dynamic Discovery for Novel / Unknown Query
        if not suggestions_map and query:
            words = [w.strip() for w in re.findall(r'\w+', query.lower()) if len(w) > 2 and w not in GENERIC_STOPWORDS]
            for w in words:
                suggestions_map[w.title()] = {
                    "id": w.title(),
                    "label": w.title(),
                    "type": "skill",
                    "category": "Discovered Keyword",
                    "score": 0.65,
                    "match_type": "dynamic_discovery"
                }
            if len(words) >= 2:
                phrase = " ".join(w.title() for w in words)
                if phrase.lower() != query.lower():
                    suggestions_map[phrase] = {
                        "id": phrase,
                        "label": phrase,
                        "type": "skill",
                        "category": "Domain Term",
                        "score": 0.70,
                        "match_type": "dynamic_discovery"
                    }

        # Filter out terms that are already active search tags
        active_lower = {t.lower() for t in active_tags}
        filtered_suggestions = [
            s for s in suggestions_map.values()
            if s["label"].lower() not in active_lower
        ]

        # Rank by score descending
        ranked_suggestions = sorted(filtered_suggestions, key=lambda x: x["score"], reverse=True)[:limit]

        response_data = {
            "query": query,
            "count": len(ranked_suggestions),
            "results": ranked_suggestions,
            "suggestions": ranked_suggestions
        }

        cache.set(safe_cache_key, response_data, timeout=600)
        return response_data

    @classmethod
    def get_role_autocomplete(cls, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fast typeahead autocomplete specifically for Job Role fields.
        """
        cls.ensure_seeded()
        query = cls.normalize_term(query)
        if not query:
            return []

        q_lower = query.lower()
        results: List[Dict[str, Any]] = []
        seen = set()

        roles = JobRole.objects.filter(
            Q(normalized_name__icontains=q_lower) | Q(canonical_name__icontains=query),
            status=TaxonomyStatus.ACTIVE
        ).select_related('industry', 'department')[:limit * 2]

        for r in roles:
            if r.canonical_name in seen:
                continue
            seen.add(r.canonical_name)
            is_exact = r.canonical_name.lower() == q_lower
            is_prefix = r.canonical_name.lower().startswith(q_lower)
            score = 1.00 if is_exact else (0.90 if is_prefix else 0.75)

            results.append({
                "id": str(r.id),
                "name": r.canonical_name,
                "value": r.canonical_name,
                "type": "job_role",
                "seniority": r.get_seniority_display(),
                "department": r.department.name if r.department else (r.industry.name if r.industry else "General"),
                "score": score
            })

        # Check aliases
        aliases = TaxonomyAlias.objects.filter(
            Q(normalized_alias__icontains=q_lower) | Q(alias__icontains=query),
            entity_type=TaxonomyAlias.EntityType.JOB_ROLE,
            status=TaxonomyStatus.ACTIVE
        ).select_related('job_role')[:limit]

        for al in aliases:
            if al.canonical_name in seen:
                continue
            seen.add(al.canonical_name)
            is_exact = al.alias.lower() == q_lower
            results.append({
                "id": str(al.id),
                "name": al.canonical_name,
                "value": al.canonical_name,
                "type": "job_role",
                "seniority": "Alias",
                "department": f"Alias of '{al.alias}'",
                "score": 0.95 if is_exact else 0.80
            })

        return sorted(results, key=lambda x: x["score"], reverse=True)[:limit]

    @classmethod
    def get_skill_autocomplete(cls, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fast typeahead autocomplete specifically for Skills, Technologies & Tools.
        """
        cls.ensure_seeded()
        query = cls.normalize_term(query)
        if not query:
            return []

        q_lower = query.lower()
        results: List[Dict[str, Any]] = []
        seen = set()

        skills = Skill.objects.filter(
            Q(normalized_name__icontains=q_lower) | Q(canonical_name__icontains=query),
            status=TaxonomyStatus.ACTIVE
        )[:limit]

        for sk in skills:
            if sk.canonical_name in seen:
                continue
            seen.add(sk.canonical_name)
            is_exact = sk.canonical_name.lower() == q_lower
            is_prefix = sk.canonical_name.lower().startswith(q_lower)
            score = 1.00 if is_exact else (0.90 if is_prefix else 0.75)

            results.append({
                "id": str(sk.id),
                "name": sk.canonical_name,
                "value": sk.canonical_name,
                "type": "skill",
                "score": score
            })

        techs = Technology.objects.filter(
            Q(normalized_name__icontains=q_lower) | Q(canonical_name__icontains=query),
            status=TaxonomyStatus.ACTIVE
        )[:limit]

        for t in techs:
            if t.canonical_name in seen:
                continue
            seen.add(t.canonical_name)
            is_exact = t.canonical_name.lower() == q_lower
            is_prefix = t.canonical_name.lower().startswith(q_lower)
            score = 1.00 if is_exact else (0.90 if is_prefix else 0.75)

            results.append({
                "id": str(t.id),
                "name": t.canonical_name,
                "value": t.canonical_name,
                "type": "technology",
                "score": score
            })

        return sorted(results, key=lambda x: x["score"], reverse=True)[:limit]

    @classmethod
    def get_job_posting_suggestions(cls, job_title: str, limit: int = 10) -> Dict[str, Any]:
        """
        When recruiter types a Job Title, suggests related companion roles and core skills.
        """
        cls.ensure_seeded()
        clean_title = cls.normalize_term(job_title)
        canonical = cls.resolve_role_alias(clean_title) or clean_title

        role_obj = JobRole.objects.filter(canonical_name__iexact=canonical, status=TaxonomyStatus.ACTIVE).first()
        suggested_roles = []
        suggested_skills = []

        if role_obj:
            # Related roles
            for rel in role_obj.outgoing_role_relations.filter(status=TaxonomyStatus.ACTIVE).select_related('target_role')[:6]:
                suggested_roles.append(rel.target_role.canonical_name)

            # Core skills
            for rs in role_obj.role_skills.filter(status=TaxonomyStatus.ACTIVE).select_related('skill', 'technology', 'tool')[:12]:
                s_name = rs.skill.canonical_name if rs.skill else (rs.technology.canonical_name if rs.technology else (rs.tool.canonical_name if rs.tool else None))
                if s_name and s_name not in suggested_skills:
                    suggested_skills.append(s_name)

        return {
            "job_title": job_title,
            "canonical_title": canonical,
            "suggested_roles": suggested_roles[:limit],
            "suggested_skills": suggested_skills[:limit]
        }
