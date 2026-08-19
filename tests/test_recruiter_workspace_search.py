import pytest
import json
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
import datetime

from apps.candidates.models import (
    CandidateProfile, CandidateSkill, Experience, Education, CandidateTag,
    SavedCandidateSearch, RecentCandidateSearch
)
from services.universal_candidate_search_service import UniversalCandidateSearchService
from apps.taxonomy.services.taxonomy_engine import TaxonomyEngine

User = get_user_model()

@pytest.mark.django_db
class TestRecruiterCandidateSearchWorkspace:

    @pytest.fixture(autouse=True)
    def setup_data(self, db):
        TaxonomyEngine.ensure_seeded()

        # Create Recruiter
        self.recruiter = User.objects.create_user(
            email="recruiter.workspace@talentvault.io",
            password="Password123!",
            role="RECRUITER",
            first_name="Jane",
            last_name="Recruiter",
            is_verified=True
        )

        # 1. Sales Manager Candidate
        user_sales = User.objects.create_user(email="rahul.sales@example.com", role="CANDIDATE", first_name="Rahul", last_name="Verma")
        self.cand_sales = CandidateProfile.objects.create(
            user=user_sales,
            full_name="Rahul Verma",
            current_designation="Area Sales Manager",
            current_company="FMCG Retail Corp",
            location="Delhi",
            total_experience=6.5,
            current_salary=800000.0,
            expected_salary=1200000.0,
            notice_period=15,
            department="Sales",
            industry="FMCG",
            gender="MALE",
            willing_to_relocate=True,
            candidate_status="ACTIVE",
            summary="Experienced Area Sales Manager with 6+ years driving enterprise sales and CRM pipeline."
        )
        CandidateSkill.objects.create(profile=self.cand_sales, skill_name="Sales Management", years_of_experience=6.0)
        CandidateSkill.objects.create(profile=self.cand_sales, skill_name="CRM", years_of_experience=5.0)
        CandidateSkill.objects.create(profile=self.cand_sales, skill_name="B2B Sales", years_of_experience=4.0)
        Education.objects.create(
            profile=self.cand_sales,
            institution="Delhi University",
            degree="B.Com",
            qualification_level="UG",
            education_type="FULL_TIME",
            passing_year=2018
        )
        Education.objects.create(
            profile=self.cand_sales,
            institution="IIM Lucknow",
            degree="MBA",
            specialization="Marketing & Sales",
            qualification_level="PG",
            education_type="FULL_TIME",
            passing_year=2020
        )

        # 2. Python / Java Backend Developer
        user_dev = User.objects.create_user(email="priya.dev@example.com", role="CANDIDATE", first_name="Priya", last_name="Sharma", is_verified=True)
        self.cand_dev = CandidateProfile.objects.create(
            user=user_dev,
            full_name="Priya Sharma",
            current_designation="Senior Software Engineer",
            current_company="Tech Global Solutions",
            location="Bangalore",
            total_experience=4.5,
            current_salary=1400000.0,
            notice_period=30,
            department="Engineering",
            industry="IT Services",
            gender="FEMALE",
            has_career_break=True,
            candidate_status="ACTIVE",
            summary="Full stack python and java engineer building cloud native scalable microservices."
        )
        CandidateSkill.objects.create(profile=self.cand_dev, skill_name="Python", years_of_experience=4.0)
        CandidateSkill.objects.create(profile=self.cand_dev, skill_name="Django", years_of_experience=3.5)
        CandidateSkill.objects.create(profile=self.cand_dev, skill_name="Java", years_of_experience=3.0)
        CandidateSkill.objects.create(profile=self.cand_dev, skill_name="AWS", years_of_experience=2.5)
        Education.objects.create(
            profile=self.cand_dev,
            institution="IIT Bombay",
            degree="B.Tech",
            specialization="Computer Science",
            qualification_level="UG",
            education_type="FULL_TIME",
            passing_year=2021
        )

        # 3. Data Analyst Candidate
        user_data = User.objects.create_user(email="amit.data@example.com", role="CANDIDATE", first_name="Amit", last_name="Patel")
        self.cand_data = CandidateProfile.objects.create(
            user=user_data,
            full_name="Amit Patel",
            current_designation="Data Analyst",
            current_company="Analytics Inc",
            location="Mumbai",
            total_experience=3.0,
            current_salary=600000.0,
            notice_period=0,
            is_immediate_joiner=True,
            department="Data",
            industry="Analytics",
            is_differently_abled=True,
            disability_category="Low Vision",
            candidate_status="SHORTLISTED",
            is_shortlisted=True,
            summary="Data analyst specializing in SQL, Python, Tableau dashboards and business intelligence."
        )
        CandidateSkill.objects.create(profile=self.cand_data, skill_name="SQL", years_of_experience=3.0)
        CandidateSkill.objects.create(profile=self.cand_data, skill_name="Tableau", years_of_experience=2.0)
        CandidateSkill.objects.create(profile=self.cand_data, skill_name="Python", years_of_experience=2.0)
        Education.objects.create(
            profile=self.cand_data,
            institution="Mumbai University",
            degree="B.Sc",
            specialization="Statistics",
            qualification_level="UG",
            education_type="FULL_TIME",
            passing_year=2022
        )

        # 4. Telecaller / Customer Support (to test exclude keywords)
        user_bpo = User.objects.create_user(email="vikram.bpo@example.com", role="CANDIDATE", first_name="Vikram", last_name="Singh")
        self.cand_bpo = CandidateProfile.objects.create(
            user=user_bpo,
            full_name="Vikram Singh",
            current_designation="Telecaller Executive",
            current_company="CallCenter Pvt Ltd",
            location="Delhi",
            total_experience=1.0,
            current_salary=250000.0,
            department="Customer Support",
            industry="BPO",
            summary="Telecaller handling outbound sales calls and customer inquiries."
        )
        CandidateSkill.objects.create(profile=self.cand_bpo, skill_name="Telecalling", years_of_experience=1.0)
        CandidateSkill.objects.create(profile=self.cand_bpo, skill_name="Customer Service", years_of_experience=1.0)

    def test_multi_domain_autocomplete_sales_returns_sales_manager(self):
        """Test that typing 'sales' returns Sales Manager and related designations in autocomplete."""
        res = TaxonomyEngine.get_smart_suggestions("sales")
        labels = [s["label"] for s in res["suggestions"]]
        assert any("Sales" in l for l in labels)
        assert any("Sales Manager" in l or "Regional Sales Manager" in l or "Area Sales Manager" in l for l in labels)

    def test_multi_domain_autocomplete_data_and_manager(self):
        """Test autocomplete for data, manager, java, and account."""
        # Data
        res_data = TaxonomyEngine.get_smart_suggestions("data")
        labels_data = [s["label"] for s in res_data["suggestions"]]
        assert any("Data Analyst" in l or "Data Scientist" in l or "Data Engineer" in l for l in labels_data)

        # Manager
        res_mgr = TaxonomyEngine.get_smart_suggestions("manager")
        labels_mgr = [s["label"] for s in res_mgr["suggestions"]]
        assert any("Manager" in l for l in labels_mgr)

        # Java
        res_java = TaxonomyEngine.get_smart_suggestions("java")
        labels_java = [s["label"] for s in res_java["suggestions"]]
        assert any("Java" in l for l in labels_java)

    def test_candidate_search_sales_finds_sales_manager(self):
        """Test searching 'sales' retrieves Area Sales Manager with calibrated match score."""
        qs = CandidateProfile.objects.all()
        results = UniversalCandidateSearchService.search_candidates(
            base_queryset=qs,
            query="sales"
        )
        assert len(results) > 0
        cand_ids = [r["candidate"].id for r in results]
        assert self.cand_sales.id in cand_ids
        
        # Check sales candidate score and reasons
        sales_res = next(r for r in results if r["candidate"].id == self.cand_sales.id)
        assert sales_res["relevance_score"] >= 80
        assert sales_res["match_quality"] in ["EXACT MATCH", "STRONG MATCH"]
        assert len(sales_res["why_matched"]) > 0

    def test_exclude_keywords_filters_out_unwanted_roles(self):
        """Test excluding 'Telecaller' removes BPO candidate from sales results."""
        qs = CandidateProfile.objects.all()
        results = UniversalCandidateSearchService.search_candidates(
            base_queryset=qs,
            query="sales",
            exclude_keywords=["Telecaller", "BPO"]
        )
        cand_ids = [r["candidate"].id for r in results]
        assert self.cand_sales.id in cand_ids
        assert self.cand_bpo.id not in cand_ids

    def test_mandatory_keywords_enforces_must_have(self):
        """Test mandatory keywords (e.g. candidate MUST have Python AND AWS)."""
        qs = CandidateProfile.objects.all()
        results = UniversalCandidateSearchService.search_candidates(
            base_queryset=qs,
            query="Python",
            mandatory_keywords=["AWS"]
        )
        cand_ids = [r["candidate"].id for r in results]
        # cand_dev has Python AND AWS, while cand_data has only Python (no AWS)
        assert self.cand_dev.id in cand_ids
        assert self.cand_data.id not in cand_ids

    def test_boolean_search_expression(self):
        """Test Boolean query: ("Sales" OR "Developer") NOT "Telecaller"."""
        qs = CandidateProfile.objects.all()
        results = UniversalCandidateSearchService.search_candidates(
            base_queryset=qs,
            boolean_query='("Sales Manager" OR "Software Engineer") NOT "Telecaller"'
        )
        cand_ids = [r["candidate"].id for r in results]
        assert self.cand_sales.id in cand_ids
        assert self.cand_dev.id in cand_ids
        assert self.cand_bpo.id not in cand_ids

    def test_experience_and_salary_filters(self):
        """Test experience range (4.0 to 7.0 years) and salary range (5 to 15 LPA)."""
        qs = CandidateProfile.objects.all()
        results = UniversalCandidateSearchService.search_candidates(
            base_queryset=qs,
            min_experience=4.0,
            max_experience=7.0,
            min_salary=5.0,  # 5 LPA
            max_salary=15.0  # 15 LPA
        )
        cand_ids = [r["candidate"].id for r in results]
        assert self.cand_sales.id in cand_ids
        assert self.cand_dev.id in cand_ids
        assert self.cand_bpo.id not in cand_ids  # 1.0 yr exp

    def test_education_structured_filters_ug_and_pg(self):
        """Test UG degree (B.Tech in Computer Science) and PG degree (MBA from IIM)."""
        qs = CandidateProfile.objects.all()
        
        # Search B.Tech from IIT
        res_ug = UniversalCandidateSearchService.search_candidates(
            base_queryset=qs,
            ug_degree="B.Tech",
            ug_specialization="Computer Science",
            institute="IIT"
        )
        assert len(res_ug) == 1
        assert res_ug[0]["candidate"].id == self.cand_dev.id

        # Search MBA from IIM
        res_pg = UniversalCandidateSearchService.search_candidates(
            base_queryset=qs,
            pg_degree="MBA",
            institute="IIM"
        )
        assert len(res_pg) == 1
        assert res_pg[0]["candidate"].id == self.cand_sales.id

    def test_diversity_hiring_filters_explicit_data_only(self):
        """Test diversity filters (Female, Career Break, Differently-Abled)."""
        qs = CandidateProfile.objects.all()

        # Filter: Female candidates with career break
        res_female = UniversalCandidateSearchService.search_candidates(
            base_queryset=qs,
            gender="FEMALE",
            has_career_break=True
        )
        assert len(res_female) == 1
        assert res_female[0]["candidate"].id == self.cand_dev.id

        # Filter: Differently-abled candidates
        res_diff = UniversalCandidateSearchService.search_candidates(
            base_queryset=qs,
            is_differently_abled=True
        )
        assert len(res_diff) == 1
        assert res_diff[0]["candidate"].id == self.cand_data.id

    def test_candidate_status_and_shortlisted_tab(self):
        """Test candidate status filter and shortlisted candidates."""
        qs = CandidateProfile.objects.all()
        res_shortlisted = UniversalCandidateSearchService.search_candidates(
            base_queryset=qs,
            candidate_status="SHORTLISTED"
        )
        assert len(res_shortlisted) == 1
        assert res_shortlisted[0]["candidate"].id == self.cand_data.id

    def test_search_within_results(self):
        """Test search within results refining an existing candidate set."""
        qs = CandidateProfile.objects.all()
        # Initial search: Delhi candidates -> returns Rahul (Sales) and Vikram (BPO)
        # Search within results: "CRM" -> returns only Rahul
        results = UniversalCandidateSearchService.search_candidates(
            base_queryset=qs,
            location="Delhi",
            search_within_results="CRM"
        )
        cand_ids = [r["candidate"].id for r in results]
        assert self.cand_sales.id in cand_ids
        assert self.cand_bpo.id not in cand_ids

    def test_candidate_search_view_and_ajax_api(self, client):
        """Test CandidateSearchView HTTP GET and AJAX JSON responses."""
        client.force_login(self.recruiter)

        # 1. HTML Page Load
        resp = client.get(reverse('frontend:candidate_search'))
        assert resp.status_code == 200
        assert "Candidate Workspace" in resp.content.decode()

        # 2. AJAX Search Request
        resp_ajax = client.get(
            reverse('frontend:candidate_search') + "?q=sales&ajax=1",
            headers={"x-requested-with": "XMLHttpRequest"}
        )
        assert resp_ajax.status_code == 200
        data = resp_ajax.json()
        assert "html" in data
        assert data["count"] >= 1
        assert "Rahul Verma" in data["html"]

        # 3. Saved Searches API POST & GET
        save_resp = client.post(
            reverse('frontend:candidate_saved_searches'),
            data=json.dumps({
                "name": "Delhi Sales Managers",
                "q": "Sales Manager",
                "tags": ["Sales", "Delhi"],
                "filters": {"location": "Delhi", "min_exp": "5"},
                "count": 1
            }),
            content_type="application/json"
        )
        assert save_resp.status_code == 200
        assert save_resp.json()["success"] is True

        get_saved = client.get(reverse('frontend:candidate_saved_searches'))
        assert get_saved.status_code == 200
        saved_list = get_saved.json()["saved_searches"]
        assert len(saved_list) >= 1
        assert saved_list[0]["name"] == "Delhi Sales Managers"

    def test_all_fourteen_typeahead_queries_return_rich_suggestions(self, client):
        """
        Verify all 14 required typeahead queries:
        sales, data, manager, python, java, developer, hr, finance, account,
        marketing, medical, insurance, business, engineer.
        """
        client.force_login(self.recruiter)
        queries = [
            "sales", "data", "manager", "python", "java", "developer",
            "hr", "finance", "account", "marketing", "medical", "insurance",
            "business", "engineer"
        ]

        for q in queries:
            # 1. Test Taxonomy Engine Direct API
            resp = client.get(f"/api/taxonomy/suggestions/?q={q}")
            assert resp.status_code == 200
            data = resp.json()
            assert "suggestions" in data or "results" in data
            items = data.get("suggestions") or data.get("results")
            assert len(items) >= 1, f"Query '{q}' returned 0 suggestions"

            # Check that items have canonical name, type, and category
            first_item = items[0]
            assert "label" in first_item or "name" in first_item
            assert "type" in first_item
            assert "score" in first_item
            assert first_item["score"] > 0

            # 2. Test Candidates Autocomplete API View
            cand_resp = client.get(f"/api/candidates/autocomplete/?q={q}")
            assert cand_resp.status_code == 200
            cand_data = cand_resp.json()
            assert len(cand_data.get("results", [])) >= 1, f"Candidate autocomplete for '{q}' returned 0 results"

    def test_complete_eighteen_filter_test_matrix(self):
        """
        Verify all 18 test cases specified in the TalentVault Advanced Search test matrix.
        """
        base_qs = CandidateProfile.objects.all()

        # Test 1: Keyword = Sales Manager
        res1 = UniversalCandidateSearchService.search_candidates(base_queryset=base_qs, query="Sales Manager")
        ids1 = [r["candidate"].id for r in res1]
        assert self.cand_sales.id in ids1, "Test 1 Failed: Sales Manager not found"

        # Test 2: Keyword = Sales Manager, Location = Delhi
        res2 = UniversalCandidateSearchService.search_candidates(base_queryset=base_qs, query="Sales Manager", location="Delhi")
        ids2 = [r["candidate"].id for r in res2]
        assert self.cand_sales.id in ids2, "Test 2 Failed: Delhi Sales Manager not found"
        assert self.cand_dev.id not in ids2

        # Test 3: Keyword = Sales Manager, Experience = 3 to 7
        res3 = UniversalCandidateSearchService.search_candidates(base_queryset=base_qs, query="Sales Manager", min_experience=3.0, max_experience=7.0)
        ids3 = [r["candidate"].id for r in res3]
        assert self.cand_sales.id in ids3, "Test 3 Failed: Experience filter 3-7 failed"
        assert self.cand_bpo.id not in ids3

        # Test 4: Keyword = Sales Manager, Salary = 3 to 15 LPA
        res4 = UniversalCandidateSearchService.search_candidates(base_queryset=base_qs, query="Sales Manager", min_salary=3.0, max_salary=15.0)
        ids4 = [r["candidate"].id for r in res4]
        assert self.cand_sales.id in ids4, "Test 4 Failed: Salary filter 3-15 LPA failed"

        # Test 5: Skill = CRM
        res5 = UniversalCandidateSearchService.search_candidates(base_queryset=base_qs, skills="CRM")
        ids5 = [r["candidate"].id for r in res5]
        assert self.cand_sales.id in ids5, "Test 5 Failed: Skill CRM not found"
        assert self.cand_bpo.id not in ids5

        # Test 6: Department = Sales
        res6 = UniversalCandidateSearchService.search_candidates(base_queryset=base_qs, department="Sales")
        ids6 = [r["candidate"].id for r in res6]
        assert self.cand_sales.id in ids6, "Test 6 Failed: Department Sales not found"
        assert self.cand_dev.id not in ids6

        # Test 7: Industry = FMCG
        res7 = UniversalCandidateSearchService.search_candidates(base_queryset=base_qs, industry="FMCG")
        ids7 = [r["candidate"].id for r in res7]
        assert self.cand_sales.id in ids7, "Test 7 Failed: Industry FMCG not found"
        assert self.cand_dev.id not in ids7

        # Test 8: UG Degree = B.Tech
        res8 = UniversalCandidateSearchService.search_candidates(base_queryset=base_qs, ug_degree="B.Tech")
        ids8 = [r["candidate"].id for r in res8]
        assert self.cand_dev.id in ids8, "Test 8 Failed: UG Degree B.Tech not found"
        assert self.cand_sales.id not in ids8

        # Test 9: UG Specialization = Computer Science
        res9 = UniversalCandidateSearchService.search_candidates(base_queryset=base_qs, ug_specialization="Computer Science")
        ids9 = [r["candidate"].id for r in res9]
        assert self.cand_dev.id in ids9, "Test 9 Failed: UG Specialization Computer Science not found"
        assert self.cand_sales.id not in ids9

        # Test 10: Passing Year = 2020 to 2025
        res10 = UniversalCandidateSearchService.search_candidates(base_queryset=base_qs, passing_year_from=2020, passing_year_to=2025)
        ids10 = [r["candidate"].id for r in res10]
        assert self.cand_dev.id in ids10, "Test 10 Failed: Passing Year filter 2020-2025 failed"

        # Test 11: Company = FMCG Retail Corp
        res11 = UniversalCandidateSearchService.search_candidates(base_queryset=base_qs, company="FMCG Retail Corp")
        ids11 = [r["candidate"].id for r in res11]
        assert self.cand_sales.id in ids11, "Test 11 Failed: Company filter FMCG Retail Corp failed"
        assert self.cand_dev.id not in ids11

        # Test 12: Exclude Keyword = Telecalling
        res12 = UniversalCandidateSearchService.search_candidates(base_queryset=base_qs, exclude_keywords="Telecalling")
        ids12 = [r["candidate"].id for r in res12]
        assert self.cand_bpo.id not in ids12, "Test 12 Failed: Exclude Telecalling failed"
        assert self.cand_sales.id in ids12

        # Test 13: Verified Email = ON
        res13 = UniversalCandidateSearchService.search_candidates(base_queryset=base_qs, has_verified_email=True)
        ids13 = [r["candidate"].id for r in res13]
        assert self.cand_dev.id in ids13, "Test 13 Failed: Verified Email filter failed"

        # Test 14: Attached Resume = ON
        res14 = UniversalCandidateSearchService.search_candidates(base_queryset=base_qs, has_resume=True)
        assert isinstance(res14, list), "Test 14 Failed: Attached resume query failed"

        # Test 15: Resume Freshness = Last 30 Days
        res15 = UniversalCandidateSearchService.search_candidates(base_queryset=base_qs, freshness_days=30)
        ids15 = [r["candidate"].id for r in res15]
        assert self.cand_sales.id in ids15, "Test 15 Failed: Freshness 30 days failed"

        # Test 16: Boolean: Sales Manager AND CRM
        res16 = UniversalCandidateSearchService.search_candidates(base_queryset=base_qs, boolean_query='"Sales Manager" AND "CRM"')
        ids16 = [r["candidate"].id for r in res16]
        assert self.cand_sales.id in ids16, "Test 16 Failed: Boolean AND failed"
        assert self.cand_bpo.id not in ids16

        # Test 17: Boolean: Sales Manager OR Software Engineer
        res17 = UniversalCandidateSearchService.search_candidates(base_queryset=base_qs, boolean_query='"Sales Manager" OR "Software Engineer"')
        ids17 = [r["candidate"].id for r in res17]
        assert self.cand_sales.id in ids17, "Test 17 Failed: Boolean OR failed"
        assert self.cand_dev.id in ids17
        assert self.cand_bpo.id not in ids17

        # Test 18: Boolean: Sales NOT Telecalling
        res18 = UniversalCandidateSearchService.search_candidates(base_queryset=base_qs, boolean_query='Sales NOT Telecalling')
        ids18 = [r["candidate"].id for r in res18]
        assert self.cand_sales.id in ids18, "Test 18 Failed: Boolean NOT failed"
        assert self.cand_bpo.id not in ids18

    def test_real_world_car_inspection_combined_multi_filter(self):
        """
        Real-world recruiter search test:
        Role: Car Inspection
        Experience: 4 to 5 years (3.8 excluded, 4.0/4.6/5.0 included, 5.1 excluded)
        Salary: 1 to 8 LPA (0.8 excluded, 5.5/6.0 included, 9.0 excluded)
        Strict Conjunction: ALL criteria must match together.
        Explanations: Transparent 'Why this candidate matches' bullets with actual data.
        """
        # 1. Matching candidate: Vehicle Inspector, 4.6 yrs exp, 5.5 LPA, Delhi, Automotive
        user_match = User.objects.create_user(
            email='vehicle_inspector_match@example.com',
            password='password123',
            first_name='Amit',
            last_name='Sharma',
            role=User.Role.CANDIDATE
        )
        cand_match = CandidateProfile.objects.create(
            user=user_match,
            full_name='Amit Sharma',
            current_designation='Vehicle Inspector',
            industry='Automotive & Manufacturing',
            location='Delhi, India',
            total_experience=4.6,
            current_salary=550000, # 5.5 LPA
            expected_salary=650000,
            ats_score=92
        )
        CandidateSkill.objects.create(profile=cand_match, skill_name='Vehicle Inspection')
        CandidateSkill.objects.create(profile=cand_match, skill_name='Used Car Evaluation')
        CandidateSkill.objects.create(profile=cand_match, skill_name='OBD Scanning')
        CandidateTag.objects.create(profile=cand_match, name='Vehicle Inspector', canonical_name='Vehicle Inspector', tag_type='ROLE')

        # 2. Excluded by Experience: Car Inspector with 3.8 yrs exp (below 4 yrs)
        user_exp_low = User.objects.create_user(email='car_insp_low_exp@example.com', password='password123', first_name='Raj', last_name='Kumar', role=User.Role.CANDIDATE)
        cand_exp_low = CandidateProfile.objects.create(
            user=user_exp_low,
            full_name='Raj Kumar',
            current_designation='Car Inspector',
            industry='Automotive & Manufacturing',
            location='Delhi, India',
            total_experience=3.8, # Excluded: < 4.0
            current_salary=450000, # 4.5 LPA
            ats_score=85
        )

        # 3. Excluded by Experience: Vehicle Inspector with 5.1 yrs exp (above 5 yrs)
        user_exp_high = User.objects.create_user(email='car_insp_high_exp@example.com', password='password123', first_name='Suresh', last_name='Verma', role=User.Role.CANDIDATE)
        cand_exp_high = CandidateProfile.objects.create(
            user=user_exp_high,
            full_name='Suresh Verma',
            current_designation='Vehicle Inspector',
            industry='Automotive & Manufacturing',
            location='Delhi, India',
            total_experience=5.1, # Excluded: > 5.0
            current_salary=500000,
            ats_score=88
        )

        # 4. Excluded by Salary: Car Inspector with 9.0 LPA salary (above 8 LPA)
        user_sal_high = User.objects.create_user(email='car_insp_high_sal@example.com', password='password123', first_name='Vikas', last_name='Malhotra', role=User.Role.CANDIDATE)
        cand_sal_high = CandidateProfile.objects.create(
            user=user_sal_high,
            full_name='Vikas Malhotra',
            current_designation='Vehicle Inspector',
            industry='Automotive & Manufacturing',
            location='Delhi, India',
            total_experience=4.5,
            current_salary=900000, # 9.0 LPA -> Excluded: > 8.0 LPA
            ats_score=89
        )

        # 5. Excluded by Salary: Car Inspector with 0.8 LPA salary (below 1 LPA)
        user_sal_low = User.objects.create_user(email='car_insp_low_sal@example.com', password='password123', first_name='Manish', last_name='Yadav', role=User.Role.CANDIDATE)
        cand_sal_low = CandidateProfile.objects.create(
            user=user_sal_low,
            full_name='Manish Yadav',
            current_designation='Car Inspector',
            industry='Automotive & Manufacturing',
            location='Delhi, India',
            total_experience=4.2,
            current_salary=80000, # 0.8 LPA -> Excluded: < 1.0 LPA
            ats_score=80
        )

        # 6. Unrelated Role: Software Engineer with 4.5 yrs exp, 5.0 LPA, mentions "car inspection tool" in text
        user_sw = User.objects.create_user(email='sw_engineer_car@example.com', password='password123', first_name='Pooja', last_name='Patel', role=User.Role.CANDIDATE)
        cand_sw = CandidateProfile.objects.create(
            user=user_sw,
            full_name='Pooja Patel',
            current_designation='Software Engineer',
            industry='Information Technology',
            location='Delhi, India',
            total_experience=4.5,
            current_salary=500000, # 5.0 LPA
            raw_resume_text='Developed Python applications. Drove my personal car. Assisted code inspection.',
            ats_score=85
        )
        CandidateSkill.objects.create(profile=cand_sw, skill_name='Python')
        CandidateSkill.objects.create(profile=cand_sw, skill_name='Django')

        base_qs = CandidateProfile.objects.all()

        # Execute Combined Real-World Search: Role = "Car Inspection", Exp = 4-5 yrs, Salary = 1-8 LPA
        results = UniversalCandidateSearchService.search_candidates(
            base_queryset=base_qs,
            designation="Car Inspection",
            min_experience=4.0,
            max_experience=5.0,
            min_salary=1.0,
            max_salary=8.0,
            location="Delhi"
        )

        matched_ids = [r["candidate"].id for r in results]

        # Assert correct candidate qualified
        assert cand_match.id in matched_ids, "Expected qualified Vehicle Inspector candidate to be returned"

        # Assert all invalid candidates are strictly excluded
        assert cand_exp_low.id not in matched_ids, "Candidate with 3.8 yrs exp must be excluded when range is 4-5 yrs"
        assert cand_exp_high.id not in matched_ids, "Candidate with 5.1 yrs exp must be excluded when range is 4-5 yrs"
        assert cand_sal_high.id not in matched_ids, "Candidate with 9.0 LPA salary must be excluded when max is 8.0 LPA"
        assert cand_sal_low.id not in matched_ids, "Candidate with 0.8 LPA salary must be excluded when min is 1.0 LPA"
        assert cand_sw.id not in matched_ids, "Software Engineer must not qualify for Car Inspection search"

        # Verify Explanation Bullets
        match_result = next(r for r in results if r["candidate"].id == cand_match.id)
        assert match_result["relevance_score"] >= 85, f"Expected high relevance score >= 85, got {match_result['relevance_score']}"
        assert match_result["match_quality"] in ["EXACT MATCH", "STRONG MATCH"]

        why_bullets = match_result["why_matched"]
        why_text = " ".join(why_bullets)

        # Verify dynamic, transparent explanation bullets
        assert any("Vehicle Inspector" in b for b in why_bullets), "Explanation must mention Vehicle Inspector role match"
        assert any("Experience: 4.6 years" in b and "4–5" in b for b in why_bullets), "Explanation must show 4.6 years experience within 4-5 years"
        assert any("5.5 LPA" in b and "1–8" in b for b in why_bullets), "Explanation must show 5.5 LPA salary within 1-8 LPA"
        assert any("Location: Delhi" in b for b in why_bullets), "Explanation must show Location Delhi match"

    def test_multi_filter_strict_conjunction_sales_automobile(self):
        """
        Tests multi-filter strict conjunction:
        Role = Sales Manager AND Experience = 3–6 years AND Salary = 4–10 LPA AND Location = Delhi AND Industry = Automobile
        """
        # 1. Matching candidate
        u1 = User.objects.create_user(email='auto_sales_mgr_match@example.com', password='password123', first_name='Deepak', last_name='Gupta', role=User.Role.CANDIDATE)
        c1 = CandidateProfile.objects.create(
            user=u1,
            full_name='Deepak Gupta',
            current_designation='Area Sales Manager',
            industry='Automobile',
            location='Delhi, India',
            total_experience=5.0,
            current_salary=700000, # 7 LPA
            ats_score=90
        )
        CandidateTag.objects.create(profile=c1, name='Sales Manager', canonical_name='Sales Manager', tag_type='ROLE')
        CandidateSkill.objects.create(profile=c1, skill_name='Channel Sales')

        # 2. Excluded by Location (Mumbai)
        u2 = User.objects.create_user(email='auto_sales_mgr_mumbai@example.com', password='password123', first_name='Rohan', last_name='Mehta', role=User.Role.CANDIDATE)
        c2 = CandidateProfile.objects.create(
            user=u2,
            full_name='Rohan Mehta',
            current_designation='Sales Manager',
            industry='Automobile',
            location='Mumbai, India',
            total_experience=5.0,
            current_salary=700000,
            ats_score=90
        )

        # 3. Excluded by Industry (Banking)
        u3 = User.objects.create_user(email='bfsi_sales_mgr_delhi@example.com', password='password123', first_name='Anil', last_name='Kapoor', role=User.Role.CANDIDATE)
        c3 = CandidateProfile.objects.create(
            user=u3,
            full_name='Anil Kapoor',
            current_designation='Sales Manager',
            industry='Banking & Financial Services',
            location='Delhi, India',
            total_experience=5.0,
            current_salary=700000,
            ats_score=90
        )

        base_qs = CandidateProfile.objects.all()

        results = UniversalCandidateSearchService.search_candidates(
            base_queryset=base_qs,
            designation="Sales Manager",
            min_experience=3.0,
            max_experience=6.0,
            min_salary=4.0,
            max_salary=10.0,
            location="Delhi",
            industry="Automobile"
        )

        matched_ids = [r["candidate"].id for r in results]
        assert c1.id in matched_ids, "Candidate matching all 5 criteria must be returned"
        assert c2.id not in matched_ids, "Candidate in Mumbai must be excluded by Delhi location filter"
        assert c3.id not in matched_ids, "Candidate in BFSI must be excluded by Automobile industry filter"
