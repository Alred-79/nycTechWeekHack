"""
Regulatory research registry — the Domain-Expert REGULATORY layer (Quorum).

This is the regulatory half of the Domain-Expert research: real-world AML *legal* facts —
enforcement/typology precedents and the SAR-penalty figures behind the cost matrix — each
verified against its primary source (FinCEN / eCFR / DOJ / FATF / IRS BSA penalty guidance).

The MARKET half (ICP, real buyers, the analyst labor rate, and dated peer enforcement as
buying intent) lives in geodo_market.py, sourced from Geo (geodo.ai). The split is
deliberate: Geo is a GTM/market-intelligence platform, not a statute-lookup tool, so legal
citations are attributed to the regulators — never to Geo.

Two tables:
  • PRECEDENTS  — real cases/advisories/typologies, each tagged to the behavioural
                  ``decisive_signals`` it explains, so Agent 4 can attach the right
                  precedent to the right account.
  • COST_BASIS  — the C_FN / C_FP / C_REV figures with their rationale and source,
                  so the loss-justified threshold τ is sourced, not invented.
"""
from __future__ import annotations

# ── Real-world precedents (verified) ──────────────────────────────────────────
# signal_tags use the same names as the Detector's signals / the Adjudicator's
# decisive_signals (see agents/narrator.py:_closing_rule and agents/scout.py).
PRECEDENTS: list[dict] = [
    {
        "id": "liberty_reserve",
        "title": "Liberty Reserve — $6B layering prosecution",
        "citation": "United States v. Budovsky, DOJ/SDNY indictment (2013)",
        "url": "https://www.ice.gov/news/releases/charges-filed-against-one-largest-digital-currency-companies-employees-running-6",
        "year": 2013,
        "source": "U.S. Department of Justice",
        "signal_tags": ["relay_depth", "automation"],
        "relevance": (
            "The largest international money-laundering prosecution to date: funds were "
            "moved through layers of accounts/exchangers, structured so individual "
            "transactions stayed anonymous and untraceable — the layering pattern this "
            "ring replicates at community-bank scale."
        ),
    },
    {
        "id": "fincen_funnel",
        "title": "FinCEN Advisory FIN-2014-A005 — Funnel Accounts & TBML",
        "citation": "FinCEN Advisory FIN-2014-A005 (May 28, 2014)",
        "url": "https://www.fincen.gov/resources/advisories/fincen-advisory-fin-2014-a005",
        "year": 2014,
        "source": "Financial Crimes Enforcement Network (FinCEN)",
        "signal_tags": ["pure_sink", "relay_depth", "zero_merchant"],
        "relevance": (
            "A funnel account aggregates many deposits in one location and moves them out "
            "rapidly with little other activity — exactly the sink/relay accounts here that "
            "absorb many sub-threshold transfers and show no merchant spend."
        ),
    },
    {
        "id": "fatf_structuring",
        "title": "FATF structuring / smurfing & account-cluster typology",
        "citation": "FATF — ML typologies (placement & layering stages)",
        "url": "https://www.fincen.gov/financial-action-task-force-money-laundering-fatf",
        "year": 2024,
        "source": "Financial Action Task Force (FATF)",
        "signal_tags": ["under_threshold", "fresh_cohort"],
        "relevance": (
            "Smurfing splits value into amounts below reporting thresholds across many "
            "freshly-opened accounts that funnel into a collecting account — matching the "
            "recency-outlier cohort firing sub-$1,000 transfers."
        ),
    },
    {
        "id": "cfr_sar_obligation",
        "title": "SAR filing obligation — 31 CFR §1020.320",
        "citation": "31 CFR §1020.320 (Reports by banks of suspicious transactions)",
        "url": "https://www.ecfr.gov/current/title-31/subtitle-B/chapter-X/part-1020/subpart-C/section-1020.320",
        "year": 2024,
        "source": "31 CFR (Bank Secrecy Act implementing regs)",
        "signal_tags": ["under_threshold"],
        "relevance": (
            "A bank must file a SAR when a transaction involves or aggregates at least "
            "$5,000 and it suspects suspicious activity (filed within 30 days of detection). "
            "Each transfer stays under $1,000, but the chains aggregate far past the $5,000 "
            "SAR floor."
        ),
    },
]

# ── Cost matrix provenance (verified) ─────────────────────────────────────────
# NOTE: values are duplicated in agents/investigator.py (the operative copy). They
# MUST stay 4750 / 250 / 150 so τ = C_FP/(C_FP+C_FN) = 0.05. This table is the
# *why*, surfaced in the memo and UI.
COST_BASIS: dict[str, dict] = {
    "C_FN": {
        "value": 4750.0,
        "label": "cost of clearing a true mule",
        "rationale": (
            "A failure-to-file under the BSA carries a civil money penalty starting at "
            "$5,000 per violation (up to $1M/day), before counting the laundered funds "
            "themselves. We anchor C_FN just below the $5,000 statutory floor as a "
            "conservative per-case expected loss."
        ),
        "source": "31 CFR §1020.320 + IRS IRM 4.26.7 (BSA penalties); FinCEN enforcement "
                  "(Capital One $390M, USAA $140M for SAR failures)",
        "url": "https://www.irs.gov/irm/part4/irm_04-026-007",
    },
    "C_FP": {
        "value": 250.0,
        "label": "cost of escalating a clean account",
        "rationale": (
            "~2–3 analyst-hours of investigation and documentation. Geo (geodo.ai) segment "
            "research puts the fully-loaded community-bank AML analyst rate at $50–80/hr; the "
            "per-case HOURS are Quorum's assumption, so τ=0.05 is unchanged."
        ),
        "source": "Geo (geodo.ai) segment research — analyst $50–80/hr (see geodo_market.LABOR_COSTS)",
        "url": "",
    },
    "C_REV": {
        "value": 150.0,
        "label": "cost of one targeted human review",
        "rationale": "~1 analyst-hour for a focused second look that resolves the case "
                     "(Geo analyst rate $50–80/hr; hours are Quorum's assumption).",
        "source": "Geo (geodo.ai) segment research — analyst $50–80/hr (see geodo_market.LABOR_COSTS)",
        "url": "",
    },
}


# ── Domain-expert review (attribution) ────────────────────────────────────────
# A practicing domain expert reviewed the AML modelling choices below for
# real-world plausibility. Attribution is to the individual, not the firm — we
# credit his expertise, not an institutional endorsement.
DOMAIN_REVIEW: dict = {
    "name": "Luca Bommarito",
    "role": "Lead Data Scientist & PM, Deloitte",
    "scope": "Reviewed the AML typology mapping and cost-matrix assumptions for "
             "real-world plausibility.",
    "date": "2026-06-08",
}


def review_line() -> str:
    """One-line domain-review attribution for the memo footer / UI."""
    r = DOMAIN_REVIEW
    return f"{r['name']} — {r['role']} ({r['date']}). {r['scope']}"


def precedents_for(signals: list[str] | None) -> list[dict]:
    """The precedents whose signal_tags intersect the given signals, in registry
    order, de-duplicated. Empty/None signals → all precedents (whole-ring context)."""
    sig = set(signals or [])
    if not sig:
        return list(PRECEDENTS)
    return [p for p in PRECEDENTS if sig & set(p["signal_tags"])]


def cost_source(name: str) -> dict:
    """Provenance for one cost-matrix constant (``C_FN`` / ``C_FP`` / ``C_REV``)."""
    return COST_BASIS.get(name, {})


def format_precedent(p: dict) -> str:
    """One memo-ready line: '<title> — <citation>'."""
    return f"{p['title']} — {p['citation']}"


def summary() -> dict:
    """Compact payload for the snapshot / UI 'Sources (Geodo research)' panel."""
    return {"precedents": PRECEDENTS, "cost_basis": COST_BASIS, "review": DOMAIN_REVIEW}
