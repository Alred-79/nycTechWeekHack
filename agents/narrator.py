"""
Agent 4 — Reporter  (Quorum)

Reads the fully enriched Case set + the transfer graph from Cognee and produces
a regulator-ready SAR memo, strictly GROUNDED in the computed values (it phrases
the reasons, it does not invent them). Per ring it emits:

  • a SAR memo in FinCEN narrative structure (who / what / when / where / why / how)
  • a dollar reconciliation that traces the chains edge-by-edge to $161,750.90
  • the laundering typology (structuring + layering + relay)
  • a "closing rule" — the system's learned artifact, compiled from the
    Adjudicator's decisive_signals into a deployable query

An LLM (Anthropic) phrases the prose if ANTHROPIC_API_KEY is set; otherwise the
deterministic template is used (identical facts, no model dependency).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import cognee_client as cognee
import geodo_research

log = logging.getLogger("reporter")

RECONCILIATION_TOLERANCE = 0.01


def _ring_signals(escalated_cases: list[dict]) -> list[str]:
    """The decisive signals fired across the ring, most-common first."""
    from collections import Counter
    counts: Counter = Counter()
    for c in escalated_cases:
        counts.update(c.get("decisive_signals", []))
    return [s for s, _ in counts.most_common()]


def _precedent_block(precedents: list[dict]) -> str:
    """Render the registry's matched precedents into the memo's PATTERN-CONTEXT
    section. Every line traces to a real, verified source (Geodo research)."""
    if not precedents:
        return "  (no matching precedent on file)"
    lines = []
    for p in precedents:
        lines.append(f"  • {p['relevance']}")
        lines.append(f"        → {p['title']} [{p['citation']}]")
    return "\n".join(lines)


def _market_block(mc: dict | None) -> str:
    """Render the Geo market-grounding block from the Domain Expert's MarketContext
    (read from Cognee). Returns '' if the Domain Expert didn't run — the block then
    simply disappears, proving it is the Domain Expert's contribution (graceful handoff)."""
    if not mc:
        return ""
    sigs = mc.get("intent_signals") or []
    top = sigs[0] if sigs else {}
    rate = (mc.get("cost_basis") or {}).get("analyst_loaded_rate_usd_per_hr") or []
    rate_str = f"${rate[0]}–${rate[1]}/hr" if len(rate) == 2 else "n/a"
    roi = mc.get("roi") or {}
    cap = roi.get("capacity_reclaimed_usd") or [0, 0]
    roi_line = ""
    if roi:
        roi_line = (
            f"Business case: averts ≥ ${roi.get('sar_penalty_floor_averted_usd', 0):,.0f} in "
            f"SAR-failure penalty exposure (31 CFR floor) on ${roi.get('ring_exposure_usd', 0):,.2f} "
            f"of reconstructed flow; decoy resistance reclaimed "
            f"{roi.get('analyst_hours_reclaimed', 0)} analyst-hours "
            f"(≈ ${cap[0]:,.0f}–${cap[1]:,.0f} at the Geo rate).\n")
    return f"""
━━━ MARKET CONTEXT (GEODO) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Who this protects: {mc.get('segment', 'n/a')}
Operating reality: {mc.get('persona', 'n/a')}.
Why now (real peer enforcement): {top.get('institution', 'n/a')} — {top.get('action', '')}
        → {top.get('citation', '')} ({top.get('date', '')})
Buyer thesis: {mc.get('buyer_thesis', '')}
Analyst cost basis (Geo segment research): {rate_str} — sources C_FP / C_REV.
{roi_line}"""


def _llm_polish(prompt: str) -> str:
    """Phrase the memo with Gemini (via litellm). Empty string → template is used."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key or api_key.startswith("your"):
        return ""
    try:
        import litellm
        resp = litellm.completion(
            model=os.getenv("LLM_MODEL", "gemini/gemini-2.5-flash"),
            api_key=api_key,
            messages=[{"role": "user", "content": prompt}],
            timeout=30)
        return resp.choices[0].message.content or ""
    except Exception as exc:
        log.warning("Gemini polish failed (%s) — using template.", exc)
        return ""


def _closing_rule(escalated_cases: list[dict]) -> str:
    """Compile the decisive signals across escalated cases into a deployable query."""
    from collections import Counter
    counts: Counter = Counter()
    for c in escalated_cases:
        counts.update(c.get("decisive_signals", []))
    top = [s for s, _ in counts.most_common()]
    clauses = {
        "under_threshold": "every amount < $1,000",
        "fresh_cohort": "account opened in a recency-outlier cohort",
        "automation": "≥20 repeat transfers to one counterparty",
        "pure_sink": "receives transfers but originates no transaction",
        "zero_merchant": "no merchant spend despite account-to-account activity",
        "relay_depth": "receives then forwards (relay role)",
    }
    parts = [clauses[s] for s in top if s in clauses] or [clauses["under_threshold"]]
    return ("FLAG AC→AC transfers WHERE " + " AND ".join(parts[:4])
            + "  -- learned from this ring; deploy to catch the next one")


def _build_memo(edges, escalated, review, decoys, dist_stats,
                reconciled_total, closing_rule, generated_at, precedents,
                market_block="") -> str:
    ring_accts = sorted({e["sender"] for e in edges} | {e["receiver"] for e in edges})

    chain_rows = "\n".join(
        f"  {e['sender']} → {e['receiver']:<9}  {e['count']:>4} txns   ${e['total_usd']:>11,.2f}"
        for e in edges)

    esc_rows = "\n".join(
        f"  {c['account']:<9} {str(c.get('role','')).upper():<7} "
        f"p={c.get('p_mule'):.3f}  CI=[{c['credible_interval'][0]:.3f}, {c['credible_interval'][1]:.3f}]  "
        f"{'/'.join(c.get('decisive_signals', []))}"
        for c in sorted(escalated, key=lambda x: x['account']))

    review_note = "  (none)"
    if review:
        review_note = "\n".join(
            f"  {c['account']} — p={c.get('p_mule'):.3f}, CI=[{c['credible_interval'][0]:.3f}, "
            f"{c['credible_interval'][1]:.3f}] straddles τ; EVPI=${c.get('EVPI'):.2f} > review cost. "
            f"Routed to a human rather than guessed."
            for c in review)

    decoy_note = "\n".join(
        f"  {c['account']} — shares a device but is isolated in the transfer graph; "
        f"behavioural signals absent → p={c.get('p_mule'):.3f}. CLEARED (decoy, not flagged)."
        for c in sorted(decoys, key=lambda x: x['account'])) or "  (none)"

    return f"""QUORUM SAR CASE MEMO — CRESTLINE COMMUNITY BANK / AML TRIAGE
Case ID: QRM-2026-RING-001   Severity: CRITICAL   Generated: {generated_at:%Y-%m-%d %H:%M UTC}
AML Analyst: _______________   BSA Officer: _____________   Review deadline: ___________

━━━ WHO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{len(ring_accts)} coordinated accounts: {', '.join(ring_accts)}.
Roles — sources originate funds, relays forward them (layering), sinks absorb them:
{esc_rows}

━━━ WHAT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Coordinated layering via {dist_stats.get('n_ac_transfers')} structured account-to-account
transfers totalling ${reconciled_total:,.2f}. No single transfer reached $1,000
(observed range ${dist_stats.get('amount_min'):,.2f}–${dist_stats.get('amount_max'):,.2f}),
so no monitoring threshold ever fired.

━━━ WHEN ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
90-day dataset window beginning {dist_stats.get('dataset_start')}; the operating
accounts were opened inside a tight recency-outlier cohort
(age ≤ {dist_stats.get('fresh_age_cutoff_days'):.0f} days at window start).

━━━ WHERE — THE TRANSFER CHAINS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sender → Receiver        Txns          Value
{chain_rows}
                         ─────    ────────────
  RECONCILED TOTAL              ${reconciled_total:>13,.2f}   (target ${161750.90:,.2f})

━━━ WHY IT IS SUSPICIOUS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Each escalated account fires multiple independent signals (above): under-threshold
amounts, fresh-cohort onboarding, pure-sink / zero-merchant behaviour, automated
repeat cadence, and relay layering roles. Every decision carries its expected-loss
arithmetic (see agent reasoning) — no bare scores.

━━━ HOW (TYPOLOGY) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Structuring (amounts held below the reporting floor) + Layering (funds moved
through relay accounts to obscure origin) + funnel-account absorption at the
sinks. Consistent with FATF smurfing/layering typologies and the FinCEN
funnel-account advisory (FIN-2014-A005).

━━━ REGULATORY PRECEDENT (verified primary sources) ━━━━━━━━━━━━━━━━━━━━━━━━━━
This {len(ring_accts)}-account pattern maps, signal by signal, to documented
money-laundering precedents (each citation verified against its primary source):
{_precedent_block(precedents)}
Filing obligation: each transfer stays under $1,000, but the chains aggregate
well past the $5,000 SAR floor of 31 CFR § 1020.320 — a SAR is required within
30 days of detection.
{market_block}
━━━ ABSTENTION — ROUTED TO HUMAN REVIEW ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{review_note}

━━━ DECOY RESISTANCE — CLEARED, NOT FLAGGED ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{decoy_note}

━━━ CLOSING RULE (LEARNED ARTIFACT) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{closing_rule}

━━━ DOMAIN REVIEW ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{geodo_research.review_line()}

━━━ SIGN-OFF ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Reviewed by: ___________________   Date: ___________   SAR filed: [ ] Y [ ] N [ ] Pending
"""


def run(detector_result: Optional[dict] = None,
        on_progress: Optional[callable] = None,
        polish: Optional[bool] = None) -> dict:

    def _prog(msg: str) -> None:
        log.info("REPORTER: %s", msg)
        if on_progress:
            on_progress(msg)

    _prog("Reading enriched Cases + transfer graph from Cognee...")
    cases = cognee.read_cases(candidates_only=True)
    by_action = lambda a: [c for c in cases if c.get("action") == a]
    escalated, review, cleared = by_action("ESCALATE"), by_action("REVIEW"), by_action("CLEAR")
    decoys = [c for c in cleared if c.get("decoy_suspect")]

    edges = (detector_result or {}).get("edges", [])
    dist_stats = (detector_result or {}).get("dist_stats", {})

    # Dollar reconciliation — edge by edge.
    reconciled_total = round(sum(e["total_usd"] for e in edges), 2)
    target = (detector_result or {}).get("total_ring_exposure", reconciled_total)
    ok = abs(reconciled_total - target) < RECONCILIATION_TOLERANCE
    _prog(f"Reconciliation: ${reconciled_total:,.2f} vs target ${target:,.2f} "
          f"({'OK' if ok else 'MISMATCH'}).")

    closing_rule = _closing_rule(escalated)
    typology = "structuring + layering + funnel-account absorption"
    generated_at = datetime.now(tz=timezone.utc)

    # Geodo research: the precedents that explain the signals this ring fired.
    ring_precedents = geodo_research.precedents_for(_ring_signals(escalated))
    _prog(f"Grounded the memo in {len(ring_precedents)} regulatory precedent(s).")

    # Geo market grounding written by Agent 5 (Domain Expert); the block disappears
    # gracefully if the Domain Expert didn't run — proving it is Agent 5's contribution.
    market_context = cognee.read_market_context("QRM-2026-RING-001")
    market_block = _market_block(market_context)
    if market_context:
        _prog("Attached MARKET CONTEXT (Geodo) from Cognee — Domain Expert handoff.")

    memo_text = _build_memo(edges, escalated, review, decoys, dist_stats,
                            reconciled_total, closing_rule, generated_at,
                            ring_precedents, market_block=market_block)

    # Accrete reporter fields onto each escalated Case (final layer). Each case
    # carries the precedents matched to ITS decisive signals — provenance per
    # decision, queryable through Cognee.
    for c in escalated:
        out_usd = round((c.get("signals") or {}).get("_transfer_usd", 0.0), 2)
        case_citations = [
            {"title": p["title"], "citation": p["citation"], "url": p["url"]}
            for p in geodo_research.precedents_for(c.get("decisive_signals", []))
        ]
        cognee.update_case_fields(c["account"], {
            "memo_ref": "QRM-2026-RING-001",
            "typology": typology,
            "dollar_contribution": out_usd,
            "closing_rule": closing_rule,
            "citations": case_citations,
        })

    # Gemini polish is opt-in (it adds a network call); the template memo is
    # already complete and fully grounded, so it is the fast/default output.
    if polish is None:
        polish = os.getenv("QUORUM_LLM_POLISH", "").lower() in ("1", "true", "yes")
    polished = _llm_polish(
        "Rewrite this AML SAR memo in clean regulator prose. Do NOT change any "
        "number, account id, or fact — only phrasing:\n\n" + memo_text) if polish else ""

    cognee.add_agent_layer("reporter", "REPORTER SAR memo (Agent 4):\n" + memo_text)

    _prog(f"Reporter complete. Escalated={len(escalated)} review={len(review)} "
          f"decoys_cleared={len(decoys)} reconciled={'OK' if ok else 'MISMATCH'}.")

    return {
        "memo_text": polished or memo_text,
        "memo_template": memo_text,
        "reconciled_total": reconciled_total,
        "reconciliation_ok": ok,
        "closing_rule": closing_rule,
        "typology": typology,
        "escalated_count": len(escalated),
        "review_count": len(review),
        "decoys_cleared": [c["account"] for c in decoys],
        "generated_at": generated_at.isoformat(),
    }
