import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator
from django.utils import timezone


class Company(models.Model):
    PLAN_CHOICES = [
        ('free', 'Free'),
        ('basic', 'Basic'),
        ('premium', 'Premium'),
        ('enterprise', 'Enterprise'),
    ]

    company_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=200)
    domain = models.CharField(max_length=200, unique=True, db_index=True)
    contact_email = models.EmailField()
    contact_phone = models.CharField(
        max_length=20,
        blank=True,
        validators=[RegexValidator(r'^\+?[\d\s\-().]{5,20}$', 'Enter a valid phone number.')],
    )
    whatsapp_number = models.CharField(
        max_length=30,
        blank=True,
        help_text='WhatsApp contact number for marketplace clients (e.g. +2376XXXXXXXX)',
    )
    orange_money_number = models.CharField(
        max_length=30,
        blank=True,
        help_text='Orange Money transaction number for client payments',
    )
    mtn_momo_number = models.CharField(
        max_length=30,
        blank=True,
        help_text='MTN Mobile Money transaction number for client payments',
    )
    address = models.TextField(blank=True)
    subscription_plan = models.CharField(
        max_length=20,
        choices=PLAN_CHOICES,
        default='free',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Companies'
        ordering = ['name']
        indexes = [
            models.Index(fields=['domain']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name

    @property
    def active_user_count(self) -> int:
        return self.users.filter(is_active=True).count()

    @property
    def pending_invitations_count(self) -> int:
        return self.invitations.filter(accepted_at__isnull=True, expires_at__gt=timezone.now()).count()


class CustomUserManager(BaseUserManager):
    """Custom manager for User model with email as the unique identifier."""

    def create_user(self, email: str, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set.')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if not extra_fields.get('is_staff'):
            raise ValueError('Superuser must have is_staff=True.')
        if not extra_fields.get('is_superuser'):
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('hr_manager', 'HR Manager'),
        ('accountant', 'Accountant'),
        ('manager', 'Manager'),
        ('secretary', 'Secretary'),
        ('stock_manager', 'Stock Manager'),
        ('employee', 'Employee'),
    ]

    username = None  # replaced by email
    email = models.EmailField(unique=True, db_index=True)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='users',
        null=True,
        blank=True,
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        validators=[RegexValidator(r'^\+?[\d\s\-().]{5,20}$', 'Enter a valid phone number.')],
    )
    department = models.CharField(max_length=100, blank=True)
    position = models.CharField(max_length=100, blank=True)
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='employee',
        db_index=True,
        help_text='User role for access control.',
    )
    is_company_admin = models.BooleanField(
        default=False,
        help_text='Designates whether the user can manage company settings.',
    )
    access_controlled = models.BooleanField(
        default=False,
        help_text='When enabled, access comes only from explicit governance assignments.',
    )
    LANGUAGE_CHOICES = [
        ('en', 'English'),
        ('fr', 'Français'),
    ]
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default='en')

    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        ordering = ['email']
        indexes = [
            models.Index(fields=['company', 'role']),
            models.Index(fields=['company', 'is_active']),
        ]

    def __str__(self) -> str:
        company_name = self.company.name if self.company else 'No Company'
        return f'{self.get_full_name()} <{self.email}> ({company_name})'

    def get_full_name(self) -> str:
        return f'{self.first_name} {self.last_name}'.strip() or self.email

    @property
    def employee_profile(self):
        """Compatibility accessor for code that expects an optional Employee link.

        This does not create a profile automatically; it only returns an existing,
        explicitly-linked Employee when one is present.
        """
        from employees.models import Employee

        employee = Employee.objects.filter(user=self).select_related('company').first()
        if employee is None:
            raise Employee.DoesNotExist(f'{self.__class__.__name__} has no employee_profile.')
        return employee

    def has_role(self, *roles: str) -> bool:
        return self.is_superuser or self.role in roles

    def apply_approval_decision(self, decision):
        """Activate or deactivate a user account according to the company approval outcome."""
        if decision == 'approved':
            self.is_active = True
        elif decision in {'rejected', 'returned'}:
            self.is_active = False
        self.save(update_fields=['is_active'])

    @property
    def is_online(self) -> bool:
        if not self.last_seen:
            return False
        return (timezone.now() - self.last_seen) < timedelta(minutes=5)


class Invitation(models.Model):
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='invitations')
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invitations',
    )
    email = models.EmailField()
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_invitations',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('company', 'email')
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['company', 'email']),
        ]

    def __str__(self):
        status = 'accepted' if self.accepted_at else ('expired' if self.is_expired else 'pending')
        return f'Invite {self.email} → {self.company.name} [{status}]'

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_pending(self) -> bool:
        return self.accepted_at is None and not self.is_expired

    @classmethod
    def create_for(cls, company, email: str, invited_by, employee=None) -> 'Invitation':
        """Create (or reset) an invitation for a given email+company."""
        cls.objects.filter(company=company, email=email, accepted_at__isnull=True).delete()
        return cls.objects.create(
            company=company,
            email=email,
            employee=employee,
            invited_by=invited_by,
            expires_at=timezone.now() + timedelta(days=7),
        )


class CompanyEmailSettings(models.Model):
    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name='email_settings')
    email_host = models.CharField(max_length=255, default='smtp.gmail.com')
    email_port = models.IntegerField(default=587)
    email_use_tls = models.BooleanField(default=True)
    email_host_user = models.CharField(max_length=255)
    email_host_password = models.CharField(max_length=255)
    default_from_email = models.EmailField(default='no-reply@zentral.com')
    is_active = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Company Email Settings'
        verbose_name_plural = 'Company Email Settings'

    def __str__(self):
        return f"Email Settings for {self.company.name}"
