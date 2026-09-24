from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('governance', '0006_approvaldelegation'),
    ]

    operations = [
        migrations.RenameIndex(
            model_name='approvaldelegation',
            old_name='governance__company_approval_delegation_idx',
            new_name='governance__company_1d8bbe_idx',
        ),
    ]