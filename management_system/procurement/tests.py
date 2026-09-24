from django.core.exceptions import ValidationError
from django.test import TestCase
from decimal import Decimal

from accounts.models import Company
from inventory.models import Stock
from .models import (
    PurchaseOrder, PurchaseOrderLine, PurchaseRequisition, PurchaseRequisitionLine,
    RequestForQuotation, Supplier, SupplierInvoiceMatch, SupplierQuotation,
)
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

    def test_invoice_match_flags_exact_and_exception_totals(self):
        requisition = PurchaseRequisition.objects.create(company=self.company, requested_by=self.requester, number='REQ-3')
        PurchaseRequisitionLine.objects.create(requisition=requisition, stock=self.stock, quantity=2)
        order = PurchaseOrder.objects.create(company=self.company, requisition=requisition, supplier=self.supplier, number='PO-3', status='approved')
        PurchaseOrderLine.objects.create(order=order, stock=self.stock, ordered_quantity=2, unit_cost=Decimal('10'))

        exact = SupplierInvoiceMatch.objects.create(
            company=self.company, order=order, supplier=self.supplier, invoice_number='INV-1',
            invoice_date='2026-09-22', invoice_total=Decimal('20'), created_by=self.approver,
        )
        self.assertEqual(exact.evaluate(), 'matched')
        exception = SupplierInvoiceMatch.objects.create(
            company=self.company, order=order, supplier=self.supplier, invoice_number='INV-2',
            invoice_date='2026-09-22', invoice_total=Decimal('25'), created_by=self.approver,
        )
        self.assertEqual(exception.evaluate(), 'exception')

    def test_receipt_posts_inventory_cost_accrual_to_finance(self):
        self.stock.quantity = 0
        self.stock.cost_price = Decimal('0')
        self.stock.save(update_fields=['quantity', 'cost_price'])

        requisition = PurchaseRequisition.objects.create(company=self.company, requested_by=self.requester, number='REQ-5')
        PurchaseRequisitionLine.objects.create(requisition=requisition, stock=self.stock, quantity=5)
        requisition.submit()
        requisition.decide(approver=self.approver, approved=True)
        order = PurchaseOrder.objects.create(company=self.company, requisition=requisition, supplier=self.supplier, number='PO-5', status='approved')
        line = PurchaseOrderLine.objects.create(order=order, stock=self.stock, ordered_quantity=5, unit_cost=Decimal('18.00'))

        receipt = receive_goods(order=order, received_by=self.approver, receipt_number='GR-5', quantities={str(line.pk): 5})
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 5)
        self.assertEqual(self.stock.weighted_average_cost, Decimal('18.00'))
        self.assertTrue(receipt.lines.exists())
        from finance.models import JournalEntry
        self.assertTrue(JournalEntry.objects.filter(company=self.company, reference__icontains='GR-5').exists())

    def test_quotation_cannot_use_supplier_from_another_company(self):
        other = Company.objects.create(name='Other Co', domain='other-procurement', contact_email='other@example.com')
        other_supplier = Supplier.objects.create(company=other, name='Other Supplier')
        requisition = PurchaseRequisition.objects.create(company=self.company, requested_by=self.requester, number='REQ-4')
        rfq = RequestForQuotation.objects.create(company=self.company, requisition=requisition, number='RFQ-1', created_by=self.requester)
        quote = SupplierQuotation(rfq=rfq, supplier=other_supplier, quote_number='Q-1', quoted_total=Decimal('10'))
        with self.assertRaises(ValidationError):
            quote.full_clean()
