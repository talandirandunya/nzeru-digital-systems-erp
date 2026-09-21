"""
Test script to create sample notifications for testing the notification system.

Run this script to populate the database with sample notifications for testing.
"""

import os
import django
from datetime import timedelta
from django.utils import timezone

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'management_system.settings')
django.setup()

from django.contrib.auth import get_user_model
from notifications.utils import create_notification
from hr.models import LeaveRequest
from projects.models import Project, SousTache
from finance.models import ClientInvoice, SupplierInvoice
from inventory.models import Stock
from crm.models import Opportunity

User = get_user_model()

def create_sample_notifications():
    """Create sample notifications for testing"""

    # Get the first company and some users
    try:
        company = User.objects.first().company
        users = list(User.objects.filter(company=company)[:3])  # Get first 3 users

        if not users:
            print("No users found. Please create some users first.")
            return

        print(f"Creating sample notifications for company: {company.name}")

        # 1. Create leave request notifications
        try:
            leave_request = LeaveRequest.objects.filter(company=company).first()
            if leave_request:
                for user in users:
                    create_notification(
                        recipient=user,
                        notification_type='leave_approved',
                        title='Sample: Leave Request Approved',
                        message=f'Sample notification: Your vacation leave from {leave_request.start_date} to {leave_request.end_date} has been approved.',
                        related_object=leave_request
                    )
                print("✓ Created leave request notifications")
        except Exception as e:
            print(f"✗ Could not create leave notifications: {e}")

        # 2. Create project notifications
        try:
            project = Project.objects.filter(company=company).first()
            if project:
                for user in users:
                    create_notification(
                        recipient=user,
                        notification_type='project_status_changed',
                        title='Sample: Project Status Updated',
                        message=f'Sample notification: Project "{project.name}" status has been updated to {project.get_status_display()}.',
                        related_object=project
                    )
                print("✓ Created project notifications")
        except Exception as e:
            print(f"✗ Could not create project notifications: {e}")

        # 3. Create task notifications
        try:
            task = SousTache.objects.filter(company=company).first()
            if task:
                for user in users:
                    create_notification(
                        recipient=user,
                        notification_type='task_completed',
                        title='Sample: Task Completed',
                        message=f'Sample notification: Task "{task.titre}" in project "{task.projet.name}" has been completed.',
                        related_object=task
                    )
                print("✓ Created task notifications")
        except Exception as e:
            print(f"✗ Could not create task notifications: {e}")

        # 4. Create finance notifications
        try:
            invoice = ClientInvoice.objects.filter(company=company).first()
            if invoice:
                for user in users:
                    create_notification(
                        recipient=user,
                        notification_type='client_invoice_created',
                        title='Sample: New Client Invoice',
                        message=f'Sample notification: Client invoice "{invoice.invoice_number}" for {invoice.client.name} has been created. Amount: ${invoice.total_amount}.',
                        related_object=invoice
                    )
                print("✓ Created finance notifications")
        except Exception as e:
            print(f"✗ Could not create finance notifications: {e}")

        # 5. Create inventory notifications
        try:
            stock = Stock.objects.filter(company=company).first()
            if stock:
                for user in users:
                    create_notification(
                        recipient=user,
                        notification_type='low_stock',
                        title='Sample: Low Stock Alert',
                        message=f'Sample notification: Stock item "{stock.name}" is running low. Current quantity: {stock.quantity}.',
                        related_object=stock
                    )
                print("✓ Created inventory notifications")
        except Exception as e:
            print(f"✗ Could not create inventory notifications: {e}")

        # 6. Create CRM notifications
        try:
            opportunity = Opportunity.objects.filter(company=company).first()
            if opportunity:
                for user in users:
                    create_notification(
                        recipient=user,
                        notification_type='opportunity_won',
                        title='Sample: Opportunity Won',
                        message=f'Sample notification: Opportunity "{opportunity.title}" with {opportunity.contact.name} has been won. Value: ${opportunity.value}.',
                        related_object=opportunity
                    )
                print("✓ Created CRM notifications")
        except Exception as e:
            print(f"✗ Could not create CRM notifications: {e}")

        # 7. Create some unread notifications for testing
        for i, user in enumerate(users):
            create_notification(
                recipient=user,
                notification_type='system_test',
                title=f'Test Notification {i+1}',
                message=f'This is a test notification #{i+1} to verify the notification system is working correctly.',
            )
        print("✓ Created test notifications")

        print(f"\n🎉 Successfully created sample notifications!")
        print(f"Log in as any user to see the notifications in the bell icon.")

    except Exception as e:
        print(f"Error creating sample notifications: {e}")

if __name__ == '__main__':
    create_sample_notifications()