"""
Locks the attribution split (a Geo founder would notice a mislabel):
  • regulatory precedents are attributed to regulators — NEVER to Geo;
  • C_FN (BSA penalty) is regulatory; C_FP / C_REV (analyst labor) are Geo;
  • geodo_market provenance is complete and its intent signals are real + dated;
  • the cost constants are unchanged (τ = 0.05 stays valid).

Run: uv run pytest tests/test_geodo_attribution.py -q
"""
from __future__ import annotations

import geodo_market
import geodo_research


def test_regulatory_precedents_not_attributed_to_geo():
    for p in geodo_research.PRECEDENTS:
        assert "geo" not in p["source"].lower(), f"{p['id']} wrongly attributed to Geo"


def test_cfn_regulatory_cfp_crev_geo():
    cb = geodo_research.COST_BASIS
    assert "geo" not in cb["C_FN"]["source"].lower()
    assert "geo" in cb["C_FP"]["source"].lower()
    assert "geo" in cb["C_REV"]["source"].lower()


def test_geodo_market_provenance_complete():
    assert geodo_market.validate() == []


def test_intent_signals_are_real_and_dated():
    for s in geodo_market.INTENT_SIGNALS:
        assert s["date"] and s["citation"] and s["url"]
        assert s["source"] == "regulatory"


def test_cost_constants_unchanged_tau_stable():
    from agents import investigator
    assert investigator.C_FN == 4750 and investigator.C_FP == 250 and investigator.C_REV == 150
    assert abs(investigator.TAU - 0.05) < 1e-9
    assert geodo_market.labor_costs()["analyst_loaded_rate_usd_per_hr"] == [50, 80]
