"""
RingFence — CLI entrypoint.
Loads the Crestline CSV into DuckDB and runs the 4-agent pipeline.
Usage: python main.py data/track02_fraud_watch.csv
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import duckdb
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ringfence")


_STAGES = ["detector", "estimator", "adjudicator", "domain_expert", "reporter"]


def run_pipeline(csv_path: str, through: str = "reporter", mirror_cognee: bool = False) -> dict:
    """
    Run the 4-agent Quorum pipeline against a CSV file.

    `through` stops the pipeline after a named agent so the build stays runnable
    while the later agents are still being retrofitted (detector → estimator →
    adjudicator → reporter).
    """
    import cognee_client as cognee
    from agents import domain_expert, investigator, narrator, ranker, scout
    from db import queries

    stop_at = _STAGES.index(through)

    t0 = time.time()
    log.info("═" * 60)
    log.info("QUORUM PIPELINE START (through=%s)", through)
    log.info("CSV: %s", csv_path)
    log.info("═" * 60)

    # Load CSV into DuckDB (in-process, no server)
    log.info("[DB] Loading Crestline CSV into DuckDB...")
    con = duckdb.connect()
    stats = queries.load_csv(con, csv_path)
    log.info("[DB] Loaded %d rows, %d accounts. Dataset start: %s",
             stats["rows"], stats["accounts"], stats["dataset_start"])

    result: dict = {"db_connection": con}

    # When building the Cognee graph, each agent writes a layer to Cognee as it runs.
    if mirror_cognee:
        cognee.begin_build()

    # ── Agent 1: Detector ─────────────────────────────────────────────────────
    log.info("\n── AGENT 1: DETECTOR ───────────────────────────────────────")
    detector_result = scout.run(con, on_progress=lambda m: log.info("  %s", m))
    result["detector"] = detector_result
    log.info("Detector surfaced %d candidate Cases; ring exposure $%.2f",
             len(detector_result["cases"]), detector_result["total_ring_exposure"])
    if stop_at == 0:
        return _finish(result, t0, cognee, mirror_cognee)

    # ── Agent 2: Estimator ────────────────────────────────────────────────────
    log.info("\n── AGENT 2: ESTIMATOR ──────────────────────────────────────")
    result["estimator"] = ranker.run(on_progress=lambda m: log.info("  %s", m))
    if stop_at == 1:
        return _finish(result, t0, cognee, mirror_cognee)

    # ── Agent 3: Adjudicator ──────────────────────────────────────────────────
    log.info("\n── AGENT 3: ADJUDICATOR ────────────────────────────────────")
    result["adjudicator"] = investigator.run(
        con, detector_result=detector_result,
        on_progress=lambda m: log.info("  %s", m))
    if stop_at == 2:
        return _finish(result, t0, cognee, mirror_cognee)

    # ── Agent 5: Domain Expert (Geo market grounding) ─────────────────────────
    log.info("\n── AGENT 5: DOMAIN EXPERT (Geo) ────────────────────────────")
    result["domain_expert"] = domain_expert.run(
        detector_result=detector_result,
        on_progress=lambda m: log.info("  %s", m))
    if stop_at == 3:
        return _finish(result, t0, cognee, mirror_cognee)

    # ── Agent 4: Reporter ─────────────────────────────────────────────────────
    log.info("\n── AGENT 4: REPORTER ───────────────────────────────────────")
    result["reporter"] = narrator.run(
        detector_result=detector_result,
        on_progress=lambda m: log.info("  %s", m))

    return _finish(result, t0, cognee, mirror_cognee)


def _finish(result: dict, t0: float, cognee, mirror_cognee: bool) -> dict:
    # Flush every agent's Cognee layer + one cognify, and persist cognee_graph.json.
    # Off by default so quick CLI runs stay fast; pass --cognee to build the graph.
    # Guarded: no-ops gracefully if no Gemini key / Cognee unavailable.
    if mirror_cognee:
        result["cognee"] = cognee.finish_build()

    result["total_seconds"] = time.time() - t0
    log.info("\n" + "═" * 60)
    log.info("PIPELINE COMPLETE in %.1fs", result["total_seconds"])
    log.info("Cognee local store: %s", cognee.get_store_summary())
    log.info("Cognee SDK graph: %s", result.get("cognee", {"used": False}))
    log.info("═" * 60)
    if result.get("reporter", {}).get("memo_text"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print("\n" + result["reporter"]["memo_text"])
    return result


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    through = "reporter"
    mirror_cognee = False
    for a in list(args):
        if a.startswith("--through"):
            through = a.split("=", 1)[1] if "=" in a else "reporter"
            args.remove(a)
        elif a == "--cognee":
            mirror_cognee = True
            args.remove(a)
    if not args:
        print("Usage: python main.py <path-to-crestline.csv> [--through=detector|estimator|adjudicator|reporter] [--cognee]")
        sys.exit(1)
    csv_file = args[0]
    if not Path(csv_file).exists():
        print(f"Error: CSV file not found: {csv_file}")
        sys.exit(1)
    run_pipeline(csv_file, through=through, mirror_cognee=mirror_cognee)
