from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import Company, User
from employees.models import Employee
from .models import AttendanceRecord


class AttendanceUpgradeTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Attendance Co', domain='attendance', contact_email='attendance@example.com')
        self.user = User.objects.create_user(email='worker@example.com', password='pass12345', company=self.company, first_name='Worker', last_name='One')
        self.employee = Employee.objects.create(
            company=self.company,
            user=self.user,
            employee_id='EMP-ATT-001',
            first_name='Worker',
            last_name='One',
            role='developer',
            status='active',
            date_joined='2026-09-01',
        )

    def test_clock_in_and_out_lifecycle(self):
        record = AttendanceRecord.objects.create(company=self.company, employee=self.employee, attendance_date=date(2026, 9, 17))
        record.clock_in_now()
        record.refresh_from_db()
        self.assertIsNotNone(record.clock_in)
        record.clock_out_now()
        record.refresh_from_db()
        self.assertIsNotNone(record.clock_out)

    def test_cross_company_employee_is_rejected(self):
        other = Company.objects.create(name='Other Co', domain='other-attendance', contact_email='other@example.com')
        record = AttendanceRecord(company=other, employee=self.employee, attendance_date=date(2026, 9, 17))
        with self.assertRaises(ValidationError):
            record.full_clean()
