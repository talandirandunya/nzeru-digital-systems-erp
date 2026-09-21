from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0005_marketplacefinancesettings'),
        ('marketplace', '0005_order_finance_sync_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='finance_reversal_journal_entry',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='marketplace_reversals', to='finance.journalentry'),
        ),
        migrations.AddField(
            model_name='order',
            name='finance_reversed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='order',
            name='finance_sync_status',
            field=models.CharField(choices=[('pending', 'Pending'), ('posted', 'Posted'), ('reversed', 'Reversed'), ('failed', 'Failed')], default='pending', max_length=20),
        ),
        migrations.AlterField(
            model_name='order',
            name='payment_status',
            field=models.CharField(choices=[('pending', 'Pending'), ('paid', 'Paid'), ('refunded', 'Refunded'), ('failed', 'Failed')], default='pending', max_length=20),
        ),
    ]
