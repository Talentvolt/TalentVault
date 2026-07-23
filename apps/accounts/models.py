import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import UUIDModel, TimeStampedModel

class UserManager(BaseUserManager):
    """Define a model manager for User model with no username field."""

    def _create_user(self, email, password=None, **extra_fields):
        """Create and save a User with the given email and password."""
        if not email:
            raise ValueError('The given email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and save a SuperUser with the given email and password."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(email, password, **extra_fields)

class User(AbstractUser, UUIDModel, TimeStampedModel):
    """
    Custom User model for TalentVault.
    Uses email as the primary identifier and includes Role-Based Access.
    """
    username = None
    email = models.EmailField(_('email address'), unique=True, db_index=True)

    class Role(models.TextChoices):
        SUPER_ADMIN = "SUPER_ADMIN", _("Super Admin")
        COMPANY_ADMIN = "COMPANY_ADMIN", _("Company Admin")
        RECRUITER = "RECRUITER", _("Recruiter")
        CANDIDATE = "CANDIDATE", _("Candidate")

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.RECRUITER,
        db_index=True
    )

    profile_picture = models.URLField(max_length=500, blank=True, null=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    is_verified = models.BooleanField(default=False)

    @property
    def email_verified(self) -> bool:
        return self.is_verified

    @email_verified.setter
    def email_verified(self, value: bool):
        self.is_verified = bool(value)


    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.email} ({self.role})"


import hashlib
from django.utils import timezone
from datetime import timedelta


class OTPVerification(UUIDModel, TimeStampedModel):
    """
    Model to store and manage Email OTP Verifications securely.
    OTP codes are hashed using SHA-256 before storing.
    """
    email = models.EmailField(max_length=255, db_index=True, default='')
    phone = models.CharField(max_length=30, db_index=True, blank=True, default='')
    otp = models.CharField(max_length=128)  # Hashed OTP
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    verified = models.BooleanField(default=False)
    attempts = models.IntegerField(default=0)
    resend_count = models.IntegerField(default=0)

    class Meta:
        verbose_name = _('OTP Verification')
        verbose_name_plural = _('OTP Verifications')
        ordering = ['-created_at']

    def __str__(self):
        return f"OTP for {self.email or self.phone} (Verified: {self.verified})"


    @classmethod
    def hash_otp(cls, raw_otp: str) -> str:
        return hashlib.sha256(raw_otp.strip().encode('utf-8')).hexdigest()

    def set_otp(self, raw_otp: str):
        self.otp = self.hash_otp(raw_otp)

    def check_otp(self, raw_otp: str) -> bool:
        return self.otp == self.hash_otp(raw_otp)

    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    def can_attempt(self) -> bool:
        return self.attempts < 5 and not self.is_expired() and not self.verified

    def can_resend(self) -> bool:
        return self.resend_count < 3

    @classmethod
    def cleanup_expired(cls):
        """Automatically delete expired OTP records."""
        cls.objects.filter(expires_at__lt=timezone.now()).delete()

