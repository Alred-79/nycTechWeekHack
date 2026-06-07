"""
Phase 0 — answer-key oracle.

These tests assert the verified facts about the dataset DIRECTLY against the
CSV, independent of the Quorum pipeline. They are the foundation every later
gate builds on: if these ever go red, our understanding of the data (not just
our code) is wrong.

Run: uv run pytest tests/test_ground_truth.py -q
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict

import pytest

import quorum_truth as gt

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "track02_fraud_watch.csv")


@pytest.fixture(scope="module")
def rows():
    with open(CSV_PATH, newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def ac_transfers(rows):
    """The account-to-account transfers (counterparty is another AC account)."""
    return [r for r in rows if r["counterparty_id"].startswith("AC")]


def test_total_transaction_count(rows):
    assert len(rows) == 5000


def test_ring_transfer_count(ac_transfers):
    assert len(ac_transfers) == gt.RING_TXN_COUNT


def test_dollar_reconciliation(ac_transfers):
    total = sum(float(r["amount"]) for r in ac_transfers)
    assert abs(total - gt.RING_TOTAL_USD) < gt.RECONCILIATION_TOLERANCE_USD


def test_ring_accounts(ac_transfers):
    accts = {r["account_id"] for r in ac_transfers} | {
        r["counterparty_id"] for r in ac_transfers
    }
    assert accts == gt.RING_ACCOUNTS


def test_exactly_six_edges(ac_transfers):
    edges = {(r["account_id"], r["counterparty_id"]) for r in ac_transfers}
    assert edges == gt.RING_EDGES


def test_no_cycles(ac_transfers):
    """The defining fact: the transfer graph is acyclic (not 'circular loops')."""
    g = defaultdict(set)
    for r in ac_transfers:
        g[r["account_id"]].add(r["counterparty_id"])

    color: dict[str, int] = {}  # 0=visiting, 1=done

    def has_cycle(u: str) -> bool:
        color[u] = 0
        for v in g[u]:
            if color.get(v) == 0:
                return True
            if v not in color and has_cycle(v):
                return True
        color[u] = 1
        return False

    assert not any(has_cycle(n) for n in list(g) if n not in color)


def test_roles_sources_relays_sinks(ac_transfers):
    senders = {r["account_id"] for r in ac_transfers}
    receivers = {r["counterparty_id"] for r in ac_transfers}
    assert (senders - receivers) == gt.SOURCES
    assert (receivers - senders) == gt.SINKS
    assert (senders & receivers) == gt.RELAYS


def test_under_threshold_amounts(ac_transfers):
    amounts = [float(r["amount"]) for r in ac_transfers]
    assert min(amounts) >= 400.0
    assert max(amounts) < 1000.0  # never crosses a plausible $1,000 floor


def test_decoys_share_device_but_are_not_ring(rows, ac_transfers):
    ring_accts = {r["account_id"] for r in ac_transfers} | {
        r["counterparty_id"] for r in ac_transfers
    }
    # No decoy participates in the transfer graph.
    assert not (gt.DECOYS & ring_accts)

    # The decoys are exactly the accounts that share a device fingerprint.
    dev_accounts = defaultdict(set)
    for r in rows:
        dev_accounts[r["device_id"]].add(r["account_id"])
    shared = set()
    for accts in dev_accounts.values():
        if len(accts) > 1:
            shared |= accts
    assert shared == gt.DECOYS


def test_boundary_account_has_no_transfers(ac_transfers):
    """AC-0012 never sends or receives an AC→AC transfer — hence 'review', not 'escalate'."""
    involved = {r["account_id"] for r in ac_transfers} | {
        r["counterparty_id"] for r in ac_transfers
    }
    assert gt.BOUNDARY not in involved


def test_tau_derivation():
    assert abs(gt.tau() - 0.05) < 1e-9
