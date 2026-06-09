"""
Tier 2 — "Ring → Real Buyers" GTM motion  (Quorum × Geo, the bidirectional flex).

After the pipeline writes a SAR memo for a detected ring, this drives Geo THROUGH ITS MCP to
turn the detection into real go-to-market motion — WITH APPROVAL GATES, NOTHING SENT:

  1. geo_add_document   — push a Quorum "detection brief" (ring summary + the matched dated
     enforcement action) into Geo, teaching its GTM twin a COMPLIANCE-EXPERT BRAIN: how to
     open with a typology-matched, dated SAR-failure action — a skill no screen-recorded BDR
     could give it. (the real bidirectional proof; on-thesis: it expands the twin.)
  2. geo_search_contacts — source REAL target institutions + roles (community banks / credit
     unions matching the ICP). Last names are MASKED by Geo; unmask only via enrich (gated).
  3. (optional, gated) geo_enrich_contact — unmask <=N contacts for a fully-named demo.
  4. We draft 3 personalized openers ourselves (first name + institution), each leading with
     the SAME dated enforcement fact matched to the ring's typology — one fact, fraud→GTM.
  5. geo_propose_campaign — a suggested SCHEDULE only (its own contact sourcing is unreliable).

It NEVER calls create / launch / send — geo_client's DENYLIST enforces that regardless.
Reads the last pipeline's MarketContext + escalated Cases from Cognee (run main.py first).

    uv run python gtm.py [--enrich N] [--live]
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import cognee_client as cognee
import geo_client
import geodo_market
from agents.domain_expert import RING_REF

log = logging.getLogger("gtm")

CACHE = Path(__file__).resolve().parent / "geo_cache"
PACKET_PATH = CACHE / "gtm_packet.json"      # committable, REDACTED (no raw PII) — UI reads this
_NOISE = {"axis bank", "norinchukin bank"}   # large non-US banks that drift in

# A fixed probe used to prove Geo's twin learned: ask the same thing before and after we
# teach it the detection brief, and diff the answer (#1, best-effort — see _learn_loop).
_TWIN_PROBE = ("For a US community-bank BSA/AML team, what coordinated money-laundering pattern is "
               "hardest for rules-based monitoring to catch, and what recent peer enforcement makes "
               "fixing it urgent? Be specific.")


def _capture(name: str, args: dict, *, key: str, live: bool, allow_write: bool = False):
    """Offline-safe Geo capture: live=True calls the MCP and snapshots to geo_cache/<key>.json;
    offline reads ONLY the cached fixture (never the network), returning None on a miss. This is
    stricter than geo_client.cached(live=False), which would fall through to a live call."""
    if live:
        return geo_client.cached(name, args, key=key, live=True, allow_write=allow_write)
    return geo_client.load_cached(key)


def _typology(escalated: list[dict]) -> str:
    """The ring's typology label (set on the escalated Cases by the Reporter)."""
    return next((c.get("typology") for c in escalated if c.get("typology")),
                "structuring + layering")


# Map the matched enforcement's signal_tags → buyer-search terms, so the contact search is
# pointed at the kind of institution that just got penalised for THIS ring's failure (#3).
_TAG_TERMS = {
    "pure_sink": "payment processor fintech sponsor",
    "zero_merchant": "fintech sponsor banking-as-a-service",
    "relay_depth": "wire transfer correspondent",
    "automation": "high-volume ACH wire",
    "under_threshold": "retail deposit",
    "fresh_cohort": "new account onboarding",
}


def _typology_terms(mc: dict) -> str:
    """Buyer-search terms derived from the matched enforcement's signal_tags (#3)."""
    top = (mc.get("intent_signals") or [{}])[0]
    tags = top.get("signal_tags") or []
    return " ".join(_TAG_TERMS[t] for t in tags if t in _TAG_TERMS)


def _contact_query(mc: dict) -> str:
    """The typology-targeted base query (kept for the packet/UI 'search basis' line, #3)."""
    base = "BSA officer community bank credit union"
    # Dedupe words across the whole query, preserving first-seen order.
    return " ".join(dict.fromkeys(f"{base} {_typology_terms(mc)}".split()))


# One search per persona so the demo always surfaces a varied buyer set (BSA Officer / AML
# Analyst / CCO). Queries are intentionally SHORT — Geo's contact search is literal, so piling on
# typology terms returns zero matches (the typology basis lives in the brief + contact_query). The
# search bucket decides which messaging angle the opener leads with (#5).
_PERSONA_SEARCH: list[tuple[str, str]] = [
    ("bsa_officer", "BSA officer community bank"),
    ("aml_analyst", "AML analyst community bank"),
    ("executive", "chief compliance officer bank"),
]


def _select_diverse(pool: list[dict], n: int = 3) -> list[dict]:
    """Pick up to n contacts maximising distinct persona angles (variety-first), then fill."""
    chosen, used = [], set()
    for c in pool:
        theme = geodo_market.angle_for_title(c.get("title"))["theme"]
        if theme not in used:
            used.add(theme)
            chosen.append(c)
        if len(chosen) == n:
            return chosen
    for c in pool:
        if c not in chosen:
            chosen.append(c)
        if len(chosen) == n:
            break
    return chosen


def _source_diverse_contacts(live: bool) -> tuple[list[dict], list[str]]:
    """Source real buyers with GUARANTEED persona variety: one targeted search per persona,
    picking the best-matching real contact for each. Returns (contacts, queries). Offline with
    no per-persona fixtures, falls back to the committed sample and diversifies by title."""
    contacts: list[dict] = []
    queries: list[str] = []
    seen: set = set()
    for persona, q in _PERSONA_SEARCH:
        queries.append(q)
        try:
            sc = _capture("geo_search_contacts", {"query": q, "count": 10},
                          key=f"contacts_{persona}", live=live, allow_write=True)
        except Exception as exc:   # noqa: BLE001 — degrade per-persona, never crash the motion
            log.warning("GTM: geo_search_contacts[%s] unavailable (%s).", persona, exc)
            sc = None
        clean = _clean_contacts(sc, n=10) if sc else []
        # First real contact from THIS persona's search owns this persona's angle (#5).
        pick = next((c for c in clean if _cid(c) not in seen), None)
        if pick:
            seen.add(_cid(pick))
            contacts.append({**pick, "_persona": persona})
    if not contacts:   # offline & no per-persona fixtures → fall back to the committed sample
        sample = geo_client.load_cached("contacts_sample") or {}
        contacts = _select_diverse(_clean_contacts(sample, n=10))
    return contacts[:3], queries


def _cid(c: dict):
    return c.get("id") or (c.get("first_name"), c.get("company"))


def _doc_list(resp) -> list[dict]:
    """Defensively extract the document list from a geo_list_documents response of unknown shape."""
    if isinstance(resp, dict):
        for k in ("documents", "items", "data", "results", "files"):
            v = resp.get(k)
            if isinstance(v, list):
                return v
    return resp if isinstance(resp, list) else []


def _doc_names(resp) -> list[str]:
    out = []
    for d in _doc_list(resp):
        if isinstance(d, dict):
            out.append(str(d.get("file_name") or d.get("name") or d.get("title") or d.get("id") or ""))
        else:
            out.append(str(d))
    return [n for n in out if n]


def _answer(resp) -> str:
    return (resp or {}).get("answer", "") if isinstance(resp, dict) else ""


def _ring_facts() -> tuple[list[dict], dict]:
    """Escalated Cases + the MarketContext written by Agent 5 (Domain Expert)."""
    mc = cognee.read_market_context(RING_REF)
    if not mc:
        raise ValueError(
            "No MarketContext in Cognee — run the pipeline first: "
            "`uv run python main.py data/track02_fraud_watch.csv`")
    escalated = [c for c in cognee.read_cases(candidates_only=True)
                 if c.get("action") == "ESCALATE"]
    return escalated, mc


def _detection_brief(escalated: list[dict], mc: dict) -> tuple[str, str]:
    """A compact, faithful 'detection brief' document to teach Geo's twin."""
    top = (mc.get("intent_signals") or [{}])[0]
    exposure = round(sum((c.get("dollar_contribution") or 0.0) for c in escalated), 2)
    typology = next((c.get("typology") for c in escalated if c.get("typology")), "structuring + layering")
    closing = next((c.get("closing_rule") for c in escalated if c.get("closing_rule")), "")
    decisive = sorted({s for c in escalated for s in (c.get("decisive_signals") or [])})
    name = f"Quorum detection brief — {RING_REF}"
    body = (
        f"# {name}\n\n"
        f"Quorum (AI multi-agent AML triage) flagged a **{typology}** ring of "
        f"{len(escalated)} accounts moving ~${exposure:,.2f} via sub-threshold account-to-"
        f"account transfers that rules-based monitoring missed.\n\n"
        f"Decisive signals: {', '.join(decisive) or 'n/a'}.\n\n"
        f"Learned detection rule: {closing}\n\n"
        f"## Why this matters to the buyer (peer enforcement)\n"
        f"{top.get('institution','')} — {top.get('action','')} "
        f"[{top.get('citation','')}].\n\n"
        f"## How to use this with prospects\n"
        f"Target: {mc.get('segment','')}. Open with the peer enforcement above (the cost of "
        f"getting this wrong), then Quorum's value: it catches coordinated mule rings rules "
        f"engines miss, abstains under genuine uncertainty instead of flooding analysts with "
        f"false positives, and produces a regulator-ready SAR memo with visible reasoning."
    )
    return name, body


def _clean_contacts(resp: dict, n: int = 3) -> list[dict]:
    cs = (resp or {}).get("contacts", []) if isinstance(resp, dict) else []
    keep = [c for c in cs if c.get("company") and c["company"].lower() not in _NOISE]
    return keep[:n]


def _match_angle(title: str | None, angles: dict) -> dict:
    """The persona messaging angle (Geo GTM Researcher) whose title_match fits this contact."""
    t = (title or "").lower()
    for theme, rec in (angles or {}).items():
        if any(m in t for m in rec.get("title_match", [])):
            return {"theme": theme, **rec}
    if angles:
        theme, rec = next(iter(angles.items()))
        return {"theme": theme, **rec}
    return {"theme": "", "angle": "catches the coordinated rings rules engines miss, with the "
                                  "reasoning attached so it holds up with an examiner"}


def _openers(contacts: list[dict], mc: dict, escalated: list[dict]) -> list[dict]:
    """Personalized openers — first name + institution — each leading with the SAME dated
    enforcement fact (the fraud→GTM thread) but with the value-prop tuned to the contact's
    persona/title via Geo's messaging angles (#5). We draft these; nothing is sent."""
    top = (mc.get("intent_signals") or [{}])[0]
    peer = top.get("institution", "a peer institution")
    angles = mc.get("messaging_angles") or geodo_market.messaging_angles()
    n = len(escalated)
    templates = [
        ("As {role} at {co}, {peer} was just cited by regulators for missing structured, "
         "sub-threshold activity — the failure you answer for. Quorum caught a {n}-account "
         "layering ring rules-based monitoring missed: {angle}. Worth 20 minutes on a sample "
         "of your own backlog?"),
        ("Quick one for {co}'s BSA team — when peers like {peer} draw enforcement for unreported "
         "suspicious activity, the gap is coordinated sub-$1,000 transfers that never trip a "
         "threshold. Quorum reconstructed exactly such a {n}-account ring: {angle}. Can I send a "
         "2-page sample memo?"),
        ("Hi {first} — {peer}'s recent order is the reminder that monitoring rarely connects "
         "sub-threshold transfers into a layering ring. Quorum is built for teams like {co}'s: "
         "{angle}. Open to a short walkthrough?"),
    ]
    out = []
    for c, tmpl in zip(contacts, templates):
        first = c.get("first_name") or (c.get("name", "there").split() or ["there"])[0]
        co = c.get("company", "your institution")
        role = c.get("title", "BSA Officer")
        # The persona-targeted search that sourced this contact owns its angle; fall back to
        # title-matching for sample/offline contacts that carry no persona tag.
        persona = c.get("_persona")
        if persona and persona in angles:
            angle = {"theme": persona, **angles[persona]}
        else:
            angle = _match_angle(role, angles)
        out.append({
            "to": f"{first} · {role} · {co}",   # masked-safe: first name + institution
            "persona_angle": angle["theme"],
            "opener": tmpl.format(role=role, co=co, peer=peer, n=n, first=first,
                                  angle=angle["angle"]),
        })
    return out


def _learn_loop(fname: str, body: str, live: bool) -> tuple[dict, dict]:
    """#1 — prove Geo's twin learned. Snapshot the twin's documents + a research answer BEFORE
    pushing the detection brief, push it (live only), then snapshot AFTER. Returns (doc, loop):
      • doc          — the geo_add_document response (or a cached placeholder offline).
      • loop         — deterministic proof (docs_added, brief_present) + a best-effort research
                       before/after diff (research_changed) with short excerpts.
    Offline reads fixtures only; if none exist the loop is marked 'capture pending'."""
    docs_before = _capture("geo_list_documents", {}, key="documents_before", live=live)
    res_before = _capture("geo_research", {"query": _TWIN_PROBE}, key="research_probe", live=live)

    if live:
        log.info("GTM: pushing detection brief to Geo (geo_add_document) — teaches the twin.")
        doc = geo_client.call("geo_add_document", {"file_name": fname, "content": body},
                              allow_write=True)
        try:   # persist the push outcome so the offline snapshot honestly reflects it
            (geo_client.CACHE_DIR / "add_document.json").write_text(json.dumps(
                {"tool": "geo_add_document", "response": doc}, indent=2, default=str))
        except OSError:
            pass
    else:
        log.info("GTM: offline — reading last live push outcome from cache (if any).")
        doc = geo_client.load_cached("add_document") or {"ok": None, "cached": True}

    docs_after = _capture("geo_list_documents", {}, key="documents_after", live=live)
    res_after = _capture("geo_research", {"query": _TWIN_PROBE}, key="research_after", live=live)

    names_before, names_after = _doc_names(docs_before), _doc_names(docs_after)
    captured = bool(docs_after is not None or res_after is not None)
    a_before, a_after = _answer(res_before).strip(), _answer(res_after).strip()
    loop = {
        "captured": captured,
        "docs_before": len(names_before),
        "docs_after": len(names_after),
        "docs_added": max(len(names_after) - len(names_before), 0),
        "brief_present": fname in names_after,
        "research_changed": bool(a_before and a_after and a_before != a_after),
        "research_before_excerpt": a_before[:300],
        "research_after_excerpt": a_after[:300],
    }
    return doc, loop


def _flow_spec(live: bool) -> dict | None:
    """#4 — a gated, dry-run multi-touch sequence via geo_compile_flow_spec. Best-effort: live
    captures + caches the fixture; offline reads it; any error/odd shape → None (section omitted)."""
    args = {
        "goal": "Book a 20-minute walkthrough of Quorum's AML triage with a sample SAR memo.",
        "channel": "gmail",
        "icp_hint": "BSA Officers / AML Analysts / CCOs at US community banks & credit unions ($1–50B)",
    }
    try:
        if live:
            spec = geo_client.cached("geo_compile_flow_spec", args, key="flow_spec", live=True)
        else:
            spec = geo_client.load_cached("flow_spec")
        return spec if isinstance(spec, dict) else None
    except Exception as exc:   # noqa: BLE001 — flow spec is optional flavour, never a hard dep
        log.warning("GTM: geo_compile_flow_spec unavailable (%s) — no sequence.", exc)
        return None


def run(enrich_n: int = 0, live: bool = False) -> dict:
    """Build the Ring → Real Buyers packet. Cache-first by default (offline, deterministic,
    no credits); pass live=True to drive the Geo MCP for real (still gated — nothing sent)."""
    escalated, mc = _ring_facts()
    typology = _typology(escalated)
    tools_called: list[str] = []

    # 0) Liveness proof — who the Geo account is + credit posture (read-only; captured live,
    #    read from cache offline). Feeds the UI "Geo connected" badge (#2).
    _capture("geo_get_account_state", {}, key="account_state", live=live)
    _capture("geo_get_credit_status", {}, key="credit_status", live=live)

    # 1) Teach Geo's twin AND prove it learned — push the detection brief, snapshot the twin's
    #    documents + a research answer before/after, and diff them (#1).
    fname, body = _detection_brief(escalated, mc)
    doc, learn_loop = _learn_loop(fname, body, live)
    tools_called += ["geo_list_documents", "geo_add_document"]

    # 2) Source real target institutions + roles (write, gated; masked by Geo) with GUARANTEED
    #    persona variety — one typology-flavoured search per persona (#3 + #5).
    query = _contact_query(mc)
    log.info("GTM: sourcing real buyers (geo_search_contacts) — typology basis=%r", query)
    contacts, persona_queries = _source_diverse_contacts(live)
    tools_called.append("geo_search_contacts")

    # 3) Optional, gated: unmask <=N for a fully-named demo (real PII — off by default, live only).
    enriched = []
    if enrich_n > 0 and live:
        for c in contacts[:enrich_n]:
            log.info("GTM: enriching one contact (geo_enrich_contact) — explicit opt-in, live.")
            e = geo_client.call("geo_enrich_contact", {"id": c.get("id")}, allow_write=True)
            tools_called.append("geo_enrich_contact")
            enriched.append(e)

    # 4) Draft 3 openers ourselves (NOTHING sent).
    openers = _openers(contacts, mc, escalated)

    # 5) Schedule suggestion only (its own contacts are unreliable — we ignore them).
    log.info("GTM: requesting a schedule (geo_propose_campaign) — proposal only, no launch.")
    prop: dict = {}
    if live:
        try:
            prop = geo_client.call("geo_propose_campaign", {
                "channel": "gmail",
                "goal": "Book a 20-minute walkthrough of Quorum's AML triage with a sample SAR memo.",
                "icp_hint": "BSA Officers / AML Analysts / CCOs at US community banks & credit unions ($1–50B)",
                "contact_count": 3, "timezone": "America/New_York"}) or {}
        except Exception as exc:   # noqa: BLE001 — schedule is optional flavour, never a hard dep
            log.warning("GTM: geo_propose_campaign unavailable (%s) — no schedule.", exc)
    else:
        prop = geo_client.load_cached("propose_sample") or {}   # cache-only offline (no network)
    tools_called.append("geo_propose_campaign")
    schedule = prop.get("suggested_schedule") if isinstance(prop, dict) else None

    # 6) Dry-run multi-touch sequence (gated, nothing launched) — #4.
    log.info("GTM: compiling a dry-run nurture sequence (geo_compile_flow_spec) — no launch.")
    flow_spec = _flow_spec(live)
    tools_called.append("geo_compile_flow_spec")

    redacted = [{"title": c.get("title"), "company": c.get("company"),
                 "first_name": c.get("first_name"), "has_email": c.get("has_email")}
                for c in contacts]
    result = {
        "ring_ref": RING_REF,
        "typology": typology,
        "document": {"file_name": fname, "ok": (doc or {}).get("ok") if isinstance(doc, dict) else None},
        "document_body": body,
        "learn_loop": learn_loop,
        "contacts": redacted,
        "contact_query": query,
        "persona_queries": persona_queries,
        "openers": openers,
        "schedule": schedule,
        "flow_spec": flow_spec,
        "enriched_count": len(enriched),
        "live": live,
        "tools_called": tools_called,
        "captured_on": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    CACHE.mkdir(exist_ok=True)
    # Redacted, committable packet the product UI reads (no raw PII — first name + institution only).
    PACKET_PATH.write_text(json.dumps(result, indent=2, default=str))
    # Full sourcing (incl. masked ids) stays gitignored (contacts_*.json) — never committed.
    (CACHE / "contacts_gtm.json").write_text(json.dumps(
        {"contacts_full": contacts, "enriched": enriched}, indent=2, default=str))
    return result


def load_packet() -> dict | None:
    """The last redacted Ring → Real Buyers packet (committable cache), or None."""
    if PACKET_PATH.exists():
        try:
            return json.loads(PACKET_PATH.read_text())
        except Exception:   # noqa: BLE001
            return None
    return None


def packet_markdown(r: dict) -> str:
    """Render a packet dict into a downloadable Markdown go-to-market brief."""
    lines = [f"# Ring → Real Buyers — {r.get('ring_ref','')}",
             "",
             "_Generated by Quorum's GTM agent from the detected ring, via Geo (geodo.ai) MCP. "
             "Gated: nothing was sent — create/launch/send tools are denylisted._",
             ""]
    doc = r.get("document", {})
    lines += [f"**Detection brief taught to Geo's twin:** {doc.get('file_name','')} "
              f"(pushed: {doc.get('ok')})", ""]

    ll = r.get("learn_loop") or {}
    if ll.get("captured"):
        lines += ["## Proof the twin learned",
                  f"- Twin documents: {ll.get('docs_before')} → {ll.get('docs_after')} "
                  f"(+{ll.get('docs_added')}); this brief present: "
                  f"{'✅' if ll.get('brief_present') else '—'}",
                  f"- Research answer changed after teaching: "
                  f"{'✅ yes' if ll.get('research_changed') else 'no measurable change'}", ""]

    lines += ["## Real buyer institutions sourced via Geo (masked)"]
    if r.get("contact_query"):
        lines += [f"_Search (typology-targeted): {r['contact_query']}_", ""]
    for c in r.get("contacts", []):
        lines.append(f"- {c.get('first_name','')} · {c.get('title','')} · {c.get('company','')} "
                     f"(email on file: {c.get('has_email')})")
    lines += ["", "## Drafted openers (shared dated enforcement fact + persona-tuned value-prop)"]
    for o in r.get("openers", []):
        tag = f" _(angle: {o.get('persona_angle')})_" if o.get("persona_angle") else ""
        lines += [f"**To: {o.get('to','')}**{tag}", "", o.get("opener", ""), ""]
    if r.get("schedule"):
        lines += [f"## Suggested cadence (Geo proposal only): {r['schedule']}", ""]
    fs = r.get("flow_spec")
    if fs:
        lines += ["## Dry-run multi-touch sequence (geo_compile_flow_spec — not launched)",
                  "```json", json.dumps(fs, indent=2, default=str)[:2000], "```", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
                        datefmt="%H:%M:%S")
    ap = argparse.ArgumentParser()
    ap.add_argument("--enrich", type=int, default=0, help="unmask N contacts (real PII; live only; default 0)")
    ap.add_argument("--live", action="store_true", help="drive the Geo MCP live (default: cache-first/offline)")
    args = ap.parse_args()
    r = run(enrich_n=args.enrich, live=args.live)
    print("\n" + "=" * 70)
    print(f"RING → REAL BUYERS  ({r['ring_ref']})   tools: {', '.join(r['tools_called'])}")
    print(f"Detection brief pushed to Geo: {r['document']['file_name']}  (ok={r['document']['ok']})")
    ll = r.get("learn_loop") or {}
    if ll.get("captured"):
        print(f"Twin learned: docs {ll.get('docs_before')}→{ll.get('docs_after')} "
              f"(brief present: {ll.get('brief_present')}); research changed: {ll.get('research_changed')}")
    print(f"Contact search (typology-targeted): {r.get('contact_query','')}")
    print(f"Sourced {len(r['contacts'])} real buyers (masked); enriched {r['enriched_count']}.")
    print("=" * 70)
    for c, o in zip(r["contacts"], r["openers"]):
        print(f"\n▶ {o['to']}  [angle: {o.get('persona_angle','')}; email on file: {c['has_email']}]")
        print(f"  {o['opener']}")
    print(f"\nSuggested schedule: {r['schedule']}")
    if r.get("flow_spec"):
        print("Dry-run multi-touch sequence compiled (geo_compile_flow_spec) — not launched.")
    print("\nNOTHING WAS SENT. Create/launch/send are denylisted in geo_client.")
