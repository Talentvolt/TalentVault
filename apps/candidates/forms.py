from django import forms
from django.db.models import Q
from django.core.exceptions import ValidationError
from apps.candidates.models import CandidateProfile, CandidateSkill, Education
from apps.accounts.models import User

class CandidateProfileForm(forms.ModelForm):
    linkedin_url = forms.CharField(required=False, widget=forms.TextInput(attrs={'placeholder': 'https://linkedin.com/in/username'}))
    portfolio_url = forms.CharField(required=False, widget=forms.TextInput(attrs={'placeholder': 'https://yourportfolio.com'}))
    notice_period = forms.IntegerField(
        required=False,
        min_value=0,
        label="Notice Period (Days)",
        widget=forms.NumberInput(attrs={'placeholder': '0 for Immediate Joiner', 'min': '0'})
    )

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
            'notice_period': 'Notice Period (Days)',
        }

    def clean_linkedin_url(self):
        from utils.url_helpers import normalize_external_url
        val = self.cleaned_data.get('linkedin_url')
        return normalize_external_url(val)

    def clean_portfolio_url(self):
        from utils.url_helpers import normalize_external_url
        val = self.cleaned_data.get('portfolio_url')
        return normalize_external_url(val)

    def clean_notice_period(self):
        val = self.cleaned_data.get('notice_period')
        if val is None:
            return 30
        return val

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if self.instance.current_salary is not None:
                # Convert from raw DB value (e.g. 800000.00) to LPA (e.g. 8.00)
                self.initial['current_salary'] = self.instance.current_salary / 100000
            if self.instance.expected_salary is not None:
                self.initial['expected_salary'] = self.instance.expected_salary / 100000
            if self.instance.notice_period is not None:
                self.initial['notice_period'] = self.instance.notice_period

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

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.notice_period is not None:
            instance.is_immediate_joiner = (instance.notice_period == 0)
        else:
            instance.notice_period = 30
            instance.is_immediate_joiner = False
        if commit:
            instance.save()
            self.save_m2m()
        return instance


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
    
    # Other & Social Links
    summary = forms.CharField(widget=forms.Textarea, required=False)
    linkedin_url = forms.CharField(max_length=500, required=False)
    portfolio_url = forms.CharField(max_length=500, required=False)
    github_url = forms.CharField(max_length=500, required=False)
    
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

    def clean_notice_period(self):
        val = self.cleaned_data.get('notice_period')
        if val is None:
            return 30
        return val
