from __future__ import annotations

from .http import get_cached, put_cached


class OsvClient:
    def vulnerabilities(self, ecosystem: str, package: str, version: str | None) -> list[dict]:
        if not version:
            return []
        key = f"osv:{ecosystem}:{package}:{version}"
        cached = get_cached(key)
        if cached is not None:
            return cached
        # Public OSV query is POST-only; use the same bounded timeout policy.
        import httpx
        try:
            response = httpx.post("https://api.osv.dev/v1/query", json={"package": {"name": package, "ecosystem": ecosystem}, "version": version}, timeout=8.0)
            if response.status_code != 200:
                return []
            data = response.json()
        except (httpx.HTTPError, ValueError):
            return []
        results = data.get("vulns", []) if isinstance(data, dict) else []
        return put_cached(key, results)
