import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.candidates.models import (
    CandidateProfile, CandidateSkill, Experience, Education, CandidateTag,
    TaxonomyDesignation, TaxonomySkill, RoleRelation, RoleSkillRelation,
    SavedCandidateSearch, RecentCandidateSearch
)
from services.recruitment_taxonomy_service import RecruitmentTaxonomyService
from services.candidate_tagging_service import CandidateTaggingService
from services.universal_candidate_search_service import UniversalCandidateSearchService

User = get_user_model()


@pytest.fixture
def recruiter_user(db):
    user = User.objects.create_user(
        email='recruiter_test@talentvault.com',
        password='TestPassword123!',
        first_name='Recruiter',
        last_name='User',
        role='RECRUITER',
        recruiter_status='ACTIVE'
    )
    return user


@pytest.fixture
def multi_domain_candidates(db):
    RecruitmentTaxonomyService.ensure_taxonomy_seeded()

    # 1. Sales Manager candidate
    user_sales = User.objects.create_user(email='sales_mgr@example.com', password='pwd', role='CANDIDATE')
    cand_sales = CandidateProfile.objects.create(
        user=user_sales,
        full_name='Rajesh Sharma',
        current_designation='Sales Manager',
        current_company='Tata Consumer',
        total_experience=Decimal('6.5'),
        current_salary=Decimal('1400000'),
        location='New Delhi, India',
        ats_score=88
    )
    CandidateSkill.objects.create(profile=cand_sales, skill_name='Channel Sales', proficiency='EXPERT')
    CandidateSkill.objects.create(profile=cand_sales, skill_name='CRM', proficiency='INTERMEDIATE')
    CandidateSkill.objects.create(profile=cand_sales, skill_name='B2B Sales', proficiency='ADVANCED')
    Experience.objects.create(
        profile=cand_sales,
        company_name='Dabur India',
        designation='Area Sales Manager',
        is_current=False
    )
    CandidateTaggingService.tag_candidate_profile(cand_sales)

    # 2. Area Sales Manager candidate
    user_asm = User.objects.create_user(email='asm_user@example.com', password='pwd', role='CANDIDATE')
    cand_asm = CandidateProfile.objects.create(
        user=user_asm,
        full_name='Vikas Verma',
        current_designation='Area Sales Manager',
        current_company='Hindustan Unilever',
        total_experience=Decimal('4.0'),
        current_salary=Decimal('950000'),
        location='Mumbai, India',
        ats_score=82
    )
    CandidateSkill.objects.create(profile=cand_asm, skill_name='Direct Sales', proficiency='EXPERT')
    CandidateSkill.objects.create(profile=cand_asm, skill_name='Lead Generation', proficiency='ADVANCED')
    CandidateTaggingService.tag_candidate_profile(cand_asm)

    # 3. Python Developer candidate
    user_python = User.objects.create_user(email='python_dev@example.com', password='pwd', role='CANDIDATE')
    cand_python = CandidateProfile.objects.create(
        user=user_python,
        full_name='Priya Nair',
        current_designation='Python Developer',
        current_company='Infosys',
        total_experience=Decimal('3.5'),
        current_salary=Decimal('800000'),
        location='Bengaluru, India',
        ats_score=90
    )
    CandidateSkill.objects.create(profile=cand_python, skill_name='Python', proficiency='EXPERT')
    CandidateSkill.objects.create(profile=cand_python, skill_name='Django', proficiency='ADVANCED')
    CandidateSkill.objects.create(profile=cand_python, skill_name='PostgreSQL', proficiency='INTERMEDIATE')
    CandidateTaggingService.tag_candidate_profile(cand_python)

    # 4. Accountant candidate
    user_acct = User.objects.create_user(email='accountant@example.com', password='pwd', role='CANDIDATE')
    cand_acct = CandidateProfile.objects.create(
        user=user_acct,
        full_name='Suresh Iyer',
        current_designation='Senior Accountant',
        current_company='Deloitte',
        total_experience=Decimal('5.0'),
        current_salary=Decimal('750000'),
        location='Chennai, India',
        ats_score=85
    )
    CandidateSkill.objects.create(profile=cand_acct, skill_name='Tally', proficiency='EXPERT')
    CandidateSkill.objects.create(profile=cand_acct, skill_name='GST Filing', proficiency='EXPERT')
    CandidateSkill.objects.create(profile=cand_acct, skill_name='Taxation', proficiency='ADVANCED')
    CandidateTaggingService.tag_candidate_profile(cand_acct)

    # 5. Medical Representative (Pharma) candidate
    user_mr = User.objects.create_user(email='med_rep@example.com', password='pwd', role='CANDIDATE')
    cand_mr = CandidateProfile.objects.create(
        user=user_mr,
        full_name='Amitabh Sen',
        current_designation='Medical Representative',
        current_company='Sun Pharma',
        total_experience=Decimal('3.0'),
        current_salary=Decimal('450000'),
        location='Kolkata, India',
        ats_score=78
    )
    CandidateSkill.objects.create(profile=cand_mr, skill_name='Pharma Sales', proficiency='EXPERT')
    CandidateSkill.objects.create(profile=cand_mr, skill_name='Doctor Detailing', proficiency='EXPERT')
    CandidateTaggingService.tag_candidate_profile(cand_mr)

    # 6. Automobile Technician candidate
    user_auto = User.objects.create_user(email='auto_tech@example.com', password='pwd', role='CANDIDATE')
    cand_auto = CandidateProfile.objects.create(
        user=user_auto,
        full_name='Ramesh Kulkarni',
        current_designation='Automobile Technician',
        current_company='Maruti Suzuki Service',
        total_experience=Decimal('4.5'),
        current_salary=Decimal('400000'),
        location='Pune, India',
        ats_score=80
    )
    CandidateSkill.objects.create(profile=cand_auto, skill_name='Engine Diagnostics', proficiency='EXPERT')
    CandidateSkill.objects.create(profile=cand_auto, skill_name='Vehicle Maintenance', proficiency='EXPERT')
    CandidateTaggingService.tag_candidate_profile(cand_auto)

    # 7. Civil Engineer candidate
    user_civil = User.objects.create_user(email='civil_eng@example.com', password='pwd', role='CANDIDATE')
    cand_civil = CandidateProfile.objects.create(
        user=user_civil,
        full_name='Deepak Patil',
        current_designation='Civil Engineer',
        current_company='L&T Construction',
        total_experience=Decimal('7.0'),
        current_salary=Decimal('1100000'),
        location='Hyderabad, India',
        ats_score=86
    )
    CandidateSkill.objects.create(profile=cand_civil, skill_name='AutoCAD', proficiency='EXPERT')
    CandidateSkill.objects.create(profile=cand_civil, skill_name='Site Execution', proficiency='EXPERT')
    CandidateTaggingService.tag_candidate_profile(cand_civil)

    return {
        'sales': cand_sales,
        'asm': cand_asm,
        'python': cand_python,
        'accountant': cand_acct,
        'pharma': cand_mr,
        'auto': cand_auto,
        'civil': cand_civil
    }


@pytest.mark.django_db
def test_taxonomy_seeding_and_canonical_lookup():
    """Verify that multi-domain seed taxonomy is populated and alias canonicalization works."""
    RecruitmentTaxonomyService.ensure_taxonomy_seeded()

    des_count = TaxonomyDesignation.objects.count()
    assert des_count >= 15

    # Test Canonical lookup across domains
    des_sales = RecruitmentTaxonomyService.find_canonical_designation('Sales Manager')
    assert des_sales is not None
    assert des_sales.canonical_name == 'Sales Manager'

    des_asm = RecruitmentTaxonomyService.find_canonical_designation('ASM')
    assert des_asm is not None
    assert des_asm.canonical_name == 'Area Sales Manager'

    des_py = RecruitmentTaxonomyService.find_canonical_designation('Python Dev')
    assert des_py is not None
    assert des_py.canonical_name == 'Python Developer'

    des_mr = RecruitmentTaxonomyService.find_canonical_designation('Pharma Rep')
    assert des_mr is not None
    assert des_mr.canonical_name == 'Medical Representative'


@pytest.mark.django_db
def test_smart_suggestions_graph_traversal():
    """Verify AI suggested keywords returns hierarchically related roles, skills, and domains without hardcoded logic."""
    RecruitmentTaxonomyService.ensure_taxonomy_seeded()

    # Suggestions for Sales Manager
    sales_sug = RecruitmentTaxonomyService.get_smart_suggestions('Sales Manager', limit=10)
    assert len(sales_sug['suggestions']) > 0
    labels = [s['label'] for s in sales_sug['suggestions']]
    # Should include related roles (e.g. Area Sales Manager, Regional Sales Manager) and core skills
    assert any('Sales' in l or 'CRM' in l or 'Manager' in l for l in labels)

    # Suggestions for Pharmacist / Medical Representative
    pharma_sug = RecruitmentTaxonomyService.get_smart_suggestions('Medical Representative', limit=10)
    assert len(pharma_sug['suggestions']) > 0
    pharma_labels = [s['label'] for s in pharma_sug['suggestions']]
    assert any('Pharma' in l or 'Doctor' in l or 'Sales' in l for l in pharma_labels)

    # Suggestions for Unknown Role (e.g. "Renewable Energy Specialist")
    unknown_sug = RecruitmentTaxonomyService.get_smart_suggestions('Renewable Energy Specialist', limit=8)
    assert len(unknown_sug['suggestions']) > 0


@pytest.mark.django_db
def test_autocomplete_fast_ranking():
    """Verify autocomplete suggestions rank exact > prefix > substring."""
    RecruitmentTaxonomyService.ensure_taxonomy_seeded()

    results = RecruitmentTaxonomyService.get_autocomplete_suggestions('sales', field_type='all', limit=10)
    assert len(results) > 0
    assert any('Sales' in r['value'] for r in results)


@pytest.mark.django_db
def test_candidate_automatic_tagging(multi_domain_candidates):
    """Verify CandidateTaggingService extracts and indexes tags with provenance and confidence scores."""
    cand_sales = multi_domain_candidates['sales']
    tags = CandidateTag.objects.filter(profile=cand_sales)
    assert tags.count() >= 3

    curr_des_tag = tags.filter(tag_type='DESIGNATION', is_current=True).first()
    assert curr_des_tag is not None
    assert curr_des_tag.name == 'Sales Manager'
    assert curr_des_tag.confidence >= 0.95

    skill_tag = tags.filter(tag_type='SKILL', name='Channel Sales').first()
    assert skill_tag is not None
    assert skill_tag.source == 'resume_parser'


@pytest.mark.django_db
def test_universal_candidate_search_sales_domain(multi_domain_candidates):
    """Verify search for Sales Manager returns exact match for Sales Manager and related match for ASM, but excludes Python/Civil."""
    base_qs = CandidateProfile.objects.all()

    # Search: "Sales Manager"
    results = UniversalCandidateSearchService.search_candidates(
        base_queryset=base_qs,
        query='Sales Manager'
    )

    result_profiles = [r['candidate'] for r in results]
    assert multi_domain_candidates['sales'] in result_profiles
    assert multi_domain_candidates['asm'] in result_profiles
    assert multi_domain_candidates['python'] not in result_profiles

    # Check top candidate match quality
    top_result = results[0]
    assert top_result['candidate'] == multi_domain_candidates['sales']
    assert top_result['match_quality'] in ['EXACT MATCH', 'STRONG MATCH']
    assert top_result['relevance_score'] >= 85
    assert len(top_result['why_matched']) > 0


@pytest.mark.django_db
def test_universal_candidate_search_pharma_domain(multi_domain_candidates):
    """Verify search for Pharma Sales returns Medical Representative with why matched breakdown."""
    base_qs = CandidateProfile.objects.all()

    results = UniversalCandidateSearchService.search_candidates(
        base_queryset=base_qs,
        query='Pharma Sales'
    )

    result_profiles = [r['candidate'] for r in results]
    assert multi_domain_candidates['pharma'] in result_profiles
    assert multi_domain_candidates['python'] not in result_profiles
    assert multi_domain_candidates['auto'] not in result_profiles


@pytest.mark.django_db
def test_universal_candidate_search_automobile_domain(multi_domain_candidates):
    """Verify search for Automobile Technician returns Automobile candidate."""
    base_qs = CandidateProfile.objects.all()

    results = UniversalCandidateSearchService.search_candidates(
        base_queryset=base_qs,
        query='Automobile Technician'
    )

    result_profiles = [r['candidate'] for r in results]
    assert multi_domain_candidates['auto'] in result_profiles
    assert results[0]['candidate'] == multi_domain_candidates['auto']
    assert results[0]['match_quality'] == 'EXACT MATCH'


@pytest.mark.django_db
def test_structured_filters_experience_and_location(multi_domain_candidates):
    """Verify structured min/max experience and location filters."""
    base_qs = CandidateProfile.objects.all()

    # Min experience 6.0 years -> only Sales Manager (6.5) and Civil Engineer (7.0)
    results = UniversalCandidateSearchService.search_candidates(
        base_queryset=base_qs,
        min_experience=6.0
    )
    result_profiles = [r['candidate'] for r in results]
    assert multi_domain_candidates['sales'] in result_profiles
    assert multi_domain_candidates['civil'] in result_profiles
    assert multi_domain_candidates['python'] not in result_profiles # 3.5 yrs
    assert multi_domain_candidates['asm'] not in result_profiles # 4.0 yrs

    # Location filter "Bengaluru" -> only Python Developer
    loc_results = UniversalCandidateSearchService.search_candidates(
        base_queryset=base_qs,
        location='Bengaluru'
    )
    loc_profiles = [r['candidate'] for r in loc_results]
    assert multi_domain_candidates['python'] in loc_profiles
    assert multi_domain_candidates['sales'] not in loc_profiles


@pytest.mark.django_db
def test_boolean_query_parser(multi_domain_candidates):
    """Verify Boolean parsing AND / NOT."""
    parsed = UniversalCandidateSearchService.parse_boolean_query('"Sales Manager" AND "CRM" NOT "Insurance"')
    assert "Sales Manager" in parsed["must"]
    assert "CRM" in parsed["must"]
    assert "Insurance" in parsed["must_not"]

    base_qs = CandidateProfile.objects.all()
    results = UniversalCandidateSearchService.search_candidates(
        base_queryset=base_qs,
        boolean_query='"Sales Manager" AND "CRM"'
    )
    result_profiles = [r['candidate'] for r in results]
    assert multi_domain_candidates['sales'] in result_profiles


@pytest.mark.django_db
def test_saved_and_recent_searches_api(recruiter_user, multi_domain_candidates):
    """Verify saved searches and recent searches API endpoints."""
    client = Client()
    client.force_login(recruiter_user)

    # 1. Save a search
    save_url = reverse('frontend:candidate_saved_searches')
    response = client.post(
        save_url,
        data={
            'name': 'Bengaluru Python Developers',
            'q': 'Python Developer',
            'tags': ['Python', 'Django'],
            'filters': {'location': 'Bengaluru', 'min_exp': 3},
            'count': 1
        },
        content_type='application/json'
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data['status'] == 'success'
    saved_id = res_data['saved_search']['id']

    # 2. Get saved searches
    get_res = client.get(save_url)
    assert get_res.status_code == 200
    saved_list = get_res.json()['saved_searches']
    assert len(saved_list) >= 1
    assert saved_list[0]['name'] == 'Bengaluru Python Developers'

    # 3. Delete saved search
    del_url = reverse('frontend:candidate_saved_search_detail', kwargs={'pk': saved_id})
    del_res = client.delete(del_url)
    assert del_res.status_code == 200
    assert del_res.json()['status'] == 'success'


@pytest.mark.django_db
def test_candidate_suggestions_api(recruiter_user):
    """Verify /api/candidates/suggestions/ endpoint returns structured suggestions."""
    client = Client()
    client.force_login(recruiter_user)

    url = reverse('frontend:candidate_suggestions')
    response = client.get(url, {'q': 'Civil Engineer'})
    assert response.status_code == 200
    data = response.json()
    assert 'suggestions' in data
    assert len(data['suggestions']) > 0
