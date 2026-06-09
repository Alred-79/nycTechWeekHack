"""
Tier 1 gate — Agent 5 (Domain Expert) consumes the adjudicated ring from Cognee and
writes a MarketContext grounded in Geo + verified enforcement. The handoff is provable:
it RAISES without an adjudicated ring, and it matches the ring's typology to the correct
real, dated enforcement action. No live network — Geo research is read from geo_cache/.

Run: uv run pytest tests/test_domain_expert.py -q
"""
from __future__ import annotations

import pytest

import cognee_client as cognee
from agents import domain_expert
from ontology import Action, AccountRole, Case


def _seed_adjudicated_funnel():
    cognee.reset_store()
    c = Case(account="AC-0001", is_candidate=True, role=AccountRole.SINK,
             signals={"pure_sink": 1, "zero_merchant": 1, "under_threshold": 1})
    c.action = Action.ESCALATE
    c.decisive_signals = ["pure_sink", "zero_merchant"]
    cognee.write_case(c)


def test_writes_market_context_and_matches_funnel_enforcement():
    _seed_adjudicated_funnel()
    out = domain_expert.run(detector_result={"total_ring_exposure": 161750.90})

    mc = cognee.read_market_context(domain_expert.RING_REF)
    assert mc is not None
    assert mc["intent_signals"], "expected at least one matched enforcement action"
    # pure_sink/zero_merchant → funnel-account → Community Federal Savings Bank order
    assert out["top_intent"]["id"] == "cfsb_occ"
    assert "funnel-account absorption" in out["typology"]
    assert mc["segment"] and mc["buyer_thesis"]


def test_market_context_carries_geo_grounded_roi():
    """Tier 1 #2 — the Domain Expert grounds a business case (Geo labor rate × run actuals)
    and writes it into the MarketContext for the Reporter."""
    _seed_adjudicated_funnel()
    out = domain_expert.run(detector_result={"total_ring_exposure": 161750.90})

    roi = out["roi"]
    mc = cognee.read_market_context(domain_expert.RING_REF)
    assert mc["roi"] == roi
    # one escalated account → ≥ $5,000 SAR-failure penalty floor (31 CFR §1020.320)
    assert roi["sar_penalty_floor_averted_usd"] == 5000.0
    assert roi["ring_exposure_usd"] == 161750.90
    assert roi["analyst_rate_usd_per_hr"] == [50, 80]   # Geo segment rate sources the cost


def test_handoff_raises_without_adjudication():
    cognee.reset_store()
    cognee.write_case(Case(account="AC-0001", is_candidate=True))   # no action set
    with pytest.raises(ValueError):
        domain_expert.run(detector_result={})
