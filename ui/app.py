"""
Quorum — Streamlit UI (3 screens)

  1. Queue        — the ~10 surfaced accounts: probability + uncertainty band,
                    top reason, money touched, action chip (Escalate / Review / Clear).
  2. Case detail  — posterior plot, signals, expected-loss arithmetic, typology,
                    ring subgraph, and a downloadable SAR memo.
  3. Pipeline view — the shared Cognee Case object after each agent: fields
                    accreting from signals → probability → action → memo (criterion 2).
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui import charts, ring_graph, snapshot
from ui.graph_data import build_graph, funnel_counts
from ui.snapshot import compute_chart_data

load_dotenv()

st.set_page_config(page_title="Quorum — AML Triage", page_icon="🔭",
                   layout="wide", initial_sidebar_state="collapsed")

for key, default in [("result", None), ("selected", None), ("force_upload", False)]:
    if key not in st.session_state:
        st.session_state[key] = default

# Pre-built demo: open straight into the visuals — no upload, no run required.
if st.session_state.result is None and not st.session_state.force_upload:
    st.session_state.result = snapshot.load()

ACTION_COLOR = {"ESCALATE": "#ff4d6d", "REVIEW": "#ffb020", "CLEAR": "#2ee6a6"}
ACTION_EMOJI = {"ESCALATE": "🔴", "REVIEW": "🟡", "CLEAR": "🟢"}
ROLE_COLOR = {"source": "#7c5cff", "relay": "#22d3ee", "sink": "#ff4d6d", "none": "#8b93b5"}


def inject_theme() -> None:
    st.markdown("""
    <style>
      .stApp { background:
        radial-gradient(1200px 600px at 12% -8%, #1c2a63 0%, rgba(28,42,99,0) 55%),
        radial-gradient(900px 500px at 100% 0%, #3a1f63 0%, rgba(58,31,99,0) 50%),
        #0e1430; }
      .block-container { padding-top: 1.4rem; }
      /* gradient hero */
      .hero { background: linear-gradient(110deg,#7c5cff 0%,#5b8cff 45%,#22d3ee 100%);
        border-radius: 18px; padding: 18px 24px; margin-bottom: 6px;
        box-shadow: 0 14px 40px rgba(124,92,255,.28); }
      .hero h1 { color:#fff; margin:0; font-size: 30px; letter-spacing:-.5px; }
      .hero p  { color: rgba(255,255,255,.92); margin:.25rem 0 0; font-size: 14px; }
      /* metric cards */
      div[data-testid="stMetric"] { background: rgba(25,34,74,.65);
        border: 1px solid rgba(124,92,255,.25); border-left: 4px solid #7c5cff;
        border-radius: 14px; padding: 14px 16px; }
      div[data-testid="stMetric"]:hover { border-left-color:#22d3ee; }
      div[data-testid="stMetricValue"] { color:#fff; font-weight:700; }
      div[data-testid="stMetricLabel"] p { color:#aeb8e0; font-weight:600; }
      /* tabs */
      .stTabs [data-baseweb="tab-list"] { gap: 6px; }
      .stTabs [data-baseweb="tab"] { background: rgba(25,34,74,.55);
        border-radius: 10px 10px 0 0; padding: 8px 16px; color:#aeb8e0; }
      .stTabs [aria-selected="true"] { background: linear-gradient(180deg,#7c5cff,#5b46d6);
        color:#fff !important; }
      /* buttons */
      .stButton>button, .stDownloadButton>button { border-radius:10px; font-weight:600; }
      .stButton>button[kind="primary"], .stDownloadButton>button {
        background: linear-gradient(120deg,#7c5cff,#22d3ee); border:none; color:#06122b; }
      /* badges */
      .badge { padding:3px 10px; border-radius:99px; font-size:12px; font-weight:800;
        color:#06122b; }
    </style>
    """, unsafe_allow_html=True)


def kpi_row(r: dict) -> None:
    cn = r["counts"]
    rep = r["reporter"]
    exposure = r["detector"]["total_ring_exposure"]
    volume = r.get("total_volume") or 0
    ratio = (exposure / volume * 100) if volume else 0
    cols = st.columns(5)
    cols[0].metric("Accounts scanned", f"{cn['total']:,}", f"{cn['auto_cleared']:,} auto-cleared")
    cols[1].metric("🔴 Ring escalated", cn["escalate"])
    cols[2].metric("💰 Exposure", f"${exposure:,.0f}",
                   f"{ratio:.1f}% of ${volume/1000:,.0f}k volume"
                   + ("  ·  reconciled ✓" if rep.get("reconciliation_ok") else "  ·  ⚠ check"),
                   delta_color="off")
    cols[3].metric("🟡 Sent to human", cn["review"])
    cols[4].metric("🟢 Decoys ignored", cn["clear"])


def _run_pipeline(csv_path: str) -> dict:
    import duckdb
    import cognee_client as cognee
    from agents import investigator, narrator, ranker, scout
    from db import queries

    con = duckdb.connect()
    queries.load_csv(con, csv_path)
    detector = scout.run(con)
    ranker.run()
    adjudicator = investigator.run(con, detector_result=detector)
    reporter = narrator.run(detector_result=detector)
    cases = cognee.read_cases(candidates_only=True)
    n_total = detector["dist_stats"].get("n_accounts_total", 0)
    ring_accounts = {c["account"] for c in cases if c.get("action") == "ESCALATE"}
    return {
        "detector": detector,
        "adjudicator": adjudicator,
        "reporter": reporter,
        "cases": cases,
        "dist_stats": detector["dist_stats"],
        "total_volume": float(con.execute("SELECT SUM(amount) FROM transactions").fetchone()[0] or 0),
        "total_txns": int(con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] or 0),
        # kept open for the interactive visuals (graph + signature charts)
        "con": con,
        "graph": build_graph(con, detector, cases),
        "counts": funnel_counts(cases, n_total),
        "ring_accounts": sorted(ring_accounts),
        "chart_data": compute_chart_data(con, ring_accounts),
        # The real Cognee graph is built on demand (Pipeline view) — cognify()
        "cognee": st.session_state.get("cognee_status", {"used": False, "reason": "not built yet"}),
    }


def _posterior_plot(case: dict, tau: float):
    p = case.get("p_mule", 0.0)
    lo, hi = case.get("credible_interval", [0.0, 0.0])
    fig, ax = plt.subplots(figsize=(6, 1.5))
    ax.hlines(0, 0, 1, color="#ddd", lw=1)
    ax.fill_betweenx([-0.4, 0.4], lo, hi, color="#90caf9", alpha=0.6,
                     label="94% credible interval")
    ax.vlines(p, -0.4, 0.4, color="#1565C0", lw=2, label=f"p_mule = {p:.3f}")
    ax.vlines(tau, -0.6, 0.6, color="#d32f2f", lw=1.5, ls="--", label=f"τ = {tau:.2f}")
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.8, 0.8)
    ax.set_yticks([])
    ax.set_xlabel("P(account is a mule)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.5), ncol=3, fontsize=7, frameon=False)
    fig.tight_layout()
    return fig


def _subgraph(edges, cases_by_acct):
    import math
    nodes = sorted({e["sender"] for e in edges} | {e["receiver"] for e in edges})
    ang = 2 * math.pi / max(len(nodes), 1)
    pos = {n: (math.cos(i * ang), math.sin(i * ang)) for i, n in enumerate(nodes)}
    ex, ey = [], []
    for e in edges:
        if e["sender"] in pos and e["receiver"] in pos:
            x0, y0 = pos[e["sender"]]
            x1, y1 = pos[e["receiver"]]
            ex += [x0, x1, None]
            ey += [y0, y1, None]
    edge_tr = go.Scatter(x=ex, y=ey, mode="lines", line=dict(width=1.5, color="#888"),
                         hoverinfo="none")
    colors = [ROLE_COLOR.get(str(cases_by_acct.get(n, {}).get("role", "none")), "#546e7a")
              for n in nodes]
    node_tr = go.Scatter(
        x=[pos[n][0] for n in nodes], y=[pos[n][1] for n in nodes],
        mode="markers+text", text=nodes, textposition="top center",
        marker=dict(size=26, color=colors, line=dict(width=1, color="white")),
        hovertext=[f"{n} — {cases_by_acct.get(n, {}).get('role','')}" for n in nodes],
        hoverinfo="text")
    fig = go.Figure([edge_tr, node_tr], layout=go.Layout(
        showlegend=False, hovermode="closest", height=460,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="white")))
    return fig


# ── Header ────────────────────────────────────────────────────────────────────
inject_theme()
st.markdown(
    "<div class='hero'><h1>🛡️ Quorum</h1>"
    "<p>Calibrated AML triage — surfaces the ring, refuses to guess on the ambiguous, "
    "ignores the planted decoy, and shows the math behind every call.</p></div>",
    unsafe_allow_html=True)

if st.session_state.result is not None:
    kpi_row(st.session_state.result)

tabs = st.tabs(["📋 Queue", "🌐 Constellation", "🔎 Case detail",
                "🧬 Signatures", "📄 Memo", "🧠 Pipeline"])

# ══════════════════════════════════════════════════════════════════════════════
# Screen 1 — Queue
# ══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    if st.session_state.result is None:
        st.markdown("#### Load the Crestline transaction file")

        default_csv = Path(__file__).resolve().parents[1] / "data" / "track02_fraud_watch.csv"

        def _run_on(path: str) -> None:
            prog = st.progress(0, text="Detector → Estimator → Adjudicator → Reporter")
            t0 = time.time()
            for pct, label in [(25, "Detector: roles + signals"),
                               (50, "Estimator: calibrated probabilities"),
                               (75, "Adjudicator: expected-loss decisions"),
                               (95, "Reporter: SAR memo")]:
                prog.progress(pct, text=label)
                time.sleep(0.05)
            st.session_state.result = _run_pipeline(path)
            prog.progress(100, text=f"Done in {time.time()-t0:.1f}s")
            st.rerun()

        if default_csv.exists():
            if st.button(f"▶ Run on competition file — {default_csv.name}",
                         type="primary"):
                _run_on(str(default_csv))
            st.caption("…or upload your own:")

        uploaded = st.file_uploader("Drop the 5,000-transaction CSV", type=["csv"],
                                    label_visibility="collapsed")
        if uploaded is not None:
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
                tmp.write(uploaded.read())
                tmp_path = tmp.name
            _run_on(tmp_path)
    else:
        r = st.session_state.result
        adj = r["adjudicator"]
        ds = r["dist_stats"]
        n_total = ds.get("n_accounts_total", 0)
        tcol1, tcol2 = st.columns([3, 1])
        tcol1.markdown("#### Review queue &nbsp;·&nbsp; "
                       "the accounts the pipeline surfaced, ranked by mule probability")
        if r.get("prebuilt"):
            tcol1.caption(f"🔭 Pre-built demo · {r.get('built_at','')}")
        with tcol2:
            if st.button("↻ Run a different file", use_container_width=True):
                st.session_state.result = None
                st.session_state.force_upload = True
                st.rerun()

        st.plotly_chart(charts.posterior_strip(r["cases"], adj["tau"]),
                        use_container_width=True)

        show_cleared = st.toggle("Show cleared accounts (decoys)", value=True)
        cases = sorted(r["cases"], key=lambda c: c.get("p_mule", 0), reverse=True)
        rows = []
        for c in cases:
            act = c.get("action", "")
            if act == "CLEAR" and not show_cleared:
                continue
            lo, hi = c.get("credible_interval", [0, 0])
            rows.append({
                "Account": c["account"],
                "Decision": f"{ACTION_EMOJI.get(act,'')} {act}",
                "Role": (c.get("role") or "").upper(),
                "P(mule)": round(c.get("p_mule", 0), 3),
                "Uncertainty": f"[{lo:.3f} – {hi:.3f}]",
                "$ moved": round((c.get("signals") or {}).get("_transfer_usd", 0.0), 0),
                "Why (decisive signals)": ", ".join(c.get("decisive_signals") or [])
                    or (c.get("detect_reason", "")[:60]),
            })
        df = pd.DataFrame(rows)
        event = st.dataframe(
            df, use_container_width=True, hide_index=True,
            on_select="rerun", selection_mode="single-row",
            column_config={
                "P(mule)": st.column_config.ProgressColumn(
                    "P(mule)", min_value=0.0, max_value=1.0, format="%.3f"),
                "$ moved": st.column_config.NumberColumn("$ moved", format="$%d"),
                "Decision": st.column_config.TextColumn("Decision", width="small"),
            })
        sel_rows = event.selection.get("rows", []) if event and event.selection else []
        if sel_rows:
            st.session_state.selected = df.iloc[sel_rows[0]]["Account"]
            st.info(f"Selected **{st.session_state.selected}** → open the "
                    f"**🔎 Case detail** tab for the full breakdown.")
        st.caption(f"The {n_total - len(cases)} accounts with no firing signal were "
                   f"auto-cleared by the Detector and never surfaced. "
                   f"Click a row to inspect it.")

# ══════════════════════════════════════════════════════════════════════════════
# Screen 1b — Constellation (the interactive 3D drag-and-drop ring graph)
# ══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    if st.session_state.result is None:
        st.info("Load the file on the Queue screen first.")
    else:
        r = st.session_state.result
        cn = r["counts"]
        st.markdown("#### The transaction graph &nbsp;·&nbsp; "
                    "294 accounts of noise → the 9-account ring")
        st.caption("**Drag** any node · scroll to zoom out far · **Reveal the ring** collapses the "
                   "5,000-txn hairball · **Money flow** animates the transfers · "
                   "**click** a node to inspect its posterior + decision math.")
        ring_graph.render(r["graph"], height=640)
        st.markdown("#### Triage funnel")
        st.plotly_chart(charts.funnel(cn), use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# Screen 2 — Case detail
# ══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    if st.session_state.result is None:
        st.info("Load the file on the Queue screen first.")
    else:
        r = st.session_state.result
        cases_by_acct = {c["account"]: c for c in r["cases"]}
        accts = sorted(cases_by_acct, key=lambda a: cases_by_acct[a].get("p_mule", 0), reverse=True)
        sel = st.selectbox("Account", accts,
                           index=accts.index(st.session_state.selected)
                           if st.session_state.selected in accts else 0)
        c = cases_by_acct[sel]
        tau = r["adjudicator"]["tau"]

        chip = c.get("action", "")
        st.markdown(
            f"### {sel} &nbsp; "
            f"<span style='background:{ACTION_COLOR.get(chip,'#555')};color:white;"
            f"padding:3px 10px;border-radius:6px;font-size:15px'>{chip}</span>",
            unsafe_allow_html=True)
        if c.get("decoy_suspect"):
            st.warning("Planted **decoy**: shares a device but is isolated in the transfer "
                       "graph. The skeptical prior keeps its probability low — not flagged.")

        left, right = st.columns([1.1, 1])
        with left:
            st.markdown("**Posterior — P(mule) with 94% credible interval**")
            st.pyplot(_posterior_plot(c, tau))
            st.markdown("**Expected-loss arithmetic**")
            st.code(c.get("action_reason", ""), language="text")
            st.markdown(f"**Typology:** {c.get('typology') or '—'}")
            if c.get("closing_rule"):
                st.markdown("**Learned closing rule**")
                st.code(c["closing_rule"], language="sql")
        with right:
            st.markdown("**Signals that fired**")
            sig = c.get("signals") or {}
            fired = {k: v for k, v in sig.items()
                     if not k.startswith("_") and v}
            st.json(fired)
            st.markdown("**Signal contributions (logit)**")
            st.json(c.get("signal_contributions") or {})

        st.divider()
        st.markdown("**Ring subgraph** (node colour = role)")
        st.plotly_chart(_subgraph(r["detector"]["edges"], cases_by_acct),
                        use_container_width=True)

        st.download_button("⬇ Download SAR memo", r["reporter"]["memo_text"],
                           "QRM-2026-RING-001-memo.txt", "text/plain")

# ══════════════════════════════════════════════════════════════════════════════
# Screen 3 — Signatures (the mechanical fingerprints, learned from the data)
# ══════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    if st.session_state.result is None:
        st.info("Load the file on the Queue screen first.")
    else:
        r = st.session_state.result
        cd = r["chart_data"]
        st.caption("Three independent fingerprints isolate the same ring — none was "
                   "hardcoded; the pipeline learned each boundary from the data.")
        c1, c2 = st.columns(2)
        c1.plotly_chart(charts.second_clock(cd["second_clock"]), use_container_width=True)
        c2.plotly_chart(charts.opening_burst(cd["opening_burst"]["ring"],
                                             cd["opening_burst"]["other"]),
                        use_container_width=True)
        st.plotly_chart(charts.amount_hist(cd["amount_hist"]["ac"],
                                           cd["amount_hist"]["mr"]),
                        use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# Screen 4 — Memo (money-flow Sankey + SAR memo + learned closing rule)
# ══════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    if st.session_state.result is None:
        st.info("Load the file on the Queue screen first.")
    else:
        r = st.session_state.result
        rep = r["reporter"]
        st.plotly_chart(charts.money_sankey(r["detector"]["edges"]),
                        use_container_width=True)
        ok = "✅" if rep.get("reconciliation_ok") else "⚠️"
        cM = st.columns([1, 2])
        cM[0].metric("Reconciled total", f"${rep.get('reconciled_total', 0):,.2f}",
                     f"{ok} target $161,750.90")
        cM[1].markdown(f"**Typology:** {rep.get('typology', '')}")
        cM[1].markdown("**Learned closing rule** — deploy to catch the next ring:")
        cM[1].code(rep.get("closing_rule", ""), language="sql")
        st.download_button("⬇ Download SAR memo (TXT)", rep.get("memo_text", ""),
                           "QRM-2026-RING-001-memo.txt", "text/plain", type="primary")
        with st.expander("Preview SAR memo"):
            st.text(rep.get("memo_text", ""))

# ══════════════════════════════════════════════════════════════════════════════
# Screen 5 — Pipeline view (criterion 2: fields accreting)
# ══════════════════════════════════════════════════════════════════════════════
with tabs[5]:
    if st.session_state.result is None:
        st.info("Load the file on the Queue screen first.")
    else:
        r = st.session_state.result
        cases_by_acct = {c["account"]: c for c in r["cases"]}
        accts = sorted(cases_by_acct)
        sel = st.selectbox("Trace this account's Case node through the pipeline", accts,
                           key="pipeline_sel")
        c = cases_by_acct[sel]
        st.caption("Each agent reads the previous agent's fields from Cognee and writes a "
                   "new layer. The same Case node grows as the pipeline runs.")
        layers = [
            ("Agent 1 — Detector wrote", ["role", "signals", "is_candidate",
                                          "decoy_suspect", "dist_stats", "detect_reason"]),
            ("Agent 2 — Estimator added", ["p_mule", "credible_interval",
                                           "signal_contributions"]),
            ("Agent 3 — Adjudicator added", ["action", "E_loss_escalate", "E_loss_clear",
                                             "EVPI", "quorum", "decisive_signals"]),
            ("Agent 4 — Reporter added", ["memo_ref", "typology", "dollar_contribution",
                                          "closing_rule"]),
        ]
        for title, fields in layers:
            with st.expander(title, expanded=True):
                st.json({f: c.get(f) for f in fields})

        st.divider()
        st.markdown("#### Cognee memory graph — the enriched Case nodes")
        st.caption("This is the shared memory the 4 agents read and write: each surfaced "
                   "account is a Case node, linked by AC→AC transfers (red) and shared-device "
                   "edges (amber). Drag to explore · click a node to inspect.")
        from ui.graph_data import filter_ring
        ring_graph.render(filter_ring(r["graph"]), height=460)

        st.divider()
        st.markdown("#### Cognee semantic graph — natural-language layer (Gemini)")
        import cognee_client as cognee
        graph = cognee.load_cognee_graph()

        if graph and graph.get("used"):
            st.success(f"✅ Pre-built Cognee graph — each of the 4 agents wrote a layer "
                       f"(`add`), unified with one `cognify`. Built {graph.get('built_at','')}.")
            st.caption("Agents that wrote to Cognee: " + ", ".join(graph.get("agents", [])))
            for agent, text in (graph.get("layers") or {}).items():
                with st.expander(f"Cognee layer written by agent: {agent}"):
                    st.text(text[:4000])
            st.markdown("**Questions answered from the Cognee graph** (`cognee.search`):")
            for item in graph.get("qa", []):
                st.markdown(f"**Q — {item['q']}**")
                st.write(item["a"])
            # Optional live query against the persisted graph (this process).
            q = st.text_input("Ask the graph something else", value="",
                              placeholder="e.g. which account is the hub source?")
            if q and st.button("Search Cognee live"):
                with st.spinner("Searching the Cognee graph…"):
                    res = cognee.cognee_search(q)
                st.write(res if res is not None else "No result / Cognee unavailable.")
        elif not cognee.USE_REAL_COGNEE:
            st.info("Cognee SDK inactive — set `GEMINI_API_KEY` in `.env`, then pre-build the "
                    "graph:  `uv run python main.py data/track02_fraud_watch.csv --cognee`")
        else:
            st.warning("No pre-built Cognee graph found. Build it once (writes "
                       "`cognee_graph.json`): `uv run python main.py "
                       "data/track02_fraud_watch.csv --cognee`  —  or build live below "
                       "(re-runs the agents in Cognee build mode; slow on the free tier).")
            if r.get("con") and st.button("🔭 Build Cognee graph now"):
                from agents import investigator, narrator, ranker, scout
                with st.spinner("Each agent writing its layer → cognify (Gemini)…"):
                    cognee.begin_build()
                    scout.run(r["con"]); ranker.run()
                    investigator.run(r["con"], detector_result=r["detector"])
                    narrator.run(detector_result=r["detector"])
                    cognee.finish_build()
                st.rerun()
            elif not r.get("con"):
                st.caption("Pre-built demo mode — rebuild the Cognee graph from the CLI: "
                           "`uv run python main.py data/track02_fraud_watch.csv --cognee`")
