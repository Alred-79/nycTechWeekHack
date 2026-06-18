"""
Interactive Plotly visuals for Quorum — all dark-themed and colour-consistent
with the 3D graph (red=escalate, amber=review, gray=decoy, green=clear).

Every figure is built from the live pipeline output or the raw DuckDB table,
so the charts ARE the evidence, not decoration.
"""
from __future__ import annotations

import math

import numpy as np
import plotly.graph_objects as go

try:
    from scipy.stats import beta as _BETA
    _HAVE_SCIPY = True
except Exception:  # pragma: no cover — degrade to a moment-matched Beta
    _HAVE_SCIPY = False

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


# ════════════════════════════════════════════════════════════════════════════
# ⚖️ Reasoning tab — Bayesian + decision-theory explainers
# ════════════════════════════════════════════════════════════════════════════
_WF_FEATURES = ["under_threshold", "fresh_cohort", "zero_merchant",
                "pure_sink", "automation", "relay_depth", "device_shared"]
# Prior expectations (Beta means) — the fallback when no stats pack is present.
_PHI_PRIOR_MULE = {f: 0.8 for f in _WF_FEATURES} | {"device_shared": 0.5}
_PHI_PRIOR_LEGIT = {f: 0.2 for f in _WF_FEATURES} | {"device_shared": 0.5}


def _rgba_hex(hexc: str, a: float) -> str:
    h = hexc.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{a})"


def _fit_beta(mu: float, lo: float, hi: float) -> tuple[float, float]:
    """Beta(a,b) whose mean=mu and whose 94% mass ≈ [lo,hi] (ported from
    docs/diagrams/_posterior_views.py: scipy bisection, numpy moment-match fallback)."""
    mu = min(max(mu, 1e-4), 1 - 1e-4)
    w = max(hi - lo, 8e-4)
    if _HAVE_SCIPY:
        def width(k):
            a, b = mu * k, (1 - mu) * k
            return _BETA.ppf(0.97, a, b) - _BETA.ppf(0.03, a, b)
        loK, hiK = 0.6, 5e5
        for _ in range(60):
            mid = (loK * hiK) ** 0.5
            if width(mid) > w:
                loK = mid
            else:
                hiK = mid
        k = (loK * hiK) ** 0.5
    else:
        sd = w / (2 * 1.881)
        k = max(mu * (1 - mu) / max(sd * sd, 1e-8) - 1, 1.2)
    return mu * k, (1 - mu) * k


def _density(mu: float, lo: float, hi: float, x) -> "np.ndarray":
    """Peak-normalised Beta density (shape only) — for overlaid posterior curves."""
    a, b = _fit_beta(mu, lo, hi)
    lp = (a - 1) * np.log(x) + (b - 1) * np.log1p(-x)
    d = np.exp(lp - lp.max())
    return d / d.max()


def _beta_pdf(mu: float, lo: float, hi: float, x) -> "np.ndarray":
    """True Beta pdf (area 1) — for overlaying on a probability-density histogram."""
    a, b = _fit_beta(mu, lo, hi)
    if _HAVE_SCIPY:
        return _BETA.pdf(x, a, b)
    lp = (a - 1) * np.log(x) + (b - 1) * np.log1p(-x)
    d = np.exp(lp - lp.max())
    area = float(np.trapz(d, x)) or 1.0
    return d / area


# ── Act II: per-account log-odds (weight-of-evidence) waterfall ──────────────
def logodds_waterfall(case: dict, phi: dict | None = None) -> go.Figure:
    """Decompose the posterior log-odds: prior logit(π̄) + Σ over APPLICABLE signals
    of the weight of evidence (fired: log(φ_mule/φ_legit); absent: log((1−φ_mule)/(1−φ_legit))).
    Sums by construction to the plug-in logit → σ(·)=p̂. `phi` = stats-pack φ means
    (real, learned); falls back to prior Beta means."""
    sig = case.get("signals") or {}
    contrib = case.get("signal_contributions") or {}
    bias = float(contrib.get("bias", 0.0))
    if phi:
        mule = dict(zip(phi["feature"], phi["mule_mean"]))
        legit = dict(zip(phi["feature"], phi["legit_mean"]))
        src = "learned φ (NUTS posterior means)"
    else:
        mule, legit, src = _PHI_PRIOR_MULE, _PHI_PRIOR_LEGIT, "prior φ means (run the stats pack for learned)"

    # applicability mask — mirrors agents/ranker._applicability_mask
    has_age = sig.get("_age_days") is not None
    originates = (sig.get("_out_deg", 0) or 0) > 0
    applicable = {"under_threshold": True, "fresh_cohort": has_age, "zero_merchant": True,
                  "pure_sink": True, "automation": originates, "relay_depth": originates,
                  "device_shared": True}

    measures, xs, labels, texts, colors = ["absolute"], [bias], ["prior<br>logit(π̄)"], [f"{bias:+.2f}"], [C["violet"]]
    for f in _WF_FEATURES:
        if not applicable.get(f, True):
            continue
        fired = bool(sig.get(f, 0))
        pm = min(max(float(mule[f]), 1e-4), 1 - 1e-4)
        pl = min(max(float(legit[f]), 1e-4), 1 - 1e-4)
        w = (math.log(pm) - math.log(pl)) if fired else (math.log(1 - pm) - math.log(1 - pl))
        measures.append("relative")
        xs.append(round(w, 3))
        labels.append(f"{f.replace('_', ' ')}<br>{'✓ fired' if fired else '· absent'}")
        texts.append(f"{w:+.2f}")
        colors.append(C["ring"] if w >= 0 else C["clear"])
    total = bias + sum(xs[1:])
    p_plugin = 1.0 / (1.0 + math.exp(-total))
    measures.append("total")
    xs.append(round(total, 3))
    labels.append("posterior<br>log-odds")
    texts.append(f"{total:+.2f}")
    colors.append(_color_for(case))

    fig = go.Figure(go.Waterfall(
        orientation="v", measure=measures, x=labels, y=xs,
        text=texts, textposition="outside", textfont=dict(size=11),
        connector=dict(line=dict(color=C["grid"], width=1)),
        increasing=dict(marker=dict(color=C["ring"])),
        decreasing=dict(marker=dict(color=C["clear"])),
        totals=dict(marker=dict(color=_color_for(case))),
        hovertemplate="%{x}<br>Δ log-odds = %{text}<extra></extra>",
    ))
    logit_tau = math.log(0.05 / 0.95)
    fig.add_hline(y=logit_tau, line=dict(color=C["money"], dash="dot"),
                  annotation_text="logit(τ) = −2.94  ·  escalate line",
                  annotation_font_color=C["money"], annotation_position="top left")
    fig.add_hline(y=0, line=dict(color=C["grid"], width=1))
    p_stored = case.get("p_mule")
    stored = f"  ·  stored p={p_stored:.3f}" if p_stored is not None else ""
    fig.update_yaxes(title="log-odds (mule vs legit)")
    return _dark(fig, 440,
                 f"{case['account']}: prior {bias:+.2f} → evidence → logit {total:+.2f} ⇒ p̂={p_plugin:.3f}{stored}  ·  {src}")


# ── Act III: reconstructed posterior densities (ring / boundary / decoy + focus) ─
_ARCHETYPES = [("AC-0009", "ring", "#ff5468"), ("AC-0012", "boundary", "#f7b733"),
               ("AC-0045", "decoy", "#8a93a6")]


def posterior_density(cases: list[dict], focus_account: str | None = None,
                      tau: float = 0.05) -> go.Figure:
    """Overlaid posterior shapes for the three regimes (+ the focus account), each a
    Beta reconstructed to match that account's real posterior mean + 94% HDI."""
    by = {c["account"]: c for c in cases}
    x = np.linspace(0.0009, 0.9991, 700)
    fig = go.Figure()
    arch_accts = [a for a, _, _ in _ARCHETYPES]
    for acct, grp, col in _ARCHETYPES:
        c = by.get(acct)
        if not c:
            continue
        mu = float(c.get("p_mule") or 0.0)
        lo, hi = (list(c.get("credible_interval") or []) + [mu, mu])[:2]
        d = _density(mu, lo, hi, x)
        fig.add_trace(go.Scatter(
            x=x, y=d, name=f"{grp} · {acct}", fill="tozeroy", mode="lines",
            line=dict(color=col, width=2), fillcolor=_rgba_hex(col, 0.12),
            hovertemplate=f"{grp} {acct}<br>mean %{{customdata:.3f}}<extra></extra>",
            customdata=[mu] * len(x)))
    fc = by.get(focus_account or "")
    if fc and focus_account not in arch_accts:
        mu = float(fc.get("p_mule") or 0.0)
        lo, hi = (list(fc.get("credible_interval") or []) + [mu, mu])[:2]
        fig.add_trace(go.Scatter(x=x, y=_density(mu, lo, hi, x), name=f"{focus_account} · focus",
                                 mode="lines", line=dict(color=C["ink"], width=3, dash="dot")))
    fig.add_vline(x=tau, line=dict(color=C["money"], dash="dash"),
                  annotation_text=f"τ={tau:g}", annotation_font_color=C["money"])
    fig.update_xaxes(title="P(mule | signals) — posterior", range=[-0.02, 1.02])
    fig.update_yaxes(title="density (peak-normalised)", showticklabels=False)
    return _dark(fig, 380,
                 "Posterior shape — tall+narrow = confident · low+broad = uncertain  (Beta fit to real mean + 94% HDI)")


def theta_hist(samples: list[float], mu: float, lo: float, hi: float,
               color: str = "#ff5468", tau: float = 0.05) -> go.Figure:
    """Real (thinned) NUTS θ samples with the reconstructed Beta overlaid — proves the
    Beta fit matches the true sampler output. Only shown when a stats pack is present."""
    x = np.linspace(0.0009, 0.9991, 400)
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=samples, histnorm="probability density", nbinsx=40,
                               name="real NUTS samples", marker_color=color, opacity=0.45))
    fig.add_trace(go.Scatter(x=x, y=_beta_pdf(mu, lo, hi, x), name="Beta reconstruction",
                             mode="lines", line=dict(color=color, width=2.4)))
    fig.add_vline(x=tau, line=dict(color=C["money"], dash="dash"),
                  annotation_text=f"τ={tau:g}", annotation_font_color=C["money"])
    fig.update_xaxes(title="P(mule | signals)", range=[-0.02, 1.02])
    fig.update_yaxes(title="density", showticklabels=False)
    return _dark(fig, 320, "Real posterior samples vs the Beta reconstruction (they agree)")


# ── Act IV: expected-loss crossing + abstention band ─────────────────────────
def loss_crossing(case: dict, c_fp: float = 250.0, c_fn: float = 4750.0,
                  c_rev: float = 150.0, tau: float | None = None) -> go.Figure:
    tau = tau if tau is not None else c_fp / (c_fp + c_fn)
    p = np.linspace(0, 1, 240)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=p, y=c_fp * (1 - p), name="E[loss | escalate] = C_FP·(1−p)",
                             mode="lines", line=dict(color=C["ring"], width=2.4)))
    fig.add_trace(go.Scatter(x=p, y=c_fn * p, name="E[loss | clear] = C_FN·p",
                             mode="lines", line=dict(color=C["clear"], width=2.4)))
    fig.add_hline(y=c_rev, line=dict(color=C["review"], dash="dot"),
                  annotation_text=f"C_REV = ${c_rev:,.0f}", annotation_font_color=C["review"])
    # EVPI = min(E_esc,E_clr) exceeds C_REV inside this band → abstention is cost-justified
    band_lo, band_hi = c_rev / c_fn, 1 - c_rev / c_fp
    if band_hi > band_lo:
        fig.add_vrect(x0=max(0, band_lo), x1=min(1, band_hi), fillcolor=C["review"],
                      opacity=0.09, line_width=0,
                      annotation_text="EVPI > C_REV — review beats guessing",
                      annotation_font_color=C["review"], annotation_position="top left")
    fig.add_vline(x=tau, line=dict(color=C["money"], dash="dash"),
                  annotation_text=f"τ = {tau:.3f}", annotation_font_color=C["money"])
    p0 = float(case.get("p_mule") or 0.0)
    fig.add_vline(x=p0, line=dict(color=_color_for(case), dash="dot"))
    ymark = min(c_fp * (1 - p0), c_fn * p0)
    fig.add_trace(go.Scatter(x=[p0], y=[ymark], mode="markers",
                             name=f"{case['account']} · p={p0:.3f} → {case.get('action','')}",
                             marker=dict(size=13, color=_color_for(case),
                                         line=dict(width=1, color="#05070d"))))
    fig.update_xaxes(title="P(mule)", range=[-0.02, 1.02])
    fig.update_yaxes(title="expected loss ($)")
    return _dark(fig, 400,
                 f"Expected loss vs probability — lines cross at τ = C_FP/(C_FP+C_FN) = {tau:.3f}")


# ── Act V: learned fire-rates φ_mule vs φ_legit (identifiability) ────────────
def phi_posteriors(phi: dict) -> go.Figure:
    feats = phi["feature"]
    labels = [f.replace("_", " ") for f in feats]
    mm, lm = phi["mule_mean"], phi["legit_mean"]
    mh, lh = phi.get("mule_hdi"), phi.get("legit_hdi")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels, x=mm, orientation="h", name="φ mule  (P fire | mule)",
        marker_color=C["ring"],
        error_x=(dict(type="data", symmetric=False,
                      array=[mh[i][1] - mm[i] for i in range(len(feats))],
                      arrayminus=[mm[i] - mh[i][0] for i in range(len(feats))],
                      color="rgba(255,255,255,0.35)", thickness=1.2, width=3) if mh else None)))
    fig.add_trace(go.Bar(
        y=labels, x=lm, orientation="h", name="φ legit  (P fire | legit)",
        marker_color=C["clear"],
        error_x=(dict(type="data", symmetric=False,
                      array=[lh[i][1] - lm[i] for i in range(len(feats))],
                      arrayminus=[lm[i] - lh[i][0] for i in range(len(feats))],
                      color="rgba(255,255,255,0.35)", thickness=1.2, width=3) if lh else None)))
    fig.update_layout(barmode="group")
    fig.update_xaxes(title="learned fire-rate φ (94% HDI)", range=[0, 1])
    return _dark(fig, 430,
                 "Learned fire-rates — φ_mule ≫ φ_legit on behaviour (identifiable); device-shared reverses (decoy-proof)")


# ── Act I: the prior on the base rate π, and what the data taught it ─────────
def pi_prior_posterior(pack: dict | None = None) -> go.Figure:
    x = np.linspace(0.0009, 0.9991, 500)
    prior = (1 - x) ** 8            # Beta(1,9) ∝ (1−x)^8
    prior = prior / prior.max()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=prior, name="prior · π ~ Beta(1, 9), E=0.10",
                             mode="lines", line=dict(color=C["violet"], width=2),
                             fill="tozeroy", fillcolor=_rgba_hex(C["violet"], 0.10)))
    if pack and pack.get("pi"):
        mu = float(pack["pi"]["mean"])
        lo, hi = (list(pack["pi"].get("hdi") or []) + [mu, mu])[:2]
        fig.add_trace(go.Scatter(x=x, y=_density(mu, lo, hi, x),
                                 name=f"learned posterior · π̄={mu:.2f}",
                                 mode="lines", line=dict(color=C["money"], width=2.6)))
    fig.update_xaxes(title="π — fraction of surfaced accounts that are mules", range=[-0.02, 1.02])
    fig.update_yaxes(title="density (peak-normalised)", showticklabels=False)
    return _dark(fig, 300, "The base rate — a skeptical prior (E=0.10), then what the evidence pulled it to")


# ── Account summary: posterior membership as a radial gauge vs τ ─────────────
def posterior_gauge(case: dict, tau: float = 0.05) -> go.Figure:
    p = float(case.get("p_mule") or 0.0)
    col = _color_for(case)
    act = case.get("action", "")
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=p,
        number={"font": {"size": 30, "color": col, "family": _FONT}, "valueformat": ".3f"},
        delta={"reference": tau, "valueformat": ".3f", "position": "bottom",
               "increasing": {"color": C["ring"]}, "decreasing": {"color": C["clear"]},
               "font": {"size": 11}},
        gauge={
            "axis": {"range": [0, 1], "tickwidth": 1, "tickcolor": C["grid"],
                     "tickfont": {"size": 9, "color": C["decoy"]}},
            "bar": {"color": col, "thickness": 0.30},
            "bgcolor": C["panel"], "borderwidth": 0,
            "steps": [{"range": [0, tau], "color": "rgba(52,214,164,0.10)"},
                      {"range": [tau, 1], "color": "rgba(255,84,104,0.07)"}],
            "threshold": {"line": {"color": C["money"], "width": 3}, "thickness": 0.85, "value": tau},
        },
        title={"text": f"P(mule) → {act}  ·  vs τ={tau:g}", "font": {"size": 12, "color": col}},
    ))
    return _dark(fig, 250, "")
