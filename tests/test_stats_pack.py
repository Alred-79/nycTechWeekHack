"""The deterministic stats pack (ui/stats_pack.py) re-runs the Estimator (seed=0,
pure PyMC/NUTS, no LLM) and reproduces the calibration story: converged, identifiable,
and its archetype posteriors match the committed snapshot.

Runs NUTS (~1 min). Run: uv run pytest tests/test_stats_pack.py -q
"""
from __future__ import annotations

import pytest

from ui import snapshot, stats_pack


@pytest.fixture(scope="module")
def pack():
    return stats_pack.build()   # seed=0 → deterministic


def test_converged(pack):
    cv = pack["convergence"]
    assert cv["divergences"] == 0
    assert cv["max_rhat"] < 1.01


def test_identifiable(pack):
    phi = pack["phi"]
    # the 'mule' class fires the 6 behavioural signals more than 'legit' (no label switching)
    assert all(phi["mule_mean"][i] > phi["legit_mean"][i] for i in range(6))


def test_archetype_posteriors_match_snapshot(pack):
    snap = snapshot.load()
    if snap is None:
        pytest.skip("no prebuilt snapshot")
    by = {c["account"]: c for c in snap["cases"]}
    for acct, samples in pack["theta_samples"].items():
        mean = sum(samples) / len(samples)
        assert abs(mean - by[acct]["p_mule"]) < 0.05   # offline pack ties to the committed pipeline
