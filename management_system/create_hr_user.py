import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'management_system.settings')
import django
django.setup()

from accounts.models import Company, User

company = Company.objects.filter(domain='grandpalacehotel').first()
if not company:
    raise SystemExit('Company with domain grandpalacehotel not found.')

user, created = User.objects.get_or_create(
    email='hr@grandpalacehotel.com',
    defaults={
        'first_name': 'HR',
        'last_name': 'Manager',
        'company': company,
        'role': 'hr_manager',
        'is_company_admin': False,
        'is_active': True,
        'department': 'Human Resources',
        'position': 'HR Manager',
    },
)

if created:
    user.set_password('Hr12345!')
    user.save()

print('company=' + company.domain)
print('status=' + ('created' if created else 'exists'))
print('email=' + user.email)
print('password=Hr12345!')
print('role=' + user.role)
