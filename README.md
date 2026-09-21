ERP System
Multi-Tenant Company Management Platform
Django 6.0  ·  Bootstrap 5  ·  Python 3.12


Overview
This ERP system is a Django-based multi-tenant platform that lets multiple independent companies (tenants) share a single deployment while keeping their data fully isolated. Each company has its own employees, projects, inventory, finances, and CRM records.
The system ships with nine Django apps, role-based access control, a Bootstrap 5 UI, and is production-ready via Docker or Railway.

Apps
App	Purpose	Key models
accounts	Multi-tenancy & authentication	Company, User
core	Dashboard & shared views	—
employees	Staff directory & departments	Employee, Department
hr	Positions & leave workflow	Position, LeaveRequest
finance	Accounts & transactions	Account, Transaction
projects	Projects & subtasks	Project, SousTache, CommentaireTache
inventory	Stock management	Item, StockMovement
crm	Customer relations	Customer, Interaction
marketplace	Multi-vendor storefront	Vendor, Product, Order

Getting Started
Prerequisites
•Python 3.12+
•pip
•Git

Local setup
1.Clone the repository
git clone https://github.com/J-Lok/ERP.git
cd ERP/management_system
2.Create and activate a virtual environment
python -m venv env
source env/bin/activate      # Windows: env\Scripts\activate
3.Install dependencies
pip install -r ../requirements.txt
4.Apply migrations
python manage.py migrate
5.Create a superuser
python manage.py createsuperuser
6.Start the development server
python manage.py runserver
The app is now available at http://127.0.0.1:8000

Docker
docker build -t erp .
docker run -p 8000:8000 erp

Railway deployment
This repository includes `railway.json` and a production Dockerfile. Railway will build
the Docker image and use the configured Gunicorn command automatically.

1. Create a Railway project from this GitHub repository.
2. Add a PostgreSQL service in the same project.
3. In the web service Variables, add:
    - `SECRET_KEY`: a long random secret generated outside the repository
    - `DEBUG`: `False`
    - `DJANGO_SETTINGS_MODULE`: `management_system.settings`
    - `ALLOWED_HOSTS`: your Railway hostname, for example `your-service.up.railway.app`
    - `CSRF_TRUSTED_ORIGINS`: `https://your-service.up.railway.app`
    - `DATABASE_URL`: `${{Postgres.DATABASE_URL}}` (use the exact PostgreSQL service name)
    - `SECURE_SSL_REDIRECT`: `True`
    - `SECURE_HSTS_SECONDS`: `31536000`
    - `DEFAULT_FROM_EMAIL`: your verified sender address
4. For email, configure either `RESEND_API_KEY` or SMTP variables:
    `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`.
5. Deploy. The container runs migrations before Gunicorn starts.
6. Create the first administrator from the Railway shell:
    `python management_system/manage.py createsuperuser`
7. Confirm `https://your-service.up.railway.app/health/` returns `{"status":"ok"}`.

Railway notes:
- Railway injects the public `PORT`; do not hard-code it in service variables.
- Uploaded media requires Cloudinary variables (`CLOUDINARY_CLOUD_NAME`,
  `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`) because Railway volumes are not
  a substitute for durable media storage.
- Use Railway PostgreSQL in production; do not deploy the local SQLite database.
- Keep `SECRET_KEY`, database URLs, API keys, and email passwords out of Git.

Architecture
Multi-tenancy
Every data model includes a company foreign key. Tenant isolation is enforced at the view layer — every queryset is filtered to request.user.company. The CompanyContextMiddleware attaches the current company to every request object for convenience.
New users self-register by supplying a company domain and the shared company password. The first user created for a company is automatically assigned the admin role.

Authentication
•Email is the login identifier (username field is removed).
•Custom AbstractUser in the accounts app (AUTH_USER_MODEL = "accounts.User").
•Company-scoped registration with a shared company password.

Role-Based Access Control
All access logic lives in accounts/permissions.py — the single source of truth for role constants and the role_required decorator.
Roles
Role	Description
admin	Full access to all company data and settings
hr_manager	Manage employees, positions, and leave requests
accountant	Read and write financial accounts and transactions
manager	Manage projects, view employees and inventory
secretary	CRM access, leave submission, project viewing
stock_manager	Write access to inventory and stock movements
employee	Self-service only — submit leave, view projects

Permission matrix
Feature / App	Admin	HR Mgr	Accountant	Manager	Secretary	Stock Mgr	Employee
Employees — view	✓	✓	✓	✓	✓	✓	✓
Employees — create / edit	✓	✓					
Employees — delete	✓						
HR — positions & leave	✓	✓					
Leave — submit	✓	✓	✓	✓	✓	✓	✓
Finance	✓		✓	✓			
Projects — view	✓	✓	✓	✓	✓	✓	✓
Projects — create / edit	✓	✓		✓			
Inventory — view	✓	✓	✓	✓	✓	✓	✓
Inventory — write	✓					✓	
CRM	✓			✓	✓		
Marketplace admin	✓						

Usage in views
Decorate any view function with role_required, passing one or more role constants:
from accounts.permissions import role_required, EMPLOYEE_WRITE_ROLES

@role_required(*EMPLOYEE_WRITE_ROLES)
def employee_create(request):
    ...
Superusers bypass all role checks. Unauthorised requests are redirected to the dashboard with an error message.

Employee role → user access level sync
When an employee's job title (Employee.role) is saved, the linked User.role is automatically updated so that permissions take effect immediately on the next request. The mapping is:
Employee job title	User access role
manager, project_manager	manager
hr	hr_manager
accountant	accountant
secretary	secretary
stock_manager	stock_manager
developer, designer, analyst, engineer, intern, other	employee
Job titles with no special access (developer, designer, analyst, engineer, intern, other) map to the employee role.

App Reference
accounts
•Company: UUID-keyed tenant. Subscription plans: free, basic, premium, enterprise.
•User: custom AbstractUser with email login, role field, is_company_admin flag.
•CompanyContextMiddleware: attaches request.company on every request.
•company_context processor: injects company, is_company_admin, user_role into all templates.

employees
•Employee: linked 1-to-1 with User. Role choices are job titles (manager, developer, etc.).
•Department: company-scoped, soft-deletable via is_active flag.
•Auto-create: a post_save signal creates an Employee profile whenever a new User with a company is saved.
•terminate() / reactivate() methods sync the linked User.is_active.

hr
•Position: job title with a salary grade, unique per company.
•LeaveRequest: six leave types, approve/deny workflow, automatic employee status sync.

finance
•Account: named financial account with balance, unique per company.
•Transaction: credit/debit entries that auto-adjust the parent account balance atomically.
•KPI dashboard with date-range filtering.

projects
•Project: status, priority, manager FK, completion percentage.
•SousTache: subtask with status transitions via change_status().
•CommentaireTache: threaded comments on tasks.
•AJAX toggle endpoint updates subtask completion and recalculates project progress using a DB aggregate.

inventory
•Largest app by view count (1 047 lines). Manages items, categories, and stock movements.
•Report views restricted to admin, manager, accountant, stock_manager.

crm
•Customer records and interaction log, accessible to admin, manager, secretary.

marketplace
•Multi-vendor storefront with platform-wide registration.
•Uses a separate client_login_required decorator — marketplace buyers/sellers are not ERP staff and are outside the staff role hierarchy.

Dependencies
Package	Version	Purpose
Django	6.0.2	Web framework
django-crispy-forms	2.5	Form rendering
crispy-bootstrap5	2025.6	Bootstrap 5 template pack
asgiref	3.11.1	ASGI compatibility
openpyxl	3.1.5	Excel export
pandas	3.0.0	Data processing for reports
Pillow	12.1.0	Image handling (employee photos)
python-dateutil	2.9.0	Date utilities
sqlparse	0.5.5	SQL formatting
numpy	2.4.2	Numerical support for pandas
et_xmlfile	2.0.0	openpyxl XML engine
tzdata	2025.3	Timezone data
gunicorn	—	Production WSGI server

Project Structure
ERP/
├── Dockerfile
├── railpack.toml
├── requirements.txt
├── manage.py
└── management_system/
    ├── accounts/          # Multi-tenancy & auth
    ├── core/              # Dashboard
    ├── employees/         # Staff directory
    ├── hr/                # Leave & positions
    ├── finance/           # Accounts & transactions
    ├── projects/          # Project tracking
    ├── inventory/         # Stock management
    ├── crm/               # Customer relations
    ├── marketplace/       # Multi-vendor shop
    ├── templates/         # App-specific HTML
    └── management_system/ # Settings & root URLs

Contributing
7.Fork the repository and create a feature branch.
8.Make your changes with clear commit messages.
9.Run python manage.py check before pushing.
10.Open a pull request against the main branch.

Repository: https://github.com/J-Lok/ERP
