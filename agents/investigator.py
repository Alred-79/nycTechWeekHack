"""
Agent 3 — Adjudicator  (Quorum)

Reads each Case's posterior (p_mule + credible interval) from Cognee and turns
it into an ACTION by Bayesian decision theory — minimising expected loss under
an explicit cost matrix, not thresholding a raw score.

    τ = C_FP / (C_FP + C_FN)                  loss-justified escalation threshold
    E[loss | escalate] = (1 − p)·C_FP
    E[loss | clear]    = p·C_FN
    EVPI               = min(E_escalate, E_clear)   value of a perfect answer

Decisions are deterministic (argmin) so there is never a "the model said so".
When the credible interval STRADDLES τ and a human review would pay for itself
(EVPI > C_rev), the agent ABSTAINS and routes the case to review instead of
guessing — the one behaviour a raw score cannot offer.

Writes action, E_loss_escalate, E_loss_clear, EVPI, quorum, decisive_signals.
"""
from __future__ import annotations

import logging
from typing import Optional

import duckdb

import cognee_client as cognee
from ontology import Action

log = logging.getLogger("adjudicator")

# Cost matrix (institution-tunable; the FN ≫ FP asymmetry is the AML reality).
C_FN = 4750.0   # clearing a true mule
C_FP = 250.0    # escalating a clean account
C_REV = 150.0   # a human review (resolves the case)
TAU = C_FP / (C_FP + C_FN)   # = 0.05


def _decisive_signals(contributions: dict, k: int = 3) -> list[str]:
    """The signals that moved the decision most (largest logit contributions)."""
    items = [(name, val) for name, val in (contributions or {}).items()
             if name != "bias"]
    items.sort(key=lambda kv: abs(kv[1]), reverse=True)
    return [name for name, _ in items[:k]]


def run(con: Optional[duckdb.DuckDBPyConnection] = None,
        detector_result: Optional[dict] = None,
        on_progress: Optional[callable] = None) -> dict:

    def _prog(msg: str) -> None:
        log.info("ADJUDICATOR: %s", msg)
        if on_progress:
            on_progress(msg)

    _prog(f"Reading posteriors from Cognee. Cost matrix C_FN={C_FN:.0f} "
          f"C_FP={C_FP:.0f} C_rev={C_REV:.0f} → τ={TAU:.3f}")
    cases = cognee.read_cases(candidates_only=True)

    escalate, review, clear = [], [], []
    layer_lines: list[str] = []
    for case in cases:
        acct = case["account"]
        p = case.get("p_mule")
        ci = case.get("credible_interval")
        if p is None or ci is None:
            raise ValueError(
                f"Adjudicator cannot run on {acct}: missing posterior from the Estimator.")
        lo, hi = ci

        e_escalate = (1.0 - p) * C_FP
        e_clear = p * C_FN
        evpi = min(e_escalate, e_clear)
        straddles = lo < TAU < hi
        quorum = not straddles   # one-sided interval → confident → we have quorum

        if straddles and evpi > C_REV:
            action = Action.REVIEW
        elif e_escalate < e_clear:      # equivalently p > τ
            action = Action.ESCALATE
        else:
            action = Action.CLEAR

        decisive = _decisive_signals(case.get("signal_contributions", {}))

        reason = (
            f"p_mule={p:.3f}, CI=[{lo:.3f}, {hi:.3f}], τ={TAU:.3f}. "
            f"E[loss|escalate]=(1−{p:.3f})·{C_FP:.0f}=${e_escalate:.2f}; "
            f"E[loss|clear]={p:.3f}·{C_FN:.0f}=${e_clear:.2f}; "
            f"EVPI=${evpi:.2f}. "
            + (f"Interval straddles τ and EVPI>${C_REV:.0f} → ABSTAIN to human review."
               if action == Action.REVIEW else
               f"Interval is one-sided (quorum) → argmin expected loss = {action.value}.")
            + (f" Decisive signals: {', '.join(decisive)}." if decisive else "")
        )

        cognee.update_case_fields(acct, {
            "action": action,
            "E_loss_escalate": round(e_escalate, 2),
            "E_loss_clear": round(e_clear, 2),
            "EVPI": round(evpi, 2),
            "quorum": quorum,
            "decisive_signals": decisive,
            "action_reason": reason,
        })
        log.info("ADJUDICATOR  account=%s  action=%s  p=%.3f  EVPI=$%.2f  quorum=%s",
                 acct, action.value, p, evpi, quorum)

        layer_lines.append(f"- {acct}: {action.value} (p_mule={p:.3f}, EVPI=${evpi:.2f}, "
                           f"quorum={quorum}); {reason}")
        {"ESCALATE": escalate, "REVIEW": review, "CLEAR": clear}[action.value].append(acct)

    cognee.add_agent_layer("adjudicator",
                           "ADJUDICATOR decisions (Agent 3, Bayesian decision theory):\n"
                           + "\n".join(layer_lines))

    n_total = None
    if detector_result and detector_result.get("dist_stats"):
        n_total = detector_result["dist_stats"].get("n_accounts_total")
    # Accounts not surfaced as candidates were auto-cleared by the Detector.
    n_cleared_total = (n_total - len(escalate) - len(review)) if n_total else len(clear)
    clear_ratio = (n_cleared_total / n_total) if n_total else None

    _prog(f"Adjudicator complete. ESCALATE={len(escalate)} "
          f"REVIEW={len(review)} CLEAR(surfaced)={len(clear)} "
          + (f"clear_ratio={clear_ratio:.3f}" if clear_ratio else ""))

    return {
        "escalate": escalate,
        "review": review,
        "clear": clear,
        "escalate_count": len(escalate),
        "review_count": len(review),
        "clear_count": len(clear),
        "clear_ratio": clear_ratio,
        "tau": TAU,
    }
