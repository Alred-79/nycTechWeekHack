"""
Tier 0 gate — geo_client enforces the safety policy and the cache is offline.

No live network: _raw is monkeypatched everywhere. Asserts (a) denylisted outreach
tools are refused, (b) write tools require allow_write, (c) writes auto-add an
idempotency_key, and (d) a cache hit performs ZERO network calls.

Run: uv run pytest tests/test_geo_client.py -q
"""
from __future__ import annotations

import json

import pytest

import geo_client


def _envelope(payload: dict) -> dict:
    return {"result": {"content": [{"type": "text", "text": json.dumps(payload)}]}}


def test_denylist_outreach_tool_is_refused():
    with pytest.raises(PermissionError):
        geo_client.call("geo_launch_campaign", {"sequence_id": "x"})
    with pytest.raises(PermissionError):
        geo_client.call("geo_send_manual_message", {"to": "x"})


def test_write_tool_requires_allow_write(monkeypatch):
    monkeypatch.setattr(geo_client, "_raw", lambda n, a: _envelope({"ok": True}))
    with pytest.raises(PermissionError):
        geo_client.call("geo_search_contacts", {"query": "x"})          # no allow_write
    # with allow_write it proceeds
    assert geo_client.call("geo_search_contacts", {"query": "x"}, allow_write=True) == {"ok": True}


def test_write_auto_adds_idempotency_key(monkeypatch):
    seen = {}
    monkeypatch.setattr(geo_client, "_raw",
                        lambda n, a: seen.update(a) or _envelope({"ok": True}))
    geo_client.call("geo_add_document", {"file_name": "f", "content": "c"}, allow_write=True)
    assert "idempotency_key" in seen and seen["idempotency_key"].startswith("quorum-")


def test_allowlisted_research_needs_no_allow_write(monkeypatch):
    monkeypatch.setattr(geo_client, "_raw", lambda n, a: _envelope({"ok": True, "answer": "hi"}))
    out = geo_client.call("geo_research", {"query": "who buys this?"})
    assert out["answer"] == "hi"


def test_cache_hit_makes_zero_network_calls(monkeypatch, tmp_path):
    # Point the cache at a temp dir with a pre-written record.
    monkeypatch.setattr(geo_client, "CACHE_DIR", tmp_path)
    (tmp_path / "research_probe.json").write_text(json.dumps(
        {"tool": "geo_research", "args": {}, "response": {"ok": True, "answer": "cached"}}))

    def _boom(name, args):
        raise AssertionError("network must not be touched on a cache hit")

    monkeypatch.setattr(geo_client, "_raw", _boom)
    out = geo_client.cached("geo_research", {"query": "q"}, key="research_probe", live=False)
    assert out["answer"] == "cached"


def test_confirmation_handshake_resubmits_with_token(monkeypatch):
    calls = []

    def _raw(name, args):
        calls.append(args)
        if "confirmation_token" not in args:
            return _envelope({"requires_confirmation": True, "confirmation_token": "tok-123"})
        return _envelope({"ok": True, "confirmed": True})

    monkeypatch.setattr(geo_client, "_raw", _raw)
    out = geo_client.call("geo_add_document", {"file_name": "f", "content": "c"}, allow_write=True)
    assert out["confirmed"] is True
    assert calls[-1]["confirmation_token"] == "tok-123"
