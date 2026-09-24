from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import Company, User
from employees.models import Employee

from .models import CommentaireTache, Project, SousTache


class ProjectModelTests(TestCase):
	def setUp(self):
		self.company = Company.objects.create(
			name='Projects Co', domain='projects-co', contact_email='admin@projects.co'
		)
		self.admin = User.objects.create(
			email='admin@projects.co', company=self.company, role='admin', is_active=True
		)
		self.employee = Employee.objects.create(
			company=self.company,
			employee_id='EMP-1',
			first_name='Project',
			last_name='Manager',
			date_joined=date(2026, 1, 1),
		)

	def project(self, **kwargs):
		values = {
			'company': self.company,
			'name': 'ERP rollout',
			'budget': 1000,
			'start_date': date(2026, 1, 1),
			'end_date': date(2026, 12, 31),
			'created_by': self.admin,
		}
		values.update(kwargs)
		return Project.objects.create(**values)

	def test_task_completion_rolls_up_to_project_and_status(self):
		project = self.project()
		task = SousTache.objects.create(
			company=self.company,
			projet=project,
			titre='Configure accounting',
			created_by=self.admin,
		)

		task.change_status('termine')
		project.refresh_from_db()

		self.assertEqual(project.completion_percentage, 100)
		self.assertEqual(project.status, 'completed')
		self.assertIsNotNone(task.date_achevement)

	def test_project_rejects_foreign_manager(self):
		other_company = Company.objects.create(
			name='Other Projects Co', domain='other-projects', contact_email='other@projects.co'
		)
		foreign_employee = Employee.objects.create(
			company=other_company,
			employee_id='OTHER-1',
			date_joined=date(2026, 1, 1),
		)

		with self.assertRaises(ValidationError):
			self.project(manager=foreign_employee).full_clean()

	def test_task_rejects_foreign_project_and_dependency(self):
		other_company = Company.objects.create(
			name='Other Projects Co', domain='other-projects', contact_email='other@projects.co'
		)
		foreign_project = Project.objects.create(
			company=other_company,
			name='Foreign project',
			budget=100,
			start_date=date(2026, 1, 1),
			end_date=date(2026, 12, 31),
		)
		foreign_task = SousTache.objects.create(
			company=other_company,
			projet=foreign_project,
			titre='Foreign task',
		)
		with self.assertRaises(ValidationError):
			SousTache(
				company=self.company,
				projet=self.project(),
				titre='Invalid task',
				depend_de=foreign_task,
			).full_clean()

	def test_comment_rejects_foreign_task(self):
		other_company = Company.objects.create(
			name='Other Projects Co', domain='other-projects', contact_email='other@projects.co'
		)
		foreign_project = Project.objects.create(
			company=other_company,
			name='Foreign project',
			budget=100,
			start_date=date(2026, 1, 1),
			end_date=date(2026, 12, 31),
		)
		foreign_task = SousTache.objects.create(
			company=other_company,
			projet=foreign_project,
			titre='Foreign task',
		)
		with self.assertRaises(ValidationError):
			CommentaireTache(
				company=self.company,
				tache=foreign_task,
				auteur=self.admin,
				contenu='Invalid comment',
			).full_clean()
