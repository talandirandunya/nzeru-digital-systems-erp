"""Administrator-facing catalog of enforced module and function capabilities."""

MODULE_ACCESS_CATALOG = (
    {
        'key': 'dashboard',
        'label': 'Main Dashboard',
        'capabilities': (('dashboard.view', 'View dashboard'),),
    },
    {
        'key': 'employees',
        'label': 'Employee Management',
        'capabilities': (('employees.view', 'View employees'), ('employees.manage', 'Manage employees'), ('reporting.export', 'Export employee reports')),
    },
    {
        'key': 'hr',
        'label': 'HR',
        'capabilities': (('hr.view', 'View HR'), ('hr.manage', 'Manage HR'), ('hr.manage_payroll', 'Manage payroll')),
    },
    {
        'key': 'finance',
        'label': 'Finance',
        'capabilities': (('finance.view', 'View finance'), ('finance.manage', 'Manage finance'), ('finance.post_journal', 'Post journals'), ('finance.approve_payment', 'Approve payments')),
    },
    {
        'key': 'procurement',
        'label': 'Procurement',
        'capabilities': (('procurement.view', 'View procurement'), ('procurement.manage', 'Manage procurement'), ('procurement.approve', 'Approve procurement')),
    },
    {
        'key': 'inventory',
        'label': 'Inventory',
        'capabilities': (('inventory.view', 'View inventory'), ('inventory.manage', 'Manage inventory'), ('inventory.issue', 'Issue stock')),
    },
    {
        'key': 'crm',
        'label': 'CRM',
        'capabilities': (('crm.view', 'View CRM'), ('crm.manage', 'Manage CRM')),
    },
    {
        'key': 'projects',
        'label': 'Projects',
        'capabilities': (('projects.view', 'View projects'), ('projects.manage', 'Manage projects')),
    },
    {
        'key': 'meetings',
        'label': 'Meetings',
        'capabilities': (('meetings.view', 'View meetings'), ('meetings.manage', 'Manage meetings')),
    },
    {
        'key': 'notifications',
        'label': 'Notifications',
        'capabilities': (('notifications.view', 'View notifications'),),
    },
    {
        'key': 'governance',
        'label': 'Governance and Administration',
        'capabilities': (('governance.view', 'View governance'), ('admin.manage_users', 'Manage users'), ('admin.manage_roles', 'Assign permissions'), ('admin.manage_organisation', 'Manage workflows')),
    },
    {
        'key': 'reports',
        'label': 'Reports and Audit',
        'capabilities': (('reporting.view', 'View reports'), ('reporting.export', 'Export reports')),
    },
)

CAPABILITY_LABELS = {
    capability: label
    for module in MODULE_ACCESS_CATALOG
    for capability, label in module['capabilities']
}
