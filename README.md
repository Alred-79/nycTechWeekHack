# 🛡️ RingFence — Calibrated AML Triage

**RingFence** scans a bank's transactions, surfaces the money-laundering ring, routes the
one genuinely ambiguous account to a human instead of guessing, and ignores the planted
decoy — and it shows the math behind every call.

On the Crestline Community Bank dataset (5,000 transactions · 294 accounts · 90 days) it
finds the **9-account ring** moving **\$161,750.90**, flags the boundary case `AC-0012`
for human review, and clears the 4 device-sharing decoys.

---

## ▶ See it in 30 seconds — two ways, both need **no setup and no internet**

### 1. The interactive 3D graph — just double-click

Open this file in any web browser:

```
ui/RingFence_constellation.html
```

It is **fully self-contained** (all JS baked in — no install, no server, no Wi-Fi). It's
the live money-laundering graph:

- **Drag** any node · **scroll** to zoom out far · **Fit ⤢** to recenter
- **Reveal the ring** — collapses the 5,000-txn noise cloud to the ~14 surfaced accounts
- **Money flow ▶** — animates funds moving through the layering chains
- **Click** any node — its probability, uncertainty, \$ moved, and the decision math
- **Search** an account (e.g. `AC-0009`) to fly to it

🔴 escalated mule · 🟡 sent to a human · ⚪ decoy (cleared) · merchant hubs in blue.

### 2. The full app — localhost

```bash
uv run streamlit run ui/app.py
```

Open **http://localhost:8501**. It opens straight into the pre-built demo — no upload,
no waiting.

| Tab | What's there |
|-----|--------------|
| 📋 **Queue** | Every surfaced account ranked by mule probability — click a row to inspect |
| 🌐 **Constellation** | The interactive 3D graph (same as `ui/RingFence_constellation.html`) + triage funnel |
| 🔎 **Case detail** | Posterior, expected-loss math, signals, ring subgraph, SAR download |
| 🧬 **Signatures** | The 3 fingerprints: `:00`-second automation · account-opening burst · sub-threshold amounts |
| 📄 **Memo** | Money-flow Sankey (\$161,750.90) + downloadable SAR memo + the learned rule |
| 🧠 **Pipeline** | How the 4 agents build on each other through Cognee memory |

---

## How it works — 4 agents over shared Cognee memory

Each agent reads the previous agent's fields from Cognee and writes a new layer onto a
shared `Case` object (one per account):

| Agent | Adds to each Case |
|-------|-------------------|
| **1 · Detector** | topological role, the behavioural signals, decoy flag, distribution stats |
| **2 · Estimator** (PyMC) | calibrated `p_mule` + 94% credible interval |
| **3 · Adjudicator** | the decision (escalate / clear / **review**) from expected-loss math + EVPI |
| **4 · Reporter** | SAR memo, dollar reconciliation, and the learned closing rule |

The one idea: **calibrated abstention.** `AC-0012`'s interval straddles the loss-justified
threshold τ, so RingFence routes it to a human rather than forcing a call.

---

## Rebuild the demo data

After any code or dataset change, regenerate the snapshot **and** the standalone HTML:

```bash
uv run python -m ui.snapshot
```

This rewrites:
- `ui/RingFence_snapshot.json` — what the app loads on startup
- `ui/RingFence_constellation.html` — the double-click graph

Run the full pipeline from the CLI instead:

```bash
uv run python main.py data/track02_fraud_watch.csv
uv run pytest -q          # acceptance tests against the known ring
```

---

## Layout

```
ui/RingFence_constellation.html   ← double-click: the standalone interactive graph
ui/app.py                      ← the Streamlit app (localhost:8501)
ui/ring_graph.py               ← 3D force-graph component (vendored JS, fully offline)
ui/charts.py                   ← funnel · posterior strip · :00 clock · Sankey · …
ui/snapshot.py                 ← builds RingFence_snapshot.json + RingFence_constellation.html
ui/vendor/                     ← three.js / 3d-force-graph (local, no CDN)
agents/                        ← Detector → Estimator → Adjudicator → Reporter
data/track02_fraud_watch.csv   ← the Crestline dataset
RingFence_Final_Plan.md           ← full product spec
```

> The previous RingFence write-up is archived in [README_ringfence.md](README_ringfence.md)
> for history; its premise (circular loops, shared-device = ring) was contradicted by the
> data. The source of truth is [RingFence_Final_Plan.md](RingFence_Final_Plan.md).
