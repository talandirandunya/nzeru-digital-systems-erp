from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_alter_user_role'),
        ('finance', '0004_bankaccount_bankstatement_banktransaction_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='MarketplaceFinanceSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_enabled', models.BooleanField(default=False, help_text='Enable this after all required finance mappings are ready.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='marketplace_finance_settings', to='accounts.company')),
                ('receivable_account', models.ForeignKey(help_text='Asset account used until marketplace orders are settled.', on_delete=django.db.models.deletion.PROTECT, related_name='marketplace_receivable_settings', to='finance.account')),
                ('revenue_account', models.ForeignKey(help_text='Revenue account credited for marketplace sales.', on_delete=django.db.models.deletion.PROTECT, related_name='marketplace_revenue_settings', to='finance.account')),
                ('sales_journal', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='marketplace_settings', to='finance.journal')),
                ('tax_account', models.ForeignKey(blank=True, help_text='Optional liability account used when marketplace tax is posted separately.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='marketplace_tax_settings', to='finance.account')),
            ],
            options={
                'verbose_name': 'Marketplace finance settings',
                'verbose_name_plural': 'Marketplace finance settings',
            },
        ),
    ]
