"""In-memory store for human-approval-gated modify-mode patches.

A ``PendingApproval`` holds a validated but NOT-yet-applied patch proposal,
bound to the workspace that created it. Approval must come from the same
workspace and is single-use; entries expire after a bounded TTL. Nothing here
touches the filesystem or executes code -- application happens only after the
approval token is consumed by the approve endpoint.

This is process-local. For a multi-worker/multi-process deployment, this store
must be backed by a shared datastore (e.g. the database); the interface is
intentionally small so that swap is contained to this module.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class PendingApproval:
    workspace_id: str
    repository_id: int
    proposal: Any  # app.agents.patching.PatchProposal
    changed_paths: list[str]
    task: str
    context: str
    route: str | None
    acceptance_criteria: list[str]
    created_at: float
    consumed: bool = False


class ApprovalStore:
    TTL_SECONDS = 30 * 60

    def __init__(self, ttl_seconds: int = TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._items: dict[str, PendingApproval] = {}

    def create(
        self,
        workspace_id: str,
        repository_id: int,
        proposal: Any,
        changed_paths: list[str],
        task: str,
        context: str,
        route: str | None,
        acceptance_criteria: list[str],
    ) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._items[token] = PendingApproval(
                workspace_id=workspace_id,
                repository_id=repository_id,
                proposal=proposal,
                changed_paths=changed_paths,
                task=task,
                context=context,
                route=route,
                acceptance_criteria=acceptance_criteria,
                created_at=time.monotonic(),
            )
        return token

    def consume(self, token: str, workspace_id: str) -> PendingApproval | None:
        """Return the pending approval only for the owning workspace; single-use + TTL."""
        with self._lock:
            pending = self._items.get(token)
            if pending is None or pending.consumed:
                return None
            if pending.workspace_id != workspace_id:
                return None
            if time.monotonic() - pending.created_at > self._ttl:
                self._items.pop(token, None)
                return None
            pending.consumed = True
            self._items.pop(token, None)
            return pending


_store = ApprovalStore()


def get_approval_store() -> ApprovalStore:
    return _store