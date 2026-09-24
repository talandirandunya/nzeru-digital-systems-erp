from django.db import migrations, models
import django.db.models.deletion
import django.conf


class Migration(migrations.Migration):
    dependencies = [
        ('governance', '0005_approvalworkflow_escalation_timing'),
        migrations.swappable_dependency(django.conf.settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ApprovalDelegation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transaction_type', models.CharField(max_length=100)),
                ('capability', models.CharField(choices=[('dashboard.view', 'dashboard.view'), ('employees.view', 'employees.view'), ('employees.manage', 'employees.manage'), ('finance.view', 'finance.view'), ('finance.manage', 'finance.manage'), ('finance.post_journal', 'finance.post_journal'), ('finance.reverse_journal', 'finance.reverse_journal'), ('inventory.view', 'inventory.view'), ('inventory.manage', 'inventory.manage'), ('inventory.issue', 'inventory.issue'), ('procurement.view', 'procurement.view'), ('procurement.manage', 'procurement.manage'), ('procurement.approve', 'procurement.approve'), ('hr.view', 'hr.view'), ('hr.manage', 'hr.manage'), ('hr.manage_payroll', 'hr.manage_payroll'), ('crm.view', 'crm.view'), ('crm.manage', 'crm.manage'), ('projects.view', 'projects.view'), ('projects.manage', 'projects.manage'), ('meetings.view', 'meetings.view'), ('meetings.manage', 'meetings.manage'), ('notifications.view', 'notifications.view'), ('governance.view', 'governance.view'), ('approvals.decide', 'approvals.decide'), ('reporting.view', 'reporting.view'), ('reporting.export', 'reporting.export'), ('admin.manage_users', 'admin.manage_users'), ('admin.manage_roles', 'admin.manage_roles'), ('admin.manage_organisation', 'admin.manage_organisation'), ('finance.approve_payment', 'finance.approve_payment')], default='approvals.decide', max_length=100)),
                ('department', models.CharField(blank=True, max_length=100)),
                ('branch', models.CharField(blank=True, max_length=100)),
                ('starts_at', models.DateTimeField()),
                ('ends_at', models.DateTimeField()),
                ('enabled', models.BooleanField(default=True)),
                ('reason', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='approval_delegations', to='accounts.company')),
                ('delegate', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='approval_delegations_received', to=django.conf.settings.AUTH_USER_MODEL)),
                ('delegator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='approval_delegations_given', to=django.conf.settings.AUTH_USER_MODEL)),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('delegator', 'delegate', 'transaction_type', 'starts_at'), name='unique_approval_delegation')],
                'indexes': [models.Index(fields=('company', 'delegate', 'transaction_type', 'enabled'), name='governance__company_approval_delegation_idx')],
            },
        ),
    ]