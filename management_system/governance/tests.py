from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.contrib.contenttypes.models import ContentType

from accounts.models import Company, User
from employees.models import Employee
from .forms import CreateManagedUserForm
from .models import AuditEvent, UserApprovalAuthority, UserCapability, has_capability
from .models import ApprovalRequest, ApprovalStep, ApprovalWorkflow
from .services import decide_approval, latest_approval_for, submit_for_approval


class GovernanceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Governance Co', domain='governance', contact_email='admin@example.com')
        self.admin = self.company.users.create(email='admin@example.com', role='admin', is_company_admin=True, is_active=True)
        self.admin.set_password('pass12345')
        self.admin.save()

    def test_audit_event_is_immutable(self):
        event = AuditEvent.record(actor=self.admin, company=self.company, module='test', action='created')
        event.action = 'changed'
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()

    def test_capability_override_can_revoke_role_default(self):
        self.assertTrue(has_capability(self.admin, 'finance.view'))
        UserCapability.objects.create(company=self.company, user=self.admin, capability='finance.view', enabled=False)
        self.assertFalse(has_capability(self.admin, 'finance.view'))

    def test_legacy_role_cannot_bypass_revoked_finance_capability(self):
        UserCapability.objects.create(company=self.company, user=self.admin, capability='finance.manage', enabled=False)

        self.client.force_login(self.admin)
        response = self.client.get(reverse('finance:index'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('core:dashboard'))

    def test_dashboard_uses_nzeru_branding_and_role_scope(self):
        employee = self.company.users.create(email='employee@example.com', first_name='John', last_name='Banda', role='employee', is_active=True)
        employee.set_password('pass12345')
        employee.save()

        self.client.force_login(employee)
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('NZERU ERP', content)
        self.assertIn('Developed by Nzeru Digital Systems', content)
        self.assertNotIn('User management', content)
        self.assertNotIn('Payroll administration', content)

    def test_approval_rejects_cross_company_target(self):
        other_company = Company.objects.create(name='Other Co', domain='other', contact_email='other@example.com')
        workflow = ApprovalWorkflow.objects.create(
            company=self.company,
            name='Test approval',
            transaction_type='test_transaction',
        )
        ApprovalStep.objects.create(workflow=workflow, sequence=1, role='manager')
        target = other_company

        with self.assertRaises(ValidationError):
            submit_for_approval(target=target, requester=self.admin, transaction_type='test_transaction')

        self.assertFalse(ApprovalRequest.objects.filter(object_id=target.pk).exists())

    def test_latest_approval_is_company_scoped(self):
        other_company = Company.objects.create(name='Other Co', domain='other', contact_email='other@example.com')
        workflow = ApprovalWorkflow.objects.create(
            company=other_company,
            name='Other approval',
            transaction_type='test_transaction',
        )
        ApprovalStep.objects.create(workflow=workflow, sequence=1, role='manager')
        approval = ApprovalRequest.objects.create(
            company=other_company,
            workflow=workflow,
            requester=self.admin,
            content_type=ContentType.objects.get_for_model(other_company),
            object_id=other_company.pk,
        )

        self.assertIsNone(latest_approval_for(other_company, company=self.company))
        self.assertEqual(latest_approval_for(other_company, company=other_company), approval)

    def test_optional_step_is_skipped_when_no_approver_matches(self):
        workflow = ApprovalWorkflow.objects.create(
            company=self.company,
            name='Optional then admin',
            transaction_type='optional_transaction',
            allow_self_approval=True,
        )
        ApprovalStep.objects.create(workflow=workflow, sequence=1, role='manager', required=False)
        ApprovalStep.objects.create(workflow=workflow, sequence=2, role='admin', required=True)

        approval = submit_for_approval(
            target=self.company,
            requester=self.admin,
            transaction_type='optional_transaction',
        )

        self.assertEqual(approval.current_step, 2)
        self.assertEqual(approval.status, 'pending')
        decide_approval(approval=approval, actor=self.admin, decision='approved')
        approval.refresh_from_db()
        self.assertEqual(approval.status, 'approved')

    def test_required_step_without_approver_keeps_request_pending(self):
        workflow = ApprovalWorkflow.objects.create(
            company=self.company,
            name='Unassigned approval',
            transaction_type='unassigned_transaction',
        )
        ApprovalStep.objects.create(workflow=workflow, sequence=1, role='manager', required=True)

        approval = submit_for_approval(
            target=self.company,
            requester=self.admin,
            transaction_type='unassigned_transaction',
        )

        self.assertEqual(approval.status, 'pending')
        self.assertEqual(approval.current_step, 1)
        self.assertTrue(AuditEvent.objects.filter(action='routing_failed', object_id=str(self.company.pk)).exists())

    def test_dashboard_shows_actionable_approval_for_manager(self):
        manager = self.company.users.create(
            email='manager@example.com',
            first_name='Finance',
            last_name='Manager',
            role='manager',
            is_active=True,
        )
        workflow = ApprovalWorkflow.objects.create(
            company=self.company,
            name='Dashboard approval',
            transaction_type='dashboard_transaction',
        )
        ApprovalStep.objects.create(workflow=workflow, sequence=1, role='manager')
        submit_for_approval(
            target=self.company,
            requester=self.admin,
            transaction_type='dashboard_transaction',
        )

        self.client.force_login(manager)
        response = self.client.get(reverse('core:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pending my approval')
        self.assertContains(response, 'APR-')

    def test_unauthorised_user_cannot_decide_approval_directly(self):
        self.company.users.create(email='manager@example.com', role='manager', is_active=True)
        workflow = ApprovalWorkflow.objects.create(
            company=self.company,
            name='Secure approval',
            transaction_type='secure_transaction',
        )
        ApprovalStep.objects.create(workflow=workflow, sequence=1, role='manager')
        approval = submit_for_approval(
            target=self.company,
            requester=self.admin,
            transaction_type='secure_transaction',
        )
        employee = self.company.users.create(email='employee@example.com', role='employee', is_active=True)
        self.client.force_login(employee)

        response = self.client.post(
            reverse('governance:approval_decide', kwargs={'pk': approval.pk}),
            {'decision': 'approved'},
        )

        approval.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(approval.status, 'pending')

    def test_managed_user_can_link_existing_employee_without_duplicate(self):
        employee = Employee.objects.create(
            company=self.company,
            first_name='Existing',
            last_name='Employee',
            employee_id='EMP-100',
            role='developer',
            status='inactive',
            date_joined='2026-09-20',
        )
        form = CreateManagedUserForm(
            data={
                'first_name': 'Existing',
                'last_name': 'Employee',
                'email': 'existing@example.com',
                'password': 'StrongPass123',
                'role': 'employee',
                'is_active': 'on',
                'employee': str(employee.pk),
            },
            company=self.company,
        )

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        employee.refresh_from_db()
        self.assertEqual(employee.user_id, user.pk)
        self.assertEqual(Employee.objects.filter(employee_id='EMP-100').count(), 1)

    def test_managed_user_cannot_link_employee_from_another_company(self):
        other_company = Company.objects.create(name='Other Co', domain='other-link', contact_email='other@example.com')
        employee = Employee.objects.create(
            company=other_company,
            first_name='Other',
            last_name='Employee',
            employee_id='EMP-200',
            date_joined='2026-09-20',
        )
        form = CreateManagedUserForm(
            data={
                'first_name': 'Other',
                'last_name': 'Employee',
                'email': 'other-link@example.com',
                'password': 'StrongPass123',
                'role': 'employee',
                'employee': str(employee.pk),
            },
            company=self.company,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('employee', form.errors)

    def test_controlled_user_gets_only_explicit_capabilities(self):
        user = self.company.users.create(
            email='controlled@example.com', role='manager', access_controlled=True, is_active=True,
        )
        UserCapability.objects.create(company=self.company, user=user, capability='dashboard.view')
        self.assertTrue(has_capability(user, 'dashboard.view'))
        self.assertFalse(has_capability(user, 'finance.view'))

    def test_controlled_user_cannot_open_unassigned_module(self):
        user = self.company.users.create(
            email='hr-only@example.com', role='hr_manager', access_controlled=True, is_active=True,
        )
        UserCapability.objects.create(company=self.company, user=user, capability='dashboard.view')
        UserCapability.objects.create(company=self.company, user=user, capability='hr.view')
        self.client.force_login(user)

        self.assertEqual(self.client.get(reverse('hr:index')).status_code, 200)
        self.assertEqual(self.client.get(reverse('finance:index')).status_code, 403)
        dashboard = self.client.get(reverse('core:dashboard'))
        self.assertEqual(dashboard.status_code, 200)
        self.assertNotContains(dashboard, 'href="/finance/')

    def test_controlled_user_without_dashboard_assignment_is_denied(self):
        user = self.company.users.create(
            email='no-dashboard@example.com', role='employee', access_controlled=True, is_active=True,
        )
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('core:dashboard')).status_code, 403)

    def test_admin_bulk_assignment_records_audit_event(self):
        user = self.company.users.create(
            email='assigned@example.com', role='finance', access_controlled=False, is_active=True,
        )
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('governance:user_capabilities', kwargs={'pk': user.pk}),
            {'action': 'save_access', 'access_controlled': 'on', 'capability__dashboard.view': 'on', 'capability__finance.view': 'on'},
        )
        user.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(user.access_controlled)
        self.assertEqual(set(user.capability_overrides.filter(enabled=True).values_list('capability', flat=True)), {'dashboard.view', 'finance.view'})
        self.assertTrue(AuditEvent.objects.filter(action='capability_assignments_changed', object_id=str(user.pk)).exists())

    def test_controlled_approval_requires_explicit_authority(self):
        approver = self.company.users.create(
            email='controlled-manager@example.com', role='manager', access_controlled=True, is_active=True,
        )
        UserCapability.objects.create(company=self.company, user=approver, capability='approvals.decide')
        workflow = ApprovalWorkflow.objects.create(company=self.company, name='Explicit authority', transaction_type='explicit_transaction')
        ApprovalStep.objects.create(workflow=workflow, sequence=1, role='manager')
        approval = submit_for_approval(target=self.company, requester=self.admin, transaction_type='explicit_transaction')
        self.assertEqual(approval.status, 'pending')
        self.assertEqual(approval.current_step, 1)
        UserApprovalAuthority.objects.create(
            company=self.company, user=approver, transaction_type='explicit_transaction',
            capability='approvals.decide', max_amount=None, granted_by=self.admin,
        )
        approval = submit_for_approval(target=self.company, requester=self.admin, transaction_type='explicit_transaction')
        decide_approval(approval=approval, actor=approver, decision='approved')
        approval.refresh_from_db()
        self.assertEqual(approval.status, 'approved')

    def test_authority_user_cannot_assign_permissions(self):
        user = self.company.users.create(
            email='authority-only@example.com', role='manager', access_controlled=True, is_active=True,
        )
        UserCapability.objects.create(company=self.company, user=user, capability='approvals.decide')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('governance:user_list')).status_code, 403)

    def test_managed_user_can_exist_without_employee(self):
        form = CreateManagedUserForm(
            data={
                'first_name': 'External',
                'last_name': 'Auditor',
                'email': 'auditor@example.com',
                'password': 'StrongPass123',
                'role': 'employee',
            },
            company=self.company,
        )

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.company_id, self.company.pk)
        self.assertFalse(Employee.objects.filter(user=user).exists())

    def test_managed_user_creation_requires_approval_when_configured(self):
        manager = self.company.users.create(
            email='manager@example.com',
            first_name='Ops',
            last_name='Manager',
            role='manager',
            is_active=True,
        )
        workflow = ApprovalWorkflow.objects.create(
            company=self.company,
            name='User account approval',
            transaction_type='user_account_creation',
            enabled=True,
        )
        ApprovalStep.objects.create(workflow=workflow, sequence=1, role='manager', required=True)

        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('governance:user_create'),
            {
                'first_name': 'Pending',
                'last_name': 'User',
                'email': 'pending-user@example.com',
                'password': 'StrongPass123',
                'role': 'employee',
                'is_active': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email='pending-user@example.com')
        self.assertFalse(user.is_active)
        self.assertTrue(ApprovalRequest.objects.filter(company=self.company, content_type=ContentType.objects.get_for_model(user), object_id=user.pk).exists())
