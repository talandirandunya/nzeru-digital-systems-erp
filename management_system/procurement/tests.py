from django.core.exceptions import ValidationError
from django.test import TestCase
from decimal import Decimal

from accounts.models import Company
from inventory.models import Stock
from .models import PurchaseOrder, PurchaseOrderLine, PurchaseRequisition, PurchaseRequisitionLine, Supplier
from .services import receive_goods


class ProcurementWorkflowTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Procurement Co', domain='procurement', contact_email='procurement@example.com')
        self.requester = self.company.users.create(email='requester@example.com', role='employee', is_active=True)
        self.approver = self.company.users.create(email='approver@example.com', role='admin', is_company_admin=True, is_active=True)
        self.stock = Stock.objects.create(company=self.company, item_code='SKU-1', name='Solar panel', quantity=2, unit='pcs', cost_price=Decimal('10'), selling_price=Decimal('15'), reorder_level=1, supplier_name='')
        self.supplier = Supplier.objects.create(company=self.company, name='Supplier One')

    def test_partial_receipt_updates_main_stock_and_order_status(self):
        requisition = PurchaseRequisition.objects.create(company=self.company, requested_by=self.requester, number='REQ-1')
        PurchaseRequisitionLine.objects.create(requisition=requisition, stock=self.stock, quantity=5)
        requisition.submit()
        requisition.decide(approver=self.approver, approved=True)
        order = PurchaseOrder.objects.create(company=self.company, requisition=requisition, supplier=self.supplier, number='PO-1')
        line = PurchaseOrderLine.objects.create(order=order, stock=self.stock, ordered_quantity=5)
        order.submit()
        order.approve(self.approver)

        receipt = receive_goods(order=order, received_by=self.approver, receipt_number='GR-1', quantities={str(line.pk): 2})
        self.assertEqual(receipt.total_quantity, 2)
        self.stock.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.stock.quantity, 4)
        self.assertEqual(order.status, 'partially_received')

        receive_goods(order=order, received_by=self.approver, receipt_number='GR-2', quantities={str(line.pk): 3})
        self.stock.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.stock.quantity, 7)
        self.assertEqual(order.status, 'received')

    def test_receipt_cannot_exceed_order(self):
        requisition = PurchaseRequisition.objects.create(company=self.company, requested_by=self.requester, number='REQ-2')
        PurchaseRequisitionLine.objects.create(requisition=requisition, stock=self.stock, quantity=1)
        requisition.submit()
        requisition.decide(approver=self.approver, approved=True)
        order = PurchaseOrder.objects.create(company=self.company, requisition=requisition, supplier=self.supplier, number='PO-2', status='approved')
        line = PurchaseOrderLine.objects.create(order=order, stock=self.stock, ordered_quantity=1)
        with self.assertRaises(ValidationError):
            receive_goods(order=order, received_by=self.approver, receipt_number='GR-3', quantities={str(line.pk): 2})
