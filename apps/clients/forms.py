from django import forms
from .models import Client

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            'company_name',
            'spoc_name',
            'designation',
            'email',
            'phone_number',
            'website',
            'industry',
            'company_size',
            'city',
            'state',
            'country',
            'notes',
            'status'
        ]
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Acme Corp'}),
            'spoc_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. John Doe'}),
            'designation': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. HR Manager'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'e.g. hr@acme.com'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. +1 234 567 8900'}),
            'website': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'e.g. https://acme.com'}),
            'industry': forms.Select(attrs={'class': 'form-select'}),
            'company_size': forms.Select(attrs={'class': 'form-select'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. New York'}),
            'state': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. NY'}),
            'country': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. USA'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Add any additional notes about the client...'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
