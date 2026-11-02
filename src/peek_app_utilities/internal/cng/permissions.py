"""CNG's HTTP 403 handling: the gateway uses 403 for "this app is missing
permission X", which is an expected misconfiguration rather than a fault, so the
transport logs it at ``warn`` and raises the typed :class:`CngPermissionError`
carrying the named permissions.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from peek_app_utilities.errors import CngPermissionError

_PERMISSION_SEPARATOR: Final = ": "


def extract_missing_permissions(body: Any) -> list[str]:
    """Pulls the permission names out of a 403 body (``{"errors": {"permission":
    [...]}}``). The gateway reports them as sentences (``"The app does not have
    the required permission: products:read"``), so the trailing token after the
    last ``": "`` is the permission itself; a sentence without one is kept
    verbatim. Returns an empty list for any body that does not carry
    ``errors.permission`` strings."""
    if not isinstance(body, Mapping):
        return []
    errors = body.get("errors")
    if not isinstance(errors, Mapping):
        return []
    raw = errors.get("permission")
    if not isinstance(raw, list):
        return []
    permissions: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            continue
        permission = entry.rsplit(_PERMISSION_SEPARATOR, 1)[-1].strip()
        if permission:
            permissions.append(permission)
    return permissions


def forbidden_error(body: Any) -> tuple[Exception, dict[str, Any]]:
    """The :class:`RestClient` ``on_forbidden`` handler for CNG."""
    permissions = extract_missing_permissions(body)
    return CngPermissionError(permissions, body), {"permissions": permissions}
