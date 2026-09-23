from __future__ import annotations

from .http import get_cached, get_json, put_cached


class NpmClient:
    def metadata(self, package: str) -> dict[str, str | None] | None:
        key = f"npm:{package}"
        cached = get_cached(key)
        if cached is not None:
            return cached
        status, payload = get_json(f"https://registry.npmjs.org/{package}", headers={"Accept": "application/json"})
        if status != 200 or not isinstance(payload, dict):
            return None
        result = {"latest_version": (payload.get("dist-tags") or {}).get("latest"), "description": payload.get("description")}
        return put_cached(key, result)
