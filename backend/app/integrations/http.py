"""Small bounded HTTP/cache primitives for public provider APIs."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any

import httpx


@dataclass
class CacheEntry:
    expires_at: float
    value: Any


_cache: dict[str, CacheEntry] = {}


def get_cached(key: str) -> Any | None:
    entry = _cache.get(key)
    if entry and entry.expires_at > monotonic():
        return entry.value
    if entry:
        _cache.pop(key, None)
    return None


def put_cached(key: str, value: Any, ttl_seconds: int = 600) -> Any:
    _cache[key] = CacheEntry(monotonic() + ttl_seconds, value)
    return value


def get_json(url: str, *, headers: dict[str, str] | None = None, timeout: float = 8.0) -> tuple[int, Any]:
    """Call a known provider URL and return status/payload without leaking errors."""
    try:
        response = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
        try:
            payload = response.json()
        except ValueError:
            payload = None
        return response.status_code, payload
    except (httpx.HTTPError, TimeoutError):
        return 0, None
