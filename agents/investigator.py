"""
Agent 3 — Adjudicator  (Quorum)

Reads each candidate Case's posterior (p_mule + 94% credible interval, written by
the Estimator) from Cognee and turns it into a COST-OPTIMAL action via Bayesian
decision theory — never a bare threshold on a score:

  • τ (the loss-justified escalation threshold) falls out of the cost matrix:
        τ = C_FP / (C_FP + C_FN) = 0.05
    Escalating a clean account costs C_FP; clearing a true mule costs C_FN. The
    break-even posterior is exactly τ.

  • For each account we compute the expected loss of each action:
        E[loss | escalate] = C_FP · (1 − p)
        E[loss | clear]    = C_FN · p
    and the expected value of perfect information:
        EVPI = min(E[loss | escalate], E[loss | clear])
    (with perfect information you would always act correctly, so the avoidable
    loss is exactly the smaller of the two expected losses).

  • ABSTENTION (route to a human, action REVIEW) is itself cost-justified: when the
    credible interval STRADDLES τ (genuine ambiguity) AND EVPI exceeds the cost of
    a human review C_REV, paying for the review beats guessing. Otherwise we take
    the cheaper of escalate/clear by the point estimate. `quorum` records whether
    the interval was decisively on one side of τ (a confident verdict).

This reproduces the three behaviours the product promises: the coordinated ring
escalates, the planted device-sharing decoys clear (their posterior is low/tight),
and the single genuinely ambiguous account (fresh cohort, no transfers) is routed
to review rather than guessed. Every decision carries its arithmetic in
`action_reason` — explainability, not a score.

Writes the Agent-3 fields onto each Case in Cognee; the Reporter consumes them.
"""
from __future__ import annotations

import logging
from typing import Optional

import duckdb

import cognee_client as cognee
from ontology import Action

log = logging.getLogger("adjudicator")

# ── Cost matrix → loss-justified threshold τ (the operative copy; MUST match
#    quorum_truth / geodo_research: 4750 / 250 / 150 so τ = 0.05). ──────────────
C_FN = 4750.0   # cost of clearing a true mule (BSA penalty exposure — regulatory)
C_FP = 250.0    # cost of escalating a clean account (~2–3 analyst-hours — labor)
C_REV = 150.0   # cost of a focused human review that resolves the case (~1 hour)
TAU = C_FP / (C_FP + C_FN)   # = 0.05

# Behavioural signals that can justify an escalation (device_shared is excluded —
# it is non-discriminating by construction, so it never drives a decision).
BEHAVIOURAL = ["under_threshold", "fresh_cohort", "zero_merchant",
               "pure_sink", "automation", "relay_depth"]


def _decisive(signals: dict | None) -> list[str]:
    """The behavioural signals that fired for this account (drives the verdict)."""
    s = signals or {}
    return [name for name in BEHAVIOURAL if s.get(name)]


def run(con: Optional[duckdb.DuckDBPyConnection] = None,
        detector_result: Optional[dict] = None,
        on_progress: Optional[callable] = None) -> dict:

    def _prog(msg: str) -> None:
        log.info("ADJUDICATOR: %s", msg)
        if on_progress:
            on_progress(msg)

    cases = cognee.read_cases(candidates_only=True)
    if not cases:
        raise ValueError(
            "Adjudicator cannot run: no candidate Cases in Cognee "
            "(the Detector + Estimator must run first).")
    missing = [c["account"] for c in cases if c.get("p_mule") is None]
    if missing:
        raise ValueError(
            f"Adjudicator cannot run: missing posterior (p_mule) for {missing[:5]}"
            f"{'…' if len(missing) > 5 else ''} — the Estimator must run first.")

    _prog(f"Adjudicating {len(cases)} candidates against τ={TAU:.2f} "
          f"(C_FN={C_FN:.0f}, C_FP={C_FP:.0f}, C_REV={C_REV:.0f}).")

    escalate = review = clear = 0
    for c in cases:
        acct = c["account"]
        p = float(c.get("p_mule") or 0.0)
        ci = c.get("credible_interval") or [p, p]
        lo, hi = float(ci[0]), float(ci[1])

        e_loss_escalate = round(C_FP * (1.0 - p), 2)   # pay C_FP if actually clean
        e_loss_clear = round(C_FN * p, 2)              # pay C_FN if actually a mule
        evpi = round(min(e_loss_escalate, e_loss_clear), 2)
        straddles_tau = lo < TAU < hi
        quorum = not straddles_tau                     # decisively one side of τ?
        decisive = _decisive(c.get("signals"))

        if straddles_tau and evpi > C_REV:
            action = Action.REVIEW
            review += 1
            reason = (
                f"94% CI [{lo:.3f}, {hi:.3f}] straddles τ={TAU:.2f}; "
                f"EVPI=${evpi:,.2f} > review cost ${C_REV:,.0f} → abstain and route "
                f"to a human rather than guess.")
        elif p > TAU:
            action = Action.ESCALATE
            escalate += 1
            reason = (
                f"p_mule={p:.3f} > τ={TAU:.2f}; E[loss|escalate]=${e_loss_escalate:,.2f} "
                f"< E[loss|clear]=${e_loss_clear:,.2f}. Decisive signals: "
                f"{', '.join(decisive) or 'n/a'}.")
        else:
            action = Action.CLEAR
            clear += 1
            why = ("decoy: device-shared but isolated in the transfer graph"
                   if c.get("decoy_suspect") else
                   "behavioural signals absent or non-discriminating")
            reason = (
                f"p_mule={p:.3f} ≤ τ={TAU:.2f}; E[loss|clear]=${e_loss_clear:,.2f} "
                f"< E[loss|escalate]=${e_loss_escalate:,.2f} ({why}). CLEARED.")

        cognee.update_case_fields(acct, {
            "action": action,
            "E_loss_escalate": e_loss_escalate,
            "E_loss_clear": e_loss_clear,
            "EVPI": evpi,
            "quorum": quorum,
            "decisive_signals": decisive,
            "action_reason": reason,
        })
        log.info("ADJUDICATOR  account=%s  action=%s  p=%.3f  EVPI=%.2f  quorum=%s",
                 acct, action.value, p, evpi, quorum)

    # clear_ratio is measured over the WHOLE account universe — the ~280 accounts
    # the Detector auto-cleared (never surfaced) are cleared too, so the system's
    # selectivity is honest (it flags a tiny fraction, not the candidate pool only).
    n_total = ((detector_result or {}).get("dist_stats") or {}).get("n_accounts_total")
    total = int(n_total) if n_total else len(cases)
    cleared_total = total - escalate - review
    clear_ratio = round(cleared_total / total, 4) if total else 0.0

    _prog(f"Verdicts: escalate={escalate}, review={review}, clear(candidates)={clear}; "
          f"clear_ratio={clear_ratio:.4f} over {total} accounts.")

    cognee.add_agent_layer(
        "adjudicator",
        "ADJUDICATOR verdicts (Agent 3, Bayesian decision theory):\n"
        f"- τ={TAU:.2f} from cost matrix (C_FN={C_FN:.0f}/C_FP={C_FP:.0f}/C_REV={C_REV:.0f}).\n"
        f"- escalate={escalate}, review(abstain)={review}, clear={cleared_total} "
        f"(clear_ratio={clear_ratio:.4f}).\n"
        + "\n".join(f"- {c['account']}: {c.get('action_reason', '')}" for c in cases))

    return {
        "tau": TAU,
        "escalate_count": escalate,
        "review_count": review,
        "clear_count": cleared_total,
        "clear_ratio": clear_ratio,
        "candidates": len(cases),
    }
