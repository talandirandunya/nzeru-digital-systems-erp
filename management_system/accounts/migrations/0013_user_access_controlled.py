from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0012_invitation_employee_alter_company_contact_phone_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='access_controlled',
            field=models.BooleanField(
                default=False,
                help_text='When enabled, access comes only from explicit governance assignments.',
            ),
        ),
    ]
