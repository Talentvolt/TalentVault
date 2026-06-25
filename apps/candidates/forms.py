from django import forms
from apps.candidates.models import CandidateProfile

class CandidateProfileForm(forms.ModelForm):
    class Meta:
        model = CandidateProfile
        fields = [
            'full_name', 'summary', 'location', 'total_experience', 
            'current_company', 'current_designation',
            'current_salary', 'expected_salary', 'notice_period',
            'linkedin_url', 'portfolio_url'
        ]
        labels = {
            'current_salary': 'Current CTC (LPA)',
            'expected_salary': 'Expected CTC (LPA)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if self.instance.current_salary is not None:
                # Convert from raw DB value (e.g. 800000.00) to LPA (e.g. 8.00)
                self.initial['current_salary'] = self.instance.current_salary / 100000
            if self.instance.expected_salary is not None:
                self.initial['expected_salary'] = self.instance.expected_salary / 100000

    def clean_current_salary(self):
        val = self.cleaned_data.get('current_salary')
        if val is not None:
            # Convert from LPA input (e.g. 8.0) to raw DB value (e.g. 800000)
            return val * 100000
        return val

    def clean_expected_salary(self):
        val = self.cleaned_data.get('expected_salary')
        if val is not None:
            # Convert from LPA input (e.g. 12.0) to raw DB value (e.g. 1200000)
            return val * 100000
        return val
