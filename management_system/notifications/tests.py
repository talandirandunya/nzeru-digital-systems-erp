from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import Company
from employees.models import Employee
from meetings.models import ActionItem, Meeting
from .models import Notification, NotificationPreference
from .utils import create_notification

# Create your tests here.


class NotificationSecurityTests(TestCase):
	def setUp(self):
		self.company = Company.objects.create(name='Notification Co', domain='notifications', contact_email='admin@notifications.test')
		self.other_company = Company.objects.create(name='Other Co', domain='other-notifications', contact_email='admin@other.test')
		self.user = self.company.users.create(email='user@notifications.test', is_active=True)
		self.other_user = self.other_company.users.create(email='user@other.test', is_active=True)

	def test_disabled_preference_suppresses_notification_creation(self):
		NotificationPreference.objects.create(user=self.user, in_app_system_alerts=False)

		notification = create_notification(
			user=self.user,
			notification_type=Notification.SYSTEM_ALERT,
			title='System alert',
			message='Should not be stored',
		)

		self.assertIsNone(notification)
		self.assertFalse(Notification.objects.filter(user=self.user).exists())

	def test_cross_company_related_object_is_rejected(self):
		with self.assertRaises(ValidationError):
			create_notification(
				user=self.user,
				notification_type=Notification.SYSTEM_ALERT,
				title='Cross-company alert',
				message='Should be rejected',
				related_object=self.other_company,
			)

	def test_same_company_notification_is_created(self):
		notification = create_notification(
			user=self.user,
			notification_type=Notification.SYSTEM_ALERT,
			title='System alert',
			message='Valid notification',
			related_object=self.company,
		)

		self.assertEqual(notification.user_id, self.user.pk)
		self.assertEqual(notification.related_object_id, self.company.pk)

	def test_parent_meeting_company_is_resolved_for_action_item(self):
		user = self.company.users.create(email='meeting-user@notifications.test', is_active=True)
		employee = Employee.objects.create(company=self.company, user=user, employee_id='MEET-1', first_name='Meeting', last_name='User', status='active', date_joined='2026-01-01')
		meeting = Meeting.objects.create(company=self.company, title='Planning', scheduled_date='2026-09-25T10:00:00Z', organizer=employee, created_by=user)
		action = ActionItem.objects.create(meeting=meeting, title='Follow up', due_date='2026-09-26', assigned_to=employee)

		notification = create_notification(user=user, notification_type=Notification.SYSTEM_ALERT, title='Action', message='Assigned', related_object=action)

		self.assertEqual(notification.related_object_id, action.pk)

	def test_action_item_from_another_company_is_rejected(self):
		other_user = self.other_company.users.create(email='meeting-user@other.test', is_active=True)
		other_employee = Employee.objects.create(company=self.other_company, user=other_user, employee_id='MEET-2', first_name='Other', last_name='User', status='active', date_joined='2026-01-01')
		meeting = Meeting.objects.create(company=self.other_company, title='Other', scheduled_date='2026-09-25T10:00:00Z', organizer=other_employee, created_by=other_user)
		action = ActionItem.objects.create(meeting=meeting, title='Other action', due_date='2026-09-26', assigned_to=other_employee)

		with self.assertRaises(ValidationError):
			create_notification(user=self.user, notification_type=Notification.SYSTEM_ALERT, title='Cross-company', message='Rejected', related_object=action)
