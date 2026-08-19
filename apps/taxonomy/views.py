from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from apps.taxonomy.services.taxonomy_engine import TaxonomyEngine
from apps.taxonomy.services.taxonomy_importer import TaxonomyImporter


class TaxonomySuggestionsAPIView(View):
    """
    GET /api/taxonomy/suggestions/?q=data&tags=...
    Returns smart keyword suggestions, aliases, and graph relations.
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
    Typeahead autocomplete for Job Roles and Designations.
    """
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '').strip()
        limit = int(request.GET.get('limit', 10))

        results = TaxonomyEngine.get_role_autocomplete(query=query, limit=limit)
        return JsonResponse({
            "query": query,
            "count": len(results),
            "results": results
        })


class TaxonomySkillsAPIView(View):
    """
    GET /api/taxonomy/skills/?q=python
    Typeahead autocomplete for Skills, Technologies & Tools.
    """
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '').strip()
        limit = int(request.GET.get('limit', 10))

        results = TaxonomyEngine.get_skill_autocomplete(query=query, limit=limit)
        return JsonResponse({
            "query": query,
            "count": len(results),
            "results": results
        })


class TaxonomyJobSuggestionsAPIView(View):
    """
    GET /api/taxonomy/job-suggestions/?title=React Developer
    Returns companion roles and core skills for Job Posting forms.
    """
    def get(self, request, *args, **kwargs):
        title = request.GET.get('title', '').strip()
        limit = int(request.GET.get('limit', 10))

        data = TaxonomyEngine.get_job_posting_suggestions(job_title=title, limit=limit)
        return JsonResponse(data)


class TaxonomyStatsAPIView(View):
    """
    GET /api/taxonomy/stats/
    Live summary of all taxonomy entities and data sources.
    """
    def get(self, request, *args, **kwargs):
        stats = TaxonomyImporter.get_summary_statistics()
        return JsonResponse(stats)
