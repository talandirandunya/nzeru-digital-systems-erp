from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('governance', '0004_approvalstep_branch'),
    ]

    operations = [
        migrations.AddField(
            model_name='approvalworkflow',
            name='reminder_after_hours',
            field=models.PositiveIntegerField(default=24),
        ),
        migrations.AddField(
            model_name='approvalworkflow',
            name='escalation_after_hours',
            field=models.PositiveIntegerField(default=72),
        ),
    ]