from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseAppModel

class Client(BaseAppModel):
    class Industry(models.TextChoices):
        IT_SERVICES = 'IT_SERVICES', _('IT Services')
        SOFTWARE_PRODUCT = 'SOFTWARE_PRODUCT', _('Software Product')
        HEALTHCARE = 'HEALTHCARE', _('Healthcare')
        FINANCE_BANKING = 'FINANCE_BANKING', _('Finance & Banking')
        EDTECH = 'EDTECH', _('EdTech')
        E_COMMERCE = 'E_COMMERCE', _('E-Commerce')
        MANUFACTURING = 'MANUFACTURING', _('Manufacturing')
        TELECOM = 'TELECOM', _('Telecom')
        REAL_ESTATE = 'REAL_ESTATE', _('Real Estate')
        AUTOMOBILE = 'AUTOMOBILE', _('Automobile')
        RETAIL = 'RETAIL', _('Retail')
        CONSULTING = 'CONSULTING', _('Consulting')
        MEDIA_ENTERTAINMENT = 'MEDIA_ENTERTAINMENT', _('Media & Entertainment')
        LOGISTICS = 'LOGISTICS', _('Logistics')
        OTHERS = 'OTHERS', _('Others')

    class CompanySize(models.TextChoices):
        SIZE_1_50 = '1-50', _('1-50')
        SIZE_51_200 = '51-200', _('51-200')
        SIZE_201_500 = '201-500', _('201-500')
        SIZE_500_PLUS = '500+', _('500+')

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', _('Active')
        INACTIVE = 'INACTIVE', _('Inactive')

    company_name = models.CharField(max_length=255, unique=True, db_index=True)
    spoc_name = models.CharField(max_length=255, db_index=True, verbose_name="SPOC / HR Name")
    designation = models.CharField(max_length=150, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone_number = models.CharField(max_length=50, blank=True, null=True)
    website = models.URLField(blank=True, null=True)

    industry = models.CharField(
        max_length=50,
        choices=Industry.choices,
        default=Industry.OTHERS,
        db_index=True
    )
    
    company_size = models.CharField(
        max_length=50,
        choices=CompanySize.choices,
        default=CompanySize.SIZE_1_50
    )

    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)

    notes = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True
    )

    class Meta:
        verbose_name = _('client')
        verbose_name_plural = _('clients')
        ordering = ['company_name']

    def __str__(self):
        return self.company_name
