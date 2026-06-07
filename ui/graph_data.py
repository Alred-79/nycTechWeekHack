"""
Graph-data builder for the Quorum visuals.

Converts the live pipeline output (DuckDB connection + Detector result + the
enriched Cognee Cases) into the node/link JSON consumed by the 3D force graph
(ui/ring_graph.py). Every node/link carries the *real* computed fields so the
graph is the data, not a mock-up.

Two layers live in one graph so the "noise collapse" reveal works:
  • the full transaction graph  — accounts + merchant-category hubs (the hairball)
  • the ring constellation       — the ~14 surfaced Cases + the 6 directed
                                    AC→AC transfer edges + device-share links
The frontend hides the noise layer on "Reveal the ring".
"""
from __future__ import annotations

import duckdb

# Semantic palette — kept identical across every visual in the app.
COLORS = {
    "ring": "#ff4d6d",      # ESCALATE — confirmed mule
    "review": "#ffb020",    # REVIEW   — abstention / uncertain
    "decoy": "#8b93b5",     # CLEAR    — planted device decoy
    "clear": "#2ee6a6",     # CLEAR    — other
    "clean": "#39477e",     # never surfaced (noise)
    "category": "#5a6bb0",  # merchant-category hub
}


def _group(case: dict | None) -> str:
    if case is None:
        return "clean"
    if case.get("action") == "REVIEW":
        return "review"
    if case.get("decoy_suspect"):
        return "decoy"
    if case.get("action") == "ESCALATE":
        return "ring"
    return "clear"


def build_graph(con: duckdb.DuckDBPyConnection,
                detector_result: dict,
                cases: list[dict]) -> dict:
    """Return {"nodes": [...], "links": [...]} for the force graph."""
    case_by_acct = {c["account"]: c for c in cases}

    # ── merchant-category hubs (the noise layer) ──────────────────────────────
    cat_rows = con.execute("""
        SELECT account_id, merchant_category, COUNT(*) AS n
        FROM transactions
        WHERE counterparty_id LIKE 'MR-%'
        GROUP BY account_id, merchant_category
    """).fetchall()
    categories = sorted({r[1] for r in cat_rows})

    universe = con.execute("""
        SELECT account_id FROM transactions WHERE account_id LIKE 'AC-%'
        UNION
        SELECT counterparty_id FROM transactions WHERE counterparty_id LIKE 'AC-%'
    """).fetchall()
    accounts = sorted({r[0] for r in universe})

    nodes: list[dict] = []

    # category hub nodes
    for cat in categories:
        nodes.append({
            "id": f"CAT::{cat}", "label": cat, "kind": "category",
            "group": "category", "candidate": False, "val": 6,
            "color": COLORS["category"],
        })

    # account nodes
    for acc in accounts:
        c = case_by_acct.get(acc)
        grp = _group(c)
        usd = float((c or {}).get("dollar_contribution") or
                    (c or {}).get("signals", {}).get("_transfer_usd") or 0.0)
        node = {
            "id": acc, "label": acc, "kind": "account",
            "group": grp, "candidate": c is not None,
            "color": COLORS[grp],
            # sqrt scale so the big hubs read without dwarfing the rest
            "val": (3 + (usd ** 0.5) / 9) if c else 1.5,
            "usd": round(usd, 2),
        }
        if c:
            sig = c.get("signals", {})
            node.update({
                "role": c.get("role"),
                "action": c.get("action"),
                "p_mule": c.get("p_mule"),
                "ci": c.get("credible_interval"),
                "reason": c.get("detect_reason", ""),
                "action_reason": c.get("action_reason", ""),
                "decisive": c.get("decisive_signals", []),
                "decoy": bool(c.get("decoy_suspect")),
                "typology": c.get("typology"),
                "evpi": c.get("EVPI"),
                "e_loss_escalate": c.get("E_loss_escalate"),
                "e_loss_clear": c.get("E_loss_clear"),
                "n_transfers": sig.get("_n_transfers"),
                "fired": [k for k, v in sig.items()
                          if not k.startswith("_") and v],
                "signals": {k: v for k, v in sig.items()
                            if not k.startswith("_")},
            })
        nodes.append(node)

    # ── links ─────────────────────────────────────────────────────────────────
    links: list[dict] = []

    # noise: account → merchant category (hidden on reveal)
    for acc, cat, n in cat_rows:
        links.append({"source": acc, "target": f"CAT::{cat}",
                      "type": "noise", "n": int(n)})

    # ring: the directed AC→AC transfer edges (carry particles)
    max_usd = max((e["total_usd"] for e in detector_result.get("edges", [])),
                  default=1.0)
    for e in detector_result.get("edges", []):
        links.append({
            "source": e["sender"], "target": e["receiver"], "type": "ring",
            "usd": e["total_usd"], "count": e["count"],
            "width": 1 + 5 * (e["total_usd"] / max_usd),
        })

    # device: shared-device co-occurrence (the decoy trap) — dashed, no particles
    for dev in detector_result.get("shared_devices", []):
        accs = [a for a in dev.get("accounts", []) if a in case_by_acct]
        for i in range(len(accs)):
            for j in range(i + 1, len(accs)):
                links.append({"source": accs[i], "target": accs[j],
                              "type": "device", "device": dev.get("device_id")})

    return {"nodes": nodes, "links": links}


def filter_ring(graph: dict) -> dict:
    """The collapsed ring view: only surfaced Cases + their ring/device links.

    Used to render the Cognee *memory* graph (the enriched Case nodes and their
    relationships) as a static, always-visible constellation.
    """
    nodes = [n for n in graph["nodes"] if n.get("candidate")]
    ids = {n["id"] for n in nodes}
    links = [l for l in graph["links"]
             if l["type"] != "noise"
             and (l["source"].get("id") if isinstance(l["source"], dict) else l["source"]) in ids
             and (l["target"].get("id") if isinstance(l["target"], dict) else l["target"]) in ids]
    return {"nodes": nodes, "links": links}


def funnel_counts(cases: list[dict], n_accounts_total: int) -> dict:
    esc = sum(1 for c in cases if c.get("action") == "ESCALATE")
    rev = sum(1 for c in cases if c.get("action") == "REVIEW")
    clr = sum(1 for c in cases if c.get("action") == "CLEAR")
    return {
        "total": n_accounts_total,
        "surfaced": len(cases),
        "escalate": esc,
        "review": rev,
        "clear": clr,
        "auto_cleared": n_accounts_total - len(cases),
    }
