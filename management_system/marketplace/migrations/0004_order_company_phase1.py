from django.db import migrations, models
import django.db.models.deletion


def populate_order_company(apps, schema_editor):
    Order = apps.get_model('marketplace', 'Order')

    for order in Order.objects.all().iterator():
        company_ids = list(
            order.items.order_by()
            .values_list('stock__company_id', flat=True)
            .distinct()
        )

        if not company_ids:
            raise RuntimeError(
                f'Order {order.pk} has no items and cannot be assigned to a company.'
            )

        if len(company_ids) > 1:
            raise RuntimeError(
                f'Order {order.pk} contains items from multiple companies and must be fixed before Phase 1 migration.'
            )

        order.company_id = company_ids[0]
        order.save(update_fields=['company'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_alter_user_role'),
        ('marketplace', '0003_rename_shipping_postal_code_order_shipping_phone'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='company',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='marketplace_orders',
                to='accounts.company',
            ),
        ),
        migrations.RunPython(populate_order_company, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='order',
            name='company',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='marketplace_orders',
                to='accounts.company',
            ),
        ),
    ]
