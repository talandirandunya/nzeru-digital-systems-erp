# ERP Administrator Workflow Investigation

**Investigation date:** 2026-09-17  
**Scope:** Actual Django implementation in this repository  
**Method:** Read-only tracing of URLs, views, forms, models, middleware, permissions, templates, services, and tests  
**Code modified:** No

## Executive conclusion

This ERP provides a working company-scoped Django application with administrator access across employees, HR, basic finance, inventory, CRM, projects, meetings, notifications, and marketplace order management.

The administrator cannot operate a complete enterprise workflow from beginning to end. User administration, procurement, warehouses, attendance, reliable invoice lifecycles, general audit logging, and several finance workflows are missing or incomplete.

The application administrator is not the same as a Django platform superuser:

- `User.role='admin'` grants broad module access through role decorators.
- `User.is_company_admin=True` grants company-settings, invitation, and company-administration access.
- `User.is_superuser=True` bypasses role checks and can access the platform dashboard and Django admin.

## 1. Login and authentication

### Actual flow

```text
GET /login/
  -> accounts.views.company_login
  -> CompanyLoginForm

POST company domain + email + password
  -> locate active Company by domain
  -> locate active User by email and company
  -> Django authenticate()
  -> django.contrib.auth.login()
  -> store company_id in session
  -> record last_login_ip
  -> redirect to next URL or dashboard
```

Evidence:

- `company_login()` in `management_system/accounts/views.py`
- `CompanyLoginForm.clean()` in `management_system/accounts/forms.py`
- `User.USERNAME_FIELD = 'email'` in `management_system/accounts/models.py`
- Login URLs in `management_system/accounts/urls.py`

The initial company administrator is created by `company_register()` with:

```python
role='admin'
is_company_admin=True
```

Authentication failures return the login template with form validation errors. No MFA, lockout, or failed-login audit record was found. **NOT VERIFIED:** infrastructure-level protection outside the repository.

`RequireLoginMiddleware` in `management_system/accounts/middleware.py` redirects unauthenticated private requests to login. `CompanyContextMiddleware` attaches `request.company`, activates the user language, and periodically updates `last_seen`.

The login view redirects directly to the submitted `next` value. Safe-host validation was not found. **NOT VERIFIED:** whether deployment infrastructure mitigates this.

## 2. Dashboard

The main dashboard is `core.views.dashboard()` in `management_system/core/views.py`, rendered by `management_system/templates/core/dashboard.html`.

Database-calculated information includes:

- Total, active, and on-leave employees
- Recent employees
- Total, active, completed, and overdue projects
- Recent projects
- Total stock items
- Low-stock count and low-stock items
- Total account balance
- Current-month credits and debits
- Users active during the last five minutes

All dashboard queries are filtered by `request.user.company`.

The dashboard provides navigation to employees, finance, HR, leave, inventory, meetings, CRM, projects, marketplace administration, and company settings. It does not provide a general audit feed or a complete pending-approval aggregator.

Notifications are injected globally by `accounts.context_processors.company_context()` and displayed in `templates/base.html`. The base template polls `/notifications/api/unread-count/`.

The separate HR dashboard, `hr.views.index()`, calculates pending leave, approved leave, pending reviews, active courses, and training counts.

## 3. Organisation and company setup

Company profile management is implemented by `company_profile()` and `CompanyProfileForm`.

A company administrator can edit:

- Company name
- Contact information
- Address
- Marketplace contact numbers
- Subscription plan
- Active state

The company domain is read-only in the form.

Company administrators can also manage:

- SMTP settings through `company_email_settings()`
- Marketplace payment settings through `company_payment_settings()`
- Invitations through `invite_user()`

SMTP passwords are stored directly in `CompanyEmailSettings.email_host_password`.

Implemented organisation entities:

- Company
- Departments
- Employees
- HR positions
- Users linked to companies

Not implemented or not verified:

- Branches: **NOT IMPLEMENTED**
- Warehouse/location master data: **NOT IMPLEMENTED**
- Permission administration UI: **NOT IMPLEMENTED**
- User administration UI: **NOT IMPLEMENTED**

`Stock.location` is only a text field and is not a location-management module.

## 4. User management

There is no complete administrator user-management screen.

### Invitation workflow

```text
Company administrator
  -> invite_user()
  -> InvitationForm
  -> Invitation.create_for()
  -> email invitation
  -> recipient accepts token
  -> InvitationAcceptForm
  -> User created with role='employee'
  -> automatic login
  -> employee profile signal
```

Evidence:

- `invite_user()` and `accept_invitation()` in `accounts/views.py`
- `InvitationForm` and `InvitationAcceptForm` in `accounts/forms.py`
- `Invitation` in `accounts/models.py`

Invitations expire after seven days. The administrator cannot choose the role during invitation; invited users always receive the `employee` role.

### Employee-based account creation

The actual account-provisioning path is `employees.views.employee_create()` with `EmployeeForm`:

```text
Administrator
  -> employee_create()
  -> EmployeeForm validation
  -> create new User or link existing User
  -> post_save signal creates Employee profile
  -> employee fields saved
  -> employee job role mapped to User.role
```

The form supports first name, last name, email, password, phone, department, HR position, employee job role, status, salary, and photo.

Role mapping is implemented in `EmployeeForm._sync_user_role()`:

| Employee job role | User access role |
|---|---|
| `manager` | `manager` |
| `project_manager` | `manager` |
| `hr` | `hr_manager` |
| `accountant` | `accountant` |
| `secretary` | `secretary` |
| `stock_manager` | `stock_manager` |
| Other roles | `employee` |

The form cannot create an administrator role.

`create_employee_profile()` in `employees/models.py` automatically creates an Employee record when a company User is created. It generates an employee ID. The signal catches all exceptions, so a user could theoretically be created without the expected employee profile if profile creation fails.

### Editing and deletion

Implemented:

- Employee edit through `employee_edit()`
- Role synchronization through `EmployeeForm`
- Termination through `Employee.terminate()`
- Reactivation through `Employee.reactivate()`
- Employee deletion through `employee_delete()`
- Self-service password change through `CustomPasswordChangeView`

Termination sets the employee status to `terminated` and deactivates the linked user. Employee deletion is destructive; the linked user is cascade-deleted.

Not implemented:

- Administrator reset of another user password
- User list/edit/deactivate screen
- Direct administrator role-management screen
- Permission assignment screen

`UserManagementForm` exists but has no connected view or URL. It is **SCAFFOLDED**.

## 5. Roles and permissions

Roles are stored in `User.role`:

- `admin`
- `hr_manager`
- `accountant`
- `manager`
- `secretary`
- `stock_manager`
- `employee`

Authorization is primarily implemented by `role_required()` in `accounts/permissions.py`. It checks the backend request and allows superusers to bypass role checks. Unauthorized users are redirected to the dashboard.

Company settings use `company_admin_required()`, which checks `is_company_admin`.

Important backend role groups include:

- Employee writing: admin, HR manager, manager
- Employee deletion: admin, manager
- Finance: admin, accountant, manager
- Inventory writing: admin, stock manager, manager
- Inventory management: admin, manager, stock manager
- CRM: admin, manager, secretary
- Project writing: admin, manager, HR manager
- Project deletion: admin, manager
- Meeting writing: admin, HR manager, manager, secretary
- Marketplace administration: admin, manager, stock manager

Backend authorization is real and is not limited to hiding template buttons. Views use decorators and company-filtered object lookups. However, object-level rules such as “only the assigned employee can modify this task” are not consistently implemented.

Django groups and `user_permissions` are inherited from `AbstractUser`, but active use of those mechanisms was not found. **NOT VERIFIED:** meaningful group-based authorization.

There is an inconsistency between centralized role constants and local view constants. For example, `accounts/permissions.py` includes managers in `HR_ROLES`, while `hr/views.py` locally defines HR administration as admin and HR manager only.

## 6. Employees and HR

### Departments and positions

Departments are managed through `department_create()`, `department_edit()`, and `department_delete()` in `employees/views.py`. Department names are unique within a company through `DepartmentForm`.

Positions are managed through `position_create()`, `position_edit()`, and `position_delete()` in `hr/views.py`. Positions belong to a company and can be linked to employees.

### Leave approval

```text
Employee or authorised user submits request
  -> LeaveRequestForm
  -> full_clean()
  -> LeaveRequest(status='pending')
  -> HR/admin reviews
  -> approve or deny POST endpoint
  -> reviewer and timestamp saved
  -> employee status may become 'on_leave'
  -> notification created
```

Evidence:

- `my_leave_create()` and `leave_create()` in `hr/views.py`
- `leave_approve()` and `leave_deny()` in `hr/views.py`
- `LeaveRequest.approve()` and `LeaveRequest.deny()` in `hr/models.py`

Approval is backend-enforced by role checks and POST-only endpoints. There is no two-person approval or separation-of-duties enforcement.

### Payroll

```text
Create PayrollPeriod(status='draft')
  -> add active/on-leave employee entries
  -> edit entries and components
  -> lock period
  -> process period
  -> create Payslip records
  -> calculate totals
  -> mark completed
```

Evidence:

- `payroll_period_create()`
- `payroll_period_add_entries()`
- `payroll_entry_edit()`
- `payroll_period_lock()`
- `payroll_period_process()`
- `PayrollPeriod.process()`

Payroll statuses are `draft`, `locked`, `processing`, and `completed`. Payroll does not create finance transactions or payment records. Payroll entries remain editable/deletable through the views; permanent payroll protection is not implemented.

### Performance, training, skills

Actual CRUD/status workflows exist for:

- Performance goals
- Performance reviews
- Review submission and completion
- Review comments
- Training courses and sessions
- Employee training enrollment and completion
- Skills and employee skills

These are **PARTIALLY IMPLEMENTED** because broader document, attendance, finance, and approval integration is absent or not verified.

Attendance and employee document management are **NOT IMPLEMENTED** or **NOT VERIFIED**.

## 7. Finance

### Basic transactions

```text
TransactionForm
  -> company-scoped account choice
  -> set company and entered_by
  -> Transaction.save()
  -> account balance adjusted atomically
```

`Transaction.save()` in `finance/models.py`:

- Adds credit amounts to an account balance.
- Subtracts debit amounts.
- Applies the difference when an existing transaction is edited.
- Reverses the effect when a transaction is deleted.

Basic transactions can be edited and permanently deleted by finance roles.

### Accounts and journals

`Account.parent` provides a hierarchical chart of accounts. Account, journal, and journal-entry views are company-scoped.

Journal entries contain debit and credit lines. `BaseJournalEntryLineFormSet.clean()` requires total debits to equal total credits and rejects lines containing both debit and credit.

Therefore, the normal web form enforces:

```text
Debit total = Credit total
```

However:

- No database constraint enforces this invariant.
- `JournalEntry.clean()` is not automatically called by every direct save.
- There is no posting state or accounting-period lock.
- Journal entries can be edited or deleted.
- Ordinary journal reversal workflow was not found.

Double-entry accounting is therefore **PARTIALLY IMPLEMENTED**.

### Invoices

Client and supplier invoice models contain statuses and total calculations, but working lifecycle views for validation, payment, and cancellation were not found.

The invoice views also contain model/view mismatches:

- Client invoice code refers to `invoice.client.name` and `invoice.total_amount`, but the model defines `client_name` and `total`.
- Supplier invoice code refers to `invoice.supplier.name` and `invoice.total_amount`, but the model defines `supplier_name` and `total`.

Invoice lifecycle: **PARTIALLY IMPLEMENTED / BROKEN**.

### Bank reconciliation

The intended flow is bank account, statement upload, bank transactions, reconciliation, and matching.

The implementation contains confirmed mismatches:

- Upload passes `file_name` to `BankStatement`, but the model has no such field.
- Reconciliation writes `matched_transaction`, but the model field is `reconciled_transaction`.
- MT940 processing creates a placeholder transaction.

Bank reconciliation: **PARTIALLY IMPLEMENTED / BROKEN**.

### Financial reports

Financial report models and views exist, but report generation refers to fields and methods not present in the inspected model definitions, including report-line names and account balance methods.

Financial reports: **SCAFFOLDED / BROKEN**.

## 8. Inventory

Implemented workflow:

```text
Create category
  -> create stock item
  -> optional initial StockTransaction(type='in')
  -> update Stock.quantity
  -> later stock-in/out/adjustment
  -> create StockTransaction history
  -> issue low-stock notification
```

Evidence:

- `Stock`, `StockCategory`, and `StockTransaction` in `inventory/models.py`
- `stock_create()`, `stock_edit()`, and `stock_transaction()` in `inventory/views.py`
- `StockForm` and `StockTransactionForm` in `inventory/forms.py`

Supported:

- Products/items
- Categories
- Supplier name/contact fields
- Text location
- Stock-in
- Stock-out
- Adjustments
- Reorder levels
- Stock history
- Inventory reports and exports

Not implemented:

- Warehouses
- Transfers
- Bins
- Batches/lots
- Serial numbers
- Goods receipts
- Supplier master data
- Procurement integration

Negative transaction quantities are not consistently rejected. Inventory imports can overwrite quantities without matching transaction history. Basic inventory is **FULLY IMPLEMENTED**; enterprise inventory is **PARTIALLY IMPLEMENTED**.

## 9. Procurement

A procurement workflow was not found.

There are no verified models, URLs, or views for:

- Purchase requisitions
- Purchase orders
- Procurement approvals
- Supplier master records
- Goods receipts
- Purchase-to-inventory receiving
- Purchase-to-finance settlement

Supplier invoice models and a purchases journal do not constitute procurement.

Classification: **NOT IMPLEMENTED**.

## 10. CRM and sales

Actual CRM flow:

```text
Create Contact
  -> add notes
  -> create Opportunity
  -> assign employee
  -> advance stage
  -> mark won
  -> mark invoiced
  -> mark paid
  -> create finance Transaction
```

Evidence: `crm/views.py`, `crm/models.py`, and `crm/urls.py`.

When an opportunity is marked paid:

- A credit `Transaction` is created.
- The selected revenue account balance changes through `Transaction.save()`.
- The opportunity stores the transaction in `revenue_transaction`.
- Payment status becomes `paid`.

Implemented CRM capabilities:

- Contacts
- Notes
- Opportunities
- Stages
- Assignment
- Pipeline view
- Invoiced and paid status

Not implemented:

- Separate leads workflow
- Quotations
- Sales orders
- Fulfilment
- Commissions
- Full invoice integration

CRM is **FULLY IMPLEMENTED** as a lightweight opportunity system and **PARTIALLY IMPLEMENTED** as a complete sales system.

## 11. Projects

Actual flow:

```text
Create project
  -> assign manager/team members
  -> create tasks
  -> assign employees
  -> change task status
  -> add comments
  -> recalculate project completion
  -> update project status
  -> view reports/export
```

Project progress is calculated by `Project.update_completion_from_subtasks()` as the integer average of linked subtask completion percentages.

`SousTache.change_status()` sets completed tasks to 100%, sets completion dates, and recalculates the parent project. If all tasks are complete, the project becomes completed. Reopening a task can return it to in-progress.

Implemented:

- Projects
- Tasks
- Assignments
- Dependencies
- Comments
- Progress
- Kanban, Gantt, and calendar views
- Reports and export

Formal milestones, project approvals, project expenses, and project-to-finance integration are **NOT VERIFIED**.

## 12. Meetings and notifications

Meetings support:

- Dashboard statistics
- Meeting CRUD
- Attendees
- Notes
- Action items
- Attachments
- Completion toggles
- Reports
- Notifications

`meeting_dashboard()` calculates totals, upcoming meetings, completed meetings, pending actions, overdue actions, recent meetings, and assigned actions.

Notifications are stored per user in `Notification` and support read/unread, archive, delete, preferences, and an unread-count JSON endpoint.

Notifications are operational messages, not audit records. Notification producers use some types and URL names that do not match the model choices or URL declarations. Notification preference enforcement is inconsistent.

## 13. Marketplace administration

Marketplace clients use a separate session-based `Client` authentication system. Company administrators use Django authentication for marketplace administration.

Administrator capabilities include:

- Order dashboard
- Order list and filtering
- Order details
- Quick in-store orders
- Confirm orders
- Ship orders
- Deliver orders
- Cancel orders
- Update payment status
- Restore stock on cancellation
- Post or reverse some marketplace finance entries

Marketplace order dashboard statistics are database-backed.

`marketplace/admin_views.py` defines `admin_order_quick_create()` twice. The second definition overrides the first. The effective implementation reduces stock and records a stock transaction but does not call the finance posting service.

The marketplace finance service can create balanced journal entries, mirror them into the simple ledger, and create reversal entries. Marketplace administration is **PARTIALLY IMPLEMENTED**.

## 14. Approval workflows

### Fully operational approval

Leave approval:

```text
Employee submits leave
  -> pending
  -> HR/admin reviews
  -> approve or deny
  -> reviewer and timestamp recorded
  -> employee status may change
  -> employee notification
```

### Scaffolding only

Supplier invoice statuses include validation levels, but working level-1 and level-2 approval views were not found.

Payroll has lock/process transitions, not a separate approval workflow.

Marketplace order confirmation is a status transition, not a general approval engine.

No verified approval workflow exists for procurement, expenses, project approvals, user creation, role changes, or ordinary journal posting.

## 15. Cross-module workflows

### User and employee

```text
User created
  -> post_save signal
  -> Employee profile created
```

### Employee and role

```text
EmployeeForm job role
  -> User.role mapping
  -> role decorators control module access
```

### Leave and employee status

```text
Leave approved
  -> LeaveRequest.status='approved'
  -> Employee.status='on_leave' when current
  -> notification
```

### CRM and finance

```text
Opportunity marked paid
  -> Transaction created
  -> revenue Account.balance updated
  -> transaction stored on opportunity
```

### Marketplace, inventory, and finance

```text
Marketplace order
  -> OrderItems
  -> Stock.quantity reduced
  -> StockTransaction created
  -> paid order may create JournalEntry and ledger Transactions
```

This is incomplete because finance posting is not consistent across administrator order paths and stock locking is incomplete.

### Payroll and finance

No payroll-to-finance integration was found.

### Procurement, inventory, and finance

Not implemented.

## 16. Data ownership and isolation

The intended tenant boundary is:

```text
User.company
  -> request.company
  -> company foreign keys
  -> company-filtered querysets
  -> company-filtered form choices
```

Most private CRUD views use company-filtered object lookups. Forms commonly limit related choices to the current company.

Protection exists mainly at view/queryset and form level. It is not globally enforced by model managers or database row-level security. Related objects are not consistently validated as belonging to the same company.

Public marketplace browsing intentionally supports selected active companies and follows different rules.

A complete cross-tenant security test suite is **NOT VERIFIED**.

## 17. Audit trail

No general audit trail was found.

The repository contains no verified:

- `AuditLog` model
- Immutable event table
- History package
- General audit middleware
- Administrator activity viewer

Some actions write ordinary application logs, including login IP updates, invitations, employee creation, exports, and signal failures. These logs are not application-visible audit records.

Login attempts, user changes, role changes, deletions, approvals, finance edits, inventory edits, and company-setting changes are not comprehensively recorded.

Classification: **NOT IMPLEMENTED**.

## 18. Administrator powers and record protection

The administrator can generally create, edit, and delete:

- Employees and departments
- Positions and leave records
- Payroll entries
- Accounts, transactions, journals, and journal entries
- Invoice records
- Bank records
- Stock items, categories, and movements
- CRM contacts, notes, and opportunities
- Projects, tasks, and comments
- Meetings, notes, and action items
- Marketplace order statuses

Critical historical records are not consistently protected:

- Finance transactions can be deleted.
- Journal entries can be deleted.
- Payroll entries can be deleted.
- Stock items can be deleted with history.
- Employees can be permanently deleted.
- Invoices can be deleted.
- General archive/recovery is absent.

Marketplace orders have a more developed finance reversal service, but this does not apply uniformly to all finance records.

## 19. Capability classification

| Capability | Classification |
|---|---|
| Company registration and login | FULLY IMPLEMENTED |
| Company profile | FULLY IMPLEMENTED |
| Company email/payment settings | PARTIALLY IMPLEMENTED |
| User invitations | PARTIALLY IMPLEMENTED |
| User administration | NOT IMPLEMENTED |
| Employee CRUD | FULLY IMPLEMENTED |
| Employee account creation | PARTIALLY IMPLEMENTED |
| Departments and positions | FULLY IMPLEMENTED |
| Role enforcement | PARTIALLY IMPLEMENTED |
| Django group permission administration | NOT VERIFIED |
| Leave approval | FULLY IMPLEMENTED |
| Attendance | NOT IMPLEMENTED |
| Payroll | PARTIALLY IMPLEMENTED |
| Performance, training, and skills | PARTIALLY IMPLEMENTED |
| Basic accounts and transactions | FULLY IMPLEMENTED, with deletion risk |
| Double-entry journals | PARTIALLY IMPLEMENTED |
| Client and supplier invoices | PARTIALLY IMPLEMENTED / BROKEN |
| Bank reconciliation | PARTIALLY IMPLEMENTED / BROKEN |
| Financial reports | SCAFFOLDED / BROKEN |
| Stock master data | FULLY IMPLEMENTED |
| Stock movements | PARTIALLY IMPLEMENTED |
| Warehouses and transfers | NOT IMPLEMENTED |
| Procurement | NOT IMPLEMENTED |
| CRM contacts/opportunities | FULLY IMPLEMENTED |
| Complete sales cycle | NOT IMPLEMENTED |
| Projects and tasks | FULLY IMPLEMENTED |
| Project reporting | PARTIALLY IMPLEMENTED |
| Meetings | FULLY IMPLEMENTED |
| Notifications | PARTIALLY IMPLEMENTED |
| Marketplace administration | PARTIALLY IMPLEMENTED |
| Audit trail | NOT IMPLEMENTED |
| REST API | NOT IMPLEMENTED |
| React operational frontend | NOT IMPLEMENTED |
| React demo frontend | PROTOTYPE |

## 20. Realistic administrator journey

A journey supported by the actual implementation is:

```text
Administrator logs in with company domain, email, and password
  -> reviews dashboard statistics and low-stock alerts
  -> creates an employee account and assigns a job role
  -> reviews and approves a pending leave request
  -> creates a payroll period, adds entries, locks, and processes it
  -> creates or updates a stock item and records stock movement
  -> advances a CRM opportunity and records payment
  -> creates a project, assigns employees, and tracks tasks
  -> manages a marketplace order through confirmation, shipping, or delivery
  -> reads and archives notifications
  -> logs out
```

The journey cannot include procurement, warehouse receiving, attendance, a reliable invoice approval/payment cycle, or audit review because those capabilities are missing or incomplete.

## 21. Actual administrator architecture

```text
COMPANY REGISTRATION OR EXISTING USER
        ↓
COMPANY DOMAIN + EMAIL + PASSWORD LOGIN
        ↓
DJANGO SESSION AUTHENTICATION
        ↓
RequireLoginMiddleware
        ↓
CompanyContextMiddleware
        ↓
request.user.company
        ↓
role_required() OR company_admin_required()
        ↓
company-filtered queryset and form choices
        ↓
form validation
        ↓
model save or module service
        ↓
related side effects
(employee profile, account balance, stock history, notification, payslip, finance posting)
        ↓
database records
        ↓
module dashboards, lists, reports, or exports
```

The architecture does not consistently include a general approval engine, immutable audit event, procurement chain, warehouse layer, financial posting lock, or administrator permission-management layer.

## 22. Final answer: what can the administrator actually manage?

### Fully operational or substantially operational

- Company registration and authentication
- Company profile and selected settings
- Employees and departments
- HR positions
- Leave submission and approval
- Basic payroll preparation and payslips
- Basic accounts and transactions
- Stock items and stock movements
- CRM contacts and opportunities
- CRM payment-to-finance recording
- Projects and tasks
- Meetings and action items
- In-app notifications

### Partially operational

- User provisioning and role assignment
- Payroll controls and historical protection
- Double-entry accounting
- Client and supplier invoices
- Bank reconciliation
- Financial reports
- Marketplace finance synchronization
- Inventory validation and concurrency
- Notification consistency
- Tenant-isolation guarantees

### Missing

- Procurement
- Warehouses and stock transfers
- Attendance
- Permission administration
- General audit trail
- Quotations and sales orders
- Project expenses
- Payroll-to-finance integration
- Enterprise document management
- Coherent REST API

### Manual intervention or security concern

- Broken finance screens require code repair or manual database work.
- Invoice validation and payment cannot be completed through verified views.
- Bank statement upload/reconciliation contains model/view mismatches.
- Finance, payroll, inventory, employee, and invoice records can be permanently deleted.
- Login redirects are not visibly validated as same-host URLs.
- SMTP passwords are stored in plaintext.
- Negative inventory quantities are not consistently rejected.
- Marketplace payment binding and stock concurrency require additional controls.
- No application-visible administrator audit history exists.

**Overall classification:** FUNCTIONAL ERP PROTOTYPE with several real administrator workflows, but not a complete or production-ready enterprise administrator system.
