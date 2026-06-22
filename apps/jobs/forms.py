from django import forms
from apps.jobs.models import Job

class JobForm(forms.ModelForm):
    skills_tags = forms.CharField(
        required=False, 
        widget=forms.TextInput(attrs={'placeholder': 'e.g. Python, Java', 'id': 'skills_tags'}),
        help_text="Separate skills with commas"
    )
    
    assets_required = forms.CharField(required=False, widget=forms.HiddenInput())
    
    class Meta:
        model = Job
        fields = [
            'title', 'client', 'location', 'job_type',
            'min_experience', 'max_experience',
            'currency', 'min_salary', 'max_salary', 'assets_required', 'description', 'jd_file'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 10, 'id': 'job_description'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.clients.models import Client
        self.fields['client'].queryset = Client.objects.filter(status=Client.Status.ACTIVE)
        self.fields['client'].empty_label = "Select Client (Optional)"
        self.fields['client'].required = False
        self.fields['client'].widget.attrs.update({'class': 'form-select'})

    def clean_assets_required(self):
        data = self.cleaned_data.get('assets_required', '')
        if isinstance(data, str):
            return [x.strip() for x in data.split(',') if x.strip()]
        return data

    def clean(self):
        cleaned_data = super().clean()
        min_exp = cleaned_data.get('min_experience')
        max_exp = cleaned_data.get('max_experience')
        min_salary = cleaned_data.get('min_salary')
        max_salary = cleaned_data.get('max_salary')

        if min_exp is not None and max_exp is not None:
            if max_exp < min_exp:
                self.add_error('max_experience', "Max experience cannot be less than min experience.")
        
        if min_salary is not None and max_salary is not None:
            if max_salary < min_salary:
                self.add_error('max_salary', "Max salary cannot be less than min salary.")
        
        return cleaned_data
