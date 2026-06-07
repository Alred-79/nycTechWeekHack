"""
Agent 1 — Detector  (Quorum)

Reads the raw transactions, isolates the AC→AC transfer layer STRUCTURALLY
(no synthetic watermark), derives each account's topological role
(source / relay / sink), computes the discriminating behavioural signals, and
explicitly tags the device-sharing accounts as a DECOY (shared device but
isolated in the transfer graph).

Crucially it also writes empirical *distribution stats* to Cognee — the raw
material the Estimator (Agent 2) learns its thresholds from, so nothing is a
magic constant and the handoff is a provable dependency.

Writes one Case node per surfaced account to Cognee.
"""
from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from datetime import datetime
from typing import Optional

import duckdb

import cognee_client as cognee
from db import queries
from ontology import AccountRole, Case

log = logging.getLogger("detector")

# Structural constants (documented, not the answer key):
INFERRED_FLOOR_USD = 1000.0   # plausible monitoring floor; transfers sit below it
AUTOMATION_MIN_REPEAT = 20    # a legit account rarely repeat-transfers to ONE
#                               counterparty this many times in 90 days


def _to_date(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    return datetime.fromisoformat(str(v)).date()


def _fresh_age_cutoff(ages: list[int]) -> float:
    """
    Learn the 'fresh cohort' boundary from data, not a magic 30 days.

    Look inside the youngest decile and find the largest consecutive age gap;
    the cutoff is the midpoint of that gap. On Crestline this isolates the
    Feb-2026 cohort (ages 13–21d) from the next account (93d) cleanly.
    """
    if not ages:
        return 0.0
    s = sorted(ages)
    decile = s[: max(3, len(s) // 10)]
    best_gap, cutoff = 0.0, decile[-1]
    for lo, hi in zip(decile, decile[1:]):
        if hi - lo > best_gap:
            best_gap, cutoff = hi - lo, (lo + hi) / 2.0
    return float(cutoff)


def run(con: duckdb.DuckDBPyConnection,
        on_progress: Optional[callable] = None) -> dict:

    def _prog(msg: str) -> None:
        log.info("DETECTOR: %s", msg)
        if on_progress:
            on_progress(msg)

    # ── Load the structural layers ────────────────────────────────────────
    _prog("Isolating AC→AC transfers structurally (counterparty LIKE 'AC-%')...")
    transfers = queries.get_ac_transfers(con)
    universe = queries.get_account_universe(con)
    facts = queries.get_account_facts(con)
    shared_devices = queries.get_shared_devices(con)
    _prog(f"{len(transfers)} transfers across {len(universe)} accounts; "
          f"{len(shared_devices)} shared-device clusters.")

    # ── Graph degrees, roles, per-edge repeat counts ──────────────────────
    in_amt: dict[str, list[float]] = defaultdict(list)
    out_amt: dict[str, list[float]] = defaultdict(list)
    edge_count: dict[tuple, int] = defaultdict(int)
    for t in transfers:
        out_amt[t["sender"]].append(t["amount"])
        in_amt[t["receiver"]].append(t["amount"])
        edge_count[(t["sender"], t["receiver"])] += 1

    def role_of(acc: str) -> AccountRole:
        i, o = len(in_amt[acc]), len(out_amt[acc])
        if o and not i:
            return AccountRole.SOURCE
        if i and o:
            return AccountRole.RELAY
        if i and not o:
            return AccountRole.SINK
        return AccountRole.NONE

    # Accounts that share a device with at least one other account.
    device_shared_accounts: set[str] = set()
    for dev in shared_devices:
        if len(dev["accounts"]) > 1:
            device_shared_accounts.update(dev["accounts"])

    # ── Empirical distributions (the material Agent 2 learns from) ─────────
    amounts = [t["amount"] for t in transfers]
    ages: dict[str, int] = {}
    ds_start = con.execute("SELECT MIN(timestamp) FROM transactions").fetchone()[0]
    ds_start_date = _to_date(ds_start)
    for acc, f in facts.items():
        od = _to_date(f["open_date"])
        if od is not None:
            ages[acc] = (ds_start_date - od).days
    fresh_cutoff = _fresh_age_cutoff(list(ages.values()))

    dist_stats = {
        "n_ac_transfers": len(transfers),
        "amount_min": round(min(amounts), 2) if amounts else None,
        "amount_p50": round(statistics.median(amounts), 2) if amounts else None,
        "amount_max": round(max(amounts), 2) if amounts else None,
        "inferred_floor_usd": INFERRED_FLOOR_USD,
        "fresh_age_cutoff_days": round(fresh_cutoff, 1),
        "fresh_cutoff_method": "largest age-gap in youngest decile",
        "automation_min_repeat": AUTOMATION_MIN_REPEAT,
        "n_accounts_total": len(universe),
        "dataset_start": str(ds_start_date),
    }
    _prog(f"Learned fresh-cohort cutoff = {fresh_cutoff:.0f} days "
          f"(amounts {dist_stats['amount_min']}–{dist_stats['amount_max']}).")

    # ── Build a Case per account; surface only candidates ──────────────────
    cognee.reset_store()
    cases: list[Case] = []
    for acc in universe:
        f = facts.get(acc, {"open_date": None, "n_originated": 0,
                            "n_merchant": 0, "n_ac_out": 0, "devices": []})
        role = role_of(acc)
        i_deg, o_deg = len(in_amt[acc]), len(out_amt[acc])
        involved_amts = in_amt[acc] + out_amt[acc]
        age = ages.get(acc)

        max_edge = max([c for (s, _), c in edge_count.items() if s == acc] or [0])

        sig = {
            "under_threshold": int(bool(involved_amts) and max(involved_amts) < INFERRED_FLOOR_USD),
            "fresh_cohort": int(age is not None and age <= fresh_cutoff),
            "zero_merchant": int((i_deg or o_deg) and f["n_merchant"] == 0),
            "pure_sink": int(i_deg > 0 and o_deg == 0 and f["n_originated"] == 0),
            "automation": int(max_edge >= AUTOMATION_MIN_REPEAT),
            "relay_depth": int(role == AccountRole.RELAY),
            "device_shared": int(acc in device_shared_accounts),
            # evidence (used for uncertainty + the memo)
            "_in_deg": i_deg, "_out_deg": o_deg,
            "_n_transfers": i_deg + o_deg,
            "_n_originated": f["n_originated"], "_n_merchant": f["n_merchant"],
            "_amount_max": round(max(involved_amts), 2) if involved_amts else None,
            "_age_days": age,
            "_transfer_usd": round(sum(involved_amts), 2) if involved_amts else 0.0,
        }

        behavioural = ["under_threshold", "fresh_cohort", "zero_merchant",
                       "pure_sink", "automation", "relay_depth"]
        fired = [s for s in behavioural if sig[s]]
        is_candidate = bool(fired) or bool(sig["device_shared"])
        decoy_suspect = bool(sig["device_shared"]) and role == AccountRole.NONE

        if not is_candidate:
            continue   # the ~280 cleared accounts are never surfaced

        why_parts = []
        if sig["pure_sink"]:
            why_parts.append("pure sink: receives transfers but originates nothing")
        if sig["relay_depth"]:
            why_parts.append("relay: receives then forwards (layering role)")
        if sig["under_threshold"]:
            why_parts.append(f"all transfer amounts < ${INFERRED_FLOOR_USD:,.0f}")
        if sig["fresh_cohort"]:
            why_parts.append(f"fresh-cohort account (age {age}d ≤ {fresh_cutoff:.0f}d cutoff)")
        if sig["zero_merchant"]:
            why_parts.append("no merchant spend despite account-to-account activity")
        if sig["automation"]:
            why_parts.append(f"{max_edge} repeat transfers to one counterparty (automation)")
        if decoy_suspect:
            why_parts.append("DECOY: shares a device but is isolated in the transfer graph")

        case = Case(
            account=acc,
            role=role,
            signals=sig,
            is_candidate=True,
            decoy_suspect=decoy_suspect,
            dist_stats=dist_stats,
            detect_reason="; ".join(why_parts) if why_parts else "device co-occurrence only",
        )
        cases.append(case)
        cognee.write_case(case)
        log.info("DETECTOR WRITE  account=%s  role=%s  signals_fired=%s  decoy=%s",
                 acc, role.value, fired, decoy_suspect)

    _prog(f"Surfaced {len(cases)} candidate Cases "
          f"(of {len(universe)} accounts); rest auto-cleared.")

    # Contribute this agent's layer to the Cognee graph (no-op unless building).
    cognee.add_agent_layer("detector", "DETECTOR findings (Agent 1):\n" + "\n".join(
        f"- {c.account}: role={c.role.value}; "
        f"signals={[k for k, v in c.signals.items() if not k.startswith('_') and v]}; "
        f"candidate={c.is_candidate}; decoy_suspect={c.decoy_suspect}; {c.detect_reason}"
        for c in cases))

    edges = [
        {"sender": s, "receiver": r, "count": c,
         "total_usd": round(sum(a for t in transfers
                                if t["sender"] == s and t["receiver"] == r
                                for a in [t["amount"]]), 2)}
        for (s, r), c in sorted(edge_count.items())
    ]

    return {
        "cases": cases,
        "candidate_accounts": [c.account for c in cases],
        "dist_stats": dist_stats,
        "transfers": transfers,
        "edges": edges,
        "shared_devices": shared_devices,
        "total_ring_exposure": round(sum(amounts), 2),
        "total_ring_txns": len(transfers),
    }
