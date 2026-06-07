"""
Phase 4 gate — Agent 3 (Adjudicator) turns posteriors into cost-optimal actions,
abstaining on the genuinely ambiguous account.

Run: uv run pytest tests/test_adjudicator.py -q
"""
from __future__ import annotations

import duckdb
import pytest

import cognee_client as cognee
import quorum_truth as gt
from agents import investigator, ranker, scout
from db import queries

CSV = "data/track02_fraud_watch.csv"


@pytest.fixture(scope="module")
def run_result():
    con = duckdb.connect()
    queries.load_csv(con, CSV)
    detector = scout.run(con)
    ranker.run()
    result = investigator.run(con, detector_result=detector)
    cases = {c["account"]: c for c in cognee.read_cases()}
    return result, cases


def test_all_nine_ring_accounts_escalated(run_result):
    _, cases = run_result
    for acc in gt.RING_ACCOUNTS:
        assert cases[acc]["action"] == "ESCALATE", f"{acc} → {cases[acc]['action']}"


def test_no_ring_account_silently_cleared(run_result):
    _, cases = run_result
    for acc in gt.RING_ACCOUNTS:
        assert cases[acc]["action"] != "CLEAR"


def test_decoys_cleared(run_result):
    _, cases = run_result
    for acc in gt.DECOYS:
        assert cases[acc]["action"] == "CLEAR", f"decoy {acc} → {cases[acc]['action']}"


def test_boundary_routed_to_review(run_result):
    _, cases = run_result
    c = cases[gt.BOUNDARY]
    assert c["action"] == "REVIEW"
    lo, hi = c["credible_interval"]
    assert lo < gt.tau() < hi          # the abstention is justified by a straddling interval
    assert c["EVPI"] > investigator.C_REV


def test_caseload(run_result):
    result, _ = run_result
    assert result["escalate_count"] + result["review_count"] <= 12
    assert result["clear_ratio"] > 0.95


def test_decisions_are_explained(run_result):
    _, cases = run_result
    for acc in gt.RING_ACCOUNTS | gt.DECOYS | {gt.BOUNDARY}:
        c = cases[acc]
        for fld in ("E_loss_escalate", "E_loss_clear", "EVPI", "action_reason"):
            assert c.get(fld) is not None and c.get(fld) != "", f"{acc} missing {fld}"
