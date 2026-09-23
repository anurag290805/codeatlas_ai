"""Compatibility exports for the canonical browser-workspace resolver.

Workspace identity is implemented in :mod:`app.core.workspace`. This module
remains as a stable import surface for existing route dependencies.
"""

from __future__ import annotations

from fastapi import Request

from app.core.workspace import (
    WORKSPACE_COOKIE,
    _decode,
    workspace_cookie_value,
)


def get_workspace_id(request: Request) -> str:
    """Return the workspace already resolved for the current request."""
    workspace_id = getattr(request.state, "workspace_id", None)
    if workspace_id:
        return workspace_id

    workspace_id = _decode(request.cookies.get(WORKSPACE_COOKIE))
    if workspace_id is not None:
        request.state.workspace_id = workspace_id
        return workspace_id

    raise RuntimeError("Workspace was not initialized before route execution.")


def ensure_workspace_cookie(request: Request) -> str:
    """Return the request workspace for legacy direct-call integrations."""
    workspace_id = get_workspace_id(request)
    request.state.workspace_cookie_value = workspace_cookie_value(workspace_id)
    return workspace_id
