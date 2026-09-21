from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


CAPABILITIES = [
    ('dashboard.view', 'dashboard.view'),
    ('employees.view', 'employees.view'), ('employees.manage', 'employees.manage'),
    ('finance.view', 'finance.view'), ('finance.manage', 'finance.manage'),
    ('finance.post_journal', 'finance.post_journal'), ('finance.reverse_journal', 'finance.reverse_journal'),
    ('inventory.view', 'inventory.view'), ('inventory.manage', 'inventory.manage'), ('inventory.issue', 'inventory.issue'),
    ('procurement.view', 'procurement.view'), ('procurement.manage', 'procurement.manage'), ('procurement.approve', 'procurement.approve'),
    ('hr.view', 'hr.view'), ('hr.manage', 'hr.manage'), ('hr.manage_payroll', 'hr.manage_payroll'),
    ('crm.view', 'crm.view'), ('crm.manage', 'crm.manage'), ('projects.view', 'projects.view'), ('projects.manage', 'projects.manage'),
    ('meetings.view', 'meetings.view'), ('meetings.manage', 'meetings.manage'), ('notifications.view', 'notifications.view'),
    ('governance.view', 'governance.view'), ('approvals.decide', 'approvals.decide'),
    ('reporting.view', 'reporting.view'), ('reporting.export', 'reporting.export'),
    ('admin.manage_users', 'admin.manage_users'), ('admin.manage_roles', 'admin.manage_roles'),
    ('admin.manage_organisation', 'admin.manage_organisation'), ('finance.approve_payment', 'finance.approve_payment'),
]


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0013_user_access_controlled'),
        ('governance', '0002_approvalstep_alter_rolecapability_capability_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserApprovalAuthority',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transaction_type', models.CharField(max_length=100)),
                ('module', models.CharField(blank=True, max_length=80)),
                ('capability', models.CharField(choices=CAPABILITIES, default='approvals.decide', max_length=100)),
                ('min_amount', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('max_amount', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('department', models.CharField(blank=True, max_length=100)),
                ('branch', models.CharField(blank=True, max_length=100)),
                ('enabled', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='user_approval_authorities', to='accounts.company')),
                ('granted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='approval_authorities', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('user', 'transaction_type', 'module'), name='unique_user_approval_authority')],
                'indexes': [models.Index(fields=('company', 'user', 'transaction_type'), name='governance__company_178093_idx')],
            },
        ),
        migrations.AlterField(
            model_name='rolecapability',
            name='capability',
            field=models.CharField(choices=CAPABILITIES, max_length=100),
        ),
        migrations.AlterField(
            model_name='usercapability',
            name='capability',
            field=models.CharField(choices=CAPABILITIES, max_length=100),
        ),
    ]
