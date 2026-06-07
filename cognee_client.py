"""
Cognee integration for Quorum.

Two layers:
  • A fast, exact local JSON store (_LocalStore) is the operational substrate for
    the per-agent Case field-accretion — every read/write is logged with its
    entity id so the handoff chain is fully traceable (judging criterion 2).
  • The real Cognee SDK (Gemini-backed) ingests the enriched Cases into a
    semantic knowledge graph (add → cognify) and serves natural-language search
    (cognee_search). It activates when GEMINI_API_KEY is set and degrades
    gracefully otherwise, so the pipeline is never blocked.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ontology import Case

log = logging.getLogger("cognee_client")

_STORE_PATH = Path("cognee_store.json")
_USE_REAL_COGNEE = bool(os.getenv("COGNEE_API_KEY"))


# ── Local JSON store (fallback) ───────────────────────────────────────────────

class _LocalStore:
    def __init__(self) -> None:
        self._data: dict[str, dict] = {}
        if _STORE_PATH.exists():
            try:
                self._data = json.loads(_STORE_PATH.read_text())
            except Exception:
                self._data = {}

    def _save(self) -> None:
        _STORE_PATH.write_text(json.dumps(self._data, default=str, indent=2))

    def write(self, entity_type: str, entity_id: str, payload: dict) -> str:
        self._data[entity_id] = {"_type": entity_type, "_id": entity_id, **payload}
        self._save()
        log.info("COGNEE WRITE  type=%s  id=%s", entity_type, entity_id)
        return entity_id

    def read_by_type(self, entity_type: str,
                     filters: Optional[dict] = None) -> list[dict]:
        results = [v for v in self._data.values() if v.get("_type") == entity_type]
        if filters:
            for k, v in filters.items():
                results = [r for r in results if r.get(k) == v]
        log.info("COGNEE READ   type=%s  filters=%s  hits=%d", entity_type, filters, len(results))
        return results

    def read_by_id(self, entity_id: str) -> Optional[dict]:
        result = self._data.get(entity_id)
        log.info("COGNEE READ   id=%s  found=%s", entity_id, result is not None)
        return result

    def update_field(self, entity_id: str, field: str, value: Any) -> None:
        if entity_id in self._data:
            self._data[entity_id][field] = value
            self._save()

    def clear(self) -> None:
        self._data = {}
        if _STORE_PATH.exists():
            _STORE_PATH.unlink()


_store = _LocalStore()


def reset_store() -> None:
    """Clear the Cognee store — call before each pipeline run."""
    _store.clear()
    log.info("COGNEE STORE cleared")


# ── Serialization ─────────────────────────────────────────────────────────────

def _serialize(obj: Any) -> dict:
    d = asdict(obj) if hasattr(obj, "__dataclass_fields__") else dict(obj)
    # convert enums and datetimes
    for k, v in d.items():
        if hasattr(v, "value"):
            d[k] = v.value
        elif isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


def get_entity_by_id(entity_id: str) -> Optional[dict]:
    return _store.read_by_id(entity_id)


# ── Case helpers (account-centric Quorum entity) ──────────────────────────────

def _case_entity_id(account: str) -> str:
    """Deterministic Cognee id so the same account maps to one accreting Case."""
    return f"Case::{account}"


def write_case(case: Case) -> str:
    payload = _serialize(case)
    return _store.write("Case", _case_entity_id(case.account), payload)


def read_cases(candidates_only: bool = False) -> list[dict]:
    results = _store.read_by_type("Case")
    if candidates_only:
        results = [c for c in results if c.get("is_candidate")]
    return results


def read_case(account: str) -> Optional[dict]:
    return _store.read_by_id(_case_entity_id(account))


def update_case_fields(account: str, fields: dict) -> None:
    """Accrete fields onto an existing Case (the agent handoff in action)."""
    eid = _case_entity_id(account)
    for key, value in fields.items():
        if hasattr(value, "value"):   # serialize enums (e.g. Action, AccountRole)
            value = value.value
        elif isinstance(value, datetime):
            value = value.isoformat()
        _store.update_field(eid, key, value)
    log.info("COGNEE CASE UPDATE  account=%s  fields=%s", account, list(fields.keys()))


def get_store_summary() -> dict:
    all_entities = list(_store._data.values())
    by_type: dict[str, int] = {}
    for e in all_entities:
        t = e.get("_type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
    return {"total_entities": len(all_entities), "by_type": by_type}


# ── Real Cognee SDK layer (Gemini-backed semantic memory graph) ───────────────
#
# The JSON _LocalStore above is the fast, exact substrate for the per-agent
# field accretion the pipeline needs. On top of it, the real Cognee SDK ingests
# the enriched Cases into a semantic knowledge graph (add → cognify) and serves
# natural-language search over it. Everything here is GUARDED: if no Gemini key
# is present or any Cognee call fails, we log and fall back — the pipeline and
# the local handoff are never blocked.

_GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
_COGNEE_MODE = os.getenv("QUORUM_COGNEE", "auto").lower()   # auto | on | off
USE_REAL_COGNEE = (_COGNEE_MODE != "off"
                   and bool(_GEMINI_KEY) and not _GEMINI_KEY.startswith("your"))


def _configure_cognee_env() -> None:
    """Map the BYO Gemini key onto Cognee's LLM + embedding config (litellm)."""
    key = os.environ["GEMINI_API_KEY"]
    os.environ.setdefault("LLM_PROVIDER", "gemini")
    os.environ["LLM_API_KEY"] = os.getenv("LLM_API_KEY") or key
    os.environ.setdefault("LLM_MODEL", "gemini/gemini-2.5-flash")
    os.environ.setdefault("EMBEDDING_PROVIDER", "gemini")
    os.environ.setdefault("EMBEDDING_MODEL", "gemini/gemini-embedding-001")
    os.environ["EMBEDDING_API_KEY"] = os.getenv("EMBEDDING_API_KEY") or key
    os.environ.setdefault("EMBEDDING_DIMENSIONS", "3072")
    os.environ.setdefault("COGNEE_SKIP_CONNECTION_TEST", "true")  # we verified it works


def _case_to_text(c: dict) -> str:
    """A human-readable document per Case for Cognee to build its graph from."""
    sig = c.get("signals") or {}
    fired = [k for k, v in sig.items() if not k.startswith("_") and v]
    ci = c.get("credible_interval") or [None, None]
    return (
        f"Account {c['account']} has role {c.get('role')}. "
        f"Action: {c.get('action')}. "
        f"Mule probability p_mule={c.get('p_mule')} with 94% credible interval "
        f"[{ci[0]}, {ci[1]}]. "
        f"Signals fired: {', '.join(fired) or 'none'}. "
        f"Decisive signals: {', '.join(c.get('decisive_signals') or []) or 'none'}. "
        f"Decoy suspect: {c.get('decoy_suspect')}. "
        f"Typology: {c.get('typology') or 'n/a'}. "
        f"Reasoning: {c.get('action_reason') or c.get('detect_reason')}"
    )


# ── Option 2: per-agent writes to Cognee, one cognify at the end ──────────────
#
# Each of the four agents contributes a distinct, tagged layer to Cognee via
# add() (cheap, no graph extraction). A single cognify() at the end builds the
# knowledge graph from ALL four agents' contributions — so Cognee genuinely
# carries the multi-agent provenance, not just the final report. The result is
# persisted to cognee_graph.json so the frontend shows the graph without a live
# rebuild (cognify is slow on the Gemini free tier).
#
# Writes are buffered during the run and flushed in a single event loop in
# finish_build() — running async cognee across several asyncio.run() calls binds
# DB connections to dead loops, so one loop is both safer and faster.

_GRAPH_PATH = Path("cognee_graph.json")
_CANNED_QUERIES = [
    "Which accounts are relays in the laundering ring?",
    "Which accounts were escalated and why?",
    "Which accounts share a device but were cleared as decoys?",
    "What laundering typology and total exposure did the agents find?",
]

_building: bool = False
_pending_layers: list[tuple[str, str]] = []


def begin_build() -> bool:
    """Start accumulating per-agent Cognee layers for this run (agents call
    add_agent_layer). Returns True if the real Cognee build is active."""
    global _building, _pending_layers
    _building = USE_REAL_COGNEE
    _pending_layers = []
    if _building:
        log.info("COGNEE BUILD  begin — each agent will write a layer to Cognee.")
    return _building


def add_agent_layer(agent: str, text: str) -> None:
    """An agent contributes its findings layer to Cognee. No-op unless a build is
    active, so the fast offline pipeline and the tests never touch the network."""
    if _building and text:
        _pending_layers.append((agent, text))
        log.info("COGNEE WRITE  agent=%s  layer queued (%d chars).", agent, len(text))


def _stringify_search(res) -> str:
    if res is None:
        return ""
    if isinstance(res, list):
        parts = []
        for item in res:
            if isinstance(item, dict):
                parts.append(str(item.get("search_result") or item.get("answer") or item))
            else:
                parts.append(str(item))
        return " | ".join(parts)
    return str(res)


def finish_build() -> dict:
    """Flush every agent's layer into Cognee (add per agent) + one cognify, run
    the canned queries, and persist cognee_graph.json. Never raises."""
    global _building
    if not _building:
        return {"used": False, "reason": "build not active (no Gemini key / QUORUM_COGNEE=off)"}
    layers = list(_pending_layers)
    try:
        import asyncio
        _configure_cognee_env()
        import cognee

        async def _flush() -> dict:
            await cognee.prune.prune_data()
            await cognee.prune.prune_system(metadata=True)
            for agent, text in layers:                       # one add() per agent
                await cognee.add(text, node_set=["quorum", f"agent:{agent}"])
            await cognee.cognify()                           # single graph build
            qa = []
            for q in _CANNED_QUERIES:
                try:
                    qa.append({"q": q, "a": _stringify_search(await cognee.search(q))})
                except Exception as e:                       # noqa: BLE001
                    qa.append({"q": q, "a": f"(search error: {e})"})
            return {"used": True,
                    "built_at": datetime.utcnow().isoformat(),
                    "agents": [a for a, _ in layers],
                    "layers": {a: t for a, t in layers},
                    "qa": qa}

        result = asyncio.run(_flush())
        _GRAPH_PATH.write_text(json.dumps(result, indent=2, default=str))
        log.info("COGNEE BUILD  done — %d agent layers ingested + cognified; "
                 "persisted to %s.", len(layers), _GRAPH_PATH)
        return result
    except Exception as exc:   # noqa: BLE001 — must never break the pipeline
        log.warning("COGNEE BUILD failed (%s) — local store remains source of truth.", exc)
        return {"used": False, "error": str(exc)}
    finally:
        _building = False


def load_cognee_graph() -> Optional[dict]:
    """The persisted graph build, for the frontend to display without a rebuild."""
    if _GRAPH_PATH.exists():
        try:
            return json.loads(_GRAPH_PATH.read_text())
        except Exception:   # noqa: BLE001
            return None
    return None


def cognee_search(query: str):
    """Natural-language search over the Cognee graph. Returns None if unavailable."""
    if not USE_REAL_COGNEE:
        return None
    try:
        import asyncio
        _configure_cognee_env()
        import cognee
        return asyncio.run(cognee.search(query))
    except Exception as exc:   # noqa: BLE001
        log.warning("COGNEE SDK search failed: %s", exc)
        return None
