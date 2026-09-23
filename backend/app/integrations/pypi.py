from __future__ import annotations

from .http import get_cached, get_json, put_cached


class PypiClient:
    def metadata(self, package: str) -> dict[str, str | None] | None:
        key = f"pypi:{package.lower()}"
        cached = get_cached(key)
        if cached is not None:
            return cached
        status, payload = get_json(f"https://pypi.org/pypi/{package}/json")
        if status != 200 or not isinstance(payload, dict):
            return None
        info = payload.get("info") or {}
        result = {"latest_version": info.get("version"), "description": info.get("summary")}
        return put_cached(key, result)
