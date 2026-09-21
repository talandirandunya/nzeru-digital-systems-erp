"""
Example usage of the notification system in other apps.

To create notifications from any app, import the utility functions:
"""

from notifications.utils import create_notification, check_notification_preferences

# Example 1: Creating a notification when a leave request is approved
def approve_leave_request(request, leave_request):
    # Update the leave request status
    leave_request.status = 'approved'
    leave_request.save()

    # Create notification for the employee
    create_notification(
        recipient=leave_request.employee.user,
        notification_type='leave_approved',
        title='Leave Request Approved',
        message=f'Your leave request for {leave_request.start_date} to {leave_request.end_date} has been approved.',
        related_object=leave_request
    )

    return redirect('hr:leave_list')

# Example 2: Creating a notification for project task completion
def complete_task(request, task):
    task.status = 'completed'
    task.completed_date = timezone.now()
    task.save()

    # Notify project manager
    if task.project.manager != request.user.employee:
        create_notification(
            recipient=task.project.manager.user,
            notification_type='task_completed',
            title='Task Completed',
            message=f'Task "{task.title}" in project "{task.project.name}" has been completed by {request.user.get_full_name()}.',
            related_object=task
        )

    return redirect('projects:task_detail', pk=task.pk)

# Example 3: Creating notifications for inventory alerts
def check_low_stock():
    low_stock_items = InventoryItem.objects.filter(
        quantity__lte=F('min_stock_level')
    )

    for item in low_stock_items:
        # Check if notification already exists for this item
        existing = Notification.objects.filter(
            notification_type='low_stock',
            related_object=item,
            created_at__date=timezone.now().date()
        ).exists()

        if not existing:
            # Notify stock managers
            stock_managers = User.objects.filter(
                employee__role='stock_manager'
            )

            for manager in stock_managers:
                create_notification(
                    recipient=manager,
                    notification_type='low_stock',
                    title='Low Stock Alert',
                    message=f'Item "{item.name}" is running low on stock. Current quantity: {item.quantity}',
                    related_object=item
                )

# Example 4: Creating notifications for finance approvals
def submit_expense_report(request, expense_report):
    expense_report.status = 'pending_approval'
    expense_report.save()

    # Notify finance managers
    finance_managers = User.objects.filter(
        employee__role='accountant'
    )

    for manager in finance_managers:
        create_notification(
            recipient=manager,
            notification_type='expense_pending',
            title='Expense Report Pending Approval',
            message=f'New expense report from {request.user.get_full_name()} requires approval. Amount: ${expense_report.total_amount}',
            related_object=expense_report
        )

    return redirect('finance:expense_detail', pk=expense_report.pk)

# Example 5: Using notification preferences
def send_meeting_reminder(meeting):
    attendees = meeting.attendees.all()

    for attendee in attendees:
        # Check if user wants email notifications for meetings
        if check_notification_preferences(attendee.user, 'meetings', 'email'):
            # Send email notification
            send_mail(
                f'Meeting Reminder: {meeting.title}',
                f'You have a meeting scheduled for {meeting.start_time}',
                'noreply@company.com',
                [attendee.user.email]
            )

        # Always create in-app notification
        create_notification(
            recipient=attendee.user,
            notification_type='meeting_reminder',
            title='Meeting Reminder',
            message=f'Reminder: {meeting.title} at {meeting.start_time}',
            related_object=meeting
        )