"""
Targeted ring hunt for Track 02 — Fraud Watch.

First-pass EDA killed the shared-device theory (only 2 shared devices, ~$3k).
The real signal in the per-account table: a cohort of high-volume accounts that
funnel into very FEW counterparties (mule behavior), plus suspiciously clean
:00-second timestamps. This script tests those hypotheses and assembles the ring.

Run: uv run python eda/ring_hunt.py   (writes eda/out/ring_findings.md)
"""

from __future__ import annotations

import pathlib

import pandas as pd

DATA = pathlib.Path(__file__).resolve().parents[1] / "data" / "track02_fraud_watch.csv"
OUT = pathlib.Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)

out: list[str] = []


def log(m: str = "") -> None:
    print(m)
    out.append(m)


df = pd.read_csv(DATA, parse_dates=["timestamp", "account_open_date"])
df["sec"] = df.timestamp.dt.second
df["minute"] = df.timestamp.dt.minute

log("# Ring findings — Track 02 Fraud Watch\n")

# --- Hypothesis A: synthetic :00-second timestamps mark injected fraud ---
log("## A. Timestamp fingerprint")
zero_sec = df[df.sec == 0]
log(f"- txns with second == :00 : **{len(zero_sec)}** / {len(df)} "
    f"({len(zero_sec)/len(df)*100:.1f}%)  — uniform would be ~1.7%")
zz = df[(df.sec == 0) & (df.minute == 0)]
log(f"- txns at exactly HH:00:00 : **{len(zz)}**")
log(f"- total $ in :00-second txns : **${zero_sec.amount.sum():,.2f}**")
zacct = sorted(zero_sec.account_id.unique())
log(f"- distinct accounts in :00-second txns : **{len(zacct)}**")
log(f"  {zacct}\n")

# --- Hypothesis B: counterparty concentration (funnel/mule) ---
log("## B. Counterparty concentration")
acct = df.groupby("account_id").agg(
    txns=("txn_id", "count"),
    total=("amount", "sum"),
    n_cp=("counterparty_id", "nunique"),
    zero_sec_txns=("sec", lambda s: (s == 0).sum()),
)
acct["zero_sec_frac"] = acct.zero_sec_txns / acct.txns
funnel = acct[(acct.total > 5000) & (acct.n_cp <= 3)].sort_values("total", ascending=False)
log("High-volume (>$5k) accounts funneling into <=3 counterparties:")
log("```")
log(funnel.to_string())
log("```")
log(f"- count: **{len(funnel)}**, combined total **${funnel.total.sum():,.2f}**\n")

# --- Hypothesis C: the suspect cohort & shared destination ---
log("## C. Suspect cohort & shared destinations")
# Accounts that are mostly :00-second (synthetic) are the ring.
ring = acct[acct.zero_sec_frac > 0.5].sort_values("total", ascending=False)
log(f"Accounts that are >50% :00-second txns (the injected ring):")
log("```")
log(ring.to_string())
log("```")
ring_ids = list(ring.index)
log(f"- ring size: **{len(ring_ids)}**")
log(f"- ring total volume: **${ring.total.sum():,.2f}**")
ring_fraud_only = zero_sec[zero_sec.account_id.isin(ring_ids)]
log(f"- ring exposure counting ONLY :00-second txns: "
    f"**${ring_fraud_only.amount.sum():,.2f}**  (hint ~= $161,751)")
log(f"- ring accounts: {ring_ids}\n")

# Where does the ring money go?
log("Counterparties receiving the ring's :00-second money:")
dest = ring_fraud_only.groupby("counterparty_id").agg(
    amount=("amount", "sum"), txns=("txn_id", "count"),
    from_accts=("account_id", "nunique")).sort_values("amount", ascending=False)
log("```")
log(dest.head(20).to_string())
log("```\n")

# --- Hypothesis D: account_open_date clustering (burst-opened mules) ---
log("## D. Account-open clustering")
opens = df.groupby("account_id").account_open_date.first()
ring_opens = opens[opens.index.isin(ring_ids)].sort_values()
log("Open dates of ring accounts:")
log("```")
log(ring_opens.to_string())
log("```\n")

(OUT / "ring_findings.md").write_text("\n".join(out))
log(f"Wrote -> {OUT / 'ring_findings.md'}")
