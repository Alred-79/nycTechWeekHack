"""
Phase 2 gate — Agent 1 (Detector) rediscovers the ring structure from the data.

Run: uv run pytest tests/test_detector.py -q
"""
from __future__ import annotations

import duckdb
import pytest

import cognee_client as cognee
import quorum_truth as gt
from agents import scout
from db import queries

CSV = "data/track02_fraud_watch.csv"


@pytest.fixture(scope="module")
def cases():
    con = duckdb.connect()
    queries.load_csv(con, CSV)
    scout.run(con)
    by_acct = {c["account"]: c for c in cognee.read_cases()}
    return by_acct


def test_roles_match_oracle(cases):
    for acc in gt.SOURCES:
        assert cases[acc]["role"] == "source", acc
    for acc in gt.RELAYS:
        assert cases[acc]["role"] == "relay", acc
    for acc in gt.SINKS:
        assert cases[acc]["role"] == "sink", acc


def test_all_nine_ring_accounts_surfaced(cases):
    for acc in gt.RING_ACCOUNTS:
        assert acc in cases, f"{acc} not surfaced as a candidate"
        assert cases[acc]["is_candidate"] is True


def test_decoys_surfaced_tagged_and_isolated(cases):
    for acc in gt.DECOYS:
        assert acc in cases, f"decoy {acc} not surfaced"
        assert cases[acc]["decoy_suspect"] is True
        assert cases[acc]["role"] == "none"          # isolated in transfer graph
        assert cases[acc]["signals"]["device_shared"] == 1


def test_boundary_account_surfaced_with_only_cohort_signal(cases):
    c = cases[gt.BOUNDARY]
    assert c["is_candidate"] is True
    sig = c["signals"]
    assert sig["fresh_cohort"] == 1
    # AC-0012 has no transfers, so no structural transfer signals fire
    assert sig["under_threshold"] == 0
    assert sig["pure_sink"] == 0
    assert sig["relay_depth"] == 0
    assert c["decoy_suspect"] is False


def test_every_ring_account_fires_multiple_strong_signals(cases):
    behavioural = ["under_threshold", "fresh_cohort", "zero_merchant",
                   "pure_sink", "automation", "relay_depth"]
    for acc in gt.RING_ACCOUNTS:
        fired = sum(cases[acc]["signals"][s] for s in behavioural)
        assert fired >= 2, f"{acc} only fired {fired} behavioural signals"


def test_dist_stats_written_for_estimator(cases):
    # Agent 2 depends on these — they must exist on the Case in Cognee.
    ds = cases["AC-0001"]["dist_stats"]
    assert ds["n_ac_transfers"] == gt.RING_TXN_COUNT
    assert ds["amount_max"] < gt.RING_TOTAL_USD     # sanity: per-txn, not total
    assert ds["fresh_age_cutoff_days"] > 0


def test_candidate_count_is_small(cases):
    # ~9 ring + AC-0012 + 4 decoys; must not surface the whole bank.
    candidates = [a for a, c in cases.items() if c["is_candidate"]]
    assert len(candidates) <= 16, f"{len(candidates)} candidates — too many"
    assert gt.RING_ACCOUNTS <= set(candidates)
