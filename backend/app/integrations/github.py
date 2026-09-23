from __future__ import annotations

from .http import get_cached, get_json, put_cached


class GithubClient:
    def metadata(self, repository_url: str) -> dict | None:
        parts = repository_url.rstrip("/").removesuffix(".git").split("/")
        if len(parts) < 2 or parts[-3] != "github.com":
            return None
        owner, name = parts[-2], parts[-1]
        key = f"github:{owner}/{name}"
        cached = get_cached(key)
        if cached is not None:
            return cached
        status, payload = get_json(f"https://api.github.com/repos/{owner}/{name}", headers={"Accept": "application/vnd.github+json", "User-Agent": "CodeAtlas-AI"})
        if status != 200 or not isinstance(payload, dict):
            return None
        result = {"full_name": payload.get("full_name"), "description": payload.get("description"), "stars": payload.get("stargazers_count", 0), "forks": payload.get("forks_count", 0), "watchers": payload.get("subscribers_count", 0), "open_issues": payload.get("open_issues_count", 0), "default_branch": payload.get("default_branch"), "license": (payload.get("license") or {}).get("spdx_id"), "html_url": payload.get("html_url")}
        return put_cached(key, result)
