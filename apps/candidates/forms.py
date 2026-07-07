from django import forms
from django.db.models import Q
from django.core.exceptions import ValidationError
from apps.candidates.models import CandidateProfile, CandidateSkill, Education
from apps.accounts.models import User

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


class ManualCandidateForm(forms.Form):
    # Required
    full_name = forms.CharField(max_length=255, label="Candidate Name *")
    email = forms.EmailField(label="Email *")
    phone_number = forms.CharField(max_length=20, label="Mobile Number *")
    
    # Optional Profile Fields
    current_company = forms.CharField(max_length=255, required=False)
    current_designation = forms.CharField(max_length=255, required=False)
    total_experience = forms.DecimalField(max_digits=4, decimal_places=1, required=False, initial=0.0)
    relevant_experience = forms.DecimalField(max_digits=4, decimal_places=1, required=False, initial=0.0)
    location = forms.CharField(max_length=100, required=False, label="Current Location")
    preferred_location = forms.CharField(max_length=100, required=False)
    current_salary = forms.DecimalField(max_digits=12, decimal_places=2, required=False, label="Current CTC (LPA)")
    expected_salary = forms.DecimalField(max_digits=12, decimal_places=2, required=False, label="Expected CTC (LPA)")
    notice_period = forms.IntegerField(required=False, initial=30)
    
    # Education
    highest_qualification = forms.CharField(max_length=255, required=False)
    college_university = forms.CharField(max_length=255, required=False)
    
    # Skills
    primary_skills = forms.CharField(max_length=255, required=False, help_text="Comma-separated primary skills")
    secondary_skills = forms.CharField(max_length=255, required=False, help_text="Comma-separated secondary skills")
    
    # Links
    linkedin_url = forms.URLField(required=False, label="LinkedIn URL")
    github_url = forms.URLField(required=False, label="GitHub URL")
    portfolio_url = forms.URLField(required=False, label="Portfolio URL")
    
    # Other
    summary = forms.CharField(widget=forms.Textarea, required=False)
    
    # Resume file (optional in manual entry)
    resume = forms.FileField(required=False)

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            email = email.lower().strip()
        return email

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number')
        if phone:
            phone = phone.strip()
        return phone
