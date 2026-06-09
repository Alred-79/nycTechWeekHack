"""
Pre-built demo snapshot.

Runs the real 4-agent pipeline ONCE and serialises everything the UI needs
(enriched Cases, the transfer graph, the 3D-graph JSON, the funnel counts, and
the aggregates behind every chart) into a single static file. The Streamlit app
loads this on startup, so the website opens straight into the visuals — no CSV
upload, no pipeline run, no DuckDB connection required at view time.

Rebuild after any pipeline change:

    uv run python -m ui.snapshot
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = ROOT / "ui" / "quorum_snapshot.json"
DEFAULT_CSV = ROOT / "data" / "track02_fraud_watch.csv"


def compute_chart_data(con, ring_accounts: set[str]) -> dict:
    """Aggregate everything the signature charts need, so no live DB is required."""
    sc = con.execute("""
        SELECT tx_second,
               SUM(CASE WHEN counterparty_id LIKE 'AC-%' THEN 1 ELSE 0 END) AS ring,
               SUM(CASE WHEN counterparty_id LIKE 'MR-%' THEN 1 ELSE 0 END) AS merch
        FROM transactions GROUP BY tx_second ORDER BY tx_second
    """).fetchall()
    ob = con.execute("""
        SELECT account_id, MIN(account_open_date) AS od
        FROM transactions WHERE account_id LIKE 'AC-%' GROUP BY account_id
    """).fetchall()
    ring, other = [], []
    for acc, od in ob:
        (ring if acc in ring_accounts else other).append(str(od))
    ac = [float(r[0]) for r in con.execute(
        "SELECT amount FROM transactions WHERE counterparty_id LIKE 'AC-%'").fetchall()]
    mr = [float(r[0]) for r in con.execute(
        "SELECT amount FROM transactions WHERE counterparty_id LIKE 'MR-%' "
        "AND amount < 2000").fetchall()]
    return {
        "second_clock": [[int(r[0]), int(r[1]), int(r[2])] for r in sc],
        "opening_burst": {"ring": ring, "other": other},
        "amount_hist": {"ac": ac, "mr": mr},
    }


def build(csv_path: str | Path = DEFAULT_CSV) -> dict:
    """Run the pipeline and return a fully JSON-safe, view-ready result dict."""
    import duckdb
    import cognee_client as cognee
    import geo_client
    import geodo_market
    import geodo_research
    import gtm
    from agents import domain_expert, investigator, narrator, ranker, scout
    from db import queries
    from ui.graph_data import build_graph, funnel_counts

    con = duckdb.connect()
    queries.load_csv(con, str(csv_path))
    detector = scout.run(con)
    ranker.run()
    adjudicator = investigator.run(con, detector_result=detector)
    domain_expert.run(detector_result=detector)        # Agent 5 — Geo market grounding
    reporter = narrator.run(detector_result=detector)
    cases = cognee.read_cases(candidates_only=True)
    market_context = cognee.read_market_context(domain_expert.RING_REF)

    # Tier 2 — Ring → Real Buyers GTM packet (cache-first/offline; gated, nothing sent).
    try:
        gtm_packet = gtm.run(live=False)
    except Exception as exc:   # noqa: BLE001 — GTM is an add-on, never blocks the snapshot
        gtm_packet = None

    # Geo live-connection proof (read from cached fixtures; None until a `--live` capture ran).
    geo_connection = geo_client.connection_proof()

    n_total = detector["dist_stats"].get("n_accounts_total", 0)
    ring_accounts = {c["account"] for c in cases if c.get("action") == "ESCALATE"}
    total_volume = float((con.execute("SELECT SUM(amount) FROM transactions").fetchone() or (0,))[0] or 0)
    total_txns = int((con.execute("SELECT COUNT(*) FROM transactions").fetchone() or (0,))[0] or 0)

    return {
        "prebuilt": True,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_volume": round(total_volume, 2),
        "total_txns": total_txns,
        "detector": {
            "edges": detector["edges"],
            "total_ring_exposure": detector["total_ring_exposure"],
            "total_ring_txns": detector["total_ring_txns"],
            "dist_stats": detector["dist_stats"],
        },
        "adjudicator": {
            "tau": adjudicator["tau"],
            "escalate_count": adjudicator["escalate_count"],
            "review_count": adjudicator["review_count"],
            "clear_count": adjudicator["clear_count"],
            "clear_ratio": adjudicator["clear_ratio"],
        },
        "reporter": {
            "memo_text": reporter.get("memo_text", ""),
            "reconciled_total": reporter.get("reconciled_total", 0),
            "reconciliation_ok": reporter.get("reconciliation_ok", False),
            "typology": reporter.get("typology", ""),
            "closing_rule": reporter.get("closing_rule", ""),
        },
        "geodo": geodo_research.summary(),
        "geo_market": geodo_market.summary(),
        "market_context": market_context,   # carries the run-specific ROI (Geo rate × actuals)
        "gtm": gtm_packet,                   # Tier 2 — Ring → Real Buyers packet (redacted)
        "geo_connection": geo_connection,    # live-MCP proof badge (None until a --live capture)
        "cases": cases,
        "dist_stats": detector["dist_stats"],
        "counts": funnel_counts(cases, n_total),
        "ring_accounts": sorted(ring_accounts),
        "graph": build_graph(con, detector, cases),
        "chart_data": compute_chart_data(con, ring_accounts),
    }


STANDALONE_HTML = ROOT / "ui" / "quorum_constellation.html"
STATIC_HTML = ROOT / "ui" / "static" / "quorum_constellation.html"  # served by the app


def save(csv_path: str | Path = DEFAULT_CSV, out: str | Path = SNAPSHOT_PATH) -> Path:
    snap = build(csv_path)
    Path(out).write_text(json.dumps(snap, default=str))
    # also emit the standalone, double-click-openable interactive graph — both as a
    # loose file and into the served static dir the app links to.
    from ui import ring_graph
    ring_graph.write_html(snap["graph"], STANDALONE_HTML, height=860)
    STATIC_HTML.parent.mkdir(exist_ok=True)
    ring_graph.write_html(snap["graph"], STATIC_HTML, height=860)
    return Path(out)


def load(path: str | Path = SNAPSHOT_PATH) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text())


if __name__ == "__main__":
    import sys
    csv = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV
    out = save(csv)
    snap = load(out) or {}
    print(f"Snapshot written → {out}")
    print(f"Standalone graph → {STANDALONE_HTML}")
    print(f"  cases={len(snap['cases'])}  graph_nodes={len(snap['graph']['nodes'])} "
          f"links={len(snap['graph']['links'])}  built_at={snap['built_at']}")
