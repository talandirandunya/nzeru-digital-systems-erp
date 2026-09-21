"""
accounts/decorators.py

Re-exports role_required and company_admin_required from accounts.permissions
so that existing imports (from accounts.decorators import role_required) keep
working without any changes in other apps.
"""

from accounts.permissions import (  # noqa: F401  (re-export)
    company_admin_required,
    role_required,
)