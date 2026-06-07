"""
Phase 3 gate — Agent 2 (Estimator) produces calibrated probabilities with an
honest uncertainty band, and learns from Agent 1's signals (not hardcoded).

Run: uv run pytest tests/test_estimator.py -q
"""
from __future__ import annotations

import duckdb
import pytest

import cognee_client as cognee
import quorum_truth as gt
from agents import ranker, scout
from db import queries

CSV = "data/track02_fraud_watch.csv"
TAU = gt.tau()


@pytest.fixture(scope="module")
def cases():
    con = duckdb.connect()
    queries.load_csv(con, CSV)
    scout.run(con)
    ranker.run()
    return {c["account"]: c for c in cognee.read_cases()}


def test_ring_accounts_high_probability(cases):
    for acc in gt.RING_ACCOUNTS:
        assert cases[acc]["p_mule"] > 0.9, f"{acc} p={cases[acc]['p_mule']}"


def test_decoys_low_and_confident(cases):
    for acc in gt.DECOYS:
        c = cases[acc]
        assert c["p_mule"] < 0.1, f"decoy {acc} p={c['p_mule']}"
        # confidently below the threshold — upper credible bound stays under τ
        assert c["credible_interval"][1] < TAU, f"decoy {acc} CI={c['credible_interval']}"


def test_boundary_straddles_threshold_and_is_widest(cases):
    c = cases[gt.BOUNDARY]
    lo, hi = c["credible_interval"]
    # the credible interval crosses τ → genuinely ambiguous
    assert lo < TAU < hi, f"AC-0012 CI={c['credible_interval']} does not straddle τ={TAU}"
    width = hi - lo
    others = [cases[a]["credible_interval"] for a in cases if a != gt.BOUNDARY]
    assert all(width > (h - l) for l, h in others), "AC-0012 is not the widest interval"


def test_credible_intervals_well_formed(cases):
    for acc, c in cases.items():
        lo, hi = c["credible_interval"]
        assert 0.0 <= lo <= c["p_mule"] <= hi <= 1.0, f"{acc} malformed CI"


def test_not_hardcoded_model_responds_to_signals():
    """Inject ring signals into a clean-looking account → its probability rises."""
    cognee.reset_store()
    from ontology import AccountRole, Case
    clean = Case(account="AC-TEST-CLEAN", role=AccountRole.NONE,
                 signals={"under_threshold": 0, "fresh_cohort": 0, "zero_merchant": 0,
                          "pure_sink": 0, "automation": 0, "relay_depth": 0,
                          "device_shared": 0, "_n_transfers": 0},
                 is_candidate=True, dist_stats={"fresh_age_cutoff_days": 57})
    cognee.write_case(clean)
    ranker.run()
    p_before = cognee.read_case("AC-TEST-CLEAN")["p_mule"]
    assert p_before < 0.1

    # Now give it the ring's behavioural signature (with the structural evidence
    # the applicability mask reads, so fresh_cohort/automation/relay count).
    cognee.update_case_fields("AC-TEST-CLEAN", {
        "signals": {"under_threshold": 1, "fresh_cohort": 1, "zero_merchant": 1,
                    "pure_sink": 0, "automation": 1, "relay_depth": 1,
                    "device_shared": 0, "_n_transfers": 42, "_out_deg": 42,
                    "_age_days": 15}})
    ranker.run()
    p_after = cognee.read_case("AC-TEST-CLEAN")["p_mule"]
    assert p_after > 0.5, f"model did not respond to signals: {p_before} → {p_after}"


def test_estimator_requires_detector_output():
    """Without signals/dist_stats (Agent 1's writes), the Estimator must fail."""
    cognee.reset_store()
    from ontology import Case
    cognee.write_case(Case(account="AC-NO-SIGNALS", is_candidate=True))
    # signals defaults to {} (present) but dist_stats is {} too; force the
    # missing-dependency path by clearing them.
    cognee.update_case_fields("AC-NO-SIGNALS", {"signals": None, "dist_stats": None})
    with pytest.raises(ValueError):
        ranker.run()
