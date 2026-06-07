"""
Phase 5 gate — Agent 4 (Reporter) produces a memo that reconciles to the cent,
names the ring, and emits the learned closing rule; every surfaced Case is fully
explainable.

Run: uv run pytest tests/test_reporter.py -q
"""
from __future__ import annotations

import duckdb
import pytest

import cognee_client as cognee
import quorum_truth as gt
from agents import investigator, narrator, ranker, scout
from db import queries

CSV = "data/track02_fraud_watch.csv"


@pytest.fixture(scope="module")
def run_result():
    con = duckdb.connect()
    queries.load_csv(con, CSV)
    detector = scout.run(con)
    ranker.run()
    investigator.run(con, detector_result=detector)
    reporter = narrator.run(detector_result=detector)
    cases = {c["account"]: c for c in cognee.read_cases()}
    return reporter, cases


def test_dollar_reconciliation_to_the_cent(run_result):
    reporter, _ = run_result
    assert reporter["reconciliation_ok"] is True
    assert abs(reporter["reconciled_total"] - gt.RING_TOTAL_USD) < gt.RECONCILIATION_TOLERANCE_USD


def test_memo_names_all_ring_accounts(run_result):
    reporter, _ = run_result
    memo = reporter["memo_text"]
    for acc in gt.RING_ACCOUNTS:
        assert acc in memo, f"{acc} missing from memo"


def test_memo_mentions_abstention_and_decoy(run_result):
    reporter, _ = run_result
    memo = reporter["memo_text"]
    assert gt.BOUNDARY in memo                       # AC-0012 review beat
    assert any(d in memo for d in gt.DECOYS)         # decoy-cleared beat


def test_closing_rule_present(run_result):
    reporter, _ = run_result
    assert reporter["closing_rule"]
    assert "AC→AC" in reporter["closing_rule"] or "transfers" in reporter["closing_rule"]


def test_explainability_no_bare_scores(run_result):
    """Every surfaced Case carries the full evidence chain — zero black boxes."""
    _, cases = run_result
    for acc in gt.RING_ACCOUNTS | gt.DECOYS | {gt.BOUNDARY}:
        c = cases[acc]
        assert c.get("signals")
        assert c.get("p_mule") is not None
        assert c.get("credible_interval") is not None
        assert c.get("E_loss_escalate") is not None
        assert c.get("E_loss_clear") is not None


def test_escalated_cases_have_reporter_fields(run_result):
    _, cases = run_result
    for acc in gt.RING_ACCOUNTS:
        c = cases[acc]
        assert c.get("memo_ref")
        assert c.get("typology")
        assert c.get("closing_rule")
