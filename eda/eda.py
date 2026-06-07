"""
Small EDA for Track 02 — Fraud Watch (Crestline Community Bank).

Goal: understand the shape of the data and surface signals that a coordinated
ring of ~12 accounts (total exposure ~= $161,751) might leave behind, WITHOUT
crossing any single-transaction alert threshold.

Run:  uv run python eda/eda.py
Writes plots + a markdown summary into eda/out/.
"""

from __future__ import annotations

import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

DATA = pathlib.Path(__file__).resolve().parents[1] / "data" / "track02_fraud_watch.csv"
OUT = pathlib.Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)

lines: list[str] = []


def log(msg: str = "") -> None:
    print(msg)
    lines.append(msg)


def section(title: str) -> None:
    log()
    log(f"## {title}")
    log()


# ---------------------------------------------------------------------------
df = pd.read_csv(DATA, parse_dates=["timestamp", "account_open_date"])

section("Shape & schema")
log(f"- Rows: **{len(df):,}**  |  Columns: **{df.shape[1]}**")
log(f"- Date range: **{df.timestamp.min()}** → **{df.timestamp.max()}** "
    f"({(df.timestamp.max() - df.timestamp.min()).days} days)")
log(f"- Unique accounts: **{df.account_id.nunique()}**  |  "
    f"counterparties: **{df.counterparty_id.nunique()}**  |  "
    f"devices: **{df.device_id.nunique()}**")
log()
log("Column dtypes / null counts:")
log("```")
for c in df.columns:
    log(f"{c:<20} {str(df[c].dtype):<16} nulls={df[c].isna().sum()}")
log("```")

section("Amount distribution (threshold-evasion check)")
amt = df.amount
log(f"- min ${amt.min():,.2f}  median ${amt.median():,.2f}  "
    f"mean ${amt.mean():,.2f}  max ${amt.max():,.2f}")
log(f"- total volume: **${amt.sum():,.2f}**")
for thr in (1000, 3000, 5000, 10000):
    near = df[(amt >= thr * 0.9) & (amt < thr)]
    log(f"- txns in [{thr*0.9:,.0f}, {thr:,.0f}) (just-under ${thr:,}): "
        f"**{len(near)}**")
log(f"- txns >= $10,000 (CTR / structuring line): **{(amt >= 10000).sum()}**")

plt.figure(figsize=(8, 4))
amt.hist(bins=80)
plt.title("Transaction amount distribution")
plt.xlabel("amount ($)")
plt.ylabel("count")
plt.tight_layout()
plt.savefig(OUT / "amount_hist.png", dpi=110)
plt.close()

section("Categorical breakdowns")
log("Merchant categories:")
log("```")
log(df.merchant_category.value_counts().to_string())
log("```")
log("IP regions:")
log("```")
log(df.ip_region.value_counts().to_string())
log("```")

section("Per-account activity")
acct = df.groupby("account_id").agg(
    txns=("txn_id", "count"),
    total=("amount", "sum"),
    mean_amt=("amount", "mean"),
    n_devices=("device_id", "nunique"),
    n_regions=("ip_region", "nunique"),
    n_counterparties=("counterparty_id", "nunique"),
    first=("timestamp", "min"),
    last=("timestamp", "max"),
)
log(f"- txns/account: min {acct.txns.min()} median {acct.txns.median():.0f} "
    f"max {acct.txns.max()}")
log(f"- total$/account: median ${acct.total.median():,.0f} "
    f"max ${acct.total.max():,.0f}")
log()
log("Top 15 accounts by total volume:")
log("```")
log(acct.sort_values("total", ascending=False).head(15).to_string())
log("```")

# ---------------------------------------------------------------------------
# Ring signals: the prompt says ~12 accounts, ~$161,751 exposure, no single
# alert tripped. Coordinated rings tend to SHARE infrastructure (devices/IP)
# and FUNNEL money to common counterparties. Hunt for those overlaps.
section("Shared-infrastructure signals (ring hunting)")

dev_share = df.groupby("device_id")["account_id"].nunique().sort_values(ascending=False)
shared_dev = dev_share[dev_share > 1]
log(f"- devices used by >1 account: **{len(shared_dev)}** "
    f"(out of {df.device_id.nunique()})")
log("Top shared devices (device_id -> #distinct accounts):")
log("```")
log(shared_dev.head(15).to_string())
log("```")

# Accounts touching the most-shared devices
top_devs = shared_dev.head(8).index.tolist()
ring_accts = sorted(df[df.device_id.isin(top_devs)].account_id.unique())
log(f"- accounts touching the top-8 shared devices: **{len(ring_accts)}**")
log(f"  {ring_accts}")

cp_share = df.groupby("counterparty_id")["account_id"].nunique().sort_values(ascending=False)
log()
log("Top counterparties by #distinct accounts paying them:")
log("```")
log(cp_share.head(15).to_string())
log("```")

section("Candidate ring assembly")
# Heuristic: accounts that share a device with another account AND funnel into
# a heavily-shared counterparty are prime suspects. Score accounts by exposure
# concentrated on shared devices.
shared_dev_set = set(shared_dev.index)
flagged = df[df.device_id.isin(shared_dev_set)]
ring_candidate = flagged.groupby("account_id").agg(
    shared_dev_txns=("txn_id", "count"),
    shared_dev_total=("amount", "sum"),
    devices=("device_id", "nunique"),
).sort_values("shared_dev_total", ascending=False)
log("Accounts ranked by $ flowing through shared devices:")
log("```")
log(ring_candidate.head(20).to_string())
log("```")
top12 = ring_candidate.head(12)
log(f"- Top-12 candidate exposure (via shared devices): "
    f"**${top12.shared_dev_total.sum():,.2f}**  "
    f"(target hint ~= $161,751)")

# Timeline plot of overall daily volume
section("Temporal pattern")
daily = df.set_index("timestamp").resample("D")["amount"].sum()
plt.figure(figsize=(9, 4))
daily.plot()
plt.title("Daily transaction volume ($)")
plt.ylabel("$ / day")
plt.tight_layout()
plt.savefig(OUT / "daily_volume.png", dpi=110)
plt.close()
log("- See `out/daily_volume.png` for daily $ volume.")

# Hour-of-day (rings often batch at odd hours)
df["hour"] = df.timestamp.dt.hour
hourly = df.hour.value_counts().sort_index()
log("Txns by hour of day:")
log("```")
log(hourly.to_string())
log("```")

# ---------------------------------------------------------------------------
(OUT / "eda_summary.md").write_text("\n".join(lines))
log()
log(f"Wrote summary -> {OUT / 'eda_summary.md'}")
log(f"Wrote plots   -> {OUT}/*.png")
