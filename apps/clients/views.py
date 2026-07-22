from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from apps.core.permissions import RecruiterRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Count, Q
from apps.jobs.models import Job
from .models import Client
from .forms import ClientForm

class ClientListView(RecruiterRequiredMixin, ListView):
    model = Client
    template_name = 'client_list.html'
    context_object_name = 'clients'
    paginate_by = 10

    def get_queryset(self):
        # Annotate with the number of open (ACTIVE) jobs
        queryset = Client.objects.annotate(
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add search/filter selections back to template context
        context['company_name'] = self.request.GET.get('company_name', '')
        context['selected_industry'] = self.request.GET.get('industry', '')
        context['selected_status'] = self.request.GET.get('status', '')
        
        # Add lists for the dropdown filter options
        context['industries'] = Client.Industry.choices
        context['statuses'] = Client.Status.choices
        return context

class ClientDetailView(RecruiterRequiredMixin, DetailView):
    model = Client
    template_name = 'client_detail.html'
    context_object_name = 'client'

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
