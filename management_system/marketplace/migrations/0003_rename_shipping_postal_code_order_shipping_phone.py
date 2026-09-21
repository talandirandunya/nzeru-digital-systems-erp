# Generated migration for renaming shipping_postal_code to shipping_phone

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0002_alter_client_unique_together_remove_order_company_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='order',
            old_name='shipping_postal_code',
            new_name='shipping_phone',
        ),
    ]
