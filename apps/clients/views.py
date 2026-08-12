import logging
from django.shortcuts import redirect
from django.core.paginator import InvalidPage
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from apps.core.permissions import RecruiterRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Count, Q
from apps.jobs.models import Job
from .models import Client
from .forms import ClientForm
from utils.tenant import get_tenant_clients_qs

logger = logging.getLogger(__name__)

class ClientListView(RecruiterRequiredMixin, ListView):
    model = Client
    template_name = 'client_list.html'
    context_object_name = 'clients'
    paginate_by = 10

    def get_queryset(self):
        # Multi-tenant data isolation: filter clients for logged in recruiter/company
        base_qs = get_tenant_clients_qs(self.request.user)
        queryset = base_qs.annotate(
            open_jobs_count=Count('jobs', filter=Q(jobs__status=Job.JobStatus.ACTIVE))
        )
        
        # Search & Filter parameters
        company_name = self.request.GET.get('company_name', '')
        industry = self.request.GET.get('industry', '')
        status = self.request.GET.get('status', '')

        if company_name:
            queryset = queryset.filter(company_name__icontains=company_name)
        if industry:
            queryset = queryset.filter(industry=industry)
        if status:
            queryset = queryset.filter(status=status)
            
        return queryset.order_by('company_name')

    def get(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        paginator = self.get_paginator(self.object_list, self.paginate_by)

        page_kwarg = self.page_kwarg
        page_raw = request.GET.get(page_kwarg)

        if page_raw is not None:
            try:
                page_num = int(page_raw)
            except (TypeError, ValueError):
                params = request.GET.copy()
                params[page_kwarg] = 1
                return redirect(f"{request.path}?{params.urlencode()}")

            max_pages = paginator.num_pages if paginator.num_pages > 0 else 1
            if page_num < 1:
                params = request.GET.copy()
                params[page_kwarg] = 1
                return redirect(f"{request.path}?{params.urlencode()}")
            elif page_num > max_pages:
                params = request.GET.copy()
                params[page_kwarg] = max_pages
                return redirect(f"{request.path}?{params.urlencode()}")

        context = self.get_context_data(object_list=self.object_list)
        return self.render_to_response(context)

    def paginate_queryset(self, queryset, page_size):
        paginator = self.get_paginator(queryset, page_size)
        page_kwarg = self.page_kwarg
        page = self.kwargs.get(page_kwarg) or self.request.GET.get(page_kwarg) or 1
        try:
            page_number = int(page)
        except (TypeError, ValueError):
            page_number = 1
        
        try:
            page_obj = paginator.page(page_number)
        except InvalidPage:
            target_page = paginator.num_pages if paginator.num_pages > 0 else 1
            page_obj = paginator.page(target_page)

        return (paginator, page_obj, page_obj.object_list, page_obj.has_other_pages())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Search & Filter parameters
        company_name = self.request.GET.get('company_name', '')
        industry = self.request.GET.get('industry', '')
        status = self.request.GET.get('status', '')

        context['company_name'] = company_name
        context['selected_industry'] = industry
        context['selected_status'] = status

        # Build encoded filter parameters query string (excluding 'page') for pagination links
        get_params = self.request.GET.copy()
        if 'page' in get_params:
            del get_params['page']
        encoded_filters = get_params.urlencode()
        context['filter_params'] = f"&{encoded_filters}" if encoded_filters else ""

        # Add lists for the dropdown filter options
        context['industries'] = Client.Industry.choices
        context['statuses'] = Client.Status.choices
        return context

class ClientDetailView(RecruiterRequiredMixin, DetailView):
    model = Client
    template_name = 'client_detail.html'
    context_object_name = 'client'

    def get_queryset(self):
        return get_tenant_clients_qs(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch associated jobs
        context['jobs'] = self.object.jobs.all().order_by('-created_at')
        return context

class ClientCreateView(RecruiterRequiredMixin, CreateView):
    model = Client
    form_class = ClientForm
    template_name = 'client_form.html'
    success_url = reverse_lazy('clients:client_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Add New Client'
        context['action'] = 'Add Client'
        return context

class ClientUpdateView(RecruiterRequiredMixin, UpdateView):
    model = Client
    form_class = ClientForm
    template_name = 'client_form.html'

    def get_queryset(self):
        return get_tenant_clients_qs(self.request.user)

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('clients:client_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Edit Client: {self.object.company_name}'
        context['action'] = 'Save Changes'
        return context

class ClientDeleteView(RecruiterRequiredMixin, DeleteView):
    model = Client
    template_name = 'client_confirm_delete.html'
    success_url = reverse_lazy('clients:client_list')

    def get_queryset(self):
        return get_tenant_clients_qs(self.request.user)

