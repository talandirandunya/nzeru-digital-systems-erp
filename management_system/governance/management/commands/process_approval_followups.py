from django.core.management.base import BaseCommand

from governance.services import process_overdue_approvals


class Command(BaseCommand):
    help = 'Send due approval reminders and escalation notifications.'

    def handle(self, *args, **options):
        result = process_overdue_approvals()
        self.stdout.write(
            self.style.SUCCESS(
                f"Approval follow-ups complete: {result['reminded']} reminders, "
                f"{result['escalated']} escalations."
            )
        )