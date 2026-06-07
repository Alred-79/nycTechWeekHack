"""
Quorum ground-truth oracle.

This module is NOT used by the detection logic — it is the answer key the
detection logic is *validated against*. Every constant here was verified
directly against data/track02_fraud_watch.csv (see tests/test_ground_truth.py).

Keeping it separate is deliberate: the pipeline must rediscover these facts
from the data (structural + behavioral signals), not read them from here.
Tests import this; agents must not.
"""
from __future__ import annotations

# ── The ring (9 accounts that appear in the AC→AC transfer graph) ─────────────
RING_ACCOUNTS = {
    "AC-0001", "AC-0002", "AC-0003", "AC-0005", "AC-0006",
    "AC-0007", "AC-0009", "AC-0010", "AC-0011",
}

# Topological roles within the 6 directed transfer edges.
SOURCES = {"AC-0001", "AC-0005", "AC-0010"}   # send, never receive
RELAYS = {"AC-0009", "AC-0011"}               # receive then forward
SINKS = {"AC-0002", "AC-0003", "AC-0006", "AC-0007"}  # receive, never send

# The 6 directed edges (sender → receiver). No cycles exist.
RING_EDGES = {
    ("AC-0001", "AC-0002"),
    ("AC-0005", "AC-0006"),
    ("AC-0005", "AC-0009"),
    ("AC-0009", "AC-0007"),
    ("AC-0010", "AC-0011"),
    ("AC-0011", "AC-0003"),
}

# ── The planted decoy: shared device fingerprints, NOT ring members ───────────
DECOYS = {"AC-0045", "AC-0127", "AC-0131", "AC-0192"}

# ── The boundary case: fresh cohort, no transfers → route to human review ─────
BOUNDARY = "AC-0012"

# ── Dollar reconciliation target (sum of the 250 AC→AC transfers) ─────────────
RING_TOTAL_USD = 161750.90
RECONCILIATION_TOLERANCE_USD = 0.01

RING_TXN_COUNT = 250

# ── Cost matrix → loss-justified threshold τ (Quorum §5) ──────────────────────
C_FN = 4750.0   # cost of clearing a true mule (large — AML reality)
C_FP = 250.0    # cost of escalating a clean account
C_REV = 150.0   # cost of a human review (resolves the case)
TAU = C_FP / (C_FP + C_FN)   # = 0.05


def tau() -> float:
    """Loss-justified escalation threshold, derived from the cost matrix."""
    return C_FP / (C_FP + C_FN)
