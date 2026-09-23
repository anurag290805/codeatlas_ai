"""Backward-compatible settings import path.

The canonical implementation lives in :mod:`app.core.config`.
"""

from app.core.config import Settings, get_settings, settings

__all__ = ["Settings", "get_settings", "settings"]
