from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('governance', '0007_rename_delegation_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='approvalrequest',
            name='workflow_snapshot',
            field=models.JSONField(default=dict),
        ),
    ]