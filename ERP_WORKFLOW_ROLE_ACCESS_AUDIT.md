# ERP Workflow, Role-Based Access and Dashboard Compliance Audit

**System audited:** ERP MAIN Django application in this workspace  
**Audit date:** 2026-09-20  
**Audit scope:** Organisation tenancy, user and employee management, roles, capabilities, dashboards, navigation, approval authority, department workflows, notifications, auditability, and tests.

## Implementation Update: 2026-09-20

The first critical-security remediation slice has been implemented without schema changes or destructive data operations.

### Implemented

- Approval submission now requires an authenticated requester with a company.
- Approval targets must be saved and must belong to the requester's company.
- Approval decisions revalidate target ownership before changing the business object.
- `latest_approval_for()` supports a company-scoped lookup.
- Notification recipients must be active tenant users with a company.
- Notification related objects must belong to the recipient's company.
- Existing notification preferences are now applied during notification creation, including approval notifications through the system-alert preference.
- Optional approval steps are skipped only when no eligible approver matches; required steps still block safely.
- The My Work queue evaluates approval eligibility using the target's actual transaction amount.
- Regression tests cover cross-company approval targets, scoped approval lookup, notification preference suppression, same-company notifications, cross-company related objects, and optional approval steps.

### Validation after remediation

```text
python manage.py check
System check completed with one pre-existing staticfiles warning.

python manage.py test --verbosity 0
Ran 45 tests in 122.642s
OK
```

No migration was required. Existing data and database schema were preserved.

## Implementation Update: Authorization and Dashboard Phase

The next remediation slice is also implemented without schema changes:

- Sensitive legacy role groups now consult matching effective capabilities, so a revoked capability blocks direct URL access even when the user still has the legacy role.
- Employee, department, project, inventory, finance, HR, CRM, and reporting-sensitive role groups covered by the compatibility map now honor capability overrides.
- Project and inventory dashboard statistics, recent records, links, and low-stock alerts are only loaded for users with the corresponding effective capability.
- A direct-URL regression test proves that an `admin` user with revoked `finance.manage` cannot access Finance.

Validation after this phase:

```text
python manage.py test --verbosity 0
Ran 46 tests in 126.995s
OK
```

This phase improves capability enforcement and dashboard least privilege, but does not yet make branch scope, all department workflows, or every requested dashboard fully implemented.

## Implementation Update: Employee Identity and Optional Login

The employee/user relationship has now been corrected so an employee identity does not depend on a system login.

- `Employee.first_name` and `Employee.last_name` store the employee's real name.
- Both name fields are required by `EmployeeForm` in every creation mode.
- `Employee.user` is now optional and uses `SET_NULL` when a login is removed.
- Unchecked **Create user login** creates a named employee with no User record and no generated email or password.
- Checked **Create user login** creates the User account and links it to the named employee.
- Existing employee names are copied from linked users by migration `employees.0007_employee_names_optional_user`.
- Employee list, detail, delete, dashboard, and HR leave approval paths handle employees without logins safely.

Validation:

```text
python manage.py check
Completed with the existing missing static-directory warning.

python manage.py test --verbosity 0
Ran 47 tests in 154.971s
OK
```

This is a safe schema change: existing employee records are preserved and their names are backfilled before the linked user is made optional.

## Implementation Update: Separate Employee and User Workflows

Employee management and user-account management are now separate workflows while remaining connected through an explicit one-to-one link.

### Employee workflow

- HR enters the employee's first name and last name directly in Employee Information.
- Names are required whether or not a login is requested.
- Employee-only creation stores a real employee record with no generated email, password, or placeholder user.
- `Employee.user` is nullable, so employment records do not depend on ERP access.

### User workflow

- Administration -> Users -> Add User has an optional **Link existing employee** field.
- The selector is limited to unlinked employees in the administrator's company.
- Cross-company employee IDs are rejected by form validation.
- Linking updates the existing employee and never creates a duplicate employee record.
- A user may be created without an employee for the approved external-account policy, such as an auditor or consultant.
- The dedicated user form bypasses the legacy auto-profile signal so this workflow does not create an unwanted employee.
- User creation and employee linking are recorded as audit events.

### Validation

```text
python manage.py test governance employees --verbosity 1
Ran 13 tests
OK

python manage.py test --verbosity 0
Ran 50 tests
OK
```

The only remaining warnings are the existing missing static-directory warnings. No additional schema migration was required for explicit linking; the previously applied `employees.0007_employee_names_optional_user` migration remains the safe relationship migration.

## A. Executive Summary

### Overall conclusion

The system has a real multi-company foundation and a reusable approval engine, but it does **not yet satisfy the intended end-to-end architecture**:

```text
Organisation -> User -> Role -> Capabilities -> Screen/action access
             -> Data scope -> Approval authority -> Dashboard
             -> Department workflow -> Notifications -> Audit trail
```

The current implementation is best classified as **PARTIALLY IMPLEMENTED**.

### Working controls

- `accounts.Company` is the tenant root.
- Users, employees, departments, finance records, inventory records, projects, procurement records, and most top-level views carry company ownership.
- The governance module has reusable `ApprovalWorkflow`, `ApprovalStep`, `ApprovalRequest`, `ApprovalDecision`, and `AuditEvent` models.
- Approval routing supports role, capability, department, amount range, approval limit, sequential steps, rejection, return, self-approval prevention, notifications, and audit events.
- Most high-level views scope querysets to `request.user.company`.
- The employee onboarding flow now allows HR to create an employee without entering login credentials; a login is optional.
- The focused employee test suite currently passes.

### Major gaps and risks

1. **Mixed authorization model:** many modules use role-name decorators while governance/procurement use capabilities. A capability override or revocation is therefore not a consistent system-wide access control.
2. **No branch/location model:** branch-level scope, branch assignment, branch approvals, and branch filtering are missing.
3. **User and employee structures diverge:** `User.department` and `User.position` are free text, while `Employee.department` and `Employee.position` are foreign keys. User-to-employee and role synchronization are application-form behavior, not a database invariant.
4. **Approval target validation is incomplete:** `submit_for_approval()` trusts the requester company and does not independently verify that the target belongs to that same company.
5. **Approval semantics are incomplete:** `ApprovalStep.required` exists but is not used by the decision engine; the work queue checks step eligibility with `amount=None`, so amount-dependent eligibility can be inaccurate.
6. **Notification tenancy and preferences are caller-dependent:** notifications have no company field, and `create_notification()` does not call `should_send_notification()`.
7. **Dashboards are not fully personalized:** the main dashboard is role-labelled and company-filtered, but inventory and project statistics are exposed to every authenticated role regardless of effective capability, and it is not a complete assigned-work dashboard.
8. **Test coverage does not prove isolation:** cross-company access, direct URL denial, notification tenant safety, branch scope, approval edge cases, and legacy role-protected modules are not comprehensively tested.
9. **AREN cannot be audited from this workspace:** no separate AREN source, models, migrations, services, permissions, frontend, or tests are present.

## B. Organisation and User Management

### Evidence

- `accounts.Company` is the organisation/tenant model in `management_system/accounts/models.py`.
- `accounts.User.company` is a nullable foreign key to `Company`.
- `employees.Employee.company`, `employees.Department.company`, and most business records use company foreign keys.
- `User` has a free-text `department` and `position`; `Employee.department` is a foreign key and `Employee.position` is a foreign key.
- `Employee.user` is a required one-to-one relationship. The employee form creates an inactive placeholder user when HR does not request a login.
- Governance user management scopes list/edit/toggle/capability pages by `company=request.user.company`.
- `is_company_admin` is a boolean flag, but governance user management is protected by `admin.manage_users`, not exclusively by that flag.

### Compliance classification

| Requirement | Classification | Finding |
|---|---|---|
| Organisation/company tenant | **FULLY IMPLEMENTED at the top-level model** | Company exists and is used widely as a foreign key. |
| Admin manages own-company users | **PARTIALLY IMPLEMENTED** | Governance views filter users by company and capability checks protect the views. The user role/capability model is not unified. |
| Cross-company user management prevention | **PARTIALLY IMPLEMENTED** | The governance views use company filters, which is good. Global email uniqueness and nullable company users complicate tenant assumptions. Broad cross-tenant regression tests are missing. |
| User linked to employee | **PARTIALLY IMPLEMENTED** | One-to-one link exists, but it is required and can cause placeholder accounts for employee-only records. Signal/form behavior creates and reuses profiles. |
| User assigned to department | **MODEL/SCAFFOLD ONLY** | User department is free text; there is no user-to-Department foreign key or enforced alignment with Employee.department. |
| User assigned to branch/location | **MISSING** | No Branch/Location model or user assignment was found. Some modules contain location-like text, but no common scope exists. |
| One or more roles | **PARTIALLY IMPLEMENTED** | User has one string role. There is no many-to-many role assignment. |
| Roles assigned capabilities | **PARTIALLY IMPLEMENTED** | `RoleCapability` and `ROLE_DEFAULT_CAPABILITIES` exist, but enforcement is mixed with legacy role lists. |
| Per-user capability overrides | **PARTIALLY IMPLEMENTED** | `UserCapability` and effective capability calculation exist. It is not the sole authorization path across the ERP. |
| Per-user or role approval limits | **PARTIALLY IMPLEMENTED** | `ApprovalStep.approval_limit` exists; there is no separate user approval-limit model and routing is not consistently connected to every transaction. |
| Organisation/branch/department data scope | **PARTIALLY IMPLEMENTED** | Company scope is common. Branch scope is absent and department scope is not a general queryset policy. |
| Audit of access changes | **PARTIALLY IMPLEMENTED** | Governance user and capability changes create `AuditEvent`; coverage of all access mutation paths is not proven. |

### Security concerns

- A nullable `User.company` permits users without a tenant. This is needed for some platform/system flows but must be tightly controlled.
- Email is globally unique, so tenant isolation is not the only identity rule; this is a business constraint rather than a data-scope implementation.
- The relationship between User role, Employee role, Employee department, and User department can drift when records are changed outside the employee form.
- There is no branch boundary at the model or queryset layer.

## C. Roles and Capabilities

### Roles actually present

The custom user role choices in `accounts.User` are:

- `admin`
- `hr_manager`
- `accountant`
- `manager`
- `secretary`
- `stock_manager`
- `employee`

The governance defaults also define capability sets for those roles. The requested roles **Finance Manager, Procurement Officer, Sales/CRM Officer, Project Manager, Fleet/Maintenance Officer, and Auditor/Viewer** are not all represented as independent configurable user roles. Some can be approximated by capabilities or employee job roles, but that is not equivalent to a working role implementation.

### Enforcement findings

`accounts/permissions.py` defines many role tuples such as `FINANCE_ROLES`, `HR_ROLES`, and `INVENTORY_MANAGE_ROLES`. `role_required()` checks only `request.user.role`.

`governance/decorators.py` defines `capability_required()`, which uses `governance.models.has_capability()` and effective overrides. These are both active patterns.

Therefore:

- Governance and some procurement paths use capabilities.
- Existing HR, finance, inventory, CRM, projects, meetings, and other paths commonly use role-name lists.
- A user with a denied capability may still pass a legacy role-based decorator.
- A new capability grant may not make a role-based module accessible.

### Compliance classification

| Requirement | Classification | Finding |
|---|---|---|
| Super Administrator | **FULLY IMPLEMENTED** | Django superuser bypass is present, including platform dashboard access. This is a platform-level role, not an ordinary company role. |
| Organisation Administrator | **PARTIALLY IMPLEMENTED** | `admin` and `is_company_admin` exist, but the distinction between organisation administration and broad role capabilities is not consistently enforced. |
| Manager | **PARTIALLY IMPLEMENTED** | Role exists and is used in approval steps and legacy authorization. No complete team/department/branch data scope is enforced. |
| Accountant | **PARTIALLY IMPLEMENTED** | Role and finance capability defaults exist; finance access still includes legacy role enforcement and lacks full finance workflow verification. |
| Finance Manager | **MISSING as a distinct role** | No independent role with separately tested approval authority was found. |
| HR Manager | **PARTIALLY IMPLEMENTED** | Role and HR defaults exist, but dashboard/workflow coverage is not complete. |
| Procurement Officer | **MISSING as a distinct role** | Procurement uses capabilities and roles but no dedicated user role was found. |
| Warehouse/Store Manager | **PARTIALLY IMPLEMENTED** | `stock_manager` exists; branch/warehouse scope and complete workflow enforcement are incomplete. |
| Sales/CRM Officer | **PARTIALLY IMPLEMENTED** | `secretary`/`manager` role lists are used; no dedicated role and no complete sales workflow proof. |
| Project Manager | **PARTIALLY IMPLEMENTED** | Employee job role mapping exists, but access is not a distinct, end-to-end authorization role. |
| Fleet/Maintenance Officer | **MISSING** | No equivalent role/workflow was found. |
| Employee | **PARTIALLY IMPLEMENTED** | Self-service role exists, but dashboard and record scope are broader than the requested personal-workspace design. |
| Auditor/Viewer | **MISSING** | No read-only auditor role with tested data scope was found. |
| Custom role configuration | **PARTIALLY IMPLEMENTED** | Role capabilities can be configured per company, but the interface and enforcement do not replace legacy role lists. |
| Effective permission display | **BACKEND ONLY / PARTIALLY IMPLEMENTED** | Governance has an effective capability view for a managed user; full role, data scope, and approval authority are not represented together. |

## D. Personalized Dashboards

### Current implementation

`core/views.py:dashboard` is login-protected and company-scopes employee, project, stock, finance, and online-user queries. It changes a label and several stat flags based on the user role.

The dashboard currently provides:

- Company employee totals for selected roles.
- Company project totals for authenticated users.
- Company inventory totals and low-stock items for authenticated users.
- Finance totals for admin, accountant, manager, and superuser roles.
- Online users within the company.
- Role labels such as HR, Finance, Inventory, Team Operations, and My Workspace.

This is real database data, not only hard-coded statistics. However, it is not a complete role-specific dashboard architecture.

### Gaps by requested dashboard

| Dashboard | Classification | Finding |
|---|---|---|
| Employee | **PARTIALLY IMPLEMENTED** | Role label and company dashboard exist. Personal tasks, personal documents, assigned projects, payslips, and personal requests are not presented as a complete employee work area. |
| Manager | **PARTIALLY IMPLEMENTED** | Pending approvals are available through My Work, but team members, department activity, assigned tasks, and project progress are not integrated into a manager-specific data scope. |
| Accountant | **PARTIALLY IMPLEMENTED** | Finance aggregates exist, but complete invoices, receivables, payables, journals, reports, and action queues are not proven as one dashboard. |
| Finance Manager | **MISSING** | No distinct dashboard or finance-manager role was found. |
| HR Manager | **PARTIALLY IMPLEMENTED** | Employee and HR stat blocks exist, but attendance, leave, payroll, training, performance, and HR notifications are not unified in the dashboard. |
| Procurement Officer | **MISSING / PARTIALLY IMPLEMENTED** | Procurement screens and approval paths exist, but no dedicated dashboard was verified. |
| Warehouse Manager | **PARTIALLY IMPLEMENTED** | Inventory totals and low-stock data exist; receipts, transfers, adjustments, and assigned inventory work are not unified. |
| Sales/CRM Officer | **MISSING** | No dedicated sales dashboard was verified. |
| Project Manager | **MISSING** | Project screens exist but no dedicated project-manager dashboard was verified. |
| Organisation Administrator | **PARTIALLY IMPLEMENTED** | Platform and company administration screens exist, but organisation administration is not consolidated into a capability-filtered dashboard. |

### Data exposure finding

The dashboard always computes project and inventory statistics for every authenticated company user, regardless of effective capability. Company filtering reduces cross-tenant exposure, but it does not satisfy least-privilege access. The dashboard also does not filter by branch, department, manager team, or assigned work.

Root React files such as `erpis-screens.jsx` and `erpis-ui.jsx` are not evidence of the operational Django dashboard; they contain a separate frontend/prototype surface and should not be treated as the backend dashboard implementation.

## E. Dynamic Navigation and Screen Access

### Navigation

`templates/base.html` is the operational shell. It uses template role/capability tags to hide or show navigation sections. This is useful for presentation but is not sufficient security.

### Backend access

There are two authorization families:

- `role_required()` in `accounts/permissions.py` checks role names.
- `capability_required()` in `governance/decorators.py` checks effective capabilities.

Some sensitive governance screens are capability-protected, while many module screens continue to use role lists. This means hidden navigation cannot be relied upon to represent the actual authorization policy.

### Compliance classification

| Requirement | Classification | Finding |
|---|---|---|
| Unauthorized navigation hidden | **PARTIALLY IMPLEMENTED** | Template gating exists, but it is based on mixed role/capability rules. |
| Direct URL protection | **PARTIALLY IMPLEMENTED** | Decorators protect many views, but complete endpoint coverage has not been demonstrated. |
| API authorization | **MISSING/UNVERIFIED** | No comprehensive API authorization layer or endpoint test matrix was found in this audit. |
| Backend action authorization | **PARTIALLY IMPLEMENTED** | Procurement/governance have stronger checks; legacy role-based modules are inconsistent. |
| Navigation updates after permission change | **PARTIALLY IMPLEMENTED** | Server-rendered templates should reflect current permissions, but effective capability changes do not supersede role-only checks. |
| Empty sections handled | **PARTIALLY IMPLEMENTED** | Some sections are conditionally rendered; no global authorization-aware navigation registry was found. |

## F. Approval Workflows

### Reusable approval engine

The governance engine contains:

- `ApprovalWorkflow`: company, transaction type, enabled flag, amount range, self-approval option.
- `ApprovalStep`: sequence, role, capability, department, amount range, approval limit, required flag.
- `ApprovalRequest`: requester, target content type/object ID, status, current step, timestamps.
- `ApprovalDecision`: actor, step, decision, reason, timestamp.
- `AuditEvent`: append-only action history.

`governance/services.py` provides `submit_for_approval()`, `decide_approval()`, and `latest_approval_for()`.

### Working behavior

- Sequential next-step progression works for the next sequence number.
- Role, capability, department, minimum/maximum amount, and approval limit matching exist in `ApprovalStep.matches()`.
- Self-approval is blocked when the workflow disallows it.
- Rejection and return require a reason.
- Approval-required notifications are sent to eligible users.
- Rejected/returned requests notify the requester.
- Target objects with `apply_approval_decision()` can update their business status.
- Approval decisions create audit events.

### Defects and incomplete semantics

1. `ApprovalStep.required` is stored but `decide_approval()` always advances to the next sequence or completes the request. Optional steps are therefore not semantically implemented.
2. `my_work()` tests the current step with `amount=None`, so amount-based approval eligibility can disagree with the decision-time check.
3. `submit_for_approval()` derives the company from `requester.company` but does not verify that `target.company_id` matches it. A caller can potentially submit a cross-company target if it can reach the service with mismatched objects.
4. `latest_approval_for()` filters by content type and object ID but not company. It should include the company boundary wherever the caller can receive a target from an untrusted identifier.
5. No delegation, expiry, escalation, parallel approval, resubmission state transition, or approval proxy model was found.
6. Employee onboarding creates a workflow/manager step automatically when absent, but if no active manager exists it leaves the employee inactive without creating an approval request. This is safer than activating the employee, but it is an operational configuration gap that should be surfaced to HR.

### Workflow classification

| Workflow | Classification | Finding |
|---|---|---|
| Employee onboarding | **PARTIALLY IMPLEMENTED** | Employee creation can submit a manager approval and update status; no-approver configuration is not fully handled in the UI. |
| Procurement requisition | **PARTIALLY IMPLEMENTED** | Submit/return/approve behavior and generic approval integration exist; complete requisition-to-payment chain is not proven. |
| Purchase order approval | **PARTIALLY IMPLEMENTED** | Model and view checks exist, but end-to-end multi-step policy and notification coverage are incomplete. |
| Goods receipt | **PARTIALLY IMPLEMENTED** | Approved-PO prerequisite, quantity checks, inventory update, and audit event exist; company ownership is inherited through order rather than directly stored. |
| Leave approval | **PARTIALLY IMPLEMENTED** | Leave approval views/models exist; the requested Employee -> Manager -> HR chain is not proven as a reusable multi-department route. |
| Payroll | **MODEL/SCAFFOLD or PARTIALLY IMPLEMENTED** | HR payroll models/views exist, but the requested HR -> Finance -> payment -> ledger approval chain was not proven end to end. |
| Journal approval | **PARTIALLY IMPLEMENTED** | Finance models and capability names exist, but complete draft -> review -> post approval behavior needs dedicated verification. |
| Sales workflow | **PARTIALLY IMPLEMENTED** | CRM and marketplace modules exist, but the full lead -> customer -> opportunity -> quotation -> delivery -> invoice -> payment chain is not proven as one enforced workflow. |
| Project workflow | **PARTIALLY IMPLEMENTED** | Projects/tasks exist, but approval and department handoff semantics are not unified through governance. |

## G. Department Communication

The system communicates primarily through workflow state, in-app notifications, and audit events rather than user chat.

### Notifications

`notifications.Notification` stores recipient, type, title, message, read/archive state, timestamps, and an optional generic related object reference.

`governance.services.submit_for_approval()` sends `approval_required` notifications to eligible approvers. `decide_approval()` sends `approval_decision` notifications to the requester for rejected/returned requests and sends next-step notifications when a next step exists.

### Notification gaps

- `Notification` has no company foreign key.
- `create_notification()` accepts any user and related object without validating their company relationship.
- `should_send_notification()` exists, but `create_notification()` does not call it, so preferences do not control creation.
- Approval notification types are not mapped to preference fields and default to being sent.
- Notification tests are insufficient to prove recipient correctness, tenant isolation, or preferences.
- The My Work page combines actionable approvals and unread notifications, but it is not a complete task, returned-work, meeting, or cross-module work queue.

### Department workflow status

| Communication path | Classification | Finding |
|---|---|---|
| Procurement -> approver | **PARTIALLY IMPLEMENTED** | Generic approval notification and audit path exist. Full requisition, PO, receipt, invoice, payment, and ledger handoff is not complete. |
| Sales -> finance/inventory | **PARTIALLY IMPLEMENTED** | Modules exist, but the full connected chain and notifications are not proven. |
| Employee -> manager/HR leave | **PARTIALLY IMPLEMENTED** | Leave features exist; required manager-to-HR routing is not established as a generic enforced path. |
| HR -> finance payroll | **PARTIALLY IMPLEMENTED** | Payroll structures exist; multi-party approval and payment notification chain is not proven. |
| Accountant -> journal approver | **PARTIALLY IMPLEMENTED** | Finance permissions and approval-related capabilities exist; complete posting workflow needs dedicated tests. |
| Cross-department My Work | **PARTIALLY IMPLEMENTED** | Approval queue exists; a unified tasks/requests/returned-work/meetings queue does not. |

## H. Security and Tenant Isolation

### Positive controls

- Many parent querysets explicitly filter by `request.user.company`.
- Governance user, workflow, approval, and audit views generally include company filters.
- Procurement services lock orders and constrain stock queries by the order company.
- Platform dashboard is explicitly superuser-only.
- Generic approval decision checks `approval.company_id == actor.company_id`.

### Weak boundaries

- There is no branch/location scope model.
- Child records do not consistently carry or validate company ownership at database level.
- `PurchaseRequisitionLine.stock` and `PurchaseOrderLine.stock` need consistent `clean()`/service validation; the shown model validation is not a universal database constraint.
- `GoodsReceipt` has no company field and relies on its order relationship.
- Employee user/company and department/company alignment are not database constraints.
- Notifications have no company field.
- Generic content-type/object references require careful company validation at every service/view boundary.
- Export endpoints and legacy module views need a systematic cross-company test matrix.

### Classification

**PARTIALLY IMPLEMENTED, with HIGH security priority.** Company filtering is a useful baseline, but it is not equivalent to complete object-level authorization and data scope.

## I. Test Evidence

### Fresh evidence

The focused employee suite was run after the onboarding changes:

```text
python manage.py test employees --verbosity 1
Ran 2 tests in 16.869s
OK
```

The suite emits only the existing warning that the configured static directory does not exist.

The two passing employee tests cover:

- User-account creation without duplicating the employee profile.
- Employee creation resulting in a manager approval request when a manager exists.

### Existing test coverage observed

- Employee onboarding tests exist.
- Governance capability and approval tests exist in part.
- Procurement receipt behavior has tests.
- HR attendance has dedicated tests.
- Dashboard branding has some test coverage.

### Missing or insufficient test evidence

No adequate proof was found for:

- Cross-company direct URL access for every module.
- Cross-company API access and exports.
- Branch/location scope.
- Department/team scope.
- Revoked capability denial across all legacy role-protected modules.
- Notification recipient tenant validation.
- Notification preferences affecting actual notification creation.
- Optional approval steps.
- Approval target-company mismatch rejection.
- Amount-dependent work queue correctness.
- Delegation, expiry, escalation, parallel approvals, and resubmission.
- Full procurement, sales, payroll, and journal chains.
- All requested role-specific dashboards.

## J. Prioritized Remediation Plan

### Critical

1. Add target-company validation to `submit_for_approval()` and company-scoped lookup to `latest_approval_for()`.
2. Build a cross-tenant authorization test suite for direct URLs, actions, exports, generic object references, approvals, notifications, and child records.
3. Decide on one authorization source of truth. Migrate role-only decorators to capability checks or explicitly define a compatibility policy and test it.
4. Add company validation to notification creation and related-object handling.
5. Prevent company administrators from mutating users or capabilities outside their company through every code path, not only current views.

### High

1. Add a Branch/Location model and explicit assignments for users, employees, departments, warehouses, and relevant transactions.
2. Implement data-scope policy helpers for company, branch, department, team, ownership, and finance/HR confidentiality.
3. Fix approval semantics: honor `required`, pass transaction amount in work-queue eligibility, validate target ownership, and define behavior when no eligible approver exists.
4. Add dedicated roles or capability bundles for finance manager, procurement officer, CRM officer, project manager, auditor/viewer, and fleet/maintenance.
5. Complete backend authorization for all module screens and action endpoints.
6. Add approval tests for amount limits, department/capability routing, multi-level progression, self-approval, rejection reasons, return, resubmission, and target-company mismatch.

### Medium

1. Replace the role-labelled dashboard with capability- and scope-aware dashboard sections.
2. Build the requested My Work sections: tasks, approvals, returned work, requests awaiting action, and meetings.
3. Make notification preferences effective at notification creation and add approval preference mappings.
4. Add unified notification links for approval requests and related transactions.
5. Add end-to-end tests for procurement, leave, payroll, journals, sales, projects, and inventory handoffs.
6. Make employee/user department and position relationships consistent and enforceable.

### Low

1. Remove or clearly separate disconnected prototype frontend screens from the operational dashboard documentation.
2. Add the missing static directory or correct `STATICFILES_DIRS` configuration.
3. Improve dashboard empty states and role-specific presentation after backend scope is correct.
4. Document that AREN was not available in this workspace and perform a separate parity audit when its source is provided.

## Final Classification Summary

| Domain | Classification |
|---|---|
| Organisation tenancy | **PARTIALLY IMPLEMENTED** |
| User and employee management | **PARTIALLY IMPLEMENTED** |
| Role model | **PARTIALLY IMPLEMENTED** |
| Capability model | **PARTIALLY IMPLEMENTED** |
| Capability enforcement | **PARTIALLY IMPLEMENTED** |
| Branch/location scope | **MISSING** |
| Personalized dashboards | **PARTIALLY IMPLEMENTED** |
| Dynamic navigation | **PARTIALLY IMPLEMENTED** |
| Direct URL/backend protection | **PARTIALLY IMPLEMENTED** |
| Reusable approval engine | **PARTIALLY IMPLEMENTED** |
| Approval self-approval prevention | **FULLY IMPLEMENTED in generic engine, subject to caller routing** |
| Approval limits | **PARTIALLY IMPLEMENTED** |
| Approval delegation/expiry/escalation | **MISSING** |
| Notifications | **PARTIALLY IMPLEMENTED** |
| My Work | **PARTIALLY IMPLEMENTED** |
| Department workflows | **PARTIALLY IMPLEMENTED** |
| Tenant isolation | **PARTIALLY IMPLEMENTED; HIGH RISK** |
| Audit trail | **PARTIALLY IMPLEMENTED** |
| AREN parity audit | **MISSING/UNAVAILABLE in workspace** |

**Audit conclusion:** retain the existing Company, User, Employee, Governance, Notification, and AuditEvent foundations. Do not create duplicate user, role, permission, approval, or notification systems. The next implementation phase should consolidate authorization and data scope around the existing capability and governance infrastructure, then prove it with cross-tenant and workflow tests before expanding dashboards or visual features.
