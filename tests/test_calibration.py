"""
Phase v2 gate — the PyMC mixture Estimator is well-sampled, identifiable, and
reproduces the three regimes (the PyMC special-prize calibration story).

Run: uv run pytest tests/test_calibration.py -q
"""
from __future__ import annotations

import duckdb
import pytest

import arviz as az
import quorum_truth as gt
from agents import ranker, scout
from db import queries

CSV = "data/track02_fraud_watch.csv"


@pytest.fixture(scope="module")
def fit():
    import cognee_client as cognee
    con = duckdb.connect()
    queries.load_csv(con, CSV)
    scout.run(con)
    cases = cognee.read_cases(candidates_only=True)
    accounts, X, M, idata = ranker.estimate(cases)
    return accounts, X, M, idata


def test_sampler_is_healthy(fit):
    _, _, _, idata = fit
    assert float(az.rhat(idata)["phi_mule"].max()) < 1.01
    assert float(az.rhat(idata)["phi_legit"].max()) < 1.01
    assert int(idata.sample_stats["diverging"].sum()) == 0


def test_no_label_switching(fit):
    """The 'mule' class keeps high behavioural fire-rates (identifiable, no flip)."""
    _, _, _, idata = fit
    pm_ = idata.posterior["phi_mule"].mean(("chain", "draw")).values
    pl_ = idata.posterior["phi_legit"].mean(("chain", "draw")).values
    assert (pm_[:6] > pl_[:6]).all()   # 6 behavioural features (exclude device)


def test_regimes(fit):
    """Ring high · decoys low · AC-0012 intermediate with the widest interval."""
    accounts, _, _, idata = fit
    th = idata.posterior["theta"].values.reshape(-1, len(accounts))
    p = {a: float(th[:, j].mean()) for j, a in enumerate(accounts)}
    widths = {a: (lambda s: s.max() - s.min())(
        __import__("numpy").sort(th[:, j])[[int(0.03 * th.shape[0]), int(0.97 * th.shape[0]) - 1]])
        for j, a in enumerate(accounts)}

    assert min(p[a] for a in gt.RING_ACCOUNTS) > 0.9       # ring high
    assert max(p[d] for d in gt.DECOYS) < 0.05             # decoys low
    # AC-0012 is intermediate (neither the most- nor least-mule account)
    assert p[gt.BOUNDARY] not in (min(p.values()), max(p.values()))
    # and carries the widest uncertainty
    assert widths[gt.BOUNDARY] == max(widths.values())
