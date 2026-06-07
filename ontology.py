"""
Data ontology for Quorum — the typed entities that flow through Cognee.

The pipeline is account-centric: one Case per account, accreting fields as the
four agents run. See agents/ for who writes what.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class Action(str, Enum):
    ESCALATE = "ESCALATE"
    CLEAR = "CLEAR"
    REVIEW = "REVIEW"   # abstention — route to a human


class AccountRole(str, Enum):
    """Topological role within the AC→AC transfer graph."""
    SOURCE = "source"   # sends, never receives
    RELAY = "relay"     # receives then forwards (layering)
    SINK = "sink"       # receives, never sends
    NONE = "none"       # not in the transfer graph


@dataclass
class Case:
    """
    The Quorum case object: one per account, accreting fields as the four
    agents run. Each agent REQUIRES the previous agent's fields to do its job —
    a provable dependency through Cognee (criterion 2).

      After Agent 1 (Detector):    account, role, signals, is_candidate,
                                   decoy_suspect, dist_stats
      After Agent 2 (Estimator):   + p_mule, credible_interval, signal_contributions
      After Agent 3 (Adjudicator): + action, E_loss_escalate, E_loss_clear,
                                     EVPI, quorum, decisive_signals
      After Agent 4 (Reporter):    + memo_ref, typology, dollar_contribution,
                                     closing_rule
    """
    account: str

    # ── Agent 1 (Detector) ────────────────────────────────────────────────
    role: AccountRole = AccountRole.NONE
    signals: dict = field(default_factory=dict)
    is_candidate: bool = False
    decoy_suspect: bool = False
    dist_stats: dict = field(default_factory=dict)
    detect_reason: str = ""

    # ── Agent 2 (Estimator) ───────────────────────────────────────────────
    p_mule: Optional[float] = None
    credible_interval: Optional[list] = None       # [lo, hi]
    signal_contributions: dict = field(default_factory=dict)

    # ── Agent 3 (Adjudicator) ─────────────────────────────────────────────
    action: Optional[Action] = None
    E_loss_escalate: Optional[float] = None
    E_loss_clear: Optional[float] = None
    EVPI: Optional[float] = None
    quorum: Optional[bool] = None
    decisive_signals: list = field(default_factory=list)
    action_reason: str = ""

    # ── Agent 4 (Reporter) ────────────────────────────────────────────────
    memo_ref: Optional[str] = None
    typology: Optional[str] = None
    dollar_contribution: Optional[float] = None
    closing_rule: Optional[str] = None

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
