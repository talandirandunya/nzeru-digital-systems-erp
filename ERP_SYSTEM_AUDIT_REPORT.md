# ERP System Audit Report

**Audit date:** 2026-09-16  
**Scope:** Read-only inspection of the repository implementation  
**Conclusion:** Functional Django ERP prototype with substantial modules, but not production-ready as an enterprise ERP.

## 1. Executive Summary

This repository contains a Django 6 application for multiple companies (tenants). It provides company-scoped users, role-based access control, employees, HR, finance, projects, inventory, CRM, a marketplace, meetings, and notifications.

The operational application is primarily server-rendered Django templates. The React files at the repository root are a disconnected visual prototype using hard-coded data; they do not communicate with Django or the database.

The strongest implemented areas are:

- Company-aware authentication and role management
- Employee and HR data models
- Leave workflow
- Project and task management
- Basic inventory movement tracking
- CRM opportunity pipeline
- Marketplace checkout and inventory integration
- Basic and double-entry finance structures
- Meeting and notification infrastructure

The largest risks are:

- Incomplete and inconsistent finance views
- Marketplace payment callbacks not fully bound to orders
- Marketplace stock race conditions
- Negative quantity handling
- Inconsistent marketplace company and visibility filtering
- Plaintext SMTP credentials
- Limited automated security and workflow tests
- No coherent REST API
- Missing procurement and warehouse functionality

## 2. Evidence Reviewed

Important implementation surfaces inspected:

- [management_system/management_system/settings.py](management_system/management_system/settings.py)
- [management_system/management_system/urls.py](management_system/management_system/urls.py)
- [management_system/accounts/models.py](management_system/accounts/models.py)
- [management_system/accounts/views.py](management_system/accounts/views.py)
- [management_system/accounts/middleware.py](management_system/accounts/middleware.py)
- [management_system/accounts/permissions.py](management_system/accounts/permissions.py)
- App `models.py`, `views.py`, `forms.py`, `urls.py`, `services.py`, and `admin.py` files
- App test modules
- Root React/demo files
- Docker, Render, deployment, environment, and email configuration

No code was modified during this audit.

## 3. Overall Architecture

### Backend

The backend is Django 6 with Python. Django applications are routed from [management_system/management_system/urls.py](management_system/management_system/urls.py):

- `/admin/`
- `/` for accounts and authentication
- `/core/`
- `/employees/`
- `/projects/`
- `/inventory/`
- `/marketplace/`
- `/finance/`
- `/hr/`
- `/crm/`
- `/meetings/`
- `/notifications/`

The application uses function-based Django views, forms, model methods, and a small marketplace service layer.

### Frontend

The real operational frontend is Django templates under `management_system/templates`. Views render HTML pages and redirect after form submissions.

The root files [Erpis.html](Erpis.html), [erpis-ui.jsx](erpis-ui.jsx), [erpis-screens.jsx](erpis-screens.jsx), [erpis-data.js](erpis-data.js), and [tweaks-panel.jsx](tweaks-panel.jsx) are a separate React/Babel prototype. They contain hard-coded sample data and no backend integration.

Classification: **PROTOTYPE/DEMO**.

### Database

[management_system/settings.py](management_system/management_system/settings.py) selects:

- SQLite when local `DEBUG=True` and `DATABASE_URL` is absent
- PostgreSQL when `DATABASE_URL` is configured for production

Migrations exist across the Django apps. A repository SQLite database is present at `management_system/db.sqlite3`.

### API

No Django REST Framework layer was found:

- No `serializers.py` files
- No DRF `APIView` classes
- No DRF `ViewSet` classes
- No coherent versioned API

There are a few small JSON responses for internal UI actions, such as unread notification counts and task toggles. These are not a public API architecture.

### Request and response flow

```text
Browser request
  -> Django URL resolver
  -> Django authentication middleware
  -> RequireLoginMiddleware
  -> CompanyContextMiddleware
  -> role_required or explicit permission check
  -> Django view
  -> form validation and company-scoped querysets
  -> model/service business logic
  -> database transaction where used
  -> HTML template or redirect
```

## 4. Authentication and Organisation Structure

### Organisation model

`Company` is the tenant root. It has a unique domain, subscription plan, contact fields, active status, and a UUID identifier.

`User.company` associates each staff user with one company. Most business models also carry a `company` foreign key.

### User creation

Company registration in [management_system/accounts/views.py](management_system/accounts/views.py):

1. Validates the company and administrator form.
2. Creates the company.
3. Creates the first user with role `admin`.
4. Sets `is_company_admin=True`.
5. Authenticates and logs the user in.
6. Redirects to the dashboard.

Invitations are created by company administrators and expire after seven days. Accepting an invitation creates a user with the `employee` role.

Creating a company user also triggers automatic employee-profile creation in the employees app.

### Login

The custom user model uses email as the login identifier. Company login validates the company domain, email, active company, user membership, and password through the login form.

### Middleware

[management_system/accounts/middleware.py](management_system/accounts/middleware.py) contains:

- `RequireLoginMiddleware`: redirects unauthenticated private requests to login.
- `CompanyContextMiddleware`: assigns `request.company`, activates user language, and updates `last_seen` periodically.

Marketplace, registration, invitation acceptance, static/media, and password-reset routes are public according to the middleware configuration.

### Roles

Role constants are in [management_system/accounts/permissions.py](management_system/accounts/permissions.py):

- `admin`: broad company administration
- `hr_manager`: employees, departments, positions, leave, HR
- `accountant`: finance
- `manager`: projects, employees, inventory, CRM, and selected finance features
- `secretary`: CRM, meetings, and leave submission
- `stock_manager`: inventory management
- `employee`: self-service and permitted viewing/submission actions

Superusers bypass normal role checks.

Permissions are mainly enforced by `role_required()` decorators and explicit view checks. They are backend controls, not just frontend hiding.

The system does not consistently implement object-level permissions such as “only the assigned employee may modify this task.”

## 5. Tenant Isolation

### Intended mechanism

Tenant isolation is implemented through:

1. `User.company`
2. `request.company` from middleware
3. `company` foreign keys on business models
4. Company-filtered querysets in views and forms
5. Company-filtered object lookups
6. Company-scoped foreign-key choices

Typical intended query pattern:

```python
Model.objects.filter(company=request.user.company)
```

### Coverage

Private CRUD paths generally scope:

- Employees and departments
- Projects and tasks
- HR records
- Finance accounts and records
- Inventory
- CRM records
- Meetings
- Marketplace administrative records
- Invitations

No confirmed private ERP cross-company IDOR was found in the reviewed CRUD paths.

### Weaknesses

Isolation is mostly enforced by application code, not database constraints. A missed filter can therefore expose another company’s data.

Marketplace public product and cart operations do not consistently require:

- Marketplace visibility
- Positive stock
- A selected active company
- Company ownership in every lookup

Public product detail can expose hidden, inactive, or out-of-stock stock records through predictable IDs.

The finance transaction model does not visibly enforce that its account and transaction company are identical. Forms and views may protect the normal path, but the database does not guarantee the invariant.

Notifications are scoped primarily through the recipient user rather than an explicit company foreign key.

Classification: **PARTIALLY IMPLEMENTED**.

## 6. Database Design

### Main relationship graph

```text
Company
  -> User
      -> Employee
          -> Department
          -> Position
          -> LeaveRequest
          -> Payroll
          -> Skills
          -> Performance reviews
          -> Meetings
          -> Project assignments
```

```text
Company
  -> Project
      -> SousTache
          -> CommentaireTache
```

```text
Company
  -> StockCategory
      -> Stock
          -> StockTransaction
```

```text
Company
  -> Account
      -> Transaction
      -> Journal / JournalEntry / JournalEntryLine
      -> Invoices
      -> Bank records
```

```text
Company
  -> Marketplace products
  -> Orders
      -> OrderItems
      -> Returns
      -> Reviews
```

### Constraints and indexes

The code uses:

- Foreign keys with delete behavior
- One-to-one relationships
- Many-to-many relationships
- Unique company/domain combinations
- Unique company/item-code combinations
- Unique company/category-name combinations
- Unique company/invitation-email combinations
- Indexes on company, role, active state, domain, and notification fields
- Model validators and choice fields

Important caution: Django field validators are not automatically executed on every direct `.save()`. Service and view boundaries must validate input explicitly.

### Transactions and locking

`transaction.atomic()` is used in finance changes, marketplace checkout, and marketplace financial posting.

`select_for_update()` is used in important marketplace finance operations.

Marketplace stock availability checks do not consistently lock stock rows before checking and decrementing them. This leaves a confirmed concurrency weakness.

## 7. Module Inventory

### Accounts

Files: [accounts/models.py](management_system/accounts/models.py), [accounts/views.py](management_system/accounts/views.py), [accounts/forms.py](management_system/accounts/forms.py)

Models:

- `Company`
- `User`
- `Invitation`
- `CompanyEmailSettings`

Workflows:

- Company registration
- Company login/logout
- Invitations
- Invitation acceptance
- User profile
- Company profile
- Company SMTP settings
- Company payment settings
- Language selection

Classification: **IMPLEMENTED**, with security and credential-handling issues.

### Core

File: [core/views.py](management_system/core/views.py)

There are no core domain models. The app provides:

- Role-aware dashboard aggregation
- Superuser platform dashboard
- Cross-module summary statistics

Classification: **IMPLEMENTED dashboard shell**.

### Employees

Files: [employees/models.py](management_system/employees/models.py), [employees/views.py](management_system/employees/views.py)

Models include:

- `Department`
- `Employee`

Implemented functionality:

- Employee CRUD
- Department management
- User linking/creation
- Automatic employee profile creation
- Role synchronization from employee job title
- Termination/reactivation status changes
- Excel import/export
- Summary reports
- Employee images

Classification: **IMPLEMENTED**.

### HR

Files: [hr/models.py](management_system/hr/models.py), [hr/views.py](management_system/hr/views.py), [hr/forms.py](management_system/hr/forms.py)

Models include:

- `Position`
- `LeaveRequest`
- Payroll periods, entries, components, and payslips
- Performance goals and reviews
- Review comments
- Training courses, sessions, and enrollments
- Skills and employee skills

Workflows include:

- Leave submission, approval, and denial
- Employee leave status synchronization
- Payroll period creation and processing
- Payroll locking
- Payslip generation
- Performance review submission/completion
- Training enrollment/completion
- Skill assessment

Attendance/time tracking was not found as a complete implementation: **NOT VERIFIED**.

Some HR views appear defective, including a likely skill pagination error and a questionable reviewer relation in performance review listing.

Classification: **IMPLEMENTED/PARTIAL**.

### Finance

Files: [finance/models.py](management_system/finance/models.py), [finance/views.py](management_system/finance/views.py), [finance/forms.py](management_system/finance/forms.py)

Models include:

- `Account`
- Parent/child chart of accounts
- Basic `Transaction`
- `Journal`
- `JournalEntry`
- Debit/credit entry lines
- Client invoices
- Supplier invoices
- Bank accounts
- Bank statements
- Bank transactions
- Reconciliation
- Financial reports
- Marketplace finance mappings

The basic transaction model updates account balances atomically:

```text
Credit: balance = balance + amount
Debit:  balance = balance - amount
```

Editing applies the difference between the old and new transaction. Deleting reverses the original effect.

Double-entry structures are genuinely present. Journal entries contain debit and credit lines and are intended to validate that entries balance.

However, multiple views refer to fields or methods that do not exist in the current models, including:

- Client invoice fields
- Supplier invoice fields
- Bank statement upload fields
- Reconciliation field names
- Report account methods and report-line fields

Classification: **PARTIALLY IMPLEMENTED / BROKEN IN SECTIONS**.

### Inventory

Files: [inventory/models.py](management_system/inventory/models.py), [inventory/views.py](management_system/inventory/views.py), [inventory/forms.py](management_system/inventory/forms.py)

Models:

- `StockCategory`
- `Stock`
- `StockTransaction`

Stock contains:

- Item code and name
- Category
- Quantity and unit
- Cost and selling prices
- Reorder level
- Supplier name/contact
- Location
- Marketplace visibility
- Image
- Last restocked date

Computed properties:

```text
Total cost value = quantity * cost_price
Total selling value = quantity * selling_price
Needs reorder = quantity <= reorder_level
```

Stock movements support:

- Stock in
- Stock out
- Absolute adjustment

The movement workflow changes quantity and records `StockTransaction` history. Stock-in updates `last_restocked`, and low-stock notifications are attempted.

Not found as complete functionality:

- Warehouse master data
- Warehouse transfers
- Bin management
- Batch/lot tracking
- Serial number tracking
- Goods receipts from procurement
- Supplier master data

Imports can overwrite quantities without creating matching transaction history.

Negative quantities are not consistently rejected at the request/service boundary. This can corrupt stock values.

Classification: **IMPLEMENTED CORE / PARTIAL ENTERPRISE INVENTORY**.

### Projects

Files: [projects/models.py](management_system/projects/models.py), [projects/views.py](management_system/projects/views.py), [projects/forms.py](management_system/projects/forms.py)

Models:

- `Project`
- `SousTache`
- `CommentaireTache`

Implemented functionality:

- Project CRUD
- Managers and team members
- Task assignment
- Task dependencies
- Task status changes
- Comments
- AJAX completion toggles
- Gantt view
- Kanban view
- Calendar view
- Reports
- Excel export

Project progress is calculated as the average completion percentage of subtasks. Completing a task sets its completion to 100% and updates the parent project. All completed tasks can mark the project completed; reopening a task can return the project to `in_progress`.

Formal milestones and approvals were not verified: **NOT VERIFIED**.

Classification: **IMPLEMENTED**.

### CRM

Files: [crm/models.py](management_system/crm/models.py), [crm/views.py](management_system/crm/views.py), [crm/forms.py](management_system/crm/forms.py)

Models:

- `Contact`
- `Note`
- `Opportunity`

Implemented functionality:

- Contact CRUD
- Notes
- Opportunity pipeline
- Stage advancement
- Kanban view
- Employee ownership
- Marketplace-client linking
- Payment marking
- Finance transaction creation

Missing or not verified:

- Quotations
- Sales orders
- Full lead scoring
- Sales fulfillment
- Commission management

Classification: **IMPLEMENTED LIGHTWEIGHT CRM**.

### Marketplace

Files: [marketplace/models.py](marketplace/models.py), [marketplace/views.py](marketplace/views.py), [marketplace/admin_views.py](marketplace/admin_views.py), [marketplace/services.py](marketplace/services.py)

Models include:

- `Client`
- `Cart` and cart items
- `Order` and order items
- `Wishlist`
- `Review`
- `Return`
- Company payment settings

Implemented functionality:

- Client authentication
- Product listing and detail
- Cart operations
- Wishlist
- Checkout
- Orders
- Returns and reviews
- Stripe/Flutterwave integration helpers
- PDF invoices
- Administrative order management
- Inventory decrement/restoration
- Finance posting and reversal

Checkout creates orders and order items inside a transaction, decrements inventory, records stock-out history, and clears the cart.

Defects include:

- Missing row locks during stock availability checks
- Negative cart quantities
- Public product visibility/company filtering gaps
- Duplicate `admin_order_quick_create()` definition
- The second quick-create implementation does not perform the same finance posting
- Payment success does not fully verify session ownership, amount, currency, and order binding

Classification: **PARTIALLY IMPLEMENTED**.

### Meetings

Files: [meetings/models.py](meetings/models.py), [meetings/views.py](meetings/views.py), [meetings/forms.py](meetings/forms.py)

Models:

- `Meeting`
- `MeetingNote`
- `ActionItem`
- `MeetingAttachment`

Implemented functionality:

- Meeting CRUD
- Attendee management
- Notes
- Action items
- Attachments
- Completion state
- Reports
- Notifications
- DOCX extraction support

Classification: **IMPLEMENTED**, with file-upload hardening still needed.

### Notifications

Files: [notifications/models.py](notifications/models.py), [notifications/views.py](notifications/views.py), [notifications/forms.py](notifications/forms.py)

Implemented functionality:

- Notification creation
- Read/unread state
- Archive/delete
- Mark all as read
- Preferences
- Unread-count JSON endpoint

Notification producers exist in HR, CRM, inventory, projects, meetings, finance, and marketplace.

Notification type constants are inconsistent between the model and producers. Preference logic exists but is not consistently consulted before creation.

Classification: **IMPLEMENTED INFRASTRUCTURE / PARTIALLY RELIABLE**.

### Procurement

A complete procurement application was not found.

The repository does not verify a complete chain of:

```text
Requisition -> Approval -> Purchase order -> Supplier -> Goods receipt -> Invoice -> Payment
```

Supplier fields and supplier invoice models exist, but they do not constitute procurement.

Classification: **MISSING**, with partial finance/inventory data structures only.

## 8. Actual Business Workflows

### Marketplace sale

The clearest complete cross-module transaction is:

```text
Client session
  -> Add stock item to cart
  -> Validate cart composition
  -> Create Order
  -> Create OrderItems
  -> Decrease Stock
  -> Record StockTransaction
  -> Clear cart
  -> Initiate payment
  -> Mark order paid
  -> Post journal entry and ledger transactions
```

This workflow is implemented, but payment binding and concurrent stock handling are not sufficiently robust.

### CRM opportunity payment

The CRM can mark an opportunity as paid and create a finance transaction. This is a simpler CRM-to-finance flow and is not a complete quotation/order/invoice sales cycle.

### Leave

```text
Employee submits LeaveRequest
  -> Pending
  -> HR/admin approval or denial
  -> Employee status update
  -> Notification
```

### Inventory movement

```text
User submits stock movement
  -> Validate item and quantity
  -> Change Stock.quantity
  -> Create StockTransaction
  -> Update restock metadata if needed
  -> Generate low-stock notification if applicable
```

### Procurement

The procurement workflow is **NOT VERIFIED** and should be treated as missing.

## 9. Security Findings

The following are supported by the inspected code.

### High risk: negative quantity handling

Marketplace cart input and inventory movement input can accept negative integers without consistently enforcing a positive minimum at the service boundary.

Possible effects:

- Negative order quantities
- Negative order totals
- Inventory increases from a supposed stock-out
- Corrupted stock history

### High risk: marketplace checkout race condition

Checkout checks available stock and later decrements it, but does not consistently use `select_for_update()` on stock rows. Concurrent requests can both pass the check and oversell inventory.

### High risk: payment callback binding

Payment success handling checks payment status but does not sufficiently verify that the payment session belongs to the expected order/client and matches the expected amount and currency.

This is a confirmed payment-integrity weakness in the implementation.

### Medium risk: marketplace visibility and IDOR exposure

Public product detail uses broad stock lookup and does not consistently require marketplace visibility or company selection. Hidden products and stock metadata may be exposed through predictable IDs.

### Medium risk: plaintext SMTP credentials

Company SMTP passwords are stored directly in the database and are exposed through an administrative form configuration. These credentials should be encrypted or replaced by a secret-management design.

### Medium risk: open redirects

Login redirects directly to a user-controlled `next` value. Language switching also accepts a request-controlled destination/referrer without visible safe-host validation.

### Low risk: GET logout

Logout changes session state through GET. This enables forced logout and violates the expected state-changing method convention.

### Configuration risk: debug and development secret defaults

`DEBUG` defaults to true and a development secret key exists when production environment variables are missing. Production deployment must explicitly enforce secure values.

### Not confirmed

The audit did not confirm:

- Authentication bypass
- A private ERP cross-company IDOR in the reviewed CRUD paths
- `csrf_exempt` endpoints
- General mass assignment through normal forms
- Direct privilege escalation through ordinary role-controlled views

Automated tests are still needed for these claims.

## 10. Testing

Tests are distributed among app-level `tests.py` files. There are no separate large test directories.

Meaningfully tested areas include:

- Employee form/account creation
- Finance balance mutations and company scoping
- Finance settings and invoice printing
- Leave model transitions
- Basic CRM opportunity behavior
- Meeting, note, and action-item models
- Marketplace cart company isolation
- Marketplace admin scoping
- Marketplace stock restoration
- Marketplace payment transitions
- Marketplace finance posting

Placeholder or very limited test modules include:

- Accounts
- Inventory
- Projects
- Core
- Notifications

Materially under-tested areas:

- Authentication and registration
- Invitations and password reset
- Role decorators
- Cross-tenant access across all modules
- Inventory concurrency and imports
- Payment callback security
- Stripe and Flutterwave integrations
- Payroll and performance workflows
- CRM views
- Notification producers/preferences
- Upload security
- Background tasks
- Deployment and migration behavior
- Frontend behavior

The full test suite was not executed in this read-only analysis: **NOT VERIFIED**.

## 11. Production Readiness

### Present

- PostgreSQL configuration
- Environment-driven production settings
- Docker configuration
- Deployment files
- WhiteNoise static-file support
- Optional Cloudinary media storage
- CSRF middleware
- Password validation
- Migration files
- Console logging

### Risks and gaps

- Render configuration does not clearly provide persistent media storage.
- Docker and deployment scripts run migrations in multiple phases, which can be unsafe with multiple replicas.
- Production Compose exposes the application publicly rather than clearly restricting it behind the intended reverse proxy.
- Development credentials exist in local Compose configuration and must not be reused.
- Logging lacks structured audit events, request IDs, retention, and centralized error reporting.
- Background work uses daemon threads in [management_system/management_system/async_tasks.py](management_system/management_system/async_tasks.py); jobs can be lost on restart.
- Static-file configuration references a root `static/` directory that was not present in the inspected workspace.
- Uploaded files are mainly extension-checked; content validation, size limits, malware scanning, and download isolation were not verified.
- Database and media backup strategy: **NOT VERIFIED**.
- HTTPS and reverse-proxy enforcement: **NOT VERIFIED from application code**.

## 12. Code Quality

### Good design choices

- Django apps are separated by business domain.
- The custom email-based user model is established early.
- Role constants are centralized.
- Most tenant-owned models explicitly identify their company.
- Project progress behavior is encapsulated in model methods.
- Finance posting services use atomic operations and locking in important paths.
- Forms often restrict company-owned foreign-key choices.
- Marketplace finance posting attempts idempotency and reversal.

### Technical debt

- Finance views and models have drifted out of sync.
- Marketplace admin contains duplicate function definitions.
- Notification types are not centrally consistent.
- Tenant isolation is repeated manually across views.
- Business logic is divided among models, views, forms, and services without a consistently defined service boundary.
- Inventory imports bypass normal history.
- Background jobs are not durable.
- Several views appear to contain runtime defects.
- The React prototype is disconnected and may create false expectations about product completeness.

## 13. Feature Maturity Matrix

| Feature | Classification |
|---|---|
| Company registration | IMPLEMENTED |
| Email authentication | IMPLEMENTED |
| Invitations | IMPLEMENTED |
| Role-based access | IMPLEMENTED |
| Tenant isolation | PARTIALLY IMPLEMENTED |
| Dashboard | IMPLEMENTED shell |
| Employees | IMPLEMENTED |
| Departments | IMPLEMENTED |
| Positions | IMPLEMENTED |
| Leave | IMPLEMENTED |
| Payroll | PARTIALLY IMPLEMENTED |
| Attendance | MISSING or NOT VERIFIED |
| Performance reviews | IMPLEMENTED |
| Training and skills | IMPLEMENTED |
| Finance accounts | IMPLEMENTED |
| Basic transactions | IMPLEMENTED |
| Chart of accounts | IMPLEMENTED |
| Double-entry journals | IMPLEMENTED structurally |
| Client invoices | PARTIALLY IMPLEMENTED / BROKEN |
| Supplier invoices | PARTIALLY IMPLEMENTED / BROKEN |
| Bank reconciliation | PARTIALLY IMPLEMENTED / BROKEN |
| Financial reports | PARTIALLY IMPLEMENTED / BROKEN |
| Stock master data | IMPLEMENTED |
| Stock movements | IMPLEMENTED with validation weaknesses |
| Stock history | IMPLEMENTED |
| Reorder levels | IMPLEMENTED |
| Warehouses | MISSING |
| Stock transfers | MISSING |
| Procurement | MISSING |
| Projects | IMPLEMENTED |
| Tasks | IMPLEMENTED |
| Milestones | NOT VERIFIED |
| Project approvals | NOT VERIFIED |
| CRM contacts | IMPLEMENTED |
| CRM opportunities | IMPLEMENTED |
| Quotations | MISSING |
| Sales orders | MISSING |
| Marketplace cart | IMPLEMENTED |
| Marketplace checkout | PARTIALLY IMPLEMENTED |
| Marketplace payments | PARTIALLY IMPLEMENTED |
| Meetings | IMPLEMENTED |
| Notifications | IMPLEMENTED but inconsistent |
| REST API | MISSING |
| React operational frontend | MISSING |
| React demo frontend | PROTOTYPE/DEMO |
| Durable background jobs | MISSING or NOT VERIFIED |

## 14. Final Evaluation

This system is a substantial Django ERP prototype, not merely a collection of empty app folders. Several real business workflows work end to end, and the multi-company foundation is credible.

It is not yet suitable to be treated as a serious enterprise ERP because finance has broken sections, procurement is absent, inventory lacks warehouse functionality, payment handling is insufficiently bound to orders, concurrency controls are incomplete, and test coverage does not match the security and financial risk.

Before production use, the highest-priority work is:

1. Run the complete Django test suite and fix runtime failures.
2. Repair all finance model/view mismatches.
3. Add systematic cross-company authorization tests.
4. Lock stock rows during checkout and cancellation.
5. Reject zero and negative quantities at every input/service boundary.
6. Bind payment callbacks to order, client, amount, and currency.
7. Encrypt or remove plaintext SMTP passwords.
8. Validate all login and language redirects.
9. Decide whether the React prototype will be removed or connected to a real API.
10. Add procurement if purchasing is a required ERP capability.
11. Establish durable background jobs, audit logging, persistent media, and verified backups.
12. Add production monitoring and deployment checks.

Overall classification: **FUNCTIONAL ERP PROTOTYPE / PARTIALLY PRODUCTION-READY FOUNDATION**.
