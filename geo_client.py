"""
geo_client.py — Quorum's safe, cached client for the Geo (geodo.ai) MCP.

Productionizes the throwaway geo.py. Three jobs:

  1. SAFETY. Tools are partitioned into ALLOWLIST (safe to call unattended —
     read-only or no side effects), CONFIRM (writes that cost credits / touch the
     account — require allow_write=True, i.e. an explicit human OK upstream), and
     DENYLIST (real outreach / public artifacts — refused outright, always). No
     message is ever sent to a real person from this project.

  2. CACHING. ``cached()`` snapshots Geo responses to ``geo_cache/<key>.json`` so the
     judged pipeline runs OFFLINE and deterministically — same persist/load
     discipline as cognee_client's cognee_graph.json. Live calls are opt-in (live=True)
     and fall back to cache on any error.

  3. PLUMBING. JSON-RPC over HTTP, bearer PAT from .geo_token (never printed),
     auto idempotency_key on writes, and the requires_confirmation -> confirmation_token
     handshake.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("geo_client")

ROOT = Path(__file__).resolve().parent
URL = os.getenv("GEO_MCP_URL", "https://app.geodo.ai/api/mcp")
TOKEN_PATH = ROOT / ".geo_token"
CACHE_DIR = ROOT / "geo_cache"

# Safe to call unattended (read-only, or no side effects beyond a research credit).
ALLOWLIST: set[str] = {
    "geo_get_account_state", "geo_get_credit_status", "geo_list_connections",
    "geo_list_campaigns", "geo_get_campaign_benchmarks", "geo_get_profile",
    "geo_list_documents", "geo_research", "geo_compile_flow_spec", "geo_propose_campaign",
}
# Writes that cost credits / mutate the account — require an explicit human OK (allow_write).
CONFIRM: set[str] = {
    "geo_search_contacts", "geo_enrich_contact", "geo_add_document",
    "geo_update_profile", "geo_set_tool_permission", "geo_update_preferences",
}
# Real outreach / public artifacts — NEVER callable from this project.
DENYLIST: set[str] = {
    "geo_create_campaign", "geo_launch_campaign", "geo_resume_campaign", "geo_stop_campaign",
    "geo_pause_campaign", "geo_send_manual_message", "geo_send_sms",
    "geo_twitter_post", "geo_twitter_reply", "geo_reddit_post", "geo_reddit_comment",
    "geo_facebook_post", "geo_facebook_message", "geo_share_campaign", "geo_revoke_share",
    "geo_create_mini_campaign_from_contacts", "geo_enqueue_byoc_sends",
    "geo_launch_flow_from_spec", "geo_eo_pause_campaign", "geo_eo_resume_campaign",
}


def _token() -> str:
    return TOKEN_PATH.read_text().strip()


def _raw(name: str, args: dict) -> dict:
    """One JSON-RPC tools/call round trip. Token is read lazily so import never needs it."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": args}}
    req = urllib.request.Request(
        URL, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {_token()}",
                 "Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"})
    with urllib.request.urlopen(req, timeout=180) as r:
        body = r.read().decode()
    if "data:" in body[:64] and not body.lstrip().startswith("{"):   # SSE framing
        for line in body.splitlines():
            if line.startswith("data:"):
                body = line[5:].strip()
                break
    return json.loads(body)


def _inner(resp: dict) -> Any:
    """Unwrap the MCP content envelope to the tool's JSON payload (or text)."""
    try:
        txt = resp["result"]["content"][0]["text"]
        try:
            return json.loads(txt)
        except Exception:
            return txt
    except Exception:
        return resp


def call(name: str, args: Optional[dict] = None, *, allow_write: bool = False) -> Any:
    """Call a Geo MCP tool with the safety policy enforced.

    - DENYLIST -> PermissionError (always).
    - Not in ALLOWLIST -> a write; requires allow_write=True (set only after a human OK).
    - Auto-adds idempotency_key for writes; resolves the confirmation-token handshake.
    """
    args = dict(args or {})
    if name in DENYLIST:
        raise PermissionError(f"geo_client refuses denylisted (outreach) tool: {name}")
    is_write = name not in ALLOWLIST
    if is_write:
        if not allow_write:
            raise PermissionError(
                f"{name} is a write tool — pass allow_write=True only after explicit human confirmation")
        args.setdefault("idempotency_key", "quorum-" + uuid.uuid4().hex[:12])
    data = _inner(_raw(name, args))
    if isinstance(data, dict) and data.get("requires_confirmation") and data.get("confirmation_token"):
        log.info("GEO CONFIRM   resubmitting %s with confirmation_token", name)
        data = _inner(_raw(name, {**args, "confirmation_token": data["confirmation_token"]}))
    return data


def _cached_response(path):
    """Tolerant cache reader: accepts both this module's {…, 'response': …} envelope
    and a raw tool payload (as written by the throwaway geo.py). Raises on an empty or
    unparseable file (e.g. a OneDrive dataless placeholder) so callers treat it as a miss."""
    txt = path.read_text()
    if not txt.strip():
        raise ValueError(f"empty cache file (dataless placeholder?): {path.name}")
    rec = json.loads(txt)
    if isinstance(rec, dict) and "response" in rec:
        return rec["response"]
    return rec


def cached(name: str, args: Optional[dict] = None, *, key: str,
           live: bool = False, allow_write: bool = False) -> Any:
    """Return geo_cache/<key>.json if present (offline-safe), else call live and store it.

    Judged pipeline calls with live=False. A present-but-unreadable cache (empty/corrupt,
    e.g. a OneDrive placeholder) is treated as a miss; on a live error we fall back to the
    cache only if it is actually readable."""
    path = CACHE_DIR / f"{key}.json"
    if not live and path.exists():
        try:
            resp = _cached_response(path)
            log.info("GEO CACHE HIT  key=%s", key)
            return resp
        except (ValueError, OSError) as exc:
            log.warning("GEO CACHE UNREADABLE key=%s (%s) — refetching live", key, exc)
    try:
        resp = call(name, args or {}, allow_write=allow_write)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        if path.exists():
            try:
                cached_resp = _cached_response(path)
                log.warning("GEO live call failed (%s) — using cached %s", exc, key)
                return cached_resp
            except (ValueError, OSError):
                pass
        raise
    CACHE_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(
        {"tool": name, "args": args or {},
         "captured_on": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "response": resp}, indent=2, default=str))
    log.info("GEO CACHE WRITE key=%s", key)
    return resp


def research(query: str, *, key: str, live: bool = False) -> Any:
    """Cached geo_research (GTM advisor). Returns the response dict (with 'answer')."""
    return cached("geo_research", {"query": query}, key=key, live=live)


# Thin cached wrappers for the read-only health/inventory tools (all ALLOWLIST). Each is
# offline-safe (reads geo_cache/<key>.json) and only hits the network with live=True.
def account_state(*, live: bool = False) -> Any:
    """geo_get_account_state — who the connected Geo account is (proves a live MCP link)."""
    return cached("geo_get_account_state", {}, key="account_state", live=live)


def credit_status(*, live: bool = False) -> Any:
    """geo_get_credit_status — trial/credit posture (e.g. unlimited:true)."""
    return cached("geo_get_credit_status", {}, key="credit_status", live=live)


def list_documents(*, key: str = "documents", live: bool = False) -> Any:
    """geo_list_documents — the twin's knowledge base (used to prove Quorum taught it)."""
    return cached("geo_list_documents", {}, key=key, live=live)


def load_cached(key: str) -> Optional[Any]:
    """The cached response for a key, or None — for callers that want cache-only.
    Returns None for an empty/corrupt cache file (treated as absent)."""
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        try:
            return _cached_response(path)
        except (ValueError, OSError):
            return None
    return None


def connection_proof() -> Optional[dict]:
    """Liveness proof for the UI badge: reads the cached account_state / credit_status
    fixtures (written by gtm.run --live or domain_expert with live=True). Returns None
    until a live capture has run."""
    acct = load_cached("account_state")
    cred = load_cached("credit_status")
    if not acct and not cred:
        return None
    acct = acct if isinstance(acct, dict) else {}
    cred = cred if isinstance(cred, dict) else {}
    creds = (acct.get("credits") if isinstance(acct.get("credits"), dict) else None) or cred
    std = creds.get("standard") if isinstance(creds.get("standard"), dict) else {}
    return {
        "connected": bool(acct.get("ok") or cred.get("ok")),
        "user_id": acct.get("user_id"),
        "unlimited": creds.get("unlimited"),
        "source": creds.get("source"),
        "credits_used": std.get("total_used"),
    }
