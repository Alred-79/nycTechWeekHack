"""
geodo_market.py — the Geo (geodo.ai) MARKET-intelligence layer for Quorum's Domain Expert.

This is the market half of the Domain-Expert research, distinct from the regulatory half in
geodo_research.py:

  • ICP / personas / labor-cost RATE  ← Geo's GTM Researcher (geo_research), captured live via
    the MCP and snapshotted to geo_cache/research_icp.json.
  • Real, dated SAR-failure ENFORCEMENT actions, tagged by the behavioural signals they map to
    ← verified against FinCEN / OCC primary sources (NOT geo_research, whose named examples are
    unreliable). Each is both the "highest-intent buyer" trigger AND the memo's "why now": a peer
    institution recently penalised for exactly the failure this ring would cause.
  • A redacted summary of the real buyer institutions sourced via geo_search_contacts (person
    PII is never committed — only institutions, titles, counts; last names are masked by Geo
    until the gated geo_enrich_contact).

Every entry carries `source` + `captured_on`. Geo's labor RATE ($50–80/hr) sources C_FP/C_REV;
the per-case HOURS remain Quorum's assumption, so τ=0.05 is unchanged (see geodo_research).
"""
from __future__ import annotations

CAPTURED_ON = "2026-06-08"
GEO_RESEARCH = "geo:geo_research"          # Geo GTM Researcher (cached research_icp.json)
GEO_CONTACTS = "geo:geo_search_contacts"   # Geo contact sourcing (Apollo)
VERIFIED = "regulatory"                    # primary-source verified (FinCEN / OCC)

# ── ICP & personas (Geo GTM Researcher) ───────────────────────────────────────
ICP: dict = {
    "segment": "BSA/AML compliance teams at US community banks and credit unions ($1–50B assets)",
    "asset_range": "$1–50B in assets",
    "persona_time_per_case": "~3 minutes per alert",
    "operating_reality": "90%+ false-positive alert rates; small teams — attention is the scarce resource",
    "personas": [
        {"title": "BSA Officer", "pains": ["accountable for SARs that don't get filed",
            "regulatory scrutiny / penalties"], "trigger": "recent exam or peer enforcement action"},
        {"title": "AML Analyst", "pains": ["alert overload, minutes per case",
            "manual rework from weak predictive accuracy"], "trigger": "mandate to cut review time"},
        {"title": "Chief Compliance Officer", "pains": ["fines / reputational damage",
            "do more with a tight budget"], "trigger": "board-level risk-management mandate"},
        {"title": "Head of Financial Crimes", "pains": ["data overload obscures insight",
            "needs fast, defensible decisions"], "trigger": "rising local financial-crime incidence"},
    ],
    "source": GEO_RESEARCH, "captured_on": CAPTURED_ON,
}

# ── Real, dated SAR-failure enforcement actions (verified) ─────────────────────
# signal_tags use the Detector/Adjudicator vocabulary (under_threshold, fresh_cohort,
# zero_merchant, pure_sink, automation, relay_depth) so the Domain Expert can match the
# detected ring's decisive_signals to the most relevant peer action — see intent_signals().
INTENT_SIGNALS: list[dict] = [
    {
        "id": "cfsb_occ",
        "institution": "Community Federal Savings Bank (NY)",
        "action": "OCC consent order (AA-ENF-2025-21): payment-processor growth without "
                  "commensurate controls; ordered a risk-based SAR review program and a SAR "
                  "lookback for previously UNREPORTED suspicious activity.",
        "penalty_usd": None,
        "date": "2026 (OCC AA-ENF-2025-21)",
        "citation": "OCC Consent Order AA-ENF-2025-21 — Community Federal Savings Bank",
        "url": "https://www.bankingdive.com/news/occ-community-federal-savings-bank-new-york-aml-bsa-sar-deficiencies-fintech-partner/821272/",
        "signal_tags": ["pure_sink", "zero_merchant", "under_threshold"],
        "source": VERIFIED, "captured_on": CAPTURED_ON,
    },
    {
        "id": "clear_fork_occ",
        "institution": "Clear Fork Bank (TX community bank)",
        "action": "OCC consent order for BSA/AML program deficiencies — proof regulators pursue "
                  "SMALL community banks, not only large institutions.",
        "penalty_usd": None,
        "date": "2024-12",
        "citation": "OCC Consent Order — Clear Fork Bank (Dec 2024)",
        "url": "https://natlawreview.com/article/community-banks-and-bsaaml-compliance-occs-consent-order-clear-fork-bank-proves",
        "signal_tags": ["under_threshold", "fresh_cohort"],
        "source": VERIFIED, "captured_on": CAPTURED_ON,
    },
    {
        "id": "north_dade_fincen",
        "institution": "North Dade Community Development FCU (FL credit union)",
        "action": "FinCEN $300,000 civil money penalty: the AML program never scaled to high-risk "
                  "international wire activity moving hundreds of millions of dollars.",
        "penalty_usd": 300000.0,
        "date": "2014-11-25",
        "citation": "FinCEN CMP — In re North Dade Community Development FCU (Nov 25, 2014)",
        "url": "https://www.fincen.gov/news/enforcement-actions/matter-north-dade-community-development-federal-credit-union",
        "signal_tags": ["relay_depth", "automation"],
        "source": VERIFIED, "captured_on": CAPTURED_ON,
    },
]

# ── Real buyer institutions sourced via Geo (redacted: institutions/titles only) ──
BUYERS: dict = {
    "note": "Real BSA/AML decision-makers at community banks / credit unions matching the ICP, "
            "sourced via geo_search_contacts. Last names are masked by Geo until the gated "
            "geo_enrich_contact; person PII is NOT committed — only institutions, titles, counts.",
    "titles": ["BSA Officer", "BSA/AML Officer", "Chief Compliance Officer"],
    "institutions": ["Piermont Bank", "CFG Bank", "Country Bank", "Woodsboro Bank",
                     "Orrstown Bank", "Velocity Credit Union", "Citadel Credit Union",
                     "FAIRWINDS Credit Union", "Workers Credit Union", "America First Credit Union"],
    "sample_count": 10,
    "source": GEO_CONTACTS, "captured_on": CAPTURED_ON,
}

# ── Messaging angles per persona (Geo GTM Researcher) ──────────────────────────
# Curated from geo_research's "Messaging Angles" + persona sections (research_icp.json).
# Keyed by persona theme so the GTM opener can lead with the value-prop that lands for the
# specific title it is addressed to (one shared dated-enforcement "why now", persona-tuned ask).
# `title_match` are lowercase substrings matched against a sourced contact's title.
MESSAGING_ANGLES: dict = {
    # Matched in order; keep buckets disjoint so distinct titles → distinct angles.
    "bsa_officer": {
        "title_match": ["bsa"],
        "angle": "regulatory assurance — file the SARs you're accountable for, with examiner-ready "
                 "reasoning attached, so a missed filing never becomes your enforcement action",
        "source": GEO_RESEARCH, "captured_on": CAPTURED_ON,
    },
    "aml_analyst": {
        "title_match": ["analyst", "investigat"],
        "angle": "efficiency + accuracy — surface the coordinated rings rules engines miss without "
                 "drowning you in false positives, so your minutes-per-alert go to real cases",
        "source": GEO_RESEARCH, "captured_on": CAPTURED_ON,
    },
    "executive": {
        "title_match": ["cco", "chief", "compliance officer", "head", "financial crimes",
                        "director", "vp", "president"],
        "angle": "resource optimization — reclaim analyst capacity and cut audit exposure with a "
                 "defensible, fully-reasoned triage layer, doing more on a tight compliance budget",
        "source": GEO_RESEARCH, "captured_on": CAPTURED_ON,
    },
}

# Fallback theme when a title matches nothing specific.
_DEFAULT_ANGLE = "bsa_officer"


# ── Labor-cost basis (Geo) behind C_FP / C_REV ────────────────────────────────
LABOR_COSTS: dict = {
    "analyst_loaded_rate_usd_per_hr": [50, 80],
    "aml_team_size": [10, 25],
    "rationale": "C_FP ≈ 2–3 analyst-hours (investigate + document); C_REV ≈ 1 analyst-hour. "
                 "Geo segment research supports the RATE ($50–80/hr); hours-per-case is Quorum's "
                 "assumption. Constants stay (C_FP=250, C_REV=150) so τ=0.05 holds.",
    "source": GEO_RESEARCH, "captured_on": CAPTURED_ON,
}


def icp() -> dict:
    return ICP


def intent_signals(signals: list[str] | None = None) -> list[dict]:
    """Real dated enforcement actions whose signal_tags intersect the ring's decisive signals
    (registry order). Empty/None → all (whole-ring context); no match → all (never empty)."""
    sig = set(signals or [])
    if not sig:
        return list(INTENT_SIGNALS)
    matched = [s for s in INTENT_SIGNALS if sig & set(s["signal_tags"])]
    return matched or list(INTENT_SIGNALS)


def top_intent(signals: list[str] | None = None) -> dict:
    """The single most-relevant enforcement action for a ring (the memo's 'why now')."""
    return intent_signals(signals)[0]


def labor_costs() -> dict:
    return LABOR_COSTS


def buyers() -> dict:
    return BUYERS


def messaging_angles() -> dict:
    return MESSAGING_ANGLES


def angle_for_title(title: str | None) -> dict:
    """The persona messaging angle whose title_match best fits a sourced contact's title."""
    t = (title or "").lower()
    for theme, rec in MESSAGING_ANGLES.items():
        if any(m in t for m in rec["title_match"]):
            return {"theme": theme, **rec}
    rec = MESSAGING_ANGLES[_DEFAULT_ANGLE]
    return {"theme": _DEFAULT_ANGLE, **rec}


# ── ROI / business case (Geo labor rate × this run's actuals) ──────────────────
# The "what is this worth" line for the buyer. Two grounded components:
#   • regulatory loss/penalty exposure averted by catching the ring (31 CFR floor
#     + the real ring exposure the Detector reconstructed);
#   • analyst capacity reclaimed, priced at Geo's segment labor RATE ($50–80/hr).
# Hours-per-case are Quorum's stated assumption (kept explicit); only the RATE is
# Geo-sourced. Every figure carries where it came from, same discipline as ICP.
SAR_PENALTY_FLOOR_USD = 5000.0      # 31 CFR §1020.320 — per-violation SAR civil money penalty floor
HOURS_PER_FALSE_POSITIVE = 2.5      # Quorum assumption: investigate + document a chased FP
HOURS_PER_TRUE_POSITIVE = 4.0       # Quorum assumption: investigate + file a SAR on a real mule


def roi(escalated_count: int, decoys_cleared: int = 0,
        ring_exposure_usd: float = 0.0) -> dict:
    """The business case for one detected ring, grounded in Geo's labor rate + run actuals.

    `escalated_count`  — true mules the ring contains (loss + penalty exposure).
    `decoys_cleared`   — false suspects the system cleared (decoy resistance → capacity reclaimed).
    `ring_exposure_usd`— dollars the Detector reconstructed moving through the ring.
    """
    rate_lo, rate_hi = LABOR_COSTS["analyst_loaded_rate_usd_per_hr"]
    penalty_floor = SAR_PENALTY_FLOOR_USD * max(escalated_count, 0)
    hours_reclaimed = round(decoys_cleared * HOURS_PER_FALSE_POSITIVE, 1)
    capacity_lo = round(hours_reclaimed * rate_lo, 2)
    capacity_hi = round(hours_reclaimed * rate_hi, 2)
    return {
        "ring_exposure_usd": round(ring_exposure_usd or 0.0, 2),
        "sar_penalty_floor_averted_usd": penalty_floor,
        "analyst_hours_reclaimed": hours_reclaimed,
        "capacity_reclaimed_usd": [capacity_lo, capacity_hi],
        "analyst_rate_usd_per_hr": [rate_lo, rate_hi],
        "assumptions": {
            "hours_per_false_positive": HOURS_PER_FALSE_POSITIVE,
            "hours_per_true_positive": HOURS_PER_TRUE_POSITIVE,
            "sar_penalty_floor_usd": SAR_PENALTY_FLOOR_USD,
        },
        "basis": ("Loss/penalty exposure is regulatory (31 CFR §1020.320 $5,000/violation floor + "
                  "Detector-reconstructed ring exposure); analyst capacity is priced at Geo's segment "
                  "rate ($50–80/hr), hours-per-case are Quorum's stated assumption."),
        "source": f"{GEO_RESEARCH} (rate) + regulatory (penalty floor) + Quorum run actuals",
        "captured_on": CAPTURED_ON,
    }


def roi_line(r: dict) -> str:
    """One memo/UI-ready sentence from a roi() dict."""
    cap = r.get("capacity_reclaimed_usd") or [0, 0]
    return (f"Catching this ring averts ≥ ${r.get('sar_penalty_floor_averted_usd', 0):,.0f} in "
            f"SAR-failure penalty exposure (31 CFR floor) on ${r.get('ring_exposure_usd', 0):,.2f} "
            f"of reconstructed flow; decoy resistance reclaimed {r.get('analyst_hours_reclaimed', 0)} "
            f"analyst-hours (≈ ${cap[0]:,.0f}–${cap[1]:,.0f} at Geo's $"
            f"{r['analyst_rate_usd_per_hr'][0]}–${r['analyst_rate_usd_per_hr'][1]}/hr rate).")


def summary() -> dict:
    """Whole payload for the UI 'Market context (Geodo)' panel."""
    return {"icp": ICP, "intent_signals": INTENT_SIGNALS, "buyers": BUYERS,
            "labor_costs": LABOR_COSTS, "messaging_angles": MESSAGING_ANGLES}


def validate() -> list[str]:
    """Provenance-gap check (used by tests): every record needs source + captured_on."""
    gaps: list[str] = []
    records = [("icp", ICP), ("buyers", BUYERS), ("labor_costs", LABOR_COSTS)]
    records += [(s["id"], s) for s in INTENT_SIGNALS]
    records += [(f"angle:{k}", v) for k, v in MESSAGING_ANGLES.items()]
    for name, r in records:
        if not r.get("source"):
            gaps.append(f"{name}: missing source")
        if not r.get("captured_on"):
            gaps.append(f"{name}: missing captured_on")
    return gaps
