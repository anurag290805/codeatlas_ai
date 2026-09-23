"""Tests for the approval-gate store that guards modify-mode patch application."""

from __future__ import annotations

from app.agents.patching import PatchProposal
from app.core.approvals import ApprovalStore


def _proposal() -> PatchProposal:
    from app.agents.patching import PatchEdit

    return PatchProposal(patches=[PatchEdit(path="main.py", operation="modify", old_content_hash="0" * 64, diff="-+ @@")])


def test_approval_store_is_single_use() -> None:
    store = ApprovalStore()
    token = store.create("ws-a", 1, _proposal(), ["main.py"], "improve", "ctx", None, [])
    assert store.consume(token, "ws-a") is not None
    # A second consume must fail — approval is consumed exactly once.
    assert store.consume(token, "ws-a") is None


def test_approval_store_is_bound_to_owning_workspace() -> None:
    store = ApprovalStore()
    token = store.create("ws-a", 1, _proposal(), ["main.py"], "improve", "ctx", None, [])
    # A different workspace must not be able to approve it.
    assert store.consume(token, "ws-b") is None
    # And the original owner can still approve it afterwards.
    assert store.consume(token, "ws-a") is not None


def test_approval_store_expires() -> None:
    store = ApprovalStore(ttl_seconds=-1)
    token = store.create("ws-a", 1, _proposal(), ["main.py"], "improve", "ctx", None, [])
    assert store.consume(token, "ws-a") is None


def test_approval_store_rejects_unknown_token() -> None:
    store = ApprovalStore()
    assert store.consume("does-not-exist", "ws-a") is None