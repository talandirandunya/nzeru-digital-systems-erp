from django.test import TestCase
from django.core.exceptions import ValidationError

from accounts.models import Company, User
from employees.forms import CompanyAssetForm, EmployeeForm
from employees.models import CompanyAsset, Department, Employee
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

    def test_employee_onboarding_details_are_saved(self):
        form = EmployeeForm(
            data={
                'employee_id': 'EMP-004',
                'department': str(self.department.pk),
                'role': 'developer',
                'status': 'active',
                'date_joined': '2026-09-19',
                'salary': '500000',
                'first_name': 'Amina',
                'last_name': 'Banda',
                'bank_name': 'Nzeru Bank',
                'bank_account_name': 'Amina Banda',
                'bank_account_number': '1234567890',
                'tax_identification_number': 'TPIN-004',
                'next_of_kin_name': 'Peter Banda',
                'next_of_kin_relationship': 'Brother',
                'next_of_kin_phone': '+265991234567',
                'medical_notes': 'Allergy information on file.',
            },
            company=self.company,
        )

        self.assertTrue(form.is_valid(), form.errors)
        employee = form.save()

        self.assertEqual(employee.bank_name, 'Nzeru Bank')
        self.assertEqual(employee.tax_identification_number, 'TPIN-004')
        self.assertEqual(employee.next_of_kin_phone, '+265991234567')
        self.assertEqual(employee.medical_notes, 'Allergy information on file.')

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

    def test_company_asset_can_be_assigned_to_employee(self):
        employee = Employee.objects.create(
            company=self.company,
            first_name='Amina',
            last_name='Banda',
            employee_id='EMP-ASSET-001',
            role='developer',
            status='active',
            date_joined='2026-09-20',
        )
        form = CompanyAssetForm(
            data={
                'asset_tag': 'NDS-LAP-001',
                'name': 'Lenovo ThinkPad T14',
                'asset_type': 'laptop',
                'serial_number': 'SN-001',
                'purchase_date': '2026-09-20',
                'purchase_cost': '1500000',
                'status': 'assigned',
                'assigned_employee': str(employee.pk),
            },
            company=self.company,
        )

        self.assertTrue(form.is_valid(), form.errors)
        asset = form.save()
        self.assertEqual(asset.assigned_employee, employee)
        self.assertEqual(asset.status, 'assigned')

    def test_company_asset_rejects_cross_company_assignee(self):
        other_company = Company.objects.create(name='Other Company', domain='othercompany')
        employee = Employee.objects.create(
            company=other_company,
            first_name='Other',
            last_name='Employee',
            employee_id='OTHER-001',
            date_joined='2026-09-20',
        )
        asset = CompanyAsset(
            company=self.company,
            asset_tag='NDS-LAP-002',
            name='Company Laptop',
            assigned_employee=employee,
            status='assigned',
        )

        with self.assertRaisesMessage(ValidationError, 'Assigned employee must belong to the same company.'):
            asset.full_clean()
