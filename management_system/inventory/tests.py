from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import Company
from notifications.models import Notification
from .models import (
    InventoryBatch,
    Stock,
    StockCategory,
    StockMovement,
    StockReservation,
    StockTransaction,
    StockTransfer,
    Warehouse,
    create_inventory_alerts,
)

User = get_user_model()


class InventoryWarehouseAndMovementTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='InventoryCo', domain='inventoryco', contact_email='ops@example.com')
        self.user = User.objects.create_user(email='stock@example.com', password='pass', company=self.company, first_name='Stock', last_name='User', role='stock_manager')
        self.category = StockCategory.objects.create(company=self.company, name='Hardware')
        self.warehouse = Warehouse.objects.create(company=self.company, name='Main Warehouse', code='WH-1', location='Blantyre')
        self.stock = Stock.objects.create(
            company=self.company,
            item_code='SKU-100',
            name='Solar Panel',
            category=self.category,
            quantity=10,
            unit='pcs',
            cost_price=Decimal('12.50'),
            selling_price=Decimal('18.00'),
            reorder_level=3,
            supplier_name='Supplier A',
            created_by=self.user,
        )

    def test_warehouse_scoped_stock_transaction(self):
        tx = StockTransaction(company=self.company, stock=self.stock, warehouse=self.warehouse, transaction_type='in', quantity=5, user=self.user)
        tx.full_clean()
        tx.save()
        self.assertEqual(tx.warehouse, self.warehouse)

    def test_stock_transaction_creates_movement_record(self):
        tx = StockTransaction.objects.create(company=self.company, stock=self.stock, warehouse=self.warehouse, transaction_type='out', quantity=2, user=self.user)
        movement = StockMovement.objects.create(
            company=self.company,
            stock=self.stock,
            warehouse=self.warehouse,
            movement_type='out',
            quantity=2,
            reference='TEST-OUT',
            moved_by=self.user,
        )
        self.assertEqual(movement.company, self.company)
        self.assertEqual(movement.warehouse, self.warehouse)
        self.assertEqual(tx.stock, self.stock)

    def test_cross_company_warehouse_rejected(self):
        other_company = Company.objects.create(name='OtherCo', domain='otherco', contact_email='other@example.com')
        other_warehouse = Warehouse.objects.create(company=other_company, name='Other Warehouse')
        tx = StockTransaction(company=self.company, stock=self.stock, warehouse=other_warehouse, transaction_type='in', quantity=1, user=self.user)
        with self.assertRaises(ValidationError):
            tx.full_clean()

    def test_stock_transfer_rejects_cross_company_destination(self):
        other_company = Company.objects.create(name='OtherCo', domain='otherco2', contact_email='other2@example.com')
        other_warehouse = Warehouse.objects.create(company=other_company, name='Other Warehouse 2')
        transfer = StockTransfer(
            company=self.company,
            stock=self.stock,
            from_warehouse=self.warehouse,
            to_warehouse=other_warehouse,
            quantity=2,
            reference='XFER-1',
        )
        with self.assertRaises(ValidationError):
            transfer.full_clean()

    def test_stock_reservation_tracks_available_quantity(self):
        reservation = self.stock.reserve_quantity(quantity=3, warehouse=self.warehouse, reference='RES-1', reserved_by=self.user)
        self.assertEqual(reservation.status, 'reserved')
        self.assertEqual(self.stock.available_quantity, 7)
        reservation.allocate()
        self.assertEqual(reservation.status, 'allocated')

    def test_inventory_batch_and_serial_tracking_can_be_created(self):
        batch = InventoryBatch.objects.create(
            company=self.company,
            stock=self.stock,
            batch_code='BATCH-001',
            quantity=5,
            unit_cost=Decimal('11.25'),
        )
        serial = batch.serials.create(
            company=self.company,
            stock=self.stock,
            serial_number='SN-1001',
            status='available',
        )
        self.assertEqual(batch.stock, self.stock)
        self.assertEqual(serial.batch, batch)

    def test_weighted_average_cost_tracks_receipt_batches(self):
        InventoryBatch.objects.create(company=self.company, stock=self.stock, batch_code='B-1', quantity=5, unit_cost=Decimal('10.00'))
        InventoryBatch.objects.create(company=self.company, stock=self.stock, batch_code='B-2', quantity=5, unit_cost=Decimal('12.00'))
        self.stock.quantity = 10
        self.stock.cost_price = Decimal('11.00')
        self.stock.save(update_fields=['quantity', 'cost_price'])
        self.assertEqual(self.stock.weighted_average_cost, Decimal('11.00'))
        self.assertEqual(self.stock.total_value, Decimal('110.00'))

    def test_low_stock_alerts_create_company_inventory_notifications(self):
        self.user.role = 'stock_manager'
        self.user.save(update_fields=['role'])
        self.stock.quantity = 1
        self.stock.reorder_level = 3
        self.stock.save(update_fields=['quantity', 'reorder_level'])

        alerts = create_inventory_alerts(self.company, stock=self.stock)

        self.assertTrue(alerts)
        self.assertEqual(alerts[0]['alert_type'], 'low_stock')
        self.assertTrue(
            Notification.objects.filter(
                user=self.user,
                notification_type=Notification.INVENTORY_LOW,
                related_object_id=self.stock.pk,
            ).exists()
        )

    def test_stock_save_generates_low_stock_alert(self):
        self.user.role = 'stock_manager'
        self.user.save(update_fields=['role'])

        stock = Stock.objects.create(
            company=self.company,
            item_code='SKU-LOW',
            name='Low Stock Item',
            category=self.category,
            quantity=1,
            unit='pcs',
            cost_price=Decimal('12.50'),
            selling_price=Decimal('18.00'),
            reorder_level=3,
            supplier_name='Supplier A',
            created_by=self.user,
        )

        self.assertTrue(stock.quantity <= stock.reorder_level)
        self.assertTrue(
            Notification.objects.filter(
                user=self.user,
                notification_type=Notification.INVENTORY_LOW,
                related_object_id=stock.pk,
            ).exists()
        )
