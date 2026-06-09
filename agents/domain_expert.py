"""
Agent 5 — Domain Expert  (Quorum, the Geo grounding layer)

Runs between the Adjudicator and the Reporter. It reads the *adjudicated ring* from
Cognee (escalated accounts + their decisive signals + ring exposure), then grounds the
case in the real market via Geo (geodo.ai):

  • who Quorum protects (segment + persona) and the labor-cost basis behind C_FP/C_REV
    — from Geo's GTM Researcher (geo_research), cached for offline-safe runs;
  • the "why now" — the single real, dated SAR-failure enforcement action whose signal
    profile matches THIS ring's decisive signals (a peer institution recently penalised for
    exactly the failure this ring would cause). One fact that powers both the memo and
    (Tier 2) the outreach opener.

It writes ONE MarketContext entity to Cognee; the Reporter (Agent 4) consumes it — the
provable Geo handoff. Raises if the Adjudicator hasn't run (no `action` on any Case).

Geo is consumed read-only/cached here (geo_research); no writes, no outreach. The gated
geo_add_document / geo_search_contacts "Ring → Real Buyers" motion is Tier 2 (separate).
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Optional

import cognee_client as cognee
import geo_client
import geodo_market
from ontology import MarketContext

log = logging.getLogger("domain_expert")

RING_REF = "QRM-2026-RING-001"   # matches the Reporter's memo Case ID


def _typology_slug(typology: str) -> str:
    """Stable cache-key slug from a typology label (e.g. 'structuring + layering' → 'structuring_layering').
    Keeps geo_research caches per-typology so a different ring fetches its own brief, not a stale one."""
    base = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in typology.lower())
    return "_".join(base.split()[:3]) or "icp"


def _research(query: str, slug: str, live: bool):
    """Cache-first geo_research keyed by typology, with graceful fallback to the base ICP brief
    so offline/judged runs never go dark when a typology-specific brief hasn't been captured yet."""
    key = f"research_{slug}"
    if not live:
        rec = geo_client.load_cached(key) or geo_client.load_cached("research_icp")
        if rec is not None:
            return rec
    return geo_client.research(query, key=key, live=live)


def _typology_label(decisive: list[str]) -> str:
    """A human typology label derived from the ring's decisive signals."""
    parts = []
    if {"under_threshold", "fresh_cohort"} & set(decisive):
        parts.append("structuring")
    if {"relay_depth", "automation"} & set(decisive):
        parts.append("layering")
    if {"pure_sink", "zero_merchant"} & set(decisive):
        parts.append("funnel-account absorption")
    return " + ".join(parts) or "structuring + layering"


def run(detector_result: Optional[dict] = None,
        on_progress: Optional[callable] = None, *, live: bool = False) -> dict:

    def _prog(msg: str) -> None:
        log.info("DOMAIN_EXPERT: %s", msg)
        if on_progress:
            on_progress(msg)

    # ── Read the adjudicated ring from Cognee (the upstream dependency) ────────
    cases = cognee.read_cases(candidates_only=True)
    adjudicated = [c for c in cases if c.get("action")]
    if not adjudicated:
        raise ValueError(
            "Domain Expert cannot run: missing adjudicated ring from Cognee "
            "(the Adjudicator must run first).")
    escalated = [c for c in adjudicated if c.get("action") == "ESCALATE"]

    counts: Counter = Counter()
    for c in escalated:
        counts.update(c.get("decisive_signals", []))
    decisive = [s for s, _ in counts.most_common()]
    typology = _typology_label(decisive)
    exposure = (detector_result or {}).get("total_ring_exposure")
    _prog(f"Adjudicated ring read from Cognee: {len(escalated)} escalated, "
          f"typology='{typology}', decisive={decisive or 'n/a'}.")

    # ── Match the ring to a real, dated enforcement action (the "why now") ────
    matched = geodo_market.intent_signals(decisive)
    top = matched[0]
    _prog(f"Matched typology → real enforcement intent: {top['institution']} "
          f"[{top['citation']}] (signal_tags {top['signal_tags']}).")

    # ── Ground in Geo's GTM research (cached → offline-safe; live optional) ────
    excerpt = ""
    try:
        exp_str = f"${exposure:,.2f}" if exposure else "an aggregated"
        query = (
            "My product Quorum is an AI multi-agent AML platform for US community banks and "
            f"credit unions. It just detected a {typology} ring of {len(escalated)} accounts "
            f"moving {exp_str} via sub-threshold transfers (decisive signals: "
            f"{', '.join(decisive) or 'n/a'}). Who is the buyer (segment + the specific titles "
            "who champion vs approve), what is their day-to-day pain, and what is the strongest "
            "'why now' angle for an institution like this? Be concrete.")
        res = _research(query, _typology_slug(typology), live=live)
        if isinstance(res, dict):
            excerpt = (res.get("answer") or "")[:700]
        _prog(f"Geo GTM research attached (key=research_{_typology_slug(typology)}, "
              f"{'live' if live else 'cached'}).")
    except Exception as exc:   # noqa: BLE001 — Geo is enrichment, never a hard dependency
        log.warning("Geo research unavailable (%s) — grounding from local registry only.", exc)

    icp = geodo_market.icp()
    buyer_thesis = (
        f"{top['institution']} is the cost of getting this wrong — {top['action']} "
        f"Community banks and credit unions ($1–50B) running rules-based monitoring face the "
        f"same {typology} exposure; this is the buyer who just paid for missing it.")

    # ── Business case: Geo's labor rate × THIS run's actuals (the "what it's worth") ──
    decoys_cleared = sum(1 for c in adjudicated
                         if c.get("action") == "CLEAR" and c.get("decoy_suspect"))
    roi = geodo_market.roi(escalated_count=len(escalated),
                           decoys_cleared=decoys_cleared,
                           ring_exposure_usd=exposure or 0.0)
    _prog(f"ROI grounded in Geo rate: {geodo_market.roi_line(roi)}")

    mc = MarketContext(
        ring_ref=RING_REF,
        segment=icp["segment"],
        persona=icp["persona_time_per_case"],
        asset_range=icp["asset_range"],
        buyer_thesis=buyer_thesis,
        intent_signals=matched,
        cost_basis=geodo_market.labor_costs(),
        roi=roi,
        research_excerpt=excerpt,
        messaging_angles=geodo_market.messaging_angles(),
        source="Geo (geodo.ai MCP) + verified FinCEN/OCC enforcement",
        captured_on=geodo_market.CAPTURED_ON,
    )
    cognee.write_market_context(mc)
    _prog(f"Wrote MarketContext to Cognee (ring={RING_REF}); Reporter will consume it.")

    cognee.add_agent_layer(
        "domain_expert",
        "DOMAIN EXPERT market grounding (Agent 5, via Geo):\n"
        f"- Segment: {icp['segment']} (persona: {icp['persona_time_per_case']}).\n"
        f"- Why now: {top['institution']} — {top['citation']} ({top['date']}).\n"
        f"- Buyer thesis: {buyer_thesis}\n"
        f"- Labor-cost basis (Geo): ${geodo_market.LABOR_COSTS['analyst_loaded_rate_usd_per_hr'][0]}–"
        f"{geodo_market.LABOR_COSTS['analyst_loaded_rate_usd_per_hr'][1]}/hr.\n"
        f"- ROI: {geodo_market.roi_line(roi)}")

    return {
        "ring_ref": RING_REF,
        "typology": typology,
        "decisive_signals": decisive,
        "top_intent": top,
        "intent_signals": matched,
        "segment": icp["segment"],
        "buyer_thesis": buyer_thesis,
        "roi": roi,
        "research_grounded": bool(excerpt),
    }
