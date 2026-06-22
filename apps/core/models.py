import uuid
from django.db import models
from django.conf import settings

class UUIDModel(models.Model):
    """
    Abstract base class that provides UUID primary key.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True

class TimeStampedModel(models.Model):
    """
    Abstract base class that provides self-updating
    'created_at' and 'updated_at' fields.
    """
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class AuditModel(TimeStampedModel):
    """
    Abstract base class that provides 'created_by' and 'updated_by' fields.
    """
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_created",
        related_query_name="%(app_label)s_%(class)s_created_by"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_updated",
        related_query_name="%(app_label)s_%(class)s_updated_by"
    )

    class Meta:
        abstract = True

class BaseAppModel(UUIDModel, AuditModel):
    """
    Combined base model with UUID, Timestamps, and Audit fields.
    """
    class Meta:
        abstract = True

class Location(TimeStampedModel):
    name = models.CharField(max_length=255, db_index=True)
    state = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    location_type = models.CharField(max_length=50, choices=[
        ('STATE', 'State'),
        ('DISTRICT', 'District'),
        ('CITY', 'City'),
        ('OTHER', 'Other')
    ], default='CITY')
    country = models.CharField(max_length=100, default='India')

    class Meta:
        ordering = ['name']
        unique_together = ('name', 'state', 'country')

    def __str__(self):
        if self.state:
            return f"{self.name}, {self.state}"
        return self.name
