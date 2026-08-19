import re
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from decimal import Decimal
from django.db.models import Q, QuerySet, Prefetch, Case, When, Value, IntegerField, FloatField
from django.utils.html import strip_tags

from apps.candidates.models import (
    CandidateProfile, CandidateTag, CandidateSkill, Experience, Education,
    TaxonomyDesignation, TaxonomySkill, RoleRelation, RoleSkillRelation
)
from services.recruitment_taxonomy_service import (
    RecruitmentTaxonomyService, GENERIC_ROLE_MODIFIERS
)

logger = logging.getLogger(__name__)


class UniversalCandidateSearchService:
    """
    Universal, Dynamic, Naukri/Resdex-Style Recruitment Candidate Search & Relevance Engine.
    Works dynamically for ANY job title, skill, designation, domain, industry or keyword.
    """

    @classmethod
    def parse_boolean_query(cls, query_str: str) -> Dict[str, Any]:
        """
        Parses Boolean expressions (AND, OR, NOT, quoted phrases).
        Example: '"Sales Manager" AND "CRM" NOT "Insurance"'
        Example: 'Sales Manager OR Financial Analyst'
        """
        if not query_str:
            return {"must": [], "should": [], "must_not": []}

        q = query_str.strip()
        must_terms = []
        should_terms = []
        must_not_terms = []

        # Extract NOT clauses first
        not_parts = re.split(r'\bNOT\b', q, flags=re.IGNORECASE)
        main_part = not_parts[0].strip()
        for np in not_parts[1:]:
            raw_tokens = re.findall(r'"([^"]+)"|(\S+)', np)
            for t0, t1 in raw_tokens:
                cleaned = (t0 or t1).strip().strip('()"\'')
                if cleaned and cleaned.upper() not in ['AND', 'OR', 'NOT']:
                    must_not_terms.append(cleaned)

        # In main_part, check for OR vs AND
        if re.search(r'\bOR\b', main_part, re.IGNORECASE):
            or_clauses = re.split(r'\bOR\b', main_part, flags=re.IGNORECASE)
            for oc in or_clauses:
                oc_clean = oc.strip().strip('()"\'')
                if oc_clean:
                    should_terms.append(oc_clean)
        elif re.search(r'\bAND\b', main_part, re.IGNORECASE):
            and_clauses = re.split(r'\bAND\b', main_part, flags=re.IGNORECASE)
            for ac in and_clauses:
                ac_clean = ac.strip().strip('()"\'')
                if ac_clean:
                    must_terms.append(ac_clean)
        else:
            main_clean = main_part.strip().strip('()"\'')
            if main_clean:
                must_terms.append(main_clean)

        return {
            "must": [t for t in must_terms if t],
            "should": [t for t in should_terms if t],
            "must_not": [t for t in must_not_terms if t]
        }

    @classmethod
    def search_candidates(
        cls,
        base_queryset: QuerySet,
        query: str = "",
        selected_tags: List[Any] = None,
        exclude_keywords: Optional[Any] = None,
        skills: Optional[str] = None,
        it_skills: Optional[str] = None,
        min_experience: Optional[float] = None,
        max_experience: Optional[float] = None,
        location: Optional[str] = None,
        preferred_location: Optional[str] = None,
        willing_to_relocate: Optional[bool] = None,
        work_mode: Optional[str] = None,
        min_salary: Optional[float] = None,
        max_salary: Optional[float] = None,
        currency: Optional[str] = "INR",
        department: Optional[str] = None,
        role_name: Optional[str] = None,
        designation: Optional[str] = None,
        previous_designation: Optional[str] = None,
        industry: Optional[str] = None,
        company: Optional[str] = None,
        previous_company: Optional[str] = None,
        excluded_company: Optional[str] = None,
        company_type: Optional[str] = None,
        employment_type: Optional[str] = None,
        notice_period: Optional[Any] = None,
        # Education Fields
        ug_degree: Optional[str] = None,
        ug_specialization: Optional[str] = None,
        ug_education_type: Optional[str] = None,
        ug_passing_year_from: Optional[int] = None,
        ug_passing_year_to: Optional[int] = None,
        ug_institute: Optional[str] = None,
        pg_degree: Optional[str] = None,
        pg_specialization: Optional[str] = None,
        pg_education_type: Optional[str] = None,
        pg_passing_year_from: Optional[int] = None,
        pg_passing_year_to: Optional[int] = None,
        pg_institute: Optional[str] = None,
        doctorate_degree: Optional[str] = None,
        doctorate_specialization: Optional[str] = None,
        doctorate_institute: Optional[str] = None,
        education_type: Optional[str] = None,
        passing_year_from: Optional[int] = None,
        passing_year_to: Optional[int] = None,
        institute: Optional[str] = None,
        is_pursuing: Optional[bool] = None,
        # Candidate Details & Diversity Hiring (Explicit candidate data only)
        candidate_name: Optional[str] = None,
        candidate_email: Optional[str] = None,
        candidate_phone: Optional[str] = None,
        gender: Optional[str] = None,
        has_career_break: Optional[bool] = None,
        is_differently_abled: Optional[bool] = None,
        disability_category: Optional[str] = None,
        has_defence_background: Optional[bool] = None,
        defence_branch: Optional[str] = None,
        work_permit_country: Optional[str] = None,
        candidate_status: Optional[str] = None,
        freshness_days: Optional[int] = None,
        has_resume: Optional[bool] = None,
        has_verified_mobile: Optional[bool] = None,
        has_verified_email: Optional[bool] = None,
        search_within_results: Optional[str] = None,
        mandatory_keywords: Optional[List[str]] = None,
        boolean_query: Optional[str] = None,
        stage: Optional[str] = None,
        job_id: Optional[str] = None,
        sort_by: str = "relevance"
    ) -> List[Dict[str, Any]]:
        """
        Executes hybrid candidate search with all 41 structured filters,
        calibrated relevance scoring, match quality classification, and explanations.
        """
        from apps.taxonomy.services.taxonomy_engine import TaxonomyEngine
        TaxonomyEngine.ensure_seeded()

        queryset = base_queryset.select_related('user').prefetch_related(
            'skills',
            'experiences',
            'educations',
            'projects',
            'certifications',
            'candidate_tags'
        )

        # Normalize selected tags
        normalized_tags: List[Dict[str, str]] = []
        if selected_tags:
            for item in selected_tags:
                if isinstance(item, dict):
                    lbl = item.get('label') or item.get('value') or item.get('name')
                    if lbl and lbl.strip():
                        normalized_tags.append({"label": lbl.strip(), "type": item.get('type', 'general')})
                elif isinstance(item, str) and item.strip():
                    normalized_tags.append({"label": item.strip(), "type": "general"})

        tag_labels = [t["label"] for t in normalized_tags]
        all_search_terms = []
        if query and query.strip():
            all_search_terms.append(query.strip())
        if designation and designation.strip() and designation.strip() not in all_search_terms:
            all_search_terms.append(designation.strip())
        if role_name and role_name.strip() and role_name.strip() not in all_search_terms:
            all_search_terms.append(role_name.strip())
        all_search_terms.extend(tag_labels)
        if skills and skills.strip():
            for s in skills.split(','):
                if s.strip():
                    all_search_terms.append(s.strip())
        if it_skills and it_skills.strip():
            for s in it_skills.split(','):
                if s.strip():
                    all_search_terms.append(s.strip())

        # -------------------------------------------------------------
        # 1. APPLY STRUCTURED HARD FILTERS (Constraint Satisfaction)
        # -------------------------------------------------------------
        filters = Q()

        # Direct Query & Selected Tags Filtering
        query_terms = []
        if query and query.strip():
            query_terms.append(query.strip())
        query_terms.extend([t for t in tag_labels if t])

        if query_terms:
            q_filter = Q()
            for qt in query_terms:
                canonical_qt = TaxonomyEngine.resolve_role_alias(qt) or qt
                expanded_qt_roles = list(TaxonomyEngine.get_expanded_role_terms(qt))
                if canonical_qt not in expanded_qt_roles:
                    expanded_qt_roles.append(canonical_qt)
                if qt not in expanded_qt_roles:
                    expanded_qt_roles.append(qt)

                qt_term_q = (
                    Q(current_designation__icontains=qt) |
                    Q(current_designation__icontains=canonical_qt) |
                    Q(preferred_job_role__icontains=qt) |
                    Q(skills__skill_name__icontains=qt) |
                    Q(candidate_tags__name__icontains=qt) |
                    Q(candidate_tags__canonical_name__icontains=canonical_qt) |
                    Q(experiences__designation__icontains=qt) |
                    Q(summary__icontains=qt) |
                    Q(raw_resume_text__icontains=qt)
                )
                for ex_r in expanded_qt_roles[:12]:
                    qt_term_q |= (
                        Q(current_designation__icontains=ex_r) |
                        Q(preferred_job_role__icontains=ex_r) |
                        Q(experiences__designation__icontains=ex_r) |
                        Q(candidate_tags__canonical_name__icontains=ex_r) |
                        Q(candidate_tags__name__icontains=ex_r)
                    )

                q_filter |= qt_term_q

            filters &= q_filter

        # Skills & IT Skills Filters
        if skills and skills.strip():
            sk_filter = Q()
            for s in skills.split(','):
                s_clean = s.strip()
                if s_clean:
                    sk_filter |= (
                        Q(skills__skill_name__icontains=s_clean) |
                        Q(candidate_tags__name__icontains=s_clean) |
                        Q(candidate_tags__canonical_name__icontains=s_clean) |
                        Q(original_skills__icontains=s_clean) |
                        Q(ai_skills__icontains=s_clean) |
                        Q(summary__icontains=s_clean) |
                        Q(raw_resume_text__icontains=s_clean)
                    )
            filters &= sk_filter

        if it_skills and it_skills.strip():
            it_filter = Q()
            for s in it_skills.split(','):
                s_clean = s.strip()
                if s_clean:
                    it_filter |= (
                        Q(skills__skill_name__icontains=s_clean) |
                        Q(candidate_tags__name__icontains=s_clean) |
                        Q(candidate_tags__canonical_name__icontains=s_clean) |
                        Q(original_skills__icontains=s_clean) |
                        Q(ai_skills__icontains=s_clean) |
                        Q(summary__icontains=s_clean) |
                        Q(raw_resume_text__icontains=s_clean)
                    )
            filters &= it_filter

        # Candidate Details
        if candidate_name and candidate_name.strip():
            c_name = candidate_name.strip()
            filters &= (Q(full_name__icontains=c_name) | Q(user__first_name__icontains=c_name) | Q(user__last_name__icontains=c_name))
        if candidate_email and candidate_email.strip():
            filters &= Q(user__email__icontains=candidate_email.strip())
        if candidate_phone and candidate_phone.strip():
            filters &= (Q(user__phone_number__icontains=candidate_phone.strip()) | Q(user__phone__icontains=candidate_phone.strip()))

        # Experience Filter
        if min_experience is not None:
            try:
                filters &= Q(total_experience__gte=float(min_experience))
            except (ValueError, TypeError):
                pass
        if max_experience is not None:
            try:
                filters &= Q(total_experience__lte=float(max_experience))
            except (ValueError, TypeError):
                pass

        # Salary Filter (converted from LPA if < 1000)
        if min_salary is not None:
            try:
                val = float(min_salary)
                if val < 1000:
                    val = val * 100000.0
                filters &= Q(current_salary__gte=val) | Q(expected_salary__gte=val)
            except (ValueError, TypeError):
                pass

        if max_salary is not None:
            try:
                val = float(max_salary)
                if val < 1000:
                    val = val * 100000.0
                filters &= Q(current_salary__lte=val) | Q(expected_salary__lte=val)
            except (ValueError, TypeError):
                pass

        # Location Filter (City, State, Country)
        if location and location.strip():
            loc_clean = location.strip()
            if loc_clean.lower() == 'remote':
                filters &= (
                    Q(location__icontains='remote') |
                    Q(preferred_location__icontains='remote') |
                    Q(job_applications__preferred_work_mode__icontains='remote')
                )
            else:
                loc_filter = (
                    Q(location__icontains=loc_clean) |
                    Q(preferred_location__icontains=loc_clean) |
                    Q(job_applications__current_location__icontains=loc_clean) |
                    Q(job_applications__current_location_city__icontains=loc_clean) |
                    Q(job_applications__current_location_state__icontains=loc_clean)
                )
                if willing_to_relocate is not False:
                    loc_filter |= Q(preferred_location__icontains=loc_clean, willing_to_relocate=True)
                filters &= loc_filter

        if preferred_location and preferred_location.strip():
            filters &= Q(preferred_location__icontains=preferred_location.strip())

        if willing_to_relocate is True:
            filters &= Q(willing_to_relocate=True)

        if work_mode and work_mode.strip():
            wm_clean = work_mode.strip().upper()
            filters &= (Q(location__icontains=wm_clean) | Q(preferred_location__icontains=wm_clean) | Q(job_applications__preferred_work_mode__icontains=wm_clean))

        # Designation Filter
        if designation and designation.strip():
            des_clean = designation.strip()
            canonical_des = TaxonomyEngine.resolve_role_alias(des_clean) or des_clean
            expanded_des = list(TaxonomyEngine.get_expanded_role_terms(des_clean))
            des_q = (
                Q(current_designation__icontains=des_clean) |
                Q(current_designation__icontains=canonical_des) |
                Q(experiences__designation__icontains=des_clean) |
                Q(preferred_job_role__icontains=des_clean) |
                Q(candidate_tags__canonical_name__icontains=canonical_des) |
                Q(candidate_tags__name__icontains=des_clean)
            )
            for ex_d in expanded_des[:12]:
                des_q |= (
                    Q(current_designation__icontains=ex_d) |
                    Q(experiences__designation__icontains=ex_d) |
                    Q(preferred_job_role__icontains=ex_d) |
                    Q(candidate_tags__canonical_name__icontains=ex_d)
                )
            filters &= des_q

        if previous_designation and previous_designation.strip():
            prev_clean = previous_designation.strip()
            filters &= Q(experiences__designation__icontains=prev_clean, experiences__is_current=False)

        if role_name and role_name.strip():
            r_clean = role_name.strip()
            expanded_r = list(TaxonomyEngine.get_expanded_role_terms(r_clean))
            r_q = (
                Q(role_name__icontains=r_clean) |
                Q(preferred_job_role__icontains=r_clean) |
                Q(current_designation__icontains=r_clean) |
                Q(candidate_tags__canonical_name__icontains=r_clean) |
                Q(candidate_tags__name__icontains=r_clean)
            )
            for ex_r in expanded_r[:12]:
                r_q |= (
                    Q(role_name__icontains=ex_r) |
                    Q(preferred_job_role__icontains=ex_r) |
                    Q(current_designation__icontains=ex_r) |
                    Q(candidate_tags__canonical_name__icontains=ex_r)
                )
            filters &= r_q

        # Company Filter
        if company and company.strip():
            comp_clean = company.strip()
            filters &= (
                Q(current_company__icontains=comp_clean) |
                Q(experiences__company_name__icontains=comp_clean)
            )

        if previous_company and previous_company.strip():
            p_comp = previous_company.strip()
            filters &= Q(experiences__company_name__icontains=p_comp, experiences__is_current=False)

        # Excluded Company Filter
        if excluded_company and excluded_company.strip():
            ex_clean = excluded_company.strip()
            queryset = queryset.exclude(
                Q(current_company__icontains=ex_clean) |
                Q(experiences__company_name__icontains=ex_clean)
            )

        # Employment Details
        if employment_type and employment_type.strip() and employment_type.strip().upper() != 'ANY':
            filters &= Q(employment_type__iexact=employment_type.strip())

        # Industry / Department Filter
        if industry and industry.strip():
            ind_clean = industry.strip()
            filters &= (
                Q(industry__icontains=ind_clean) |
                Q(candidate_tags__canonical_name__icontains=ind_clean) |
                Q(candidate_tags__name__icontains=ind_clean) |
                Q(summary__icontains=ind_clean)
            )

        if department and department.strip():
            dept_clean = department.strip()
            filters &= (
                Q(department__icontains=dept_clean) |
                Q(candidate_tags__canonical_name__icontains=dept_clean) |
                Q(preferred_job_role__icontains=dept_clean)
            )

        # Notice Period Filter
        if notice_period is not None and str(notice_period).strip() != '':
            try:
                np_str = str(notice_period).strip()
                if np_str.lower() in ['immediate', '0']:
                    filters &= Q(is_immediate_joiner=True) | Q(notice_period=0)
                elif '-' in np_str:
                    parts = np_str.split('-')
                    filters &= Q(notice_period__gte=int(parts[0]), notice_period__lte=int(parts[1]))
                else:
                    filters &= Q(notice_period__lte=int(np_str))
            except (ValueError, TypeError):
                pass

        # -------------------------------------------------------------
        # EDUCATION FILTERS (UG, PG, Doctorate, Institute, Type, Year)
        # -------------------------------------------------------------
        if ug_degree and ug_degree.strip():
            filters &= (Q(educations__degree__icontains=ug_degree.strip()) | Q(candidate_tags__name__icontains=ug_degree.strip(), candidate_tags__tag_type='EDUCATION'))
        if ug_specialization and ug_specialization.strip():
            filters &= (Q(educations__specialization__icontains=ug_specialization.strip()) | Q(educations__field_of_study__icontains=ug_specialization.strip()))
        if ug_education_type and ug_education_type.strip() and ug_education_type.upper() != 'ANY':
            filters &= Q(educations__education_type__iexact=ug_education_type.strip())
        if ug_passing_year_from is not None:
            filters &= Q(educations__passing_year__gte=int(ug_passing_year_from))
        if ug_passing_year_to is not None:
            filters &= Q(educations__passing_year__lte=int(ug_passing_year_to))
        if ug_institute and ug_institute.strip():
            filters &= Q(educations__institution__icontains=ug_institute.strip())

        if pg_degree and pg_degree.strip():
            filters &= (Q(educations__degree__icontains=pg_degree.strip()) | Q(educations__qualification_level='PG'))
        if pg_specialization and pg_specialization.strip():
            filters &= (Q(educations__specialization__icontains=pg_specialization.strip()) | Q(educations__field_of_study__icontains=pg_specialization.strip()))
        if pg_institute and pg_institute.strip():
            filters &= Q(educations__institution__icontains=pg_institute.strip())

        if doctorate_degree and doctorate_degree.strip():
            filters &= (Q(educations__degree__icontains=doctorate_degree.strip()) | Q(educations__qualification_level='DOCTORATE'))
        if doctorate_specialization and doctorate_specialization.strip():
            filters &= (Q(educations__specialization__icontains=doctorate_specialization.strip()) | Q(educations__field_of_study__icontains=doctorate_specialization.strip()))

        if institute and institute.strip():
            filters &= Q(educations__institution__icontains=institute.strip())
        if education_type and education_type.strip() and education_type.upper() != 'ANY':
            filters &= Q(educations__education_type__iexact=education_type.strip())
        if passing_year_from is not None:
            filters &= Q(educations__passing_year__gte=int(passing_year_from))
        if passing_year_to is not None:
            filters &= Q(educations__passing_year__lte=int(passing_year_to))
        if is_pursuing is True:
            filters &= Q(educations__is_pursuing=True)

        # -------------------------------------------------------------
        # DIVERSITY & AFFIRMATIVE HIRING (Explicit Data Only)
        # -------------------------------------------------------------
        if gender and gender.strip() and gender.strip().upper() not in ['ALL', 'NOT_SPECIFIED']:
            filters &= Q(gender__iexact=gender.strip())
        if has_career_break is True:
            filters &= Q(has_career_break=True)
        if is_differently_abled is True:
            filters &= Q(is_differently_abled=True)
        if disability_category and disability_category.strip():
            filters &= Q(disability_category__icontains=disability_category.strip())
        if has_defence_background is True:
            filters &= Q(has_defence_background=True)
        if defence_branch and defence_branch.strip():
            filters &= Q(defence_branch__icontains=defence_branch.strip())
        if work_permit_country and work_permit_country.strip():
            filters &= Q(work_permit_countries__icontains=work_permit_country.strip())

        # -------------------------------------------------------------
        # CANDIDATE STATUS, FRESHNESS, CONTACT VERIFICATION
        # -------------------------------------------------------------
        if candidate_status and candidate_status.strip() and candidate_status.strip().upper() != 'ALL':
            st = candidate_status.strip().upper()
            if st == 'SHORTLISTED':
                filters &= Q(is_shortlisted=True) | Q(candidate_status='SHORTLISTED')
            elif st == 'SAVED_FOR_LATER':
                filters &= Q(is_saved_for_later=True) | Q(candidate_status='SAVED_FOR_LATER')
            elif st == 'NEW_CANDIDATE':
                from django.utils import timezone
                import datetime
                seven_days_ago = timezone.now() - datetime.timedelta(days=7)
                filters &= Q(created_at__gte=seven_days_ago)
            elif st == 'MODIFIED':
                from django.utils import timezone
                import datetime
                seven_days_ago = timezone.now() - datetime.timedelta(days=7)
                filters &= Q(updated_at__gte=seven_days_ago)
            else:
                filters &= Q(candidate_status=st)

        if freshness_days is not None:
            try:
                from django.utils import timezone
                import datetime
                cutoff = timezone.now() - datetime.timedelta(days=int(freshness_days))
                filters &= (Q(updated_at__gte=cutoff) | Q(created_at__gte=cutoff))
            except Exception:
                pass

        if has_resume is True:
            filters &= Q(resume__isnull=False) & ~Q(resume='')

        if has_verified_email is True:
            filters &= Q(user__is_verified=True)

        # -------------------------------------------------------------
        # SEARCH WITHIN RESULTS
        # -------------------------------------------------------------
        if search_within_results and search_within_results.strip():
            sw_clean = search_within_results.strip().lower()
            filters &= (
                Q(current_designation__icontains=sw_clean) |
                Q(skills__skill_name__icontains=sw_clean) |
                Q(candidate_tags__name__icontains=sw_clean) |
                Q(summary__icontains=sw_clean) |
                Q(raw_resume_text__icontains=sw_clean)
            )

        # Pipeline Stage & Job Filter
        if job_id and job_id.strip():
            try:
                filters &= Q(job_applications__job_id=job_id.strip())
            except Exception:
                pass

        if stage and stage.strip():
            stg = stage.strip().upper()
            if stg == 'OPEN':
                filters &= Q(job_applications__stage='OPEN')
            elif stg == 'APPLIED':
                filters &= Q(job_applications__stage__in=['OPEN', 'SYSTEM_SUBMITTED'])
            elif stg in ['UNDER_REVIEW', 'SCREENING']:
                filters &= Q(job_applications__stage__in=['SCREENING_FEEDBACK_PENDING', 'SYSTEM_SELECTED', 'AUTOMATION_SKIPPED', 'SCREENING_SELECT'])
            elif stg in ['SELECTED', 'SHORTLISTED']:
                filters &= Q(job_applications__stage__in=['SCREENING_SELECT', 'INTERVIEW_SELECT', 'ACCEPTED', 'JOINED', 'OFFER_STAGE'])
            elif stg in ['REJECTED']:
                filters &= Q(job_applications__stage__in=['SCREENING_REJECT', 'INTERVIEW_REJECT', 'SYSTEM_REJECTED', 'DROPOUT'])
            else:
                filters &= Q(job_applications__stage=stg)

        # Mandatory Keywords
        if mandatory_keywords:
            for mk in mandatory_keywords:
                if mk and mk.strip():
                    mk_clean = mk.strip().lower()
                    filters &= (
                        Q(candidate_tags__normalized_name__icontains=mk_clean) |
                        Q(skills__skill_name__icontains=mk_clean) |
                        Q(current_designation__icontains=mk_clean) |
                        Q(summary__icontains=mk_clean) |
                        Q(raw_resume_text__icontains=mk_clean)
                    )

        # Boolean Query Parsing
        if boolean_query and boolean_query.strip():
            parsed_bool = cls.parse_boolean_query(boolean_query)
            for must_t in parsed_bool["must"]:
                filters &= (
                    Q(current_designation__icontains=must_t) |
                    Q(skills__skill_name__icontains=must_t) |
                    Q(candidate_tags__name__icontains=must_t) |
                    Q(summary__icontains=must_t) |
                    Q(raw_resume_text__icontains=must_t)
                )
                all_search_terms.append(must_t)

            if parsed_bool["should"]:
                should_q = Q()
                for should_t in parsed_bool["should"]:
                    should_q |= (
                        Q(current_designation__icontains=should_t) |
                        Q(skills__skill_name__icontains=should_t) |
                        Q(candidate_tags__name__icontains=should_t) |
                        Q(summary__icontains=should_t) |
                        Q(raw_resume_text__icontains=should_t)
                    )
                    all_search_terms.append(should_t)
                filters &= should_q

        # Apply base inclusive filters
        queryset = queryset.filter(filters).distinct()

        # -------------------------------------------------------------
        # EXCLUDE KEYWORDS & BOOLEAN NOT CLAUSES (Reliable Exclusions)
        # -------------------------------------------------------------
        if exclude_keywords:
            ex_list = []
            if isinstance(exclude_keywords, list):
                ex_list = exclude_keywords
            elif isinstance(exclude_keywords, str):
                ex_list = [k.strip() for k in exclude_keywords.split(',') if k.strip()]

            for ex_term in ex_list:
                if ex_term and ex_term.strip():
                    ex_clean = ex_term.strip().lower()
                    queryset = queryset.exclude(
                        Q(current_designation__icontains=ex_clean) |
                        Q(skills__skill_name__icontains=ex_clean) |
                        Q(candidate_tags__name__icontains=ex_clean) |
                        Q(candidate_tags__canonical_name__icontains=ex_clean) |
                        Q(summary__icontains=ex_clean) |
                        Q(raw_resume_text__icontains=ex_clean) |
                        Q(experiences__designation__icontains=ex_clean)
                    )

        if boolean_query and boolean_query.strip():
            parsed_bool = cls.parse_boolean_query(boolean_query)
            for not_t in parsed_bool["must_not"]:
                queryset = queryset.exclude(
                    Q(current_designation__icontains=not_t) |
                    Q(skills__skill_name__icontains=not_t) |
                    Q(candidate_tags__name__icontains=not_t) |
                    Q(candidate_tags__canonical_name__icontains=not_t) |
                    Q(summary__icontains=not_t) |
                    Q(raw_resume_text__icontains=not_t) |
                    Q(experiences__designation__icontains=not_t)
                )

        # -------------------------------------------------------------
        # 2. KEYWORD & TAXONOMY RELATIONAL EXPANSION
        # -------------------------------------------------------------
        expanded_search_roles: Set[str] = set()
        expanded_search_skills: Set[str] = set()
        search_domains: Set[str] = set()

        for term in all_search_terms:
            t_clean = RecruitmentTaxonomyService.normalize_term(term).lower()
            if not t_clean:
                continue

            # Check in TV-URT TaxonomyEngine
            canonical_role = TaxonomyEngine.resolve_role_alias(term)
            if canonical_role:
                expanded_search_roles.add(canonical_role.lower())
                job_sug = TaxonomyEngine.get_job_posting_suggestions(canonical_role)
                for r in job_sug.get("suggested_roles", []):
                    expanded_search_roles.add(r.lower())
                for s in job_sug.get("suggested_skills", []):
                    expanded_search_skills.add(s.lower())

            des_obj = RecruitmentTaxonomyService.find_canonical_designation(term)
            if des_obj:
                expanded_search_roles.add(des_obj.canonical_name.lower())
                if des_obj.aliases:
                    for a in des_obj.aliases:
                        expanded_search_roles.add(a.strip().lower())
                if des_obj.industry:
                    search_domains.add(des_obj.industry.lower())

                for rel in des_obj.outgoing_relations.select_related('target_role'):
                    expanded_search_roles.add(rel.target_role.canonical_name.lower())

                for sr in des_obj.skill_relations.select_related('skill'):
                    expanded_search_skills.add(sr.skill.canonical_name.lower())
            else:
                expanded_search_skills.add(t_clean)

        # -------------------------------------------------------------
        # 3. RELEVANCE SCORING & MATCH QUALITY COMPUTATION
        # -------------------------------------------------------------
        scored_candidates: List[Dict[str, Any]] = []

        for candidate in queryset:
            relevance_score, match_quality, matched_tags_list, why_matched_reasons = cls._calculate_candidate_relevance(
                candidate=candidate,
                all_search_terms=all_search_terms,
                expanded_search_roles=expanded_search_roles,
                expanded_search_skills=expanded_search_skills,
                search_domains=search_domains,
                min_experience=min_experience,
                max_experience=max_experience,
                min_salary=min_salary,
                max_salary=max_salary,
                location=location,
                industry=industry,
                skills_filter=skills
            )

            # Skip candidates with zero relevance when search terms were specified
            if all_search_terms and relevance_score == 0:
                continue

            scored_candidates.append({
                "candidate": candidate,
                "relevance_score": relevance_score,
                "match_quality": match_quality,
                "matched_tags": matched_tags_list,
                "why_matched": why_matched_reasons,
                "ats_score": candidate.ats_score or 75
            })

        # -------------------------------------------------------------
        # 4. SORTING
        # -------------------------------------------------------------
        if sort_by in ["relevance", "match", "highest_match"]:
            scored_candidates.sort(key=lambda x: (-x["relevance_score"], -x["ats_score"], -x["candidate"].created_at.timestamp()))
        elif sort_by in ["ats_score", "highest_ats", "ats"]:
            scored_candidates.sort(key=lambda x: (-x["ats_score"], -x["relevance_score"], -x["candidate"].created_at.timestamp()))
        elif sort_by in ["experience", "highest_experience"]:
            scored_candidates.sort(key=lambda x: (-float(x["candidate"].total_experience or 0), -x["relevance_score"]))
        elif sort_by in ["newest", "created_at"]:
            scored_candidates.sort(key=lambda x: -x["candidate"].created_at.timestamp())

        return scored_candidates

    @classmethod
    def _calculate_candidate_relevance(
        cls,
        candidate: CandidateProfile,
        all_search_terms: List[str],
        expanded_search_roles: Set[str],
        expanded_search_skills: Set[str],
        search_domains: Set[str],
        min_experience: Optional[float] = None,
        max_experience: Optional[float] = None,
        min_salary: Optional[float] = None,
        max_salary: Optional[float] = None,
        location: Optional[str] = None,
        industry: Optional[str] = None,
        skills_filter: Optional[str] = None
    ) -> Tuple[int, str, List[str], List[str]]:
        """
        Calculates multi-signal relevance score (0-100), match quality label,
        matched tag chips, and transparent 'Why matched' explanation bullets.
        """
        if not all_search_terms and min_experience is None and min_salary is None and not location and not industry:
            # Default browse view: return ATS suitability
            score = candidate.ats_score or 75
            quality = "EXACT MATCH" if score >= 85 else ("STRONG MATCH" if score >= 70 else "RELATED MATCH")
            why_bullets = [
                f"✓ Candidate profile with {candidate.total_experience or 0} years experience",
                f"✓ Location: {candidate.location or 'Not specified'}"
            ]
            skills = [s.skill_name for s in candidate.skills.all()[:4]]
            return score, quality, skills, why_bullets

        total_score = 0.0
        matched_tags: Set[str] = set()
        why_bullets: List[str] = []

        cand_curr_des = (candidate.current_designation or "").strip().lower()
        cand_pref_role = (candidate.preferred_job_role or "").strip().lower()
        cand_skills = {s.skill_name.strip().lower(): s.skill_name for s in candidate.skills.all() if s.skill_name and s.skill_name.strip()}
        cand_tag_objs = list(candidate.candidate_tags.all())
        cand_tag_names = {t.normalized_name: t.name for t in cand_tag_objs}

        cand_past_des_list = [exp.designation.strip().lower() for exp in candidate.experiences.all() if exp.designation]

        exact_role_hit = False
        related_role_hit = False
        skill_hits = 0
        primary_search_term = all_search_terms[0] if all_search_terms else ""

        # Check search terms against Candidate Designation & Tags
        for term in all_search_terms:
            t_clean = RecruitmentTaxonomyService.normalize_term(term).lower()
            if not t_clean:
                continue

            # 1. Exact / Direct Designation Match
            if cand_curr_des and (t_clean == cand_curr_des or t_clean in cand_curr_des or cand_curr_des in t_clean):
                exact_role_hit = True
                total_score += 100.0
                matched_tags.add(candidate.current_designation)
                why_bullets.append(f"✓ {candidate.current_designation} — exact role match")
            elif any(t_clean == pd or t_clean in pd for pd in cand_past_des_list):
                related_role_hit = True
                total_score += 85.0
                matched_tags.add(term)
                why_bullets.append(f"✓ Previous Experience as {term} — related role")

            # 2. Canonical / Expanded Role Match (e.g. Vehicle Inspector matching Car Inspection query)
            elif any(r == cand_curr_des or r in cand_curr_des for r in expanded_search_roles):
                related_role_hit = True
                total_score += 90.0
                matched_tags.add(candidate.current_designation)
                why_bullets.append(f"✓ {candidate.current_designation} — related to {term}")

            # 3. Direct Skill Match
            if t_clean in cand_skills:
                skill_hits += 1
                total_score += 80.0
                matched_tags.add(cand_skills[t_clean])
                why_bullets.append(f"✓ Core Skill: {cand_skills[t_clean]}")
            elif t_clean in cand_tag_names:
                skill_hits += 1
                total_score += 75.0
                matched_tags.add(cand_tag_names[t_clean])
                why_bullets.append(f"✓ Candidate Tag: {cand_tag_names[t_clean]}")

        # Check expanded skills (skills associated with the queried role)
        associated_skill_matches = []
        for exp_sk in expanded_search_skills:
            if exp_sk in cand_skills:
                skill_hits += 1
                total_score += 35.0
                matched_tags.add(cand_skills[exp_sk])
                associated_skill_matches.append(cand_skills[exp_sk])
            elif exp_sk in cand_tag_names:
                skill_hits += 1
                total_score += 30.0
                matched_tags.add(cand_tag_names[exp_sk])
                associated_skill_matches.append(cand_tag_names[exp_sk])

        if associated_skill_matches:
            top_skills = list(dict.fromkeys(associated_skill_matches))[:3]
            why_bullets.append(f"✓ Domain Skills: {', '.join(top_skills)}")

        # Direct keyword match in candidate summary or raw resume text (phrase match)
        for term in all_search_terms:
            t_clean = RecruitmentTaxonomyService.normalize_term(term).lower()
            if not t_clean:
                continue
            if (candidate.summary and t_clean in candidate.summary.lower()) or (candidate.raw_resume_text and t_clean in candidate.raw_resume_text.lower()):
                skill_hits += 1
                total_score += 45.0
                matched_tags.add(term)

        # If search terms were provided but candidate had 0 matches across roles, skills, tags, or text
        if all_search_terms and not exact_role_hit and not related_role_hit and skill_hits == 0 and not matched_tags:
            return 0, "WEAK MATCH", [], []

        # Stopword dampening: if only a generic word like 'manager' or 'executive' matched without domain
        is_only_generic = all(RecruitmentTaxonomyService.normalize_term(t).lower() in GENERIC_ROLE_MODIFIERS for t in all_search_terms) if all_search_terms else False
        if is_only_generic:
            total_score = min(total_score, 40.0)

        # -------------------------------------------------------------
        # EXPERIENCE MATCH EXPLANATION & BOOST
        # -------------------------------------------------------------
        cand_exp = float(candidate.total_experience or 0.0)
        if min_experience is not None and max_experience is not None:
            total_score += 15.0
            why_bullets.append(f"✓ Experience: {cand_exp:.1f} years — within {float(min_experience):.0f}–{float(max_experience):.0f} years")
        elif min_experience is not None:
            total_score += 15.0
            why_bullets.append(f"✓ Experience: {cand_exp:.1f} years — >= {float(min_experience):.0f} years")
        elif max_experience is not None:
            total_score += 15.0
            why_bullets.append(f"✓ Experience: {cand_exp:.1f} years — <= {float(max_experience):.0f} years")
        elif cand_exp > 0:
            total_score += 10.0
            why_bullets.append(f"✓ Experience: {cand_exp:.1f} years")

        # -------------------------------------------------------------
        # SALARY MATCH EXPLANATION & BOOST
        # -------------------------------------------------------------
        sal_amount = float(candidate.current_salary or candidate.expected_salary or 0.0)
        sal_lpa = sal_amount / 100000.0 if sal_amount >= 1000 else sal_amount
        if min_salary is not None and max_salary is not None:
            min_lpa = float(min_salary) / 100000.0 if float(min_salary) >= 1000 else float(min_salary)
            max_lpa = float(max_salary) / 100000.0 if float(max_salary) >= 1000 else float(max_salary)
            total_score += 15.0
            why_bullets.append(f"✓ Current Salary: ₹{sal_lpa:.1f} LPA — within ₹{min_lpa:.0f}–{max_lpa:.0f} LPA")
        elif min_salary is not None:
            min_lpa = float(min_salary) / 100000.0 if float(min_salary) >= 1000 else float(min_salary)
            total_score += 15.0
            why_bullets.append(f"✓ Current Salary: ₹{sal_lpa:.1f} LPA — >= ₹{min_lpa:.0f} LPA")
        elif max_salary is not None:
            max_lpa = float(max_salary) / 100000.0 if float(max_salary) >= 1000 else float(max_salary)
            total_score += 15.0
            why_bullets.append(f"✓ Current Salary: ₹{sal_lpa:.1f} LPA — <= ₹{max_lpa:.0f} LPA")
        elif sal_lpa > 0:
            why_bullets.append(f"✓ Current Salary: ₹{sal_lpa:.1f} LPA")

        # -------------------------------------------------------------
        # LOCATION & INDUSTRY MATCH EXPLANATION
        # -------------------------------------------------------------
        if location and location.strip():
            loc_clean = location.strip().lower()
            if loc_clean in (candidate.location or "").lower() or loc_clean in (candidate.preferred_location or "").lower():
                total_score += 15.0
                why_bullets.append(f"✓ Location: {candidate.location or candidate.preferred_location} — matched")

        if industry and industry.strip():
            ind_clean = industry.strip().lower()
            if ind_clean in (candidate.industry or "").lower() or any(ind_clean in t.name.lower() for t in cand_tag_objs):
                total_score += 10.0
                why_bullets.append(f"✓ Industry: {candidate.industry or industry} — matched")

        # Normalize score into 0 - 100 range
        num_query_signals = max(1, len(all_search_terms))
        base_norm = total_score / num_query_signals
        if exact_role_hit:
            final_score = min(100, max(88, int(base_norm)))
        elif related_role_hit or skill_hits >= 2:
            final_score = min(92, max(75, int(base_norm)))
        elif skill_hits == 1:
            final_score = min(75, max(50, int(base_norm)))
        else:
            final_score = min(65, int(base_norm))

        # Match Quality Classification
        if final_score >= 85 and (exact_role_hit or skill_hits >= 2):
            match_quality = "EXACT MATCH"
        elif final_score >= 75 or related_role_hit or skill_hits >= 2:
            match_quality = "STRONG MATCH"
        elif final_score >= 50 or skill_hits >= 1:
            match_quality = "RELATED MATCH"
        else:
            match_quality = "WEAK MATCH"

        if not why_bullets:
            why_bullets.append(f"✓ Candidate profile matching {candidate.current_designation or 'requested criteria'}")

        return final_score, match_quality, list(matched_tags)[:6], why_bullets[:6]
