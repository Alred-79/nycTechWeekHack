"""
Phase 6 gate — criterion 2: each agent demonstrably consumes the previous
agent's Cognee output. We run the agents one at a time and watch the shared
Case node ACCRETE fields — the field is absent before agent N and present after.

Run: uv run pytest tests/test_cognee_handoff.py -q
"""
from __future__ import annotations

import duckdb
import pytest

import cognee_client as cognee
import quorum_truth as gt
from agents import investigator, narrator, ranker, scout
from db import queries

CSV = "data/track02_fraud_watch.csv"
PROBE = "AC-0001"   # a confirmed ring account we can follow through the pipeline


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect()
    queries.load_csv(c, CSV)
    return c


def test_fields_accrete_across_the_pipeline(con):
    # ── After Agent 1 (Detector) ───────────────────────────────────────────
    detector = scout.run(con)
    after_detect = cognee.read_case(PROBE)
    assert after_detect["signals"]          # Detector wrote signals
    assert after_detect.get("p_mule") is None        # Estimator hasn't run
    assert after_detect.get("action") is None        # Adjudicator hasn't run

    # ── After Agent 2 (Estimator) ──────────────────────────────────────────
    ranker.run()
    after_estimate = cognee.read_case(PROBE)
    assert after_estimate.get("p_mule") is not None   # NOW present
    assert after_estimate.get("action") is None       # still no action

    # ── After Agent 3 (Adjudicator) ────────────────────────────────────────
    investigator.run(con, detector_result=detector)
    after_adjudicate = cognee.read_case(PROBE)
    assert after_adjudicate.get("action") is not None  # NOW present
    assert after_adjudicate.get("memo_ref") is None    # Reporter hasn't run

    # ── After Agent 4 (Reporter) ───────────────────────────────────────────
    narrator.run(detector_result=detector)
    after_report = cognee.read_case(PROBE)
    assert after_report.get("memo_ref") is not None    # final layer present


def test_estimator_depends_on_detector_signals(con):
    """Remove the Detector's output and the Estimator must refuse to run."""
    cognee.reset_store()
    from ontology import Case
    cognee.write_case(Case(account="AC-0001", is_candidate=True))
    cognee.update_case_fields("AC-0001", {"signals": None, "dist_stats": None})
    with pytest.raises(ValueError):
        ranker.run()
