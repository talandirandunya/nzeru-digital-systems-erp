from datetime import date
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.urls import reverse
from accounts.models import Company
from employees.models import Employee
from governance.models import ApprovalRequest, ApprovalStep, ApprovalWorkflow
from governance.services import decide_approval, submit_for_approval
from .models import Position, LeaveRequest


class HRModelTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Org', domain='org')
        # create a user and employee via signal if needed
        # create user; employee profile created automatically by signal
        from accounts.models import User as AuthUser
        user = AuthUser.objects.create_user(
            email='emp@example.com',
            password='password',
            company=self.company,
            first_name='Emp',
            last_name='Loyee'
        )
        self.employee = Employee.objects.create(
            company=self.company,
            user=user,
            employee_id='EMP-100',
            first_name='Emp',
            last_name='Loyee',
            role='developer',
            status='active',
            date_joined='2026-01-01',
        )
        self.position = Position.objects.create(company=self.company, title='Developer', salary_grade=5)

    def test_leave_request(self):
        lr = LeaveRequest.objects.create(
            company=self.company,
            employee=self.employee,
            leave_type='vacation',
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 5),
        )
        self.assertEqual(str(lr), "Emp Loyee — Vacation (2026-03-01 → 2026-03-05)")
        # status transitions
        lr.approve()
        self.assertEqual(lr.status, 'approved')
        lr.deny()
        self.assertEqual(lr.status, 'denied')

    def test_leave_approval_uses_governance_and_updates_leave(self):
        manager = self.company.users.create(
            email='manager@example.com',
            password='password',
            role='manager',
            is_active=True,
        )
        workflow = ApprovalWorkflow.objects.create(
            company=self.company,
            name='Leave approval',
            transaction_type='leave_request',
        )
        ApprovalStep.objects.create(workflow=workflow, sequence=1, role='manager')
        leave = LeaveRequest.objects.create(
            company=self.company,
            employee=self.employee,
            leave_type='vacation',
            start_date=date(2026, 9, 20),
            end_date=date(2026, 9, 21),
            submitted_by=self.employee.user,
        )

        approval = submit_for_approval(
            target=leave,
            requester=self.employee.user,
            transaction_type='leave_request',
        )
        self.assertEqual(ApprovalRequest.objects.filter(pk=approval.pk).count(), 1)
        self.client.force_login(manager)
        response = self.client.post(
            reverse('governance:approval_decide', kwargs={'pk': approval.pk}),
            {'decision': 'approved'},
        )

        self.assertEqual(response.status_code, 302)
        leave.refresh_from_db()
        approval.refresh_from_db()
        self.assertEqual(leave.status, 'approved')
        self.assertEqual(approval.status, 'approved')

    def test_leave_request_cannot_be_approved_by_requester(self):
        workflow = ApprovalWorkflow.objects.create(
            company=self.company,
            name='Self approval blocked',
            transaction_type='leave_request',
        )
        ApprovalStep.objects.create(workflow=workflow, sequence=1, role='employee')
        leave = LeaveRequest.objects.create(
            company=self.company,
            employee=self.employee,
            leave_type='vacation',
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 2),
            submitted_by=self.employee.user,
        )
        approval = submit_for_approval(
            target=leave,
            requester=self.employee.user,
            transaction_type='leave_request',
        )

        with self.assertRaises(ValidationError):
            decide_approval(approval=approval, actor=self.employee.user, decision='approved')
