"""
Named DuckDB queries for RingFence.
All analytical SQL lives here — agents import and call these.
"""
from __future__ import annotations

import json
from datetime import datetime

import duckdb


def load_csv(con: duckdb.DuckDBPyConnection, csv_path: str) -> dict:
    """Load Crestline CSV into DuckDB. Returns ingestion stats."""
    con.execute("""
        CREATE OR REPLACE TABLE transactions AS
        SELECT
            txn_id,
            account_id,
            counterparty_id,
            CAST(amount AS DOUBLE) AS amount,
            CAST(timestamp AS TIMESTAMP) AS timestamp,
            merchant_category,
            device_id,
            ip_region,
            CAST(account_open_date AS TIMESTAMP) AS account_open_date
        FROM read_csv_auto(?, header=true)
    """, [csv_path])

    con.execute("""
        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS tx_second INTEGER;
        UPDATE transactions SET tx_second = EXTRACT(second FROM timestamp)::INTEGER;
    """)
    con.execute("""
        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS tx_hour INTEGER;
        UPDATE transactions SET tx_hour = EXTRACT(hour FROM timestamp)::INTEGER;
    """)
    # dataset_start for day-relative calculations
    start = con.execute("SELECT MIN(timestamp) FROM transactions").fetchone()[0]
    con.execute("""
        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS tx_day_of_dataset INTEGER;
        UPDATE transactions SET tx_day_of_dataset = DATEDIFF('day', ?, timestamp)
    """, [start])

    row_count = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    acct_count = con.execute("SELECT COUNT(DISTINCT account_id) FROM transactions").fetchone()[0]
    return {"rows": row_count, "accounts": acct_count, "dataset_start": start}


# ── Quorum: structural transfer isolation (no tx_second watermark) ────────────

def get_ac_transfers(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """
    Every account-to-account transfer, isolated STRUCTURALLY (counterparty is
    another AC account) — not via the synthetic tx_second==0 watermark.
    This is the 250-edge ring layer; the other 4,750 rows are merchant payments.
    """
    rows = con.execute("""
        SELECT txn_id, account_id AS sender, counterparty_id AS receiver,
               amount, timestamp
        FROM transactions
        WHERE counterparty_id LIKE 'AC-%'
        ORDER BY timestamp
    """).fetchall()
    cols = ["txn_id", "sender", "receiver", "amount", "timestamp"]
    return [dict(zip(cols, r)) for r in rows]


def get_account_universe(con: duckdb.DuckDBPyConnection) -> list[str]:
    """All AC accounts, INCLUDING pure sinks that appear only as counterparty."""
    rows = con.execute("""
        SELECT account_id FROM transactions WHERE account_id LIKE 'AC-%'
        UNION
        SELECT counterparty_id FROM transactions WHERE counterparty_id LIKE 'AC-%'
        ORDER BY 1
    """).fetchall()
    return [r[0] for r in rows]


def get_account_facts(con: duckdb.DuckDBPyConnection) -> dict[str, dict]:
    """
    Per-account originator facts (GROUP BY account_id). Note: pure-sink accounts
    never appear as account_id, so they are ABSENT here — callers must treat a
    missing account as 'originates nothing' (open_date unknown, n_originated 0).
    """
    rows = con.execute("""
        SELECT account_id,
               MIN(account_open_date)                                   AS open_date,
               COUNT(*)                                                 AS n_originated,
               SUM(CASE WHEN counterparty_id LIKE 'MR-%' THEN 1 ELSE 0 END) AS n_merchant,
               SUM(CASE WHEN counterparty_id LIKE 'AC-%' THEN 1 ELSE 0 END) AS n_ac_out,
               LIST(DISTINCT device_id ORDER BY device_id)              AS devices
        FROM transactions
        GROUP BY account_id
    """).fetchall()
    facts: dict[str, dict] = {}
    for r in rows:
        facts[r[0]] = {
            "open_date": r[1],
            "n_originated": int(r[2]),
            "n_merchant": int(r[3]),
            "n_ac_out": int(r[4]),
            "devices": list(r[5]) if r[5] else [],
        }
    return facts


# ── Ring detection (legacy RingFence — uses tx_second watermark) ──────────────

RING_TRANSFERS_SQL = """
    SELECT
        txn_id,
        account_id   AS sender,
        counterparty_id AS receiver,
        amount,
        timestamp,
        device_id,
        ip_region,
        account_open_date,
        tx_second,
        tx_hour,
        tx_day_of_dataset
    FROM transactions
    WHERE counterparty_id LIKE 'AC-%'
      AND tx_second = 0
    ORDER BY timestamp
"""


def get_ring_transfers(con: duckdb.DuckDBPyConnection) -> list[dict]:
    rows = con.execute(RING_TRANSFERS_SQL).fetchall()
    cols = ["txn_id","sender","receiver","amount","timestamp","device_id",
            "ip_region","account_open_date","tx_second","tx_hour","tx_day_of_dataset"]
    return [dict(zip(cols, r)) for r in rows]


def get_ring_edge_stats(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Per-directed-edge stats for the ring transfer channels."""
    rows = con.execute("""
        SELECT
            account_id                          AS sender,
            counterparty_id                     AS receiver,
            COUNT(*)                            AS txn_count,
            SUM(amount)                         AS total_usd,
            MIN(amount)                         AS amount_min,
            MAX(amount)                         AS amount_max,
            STDDEV_SAMP(amount)                 AS amount_std_dev,
            MIN(timestamp)                      AS first_txn,
            MAX(timestamp)                      AS last_txn,
            DATEDIFF('hour', MIN(timestamp), MAX(timestamp)) AS span_hours,
            AVG(tx_hour)                        AS avg_hour
        FROM transactions
        WHERE counterparty_id LIKE 'AC-%'
          AND tx_second = 0
        GROUP BY account_id, counterparty_id
        ORDER BY total_usd DESC
    """).fetchall()
    cols = ["sender","receiver","txn_count","total_usd","amount_min","amount_max",
            "amount_std_dev","first_txn","last_txn","span_hours","avg_hour"]
    return [dict(zip(cols, r)) for r in rows]


def get_ring_account_ids(con: duckdb.DuckDBPyConnection) -> list[str]:
    """All accounts that appear in ring transfers (as sender OR receiver)."""
    rows = con.execute("""
        SELECT DISTINCT account_id FROM transactions WHERE counterparty_id LIKE 'AC-%' AND tx_second = 0
        UNION
        SELECT DISTINCT counterparty_id FROM transactions WHERE counterparty_id LIKE 'AC-%' AND tx_second = 0
        ORDER BY 1
    """).fetchall()
    return [r[0] for r in rows]


# ── Sub-threshold clustering ──────────────────────────────────────────────────

def get_sub_threshold_accounts(con: duckdb.DuckDBPyConnection,
                                low: float = 400, high: float = 900,
                                min_frac: float = 0.8, min_txns: int = 5) -> list[dict]:
    rows = con.execute("""
        SELECT
            account_id,
            COUNT(*) AS txn_count,
            SUM(CASE WHEN amount BETWEEN ? AND ? THEN 1 ELSE 0 END) AS band_count,
            SUM(CASE WHEN amount BETWEEN ? AND ? THEN 1 ELSE 0 END)::DOUBLE / COUNT(*) AS band_frac
        FROM transactions
        GROUP BY account_id
        HAVING COUNT(*) >= ?
           AND (SUM(CASE WHEN amount BETWEEN ? AND ? THEN 1 ELSE 0 END)::DOUBLE / COUNT(*)) >= ?
        ORDER BY band_frac DESC
    """, [low, high, low, high, min_txns, low, high, min_frac]).fetchall()
    cols = ["account_id","txn_count","band_count","band_frac"]
    return [dict(zip(cols, r)) for r in rows]


# ── Shared device fingerprints ────────────────────────────────────────────────

def get_shared_devices(con: duckdb.DuckDBPyConnection) -> list[dict]:
    rows = con.execute("""
        SELECT device_id, COUNT(DISTINCT account_id) AS n_accounts,
               LIST(DISTINCT account_id ORDER BY account_id) AS accounts
        FROM transactions
        GROUP BY device_id
        HAVING COUNT(DISTINCT account_id) >= 2
        ORDER BY n_accounts DESC
    """).fetchall()
    return [{"device_id": r[0], "n_accounts": r[1], "accounts": list(r[2])} for r in rows]


# ── Coordinated opening cluster ───────────────────────────────────────────────

def get_opening_cluster(con: duckdb.DuckDBPyConnection,
                         window_days: int = 10) -> list[dict]:
    """Accounts opened within window_days of each other that transact together."""
    rows = con.execute("""
        WITH opens AS (
            SELECT account_id, MIN(account_open_date) AS open_date
            FROM transactions GROUP BY account_id
        ),
        clusters AS (
            SELECT a.account_id AS acct_a, b.account_id AS acct_b,
                   a.open_date AS open_a, b.open_date AS open_b,
                   DATEDIFF('day', a.open_date, b.open_date) AS days_apart
            FROM opens a JOIN opens b
              ON a.account_id < b.account_id
             AND ABS(DATEDIFF('day', a.open_date, b.open_date)) <= ?
        )
        SELECT acct_a, acct_b, open_a, open_b, days_apart
        FROM clusters
        ORDER BY open_a
    """, [window_days]).fetchall()
    cols = ["acct_a","acct_b","open_a","open_b","days_apart"]
    return [dict(zip(cols, r)) for r in rows]


# ── Behavioral drift (slow-burn detection) ────────────────────────────────────

def get_behavioral_drift(con: duckdb.DuckDBPyConnection,
                          baseline_days: int = 60) -> list[dict]:
    rows = con.execute("""
        WITH early AS (
            SELECT account_id,
                   AVG(amount) AS avg_early, STDDEV_SAMP(amount) AS std_early,
                   AVG(tx_hour) AS avg_hour_early, COUNT(*) AS cnt_early
            FROM transactions WHERE tx_day_of_dataset <= ?
            GROUP BY account_id
        ),
        late AS (
            SELECT account_id,
                   AVG(amount) AS avg_late, STDDEV_SAMP(amount) AS std_late,
                   AVG(tx_hour) AS avg_hour_late, COUNT(*) AS cnt_late
            FROM transactions WHERE tx_day_of_dataset > ?
            GROUP BY account_id
        )
        SELECT e.account_id,
               e.avg_early, l.avg_late,
               CASE WHEN e.std_early > 0
                    THEN ABS(l.avg_late - e.avg_early) / e.std_early
                    ELSE 0 END AS amount_drift_sigma,
               e.avg_hour_early, l.avg_hour_late,
               e.cnt_early, l.cnt_late
        FROM early e JOIN late l ON e.account_id = l.account_id
        WHERE e.cnt_early >= 3 AND l.cnt_late >= 3
        ORDER BY amount_drift_sigma DESC
    """, [baseline_days, baseline_days]).fetchall()
    cols = ["account_id","avg_early","avg_late","amount_drift_sigma",
            "avg_hour_early","avg_hour_late","cnt_early","cnt_late"]
    return [dict(zip(cols, r)) for r in rows]


# ── Account-level profile builder ─────────────────────────────────────────────

def build_account_profiles(con: duckdb.DuckDBPyConnection) -> list[dict]:
    rows = con.execute("""
        SELECT
            account_id,
            MIN(account_open_date)  AS account_open_date,
            COUNT(*)                AS total_txns,
            SUM(amount)             AS total_volume_usd,
            SUM(CASE WHEN counterparty_id LIKE 'AC-%' AND tx_second = 0 THEN 1 ELSE 0 END) AS ring_txns,
            SUM(CASE WHEN counterparty_id LIKE 'AC-%' AND tx_second = 0 THEN amount ELSE 0 END) AS ring_volume_usd,
            COUNT(DISTINCT counterparty_id) AS n_counterparties,
            LIST(DISTINCT device_id ORDER BY device_id)   AS device_ids,
            LIST(DISTINCT ip_region ORDER BY ip_region)   AS ip_regions
        FROM transactions
        GROUP BY account_id
    """).fetchall()
    cols = ["account_id","account_open_date","total_txns","total_volume_usd",
            "ring_txns","ring_volume_usd","n_counterparties","device_ids","ip_regions"]
    profiles = []
    for r in rows:
        d = dict(zip(cols, r))
        d["ring_fraction"] = d["ring_volume_usd"] / d["total_volume_usd"] if d["total_volume_usd"] else 0
        d["device_ids"] = list(d["device_ids"]) if d["device_ids"] else []
        d["ip_regions"] = list(d["ip_regions"]) if d["ip_regions"] else []
        profiles.append(d)
    return profiles
