"""⚖️ Reasoning tab — the explainer charts render from the real snapshot + stats-pack
data, and the weight-of-evidence waterfall reconciles to the plug-in posterior logit.

These exercise the pure chart builders only (no Streamlit), so they are safe in the
shared pytest session. Run: uv run pytest tests/test_reasoning_tab.py -q
"""
from __future__ import annotations

import math

import plotly.graph_objects as go
import pytest

from ui import charts, snapshot, stats_pack

_SNAP = snapshot.load()
_PACK = stats_pack.load()

pytestmark = pytest.mark.skipif(_SNAP is None, reason="no prebuilt snapshot")

CASES = (_SNAP or {}).get("cases", [])
TAU = (_SNAP or {}).get("adjudicator", {}).get("tau", 0.05)
BY = {c["account"]: c for c in CASES}
PHI = (_PACK or {}).get("phi")


@pytest.mark.parametrize("acct", ["AC-0009", "AC-0012", "AC-0045"])
def test_charts_render(acct):
    c = BY[acct]
    assert isinstance(charts.logodds_waterfall(c, PHI), go.Figure)
    assert isinstance(charts.loss_crossing(c, 250, 4750, 150, TAU), go.Figure)
    assert isinstance(charts.posterior_density(CASES, acct, TAU), go.Figure)
    assert isinstance(charts.pi_prior_posterior(_PACK), go.Figure)


def test_phi_chart_and_identifiability():
    if not PHI:
        pytest.skip("no stats pack")
    assert isinstance(charts.phi_posteriors(PHI), go.Figure)
    # 'mule' class fires the 6 behavioural signals more than 'legit' (no label switching)
    assert all(PHI["mule_mean"][i] > PHI["legit_mean"][i] for i in range(6))


def test_theta_hist_renders():
    if not _PACK or not _PACK.get("theta_samples"):
        pytest.skip("no stats pack")
    acct, samples = next(iter(_PACK["theta_samples"].items()))
    c = BY[acct]
    lo, hi = c["credible_interval"]
    assert isinstance(charts.theta_hist(samples, c["p_mule"], lo, hi, "#ff5468", TAU), go.Figure)


def _woe_logit(case: dict, phi: dict) -> float:
    """The waterfall's full weight-of-evidence sum (mirrors charts.logodds_waterfall)."""
    sig = case["signals"]
    tot = float(case["signal_contributions"]["bias"])
    has_age = sig.get("_age_days") is not None
    orig = (sig.get("_out_deg", 0) or 0) > 0
    appl = {"under_threshold": True, "fresh_cohort": has_age, "zero_merchant": True,
            "pure_sink": True, "automation": orig, "relay_depth": orig, "device_shared": True}
    mule = dict(zip(phi["feature"], phi["mule_mean"]))
    legit = dict(zip(phi["feature"], phi["legit_mean"]))
    for f in phi["feature"]:
        if not appl[f]:
            continue
        pm = min(max(mule[f], 1e-4), 1 - 1e-4)
        pl = min(max(legit[f], 1e-4), 1 - 1e-4)
        tot += (math.log(pm) - math.log(pl)) if sig.get(f, 0) else (math.log(1 - pm) - math.log(1 - pl))
    return tot


def test_waterfall_reconciles_to_plugin_posterior():
    """bias + Σ weight-of-evidence over applicable signals → plug-in logit; for the
    confident regimes σ(logit) agrees tightly with the stored posterior, and every
    account lands on the same side of τ."""
    if not PHI:
        pytest.skip("no stats pack")
    for acct in BY:
        p_plugin = 1.0 / (1.0 + math.exp(-_woe_logit(BY[acct], PHI)))
        assert (p_plugin > TAU) == (BY[acct]["p_mule"] > TAU)   # same verdict regime
    for acct in ("AC-0009", "AC-0045"):                          # confident → tight agreement
        p_plugin = 1.0 / (1.0 + math.exp(-_woe_logit(BY[acct], PHI)))
        assert abs(p_plugin - BY[acct]["p_mule"]) < 0.05
