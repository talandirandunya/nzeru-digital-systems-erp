# ERP MAIN Enterprise Upgrade Implementation Report

**Date:** 2026-09-17  
**Primary system:** ERP MAIN  
**AREN source availability:** No AREN software repository was found in the workspace or Downloads. Only AREN business documents were present. No AREN Django models, migrations, ViewSets, serializers, services, permissions, frontend, or tests were available to integrate.

## Implementation approach

ERP MAIN remains the authoritative application. The upgrade is additive and preserves existing domain models and data. No existing tables, migrations, or historical records were deleted.

Existing authoritative concepts retained:

- `accounts.Company` and `accounts.User`
- `employees.Employee` and `employees.Department`
- `inventory.Stock` and `inventory.StockTransaction`
- `finance.Account`, `Transaction`, journals, and journal entries
- Existing HR, CRM, projects, meetings, marketplace, and notifications modules

## Modules upgraded

### Governance and access control

New app: `management_system/governance/`

Added:

- `RoleCapability`
- `UserCapability`
- `AuditEvent`
- Central capability constants and role defaults
- `effective_capabilities()` and `has_capability()`
- `capability_required()` backend decorator
- Administrator user list
- Administrator create-user workflow
- Administrator edit-user workflow
- Activate/deactivate user workflow
- Per-user capability override workflow
- Audit-event viewer

The existing role field remains compatible with MAIN. Capability defaults are derived from existing roles, and explicit user or company-role overrides can add or revoke capabilities.

Backend authorization is enforced by the decorator, not only by template visibility.

Relevant files:

- `management_system/governance/models.py`
- `management_system/governance/decorators.py`
- `management_system/governance/forms.py`
- `management_system/governance/views.py`
- `management_system/governance/urls.py`
- `management_system/templates/governance/`

### Audit trail

`AuditEvent` records:

- Actor
- Company
- Module
- Action
- Object type and ID
- Before and after state
- Reason
- IP address where supplied
- Timestamp

The model rejects normal instance updates and deletes. An administrator audit viewer is available at the governance route.

Audit events were added to key actions:

- Successful login
- Employee creation
- User creation and update
- User status changes
- Capability changes
- Leave approval and denial
- Finance transaction creation
- Inventory movement creation
- Procurement actions
- Goods receipt posting

This is an application-level append-only control. **LIMITATION:** database-level prevention of all possible bulk-delete operations and privileged database access is not implemented.

### Attendance

Attendance was added to the existing `hr` app rather than creating a second employee system.

New model: `hr.AttendanceRecord`

Capabilities:

- One record per employee/company/day
- Clock-in
- Clock-out
- Status
- Late minutes
- Early-leave minutes
- Notes
- HR attendance listing
- Manual attendance creation
- Employee self-service attendance view
- Tenant and employee-company validation

Relevant files:

- `management_system/hr/models.py`
- `management_system/hr/forms.py`
- `management_system/hr/views.py`
- `management_system/hr/urls.py`
- `management_system/templates/hr/attendance_*.html`

Attendance data is ready for future payroll integration, but payroll calculations do not yet consume attendance automatically.

### Procurement and goods receipt

New app: `management_system/procurement/`

Models:

- `Supplier`
- `PurchaseRequisition`
- `PurchaseRequisitionLine`
- `PurchaseOrder`
- `PurchaseOrderLine`
- `GoodsReceipt`
- `GoodsReceiptLine`

Implemented workflow:

```text
Supplier
  -> Purchase requisition draft
  -> Requisition submission
  -> Requisition approval/rejection
  -> Purchase order creation
  -> PO submission
  -> PO approval
  -> Partial or full goods receipt
  -> Existing Stock.quantity increase
  -> Existing StockTransaction history record
  -> Purchase order status update
  -> AuditEvent
```

Controls included:

- Company-scoped suppliers, stock, requisitions, orders, and receipts
- Requester cannot approve their own requisition
- Rejection requires a reason
- PO approval requires submission
- Receipt quantities cannot exceed ordered quantities
- Partial receipt status is supported
- Full receipt status is only set after all ordered quantity is received
- Stock rows and purchase orders are locked with `select_for_update()` during receipt processing
- Receipt processing uses `transaction.atomic()`
- Receipt updates MAIN inventory rather than creating a duplicate inventory system

Relevant files:

- `management_system/procurement/models.py`
- `management_system/procurement/services.py`
- `management_system/procurement/forms.py`
- `management_system/procurement/views.py`
- `management_system/procurement/urls.py`
- `management_system/templates/procurement/`

The procurement workflow currently stops after goods receipt. Supplier invoice matching, accounts payable, supplier payment, and general-ledger posting are not yet integrated.

## Database migrations

Generated and applied without destructive operations:

- `governance/migrations/0001_initial.py`
- `hr/migrations/0006_attendancerecord.py`
- `procurement/migrations/0001_initial.py`

Existing migration history and existing database tables were preserved.

## Tests added

- Governance audit immutability and capability revocation
- Attendance clock-in/out lifecycle
- Attendance cross-company validation
- Procurement partial receipt
- Procurement full receipt
- Receipt over-order protection

The test suite result after implementation:

```text
36 tests passed
```

Django checks pass with one pre-existing warning that the configured static directory does not exist:

```text
staticfiles.W004: .../management_system/static does not exist
```

## Not implemented in this upgrade

These requested capabilities remain incomplete and are explicitly not represented as finished:

- AREN-specific integration, because AREN source code was unavailable
- Branches and organisation locations
- Warehouse master data and bin-level stock balances
- Warehouse transfers and inventory reservations
- Supplier invoice three-way matching
- Accounts payable and supplier payments
- Customer quotations and sales orders
- Sales fulfilment and delivery
- Customer payments and complete AR ledger integration
- Fiscal periods and closed-period accounting controls
- Journal posting, maker-checker, and controlled ordinary-journal reversal
- Payroll approval and payroll-to-finance posting
- Attendance-driven payroll calculations
- General document management and versioning
- Full REST/DRF API and JWT authentication
- Central reporting layer using a fully authoritative ledger
- Login throttling and lockout
- Complete permission audit administration and role templates
- Full historical protection for all critical records

These are **NOT VERIFIED**, **PARTIALLY IMPLEMENTED**, or **NOT IMPLEMENTED** in the current codebase and require subsequent controlled phases.

## Remaining technical risks

- Existing finance invoice and report views contain model/view mismatches.
- Existing inventory movement forms do not consistently reject negative quantities.
- Existing marketplace payment binding and some stock concurrency paths require hardening.
- Tenant isolation remains primarily application-level outside the new procurement and attendance validations.
- Existing employee deletion and several financial deletion paths are destructive.
- SMTP credentials remain stored by the existing company email settings implementation.
- The React files at the repository root remain a disconnected prototype.

## Validation commands

```powershell
Push-Location management_system
python manage.py check
python manage.py makemigrations --check
python manage.py migrate --noinput
python manage.py test --verbosity 1
Pop-Location
```
