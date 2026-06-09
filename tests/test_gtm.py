"""
Tier 2 gate — the "Ring → Real Buyers" motion drives Geo through allowlisted/confirm tools
ONLY, proves the twin learned (#1), targets the search by typology (#3), drafts >=3 persona-
tuned openers (#5), best-effort-compiles a dry-run sequence (#4), and NEVER reaches a
denylisted (create/launch/send) tool. Geo is fully mocked — no live network, no real outreach.

Run: uv run pytest tests/test_gtm.py -q
"""
from __future__ import annotations

import cognee_client as cognee
import geo_client
import gtm
from agents.domain_expert import RING_REF
from ontology import Action, AccountRole, Case, MarketContext

BRIEF = f"Quorum detection brief — {RING_REF}"


def _seed(tmp_path):
    cognee._STORE_PATH = tmp_path / "store.json"
    cognee._store = cognee._LocalStore()
    c = Case(account="AC-0001", is_candidate=True, role=AccountRole.SINK,
             signals={"pure_sink": 1, "zero_merchant": 1})
    c.action = Action.ESCALATE
    c.decisive_signals = ["pure_sink", "zero_merchant"]
    c.typology = "funnel-account absorption"
    c.closing_rule = "FLAG AC→AC WHERE ..."
    c.dollar_contribution = 29120.71
    cognee.write_case(c)
    cognee.write_market_context(MarketContext(
        ring_ref=RING_REF, segment="BSA/AML at community banks",
        intent_signals=[{"institution": "Community Federal Savings Bank (NY)",
                         "action": "OCC consent order — SAR lookback.",
                         "citation": "OCC AA-ENF-2025-21",
                         "signal_tags": ["pure_sink", "zero_merchant"]}]))


def _contacts():
    # Three distinct titles → three distinct persona angles (#5).
    return {"ok": True, "contacts": [
        {"id": "1", "first_name": "Jennifer", "last_name": "Re***s",
         "title": "BSA Officer", "company": "Community Bank", "has_email": True},
        {"id": "2", "first_name": "Amanda", "last_name": "Wh***r",
         "title": "AML Analyst", "company": "First Community Bank", "has_email": True},
        {"id": "3", "first_name": "Chance", "last_name": "Ru***g",
         "title": "VP Operations", "company": "Marion Community Bank", "has_email": True}]}


def _fake_call(name, args=None, *, allow_write=False):
    """Direct tool calls (geo_add_document, geo_propose_campaign, geo_enrich_contact)."""
    assert name not in geo_client.DENYLIST, f"denylisted tool reached: {name}"
    if name == "geo_propose_campaign":
        return {"ok": True, "suggested_schedule": {"contacts_per_day": 10}}
    return {"ok": True}


def _fake_cached(name, args=None, *, key=None, live=False, allow_write=False, flow_error=False):
    """Cached/live captures (search_contacts, list_documents, research, flow_spec, account/credit)."""
    assert name not in geo_client.DENYLIST, f"denylisted tool reached: {name}"
    if name == "geo_search_contacts":
        return _contacts()
    if name == "geo_list_documents":
        docs = [{"file_name": "old-brief.md"}]
        if key == "documents_after":
            docs = docs + [{"file_name": BRIEF}]          # the brief now present (+1)
        return {"ok": True, "documents": docs}
    if name == "geo_research":
        return {"ok": True, "answer": "AFTER: now references the layering ring."
                if key == "research_after" else "BEFORE: generic AML overview."}
    if name == "geo_compile_flow_spec":
        if flow_error:
            raise RuntimeError("schema mismatch")
        return {"ok": True, "steps": [{"day": 1, "channel": "gmail"}, {"day": 3, "channel": "gmail"}]}
    if name in ("geo_get_account_state", "geo_get_credit_status"):
        return {"ok": True, "account_name": "Quorum (trial)", "unlimited": True, "tool_count": 57}
    return {"ok": True}


def _patch(monkeypatch, tmp_path, *, flow_error=False):
    monkeypatch.setattr(geo_client, "call", _fake_call)
    monkeypatch.setattr(geo_client, "cached",
                        lambda n, a=None, **k: _fake_cached(n, a, flow_error=flow_error, **k))
    # Redirect packet writes to tmp so tests never clobber the committed geo_cache/ artifacts.
    monkeypatch.setattr(gtm, "CACHE", tmp_path)
    monkeypatch.setattr(gtm, "PACKET_PATH", tmp_path / "gtm_packet.json")


def test_gtm_motion_is_gated_and_drafts_openers(monkeypatch, tmp_path):
    _seed(tmp_path)
    _patch(monkeypatch, tmp_path)
    r = gtm.run(enrich_n=0, live=True)

    # Only allowlisted/confirm tools are driven; the motion's core tools are present.
    expected = {"geo_list_documents", "geo_add_document", "geo_search_contacts",
                "geo_propose_campaign", "geo_compile_flow_spec"}
    assert expected <= set(r["tools_called"])
    assert all(t not in geo_client.DENYLIST for t in r["tools_called"])
    assert "geo_enrich_contact" not in r["tools_called"]      # enrich is opt-in (default 0)

    # >=3 openers, each leading with the shared dated enforcement fact (fraud → GTM).
    assert len(r["openers"]) >= 3
    assert all(o["opener"] and o["to"] for o in r["openers"])
    assert "Community Federal Savings Bank" in r["openers"][0]["opener"]
    assert r["document"]["file_name"] == BRIEF
    assert r["document"]["ok"] is True                        # live push succeeded (no longer None)


def test_persona_tuned_openers_differ_by_title(monkeypatch, tmp_path):
    _seed(tmp_path)
    _patch(monkeypatch, tmp_path)
    r = gtm.run(live=True)
    angles = {o.get("persona_angle") for o in r["openers"]}
    assert len(angles) >= 2                                   # #5 — value-prop varies by persona


def test_learn_loop_proves_the_twin_changed(monkeypatch, tmp_path):
    _seed(tmp_path)
    _patch(monkeypatch, tmp_path)
    r = gtm.run(live=True)
    ll = r["learn_loop"]
    assert ll["captured"] is True
    assert ll["docs_added"] >= 1 and ll["brief_present"] is True
    assert ll["research_changed"] is True                     # #1 — before != after


def test_typology_targeted_contact_query(monkeypatch, tmp_path):
    _seed(tmp_path)
    _patch(monkeypatch, tmp_path)
    r = gtm.run(live=True)
    # pure_sink/zero_merchant tags steer the search toward fintech-sponsor banks (#3).
    assert "fintech" in r["contact_query"].lower()


def test_flow_spec_degrades_gracefully(monkeypatch, tmp_path):
    _seed(tmp_path)
    _patch(monkeypatch, tmp_path, flow_error=True)
    r = gtm.run(live=True)
    assert r["flow_spec"] is None                             # #4 — bad schema → section omitted
    assert "geo_compile_flow_spec" in r["tools_called"]       # still attempted


def test_gtm_requires_marketcontext(monkeypatch, tmp_path):
    cognee._STORE_PATH = tmp_path / "empty.json"
    cognee._store = cognee._LocalStore()
    _patch(monkeypatch, tmp_path)
    import pytest
    with pytest.raises(ValueError):
        gtm.run(live=True)
