"""
Interactive Plotly visuals for Quorum — all dark-themed and colour-consistent
with the 3D graph (red=escalate, amber=review, gray=decoy, green=clear).

Every figure is built from the live pipeline output or the raw DuckDB table,
so the charts ARE the evidence, not decoration.
"""
from __future__ import annotations

import plotly.graph_objects as go

C = {"ring": "#ff5468", "review": "#f7b733", "decoy": "#8a93a6",
     "clear": "#34d6a4", "noise": "#46527a", "money": "#5fd0e0",
     "violet": "#8ab4ff", "cyan": "#5fd0e0",
     "ink": "#e7ebf3", "grid": "rgba(178,198,234,0.08)",
     "bg": "#0a0c11", "panel": "#0f131b"}

_FONT = "IBM Plex Mono, ui-monospace, monospace"


def _dark(fig: go.Figure, h: int = 360, title: str = "") -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#8a93a6")),
        height=h, paper_bgcolor=C["bg"], plot_bgcolor=C["bg"],
        font=dict(color=C["ink"], size=12, family=_FONT),
        margin=dict(l=20, r=20, t=46, b=20),
        legend=dict(orientation="h", y=1.06, x=0, bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(gridcolor=C["grid"], zeroline=False)
    fig.update_yaxes(gridcolor=C["grid"], zeroline=False)
    return fig


def _color_for(case: dict) -> str:
    if case.get("action") == "ESCALATE":
        return C["ring"]
    if case.get("action") == "REVIEW":
        return C["review"]
    if case.get("decoy_suspect"):
        return C["decoy"]
    return C["clear"]


# ── Funnel: 298 → surfaced → escalate/review/clear ───────────────────────────
def funnel(counts: dict) -> go.Figure:
    fig = go.Figure(go.Funnel(
        y=["All accounts", "Surfaced", "Escalate", "Review", "Cleared (decoys)"],
        x=[counts["total"], counts["surfaced"], counts["escalate"],
           counts["review"], counts["clear"]],
        textposition="inside", textinfo="value",
        marker=dict(color=[C["noise"], C["violet"], C["ring"], C["review"], C["decoy"]]),
        connector=dict(line=dict(color=C["grid"])),
    ))
    return _dark(fig, 300, "Triage funnel — 99% auto-cleared")


# ── Posterior strip: p_mule ± credible interval per account, with τ ──────────
def posterior_strip(cases: list[dict], tau: float = 0.05) -> go.Figure:
    cs = sorted(cases, key=lambda c: c.get("p_mule") or 0)
    ys = [c["account"] for c in cs]
    ps = [c.get("p_mule") or 0 for c in cs]
    los = [p - (c.get("credible_interval") or [p, p])[0] for c, p in zip(cs, ps)]
    his = [(c.get("credible_interval") or [p, p])[1] - p for c, p in zip(cs, ps)]
    fig = go.Figure(go.Scatter(
        x=ps, y=ys, mode="markers",
        marker=dict(size=12, color=[_color_for(c) for c in cs],
                    line=dict(width=1, color="#05070d")),
        error_x=dict(type="data", symmetric=False, array=his, arrayminus=los,
                     color="rgba(255,255,255,0.4)", thickness=1.5, width=4),
        hovertext=[f"{c['account']}: {c.get('p_mule'):.3f} "
                   f"CI {c.get('credible_interval')}" for c in cs],
        hoverinfo="text",
    ))
    fig.add_vline(x=tau, line=dict(color=C["money"], dash="dash"),
                  annotation_text=f"τ={tau}", annotation_font_color=C["money"])
    fig.update_xaxes(title="P(mule) — calibrated posterior with 94% interval",
                     range=[-0.03, 1.03])
    return _dark(fig, 420, "Calibrated probability + uncertainty (the abstention story)")


# ── Expected-loss bars for one account (the decision math) ───────────────────
def expected_loss(case: dict) -> go.Figure:
    esc = case.get("E_loss_escalate") or 0
    clr = case.get("E_loss_clear") or 0
    fig = go.Figure(go.Bar(
        x=["E[loss | escalate]", "E[loss | clear]"], y=[esc, clr],
        marker_color=[C["ring"], C["clear"]],
        text=[f"${esc:,.2f}", f"${clr:,.2f}"], textposition="outside",
    ))
    fig.update_yaxes(title="expected loss ($)")
    return _dark(fig, 300, f"Why {case['account']} → {case.get('action')} (argmin expected loss)")


# ── Signal radar for one account ─────────────────────────────────────────────
def signal_radar(case: dict) -> go.Figure:
    feats = ["under_threshold", "fresh_cohort", "zero_merchant",
             "pure_sink", "automation", "relay_depth"]
    sig = case.get("signals", {})
    vals = [sig.get(f, 0) for f in feats]
    labels = [f.replace("_", " ") for f in feats]
    fig = go.Figure(go.Scatterpolar(
        r=vals + [vals[0]], theta=labels + [labels[0]], fill="toself",
        line=dict(color=_color_for(case)), fillcolor=_color_for(case), opacity=0.55,
    ))
    fig.update_layout(
        polar=dict(bgcolor=C["bg"],
                   radialaxis=dict(visible=True, range=[0, 1], showticklabels=False,
                                   gridcolor=C["grid"]),
                   angularaxis=dict(gridcolor=C["grid"])),
    )
    return _dark(fig, 320, f"{case['account']} — signals that fired")


# ── The :00-second automation fingerprint (polar histogram) ──────────────────
def second_clock(rows: list[list]) -> go.Figure:
    """rows: list of [second, ring_count, merchant_count] (precomputed)."""
    secs = [r[0] for r in rows]
    ring = [r[1] for r in rows]
    merch = [r[2] for r in rows]
    theta = [s * 6 for s in secs]   # 60 seconds → 360°
    fig = go.Figure()
    fig.add_trace(go.Barpolar(r=merch, theta=theta, name="Merchant txns",
                              marker_color=C["noise"], opacity=0.8))
    fig.add_trace(go.Barpolar(r=ring, theta=theta, name="AC→AC transfers",
                              marker_color=C["ring"]))
    fig.update_layout(
        polar=dict(bgcolor=C["bg"],
                   radialaxis=dict(showticklabels=False, gridcolor=C["grid"]),
                   angularaxis=dict(rotation=90, direction="clockwise",
                                    tickmode="array", tickvals=[0, 90, 180, 270],
                                    ticktext=[":00", ":15", ":30", ":45"],
                                    gridcolor=C["grid"])),
    )
    return _dark(fig, 400, "Automation fingerprint — every ring transfer lands on :00")


# ── Account-opening burst timeline ───────────────────────────────────────────
def opening_burst(ring_dates: list[str], other_dates: list[str]) -> go.Figure:
    """ring_dates / other_dates: precomputed account open-date lists."""
    ring_x, ring_y = ring_dates, [1] * len(ring_dates)
    base_x, base_y = other_dates, [0] * len(other_dates)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=base_x, y=base_y, mode="markers", name="Other accounts",
                             marker=dict(color=C["noise"], size=6, opacity=0.6)))
    fig.add_trace(go.Scatter(x=ring_x, y=ring_y, mode="markers", name="Ring accounts",
                             marker=dict(color=C["ring"], size=13,
                                         line=dict(width=1, color="#fff"))))
    fig.update_yaxes(showticklabels=False, range=[-0.5, 1.5])
    fig.update_xaxes(title="account open date")
    return _dark(fig, 280, "Burst-created mules — ring opened in one Feb-2026 window")


# ── Sub-threshold amount histogram ───────────────────────────────────────────
def amount_hist(ac: list[float], mr: list[float], floor: float = 1000.0) -> go.Figure:
    """ac / mr: precomputed AC→AC transfer and merchant amount lists."""
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=mr, name="Merchant", marker_color=C["noise"],
                               opacity=0.7, nbinsx=60))
    fig.add_trace(go.Histogram(x=ac, name="AC→AC transfers", marker_color=C["ring"],
                               opacity=0.85, nbinsx=40))
    fig.add_vline(x=floor, line=dict(color=C["money"], dash="dash"),
                  annotation_text="$1,000 floor", annotation_font_color=C["money"])
    fig.update_layout(barmode="overlay")
    fig.update_xaxes(title="amount ($)")
    return _dark(fig, 320, "Structuring — every transfer sits just under the floor")


# ── Money-flow Sankey, reconciles to $161,750.90 ─────────────────────────────
def money_sankey(edges: list[dict]) -> go.Figure:
    accts = sorted({e["sender"] for e in edges} | {e["receiver"] for e in edges})
    idx = {a: i for i, a in enumerate(accts)}
    fig = go.Figure(go.Sankey(
        node=dict(label=accts, pad=18, thickness=16,
                  color=C["ring"], line=dict(color="#05070d", width=0.5)),
        link=dict(
            source=[idx[e["sender"]] for e in edges],
            target=[idx[e["receiver"]] for e in edges],
            value=[e["total_usd"] for e in edges],
            color="rgba(255,209,102,0.45)",
            label=[f"${e['total_usd']:,.2f} · {e['count']} txns" for e in edges],
        ),
    ))
    total = sum(e["total_usd"] for e in edges)
    return _dark(fig, 380, f"Money flow through the ring — reconciles to ${total:,.2f}")
