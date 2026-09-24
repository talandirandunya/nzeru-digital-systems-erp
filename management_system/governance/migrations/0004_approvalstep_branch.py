from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('governance', '0003_explicit_access_and_authority'),
    ]

    operations = [
        migrations.AddField(
            model_name='approvalstep',
            name='branch',
            field=models.CharField(blank=True, max_length=100),
        ),
    ]