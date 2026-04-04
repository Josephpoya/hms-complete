"""
accounts/middleware.py
======================
Backwards-compatibility shim.
All middleware has moved to core/middleware.py.
Import from there for new code.
"""
from core.middleware import (  # noqa — re-export for backwards compat
    get_current_request,
    get_current_user,
    get_client_ip,
    AuditContextMiddleware,
)
