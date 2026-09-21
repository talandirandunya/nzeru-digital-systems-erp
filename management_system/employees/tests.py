from django.test import TestCase

from accounts.models import Company, User
from employees.forms import EmployeeForm
from employees.models import Department, Employee
from governance.models import ApprovalRequest


class EmployeeFormTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name='Test Company',
            domain='testcompany',
            contact_email='admin@testcompany.com',
        )
        self.department = Department.objects.create(
            company=self.company,
            name='Engineering',
        )

    def test_employee_creation_does_not_create_user_account(self):
        form = EmployeeForm(
            data={
                'employee_id': 'EMP-001',
                'department': str(self.department.pk),
                'role': 'developer',
                'status': 'active',
                'date_joined': '2026-09-16',
                'date_of_birth': '1995-01-15',
                'salary': '500000',
                'first_name': 'Jane',
                'last_name': 'Doe',
            },
            company=self.company,
        )

        self.assertTrue(form.is_valid(), form.errors)
        employee = form.save()

        self.assertEqual(Employee.objects.filter(employee_id='EMP-001').count(), 1)
        self.assertIsNone(employee.user)

    def test_employee_creation_requires_manager_approval(self):
        manager = User.objects.create(
            email='manager@testcompany.com',
            first_name='Maya',
            last_name='Manager',
            company=self.company,
            role='manager',
            is_active=True,
            password='pass12345',
        )
        manager.set_password('pass12345')
        manager.save()

        form = EmployeeForm(
            data={
                'employee_id': 'EMP-002',
                'department': str(self.department.pk),
                'role': 'developer',
                'status': 'inactive',
                'date_joined': '2026-09-17',
                'date_of_birth': '1996-02-21',
                'salary': '450000',
                'create_user_account': '',
                'first_name': 'Peter',
                'last_name': 'Employee',
            },
            company=self.company,
        )

        self.assertTrue(form.is_valid(), form.errors)
        employee = form.save()
        self.assertEqual(employee.status, 'inactive')
        self.assertIsNone(employee.user)
        self.assertTrue(ApprovalRequest.objects.filter(company=self.company, object_id=employee.pk).exists())

    def test_employee_name_is_required_without_login(self):
        form = EmployeeForm(
            data={
                'employee_id': 'EMP-003',
                'role': 'developer',
                'status': 'inactive',
                'date_joined': '2026-09-18',
                'salary': '450000',
                'create_user_account': '',
            },
            company=self.company,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('first_name', form.errors)
        self.assertIn('last_name', form.errors)

    def test_user_creation_does_not_auto_create_employee(self):
        user = User.objects.create(
            email='user-no-employee@testcompany.com',
            first_name='No',
            last_name='Employee',
            company=self.company,
            role='employee',
            is_active=True,
        )
        user.set_password('StrongPass123')
        user.save()
        self.assertFalse(Employee.objects.filter(user=user).exists())

    def test_employee_edit_preserves_status(self):
        employee = Employee.objects.create(
            company=self.company,
            first_name='Jane',
            last_name='Doe',
            employee_id='EMP-999',
            role='developer',
            status='active',
            date_joined='2026-09-20',
        )

        form = EmployeeForm(
            data={
                'employee_id': 'EMP-999',
                'department': str(self.department.pk),
                'role': 'developer',
                'status': 'active',
                'date_joined': '2026-09-20',
                'date_of_birth': '1995-01-15',
                'salary': '500000',
                'first_name': 'Jane',
                'last_name': 'Doe',
            },
            instance=employee,
            company=self.company,
        )

        self.assertTrue(form.is_valid(), form.errors)
        updated = form.save()
        self.assertEqual(updated.status, 'active')
