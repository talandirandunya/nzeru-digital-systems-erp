from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0005_marketplacefinancesettings'),
        ('marketplace', '0004_order_company_phase1'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='finance_journal_entry',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='marketplace_orders', to='finance.journalentry'),
        ),
        migrations.AddField(
            model_name='order',
            name='finance_sync_error',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='order',
            name='finance_sync_status',
            field=models.CharField(choices=[('pending', 'Pending'), ('posted', 'Posted'), ('failed', 'Failed')], default='pending', max_length=20),
        ),
        migrations.AddField(
            model_name='order',
            name='finance_synced_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
