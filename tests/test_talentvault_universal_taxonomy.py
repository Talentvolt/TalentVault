import pytest
import json
from django.urls import reverse
from django.core.management import call_command
from apps.taxonomy.models import (
    JobRole, Skill, Technology, Tool, TaxonomyAlias,
    RoleSkill, RoleRelation, Industry, Department,
    TaxonomyStatus, TaxonomySource
)
from apps.taxonomy.services.taxonomy_engine import TaxonomyEngine
from apps.taxonomy.services.taxonomy_importer import TaxonomyImporter
from apps.taxonomy.services.taxonomy_seeder import TaxonomySeeder
from apps.candidates.models import CandidateProfile, CandidateSkill, Experience, CandidateTag
from services.candidate_tagging_service import CandidateTaggingService


@pytest.mark.django_db
class TestTalentVaultUniversalTaxonomy:

    def setup_method(self):
        TaxonomySeeder.seed_all()

    def test_seeding_and_statistics(self):
        stats = TaxonomyImporter.get_summary_statistics()
        assert stats["total_industries"] >= 8
        assert stats["total_job_roles"] >= 30
        assert stats["total_skills"] >= 100
        assert stats["total_aliases"] >= 100
        assert stats["total_role_skills"] >= 200
        assert stats["total_role_relations"] >= 40

    def test_alias_resolution_multi_domain(self):
        # IT abbreviations
        assert TaxonomyEngine.resolve_role_alias("SDE") == "Software Engineer"
        assert TaxonomyEngine.resolve_role_alias("SWE") == "Software Engineer"
        assert TaxonomyEngine.resolve_role_alias("SRE") == "DevOps Engineer"
        
        # Sales & BD abbreviations
        assert TaxonomyEngine.resolve_role_alias("BDE") == "Business Development Executive"
        assert TaxonomyEngine.resolve_role_alias("BDM") == "Business Development Manager"
        assert TaxonomyEngine.resolve_role_alias("ASM") == "Area Sales Manager"
        assert TaxonomyEngine.resolve_role_alias("RSM") == "Regional Sales Manager"
        assert TaxonomyEngine.resolve_role_alias("KAM") == "Key Account Manager"

        # HR & Finance abbreviations
        assert TaxonomyEngine.resolve_role_alias("HRBP") == "HR Business Partner"
        assert TaxonomyEngine.resolve_role_alias("CA") == "Chartered Accountant"

        # Healthcare & Trades
        assert TaxonomyEngine.resolve_role_alias("MR") == "Medical Representative"
        assert TaxonomyEngine.resolve_role_alias("RN") == "Staff Nurse"
        assert TaxonomyEngine.resolve_role_alias("CSR") == "Customer Support Executive"

    def test_multi_domain_suggestions_data(self):
        res = TaxonomyEngine.get_smart_suggestions(query="Data")
        labels = [s["label"] for s in res["results"]]
        assert "Data Analyst" in labels
        assert "Data Scientist" in labels or "Data Engineer" in labels
        assert any(term in str(labels) for term in ["SQL", "Power BI", "Data Analysis", "Data Science"])

    def test_multi_domain_suggestions_sales(self):
        res = TaxonomyEngine.get_smart_suggestions(query="Sales")
        labels = [s["label"] for s in res["results"]]
        assert "Sales Manager" in labels
        assert "Area Sales Manager" in labels or "Regional Sales Manager" in labels

    def test_multi_domain_suggestions_hr(self):
        res = TaxonomyEngine.get_smart_suggestions(query="HR")
        labels = [s["label"] for s in res["results"]]
        assert "HR Manager" in labels or "HR Executive" in labels

    def test_multi_domain_suggestions_developer_and_languages(self):
        res_python = TaxonomyEngine.get_smart_suggestions(query="Python")
        labels_python = [s["label"] for s in res_python["results"]]
        assert any("Python" in l for l in labels_python)

        res_java = TaxonomyEngine.get_smart_suggestions(query="Java")
        labels_java = [s["label"] for s in res_java["results"]]
        assert any("Java" in l for l in labels_java)

    def test_multi_domain_suggestions_trades_and_healthcare(self):
        res_acc = TaxonomyEngine.get_smart_suggestions(query="Accountant")
        labels_acc = [s["label"] for s in res_acc["results"]]
        assert "Accountant" in labels_acc

        res_auto = TaxonomyEngine.get_smart_suggestions(query="Automobile")
        labels_auto = [s["label"] for s in res_auto["results"]]
        assert "Automobile Technician" in labels_auto

        res_nurse = TaxonomyEngine.get_smart_suggestions(query="Nurse")
        labels_nurse = [s["label"] for s in res_nurse["results"]]
        assert "Staff Nurse" in labels_nurse

    def test_weighted_ranking_tier_scores(self):
        res = TaxonomyEngine.get_smart_suggestions(query="Data Analyst")
        assert len(res["results"]) > 0
        top_match = res["results"][0]
        assert top_match["label"] == "Data Analyst"
        assert top_match["score"] == 1.0

    def test_job_posting_helper_suggestions(self):
        suggestions = TaxonomyEngine.get_job_posting_suggestions(job_title="Sales Manager")
        assert suggestions["canonical_title"] == "Sales Manager"
        assert len(suggestions["suggested_roles"]) > 0
        assert len(suggestions["suggested_skills"]) > 0
        assert any("Area Sales Manager" in r or "Regional Sales Manager" in r or "Business Development" in r for r in suggestions["suggested_roles"])

    def test_candidate_tagging_with_tv_urt(self, db):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create(email="rajesh.candidate@example.com", first_name="Rajesh", last_name="Kumar", role="CANDIDATE")
        profile = CandidateProfile.objects.create(
            user=user,
            full_name="Rajesh Kumar",
            current_designation="Sr. BDE",
            total_experience=3.5
        )
        CandidateSkill.objects.create(
            profile=profile,
            skill_name="Lead Generation",
            years_of_experience=3.0
        )
        Experience.objects.create(
            profile=profile,
            company_name="Tech Corp",
            designation="Inside Sales Executive",
            is_current=False
        )

        tags_count = CandidateTaggingService.tag_candidate_profile(profile)
        assert tags_count > 0

        des_tag = CandidateTag.objects.filter(profile=profile, tag_type="DESIGNATION").first()
        assert des_tag is not None
        assert des_tag.canonical_name == "Business Development Executive"

    def test_management_command_import_taxonomy(self, capsys):
        call_command('import_taxonomy', '--stats')
        captured = capsys.readouterr()
        assert "LIVE TAXONOMY ENTITY STATISTICS (TV-URT)" in captured.out
        assert "TOTAL JOB ROLES" in captured.out

    def test_taxonomy_rest_api_endpoints(self, client):
        # Suggestions API
        sug_url = reverse('taxonomy:api_taxonomy_suggestions')
        response = client.get(f"{sug_url}?q=Data")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) > 0

        # Roles API
        roles_url = reverse('taxonomy:api_taxonomy_roles')
        response = client.get(f"{roles_url}?q=Manager")
        assert response.status_code == 200
        roles_data = response.json()
        assert "results" in roles_data
        assert len(roles_data["results"]) > 0

        # Skills API
        skills_url = reverse('taxonomy:api_taxonomy_skills')
        response = client.get(f"{skills_url}?q=Python")
        assert response.status_code == 200
        skills_data = response.json()
        assert "results" in skills_data

        # Job Suggestions API
        job_sug_url = reverse('taxonomy:api_taxonomy_job_suggestions')
        response = client.get(f"{job_sug_url}?title=Full Stack Developer")
        assert response.status_code == 200
        job_data = response.json()
        assert "suggested_skills" in job_data
        assert len(job_data["suggested_skills"]) > 0

        # Stats API
        stats_url = reverse('taxonomy:api_taxonomy_stats')
        response = client.get(stats_url)
        assert response.status_code == 200
        stats_data = response.json()
        assert stats_data["total_job_roles"] > 0
