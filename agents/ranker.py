"""
Agent 2 — Estimator  (Quorum, v2: PyMC Bayesian mixture)

Reads each Case's signals + dist_stats from Cognee (written by the Detector) and
fuses them into a *calibrated* mule probability with an honest uncertainty band.

This is a real generative model — an unsupervised **two-component mixture**
(latent classes: legit vs mule). The likelihood conditions on the observed
signal matrix, so the class-conditional fire-rates φ are LEARNED from the data,
not asserted. Sampled with NUTS (nutpie) via PyMC.

Two refinements make it faithful to the data:

  • Masked likelihood. Some signals are structurally inapplicable to some
    accounts — a pure sink can never fire `fresh_cohort` (no open date) or
    `automation`/`relay_depth` (it never originates). Those zeros are NOT
    evidence against "mule"; they are missing. Each account contributes only its
    *applicable* signals, so sinks (which fire under_threshold/zero_merchant/
    pure_sink) are correctly confident, not ambiguous.
  • Skeptical decoy prior. `device_shared` gets the SAME weak prior in both
    classes, so identity co-occurrence is non-discriminating by construction —
    the planted decoy cannot drive a flag.

Abstention and decoy-resistance then fall out of the posterior: AC-0012 fires
only one applicable mule-signal, so its membership is genuinely ambiguous with a
wide, τ-straddling interval; the decoys fire only `device_shared`, so they land
in the legit class with low, tight probability.

See v2.md. The v1 lightweight numpy logistic is in git history.
"""
from __future__ import annotations

import logging
import warnings
from typing import Optional

import numpy as np

import cognee_client as cognee

warnings.filterwarnings("ignore")
log = logging.getLogger("estimator")

FEATURES = ["under_threshold", "fresh_cohort", "zero_merchant",
            "pure_sink", "automation", "relay_depth", "device_shared"]

# Informative, identifiability-pinning priors (domain knowledge, not the key):
#   mules fire the 6 behavioural signals readily  → Beta(4,1), mean 0.8
#   legit accounts rarely fire them               → Beta(1,4), mean 0.2
#   device_shared: SAME weak prior in both classes → non-discriminating decoy
_A_MULE = np.array([4, 4, 4, 4, 4, 4, 1.0])
_B_MULE = np.array([1, 1, 1, 1, 1, 1, 1.0])
_A_LEGIT = np.array([1, 1, 1, 1, 1, 1, 1.0])
_B_LEGIT = np.array([4, 4, 4, 4, 4, 4, 1.0])

_SEED = 0   # fixed → deterministic, reproducible gates


def _applicability_mask(case: dict) -> list[float]:
    """A signal counts in the likelihood only when it CAN structurally fire."""
    s = case.get("signals") or {}
    has_age = s.get("_age_days") is not None
    originates = (s.get("_out_deg", 0) or 0) > 0
    # [under_threshold, fresh_cohort, zero_merchant, pure_sink, automation, relay_depth, device_shared]
    return [1.0,
            1.0 if has_age else 0.0,
            1.0,
            1.0,
            1.0 if originates else 0.0,
            1.0 if originates else 0.0,
            1.0]


def _hdi94(samples) -> tuple[float, float]:
    """94% highest-density interval (arviz 1.x dropped the hdi_prob kwarg)."""
    xs = np.sort(np.asarray(samples))
    n = xs.size
    k = int(np.floor(0.94 * n))
    if k <= 0 or k >= n:
        return float(xs[0]), float(xs[-1])
    widths = xs[k:] - xs[:n - k]
    i = int(np.argmin(widths))
    return float(xs[i]), float(xs[i + k])


def estimate(cases: list[dict], draws: int = 1000, tune: int = 1000):
    """
    Fit the masked two-component mixture. Returns (accounts, X, M, idata).
    Raises ValueError if the Detector's output is missing (proves the handoff).
    """
    import pymc as pm
    import pytensor.tensor as pt

    for c in cases:
        if c.get("signals") is None or c.get("dist_stats") is None:
            raise ValueError(
                f"Estimator cannot run on {c.get('account')}: missing "
                f"{'signals' if c.get('signals') is None else 'dist_stats'} from the Detector.")

    accounts = [c["account"] for c in cases]
    X = np.array([[float((c.get("signals") or {}).get(f, 0)) for f in FEATURES]
                  for c in cases])
    M = np.array([_applicability_mask(c) for c in cases], dtype=float)

    with pm.Model(coords={"account": accounts, "feature": FEATURES}):
        pi = pm.Beta("pi", alpha=1.0, beta=9.0)                 # mules are rare
        phi_mule = pm.Beta("phi_mule", alpha=_A_MULE, beta=_B_MULE, dims="feature")
        phi_legit = pm.Beta("phi_legit", alpha=_A_LEGIT, beta=_B_LEGIT, dims="feature")

        def _ll(phi):   # masked product-of-Bernoullis log-likelihood per account
            return pt.sum(M * (X * pt.log(phi) + (1.0 - X) * pt.log1p(-phi)), axis=1)

        ll_mule, ll_legit = _ll(phi_mule), _ll(phi_legit)
        log_mix = pt.stack([pt.log(pi) + ll_mule,
                            pt.log1p(-pi) + ll_legit], axis=0)        # (2, n_acct)
        pm.Potential("obs", pt.sum(pm.math.logsumexp(log_mix, axis=0)))

        # Posterior membership P(mule | x_i) — this is p_mule, with a full posterior.
        pm.Deterministic(
            "theta",
            pt.exp((pt.log(pi) + ll_mule) - pm.math.logsumexp(log_mix, axis=0)),
            dims="account")

        idata = pm.sample(draws=draws, tune=tune, nuts_sampler="nutpie",
                          chains=4, target_accept=0.95, progressbar=False,
                          random_seed=_SEED)
    return accounts, X, M, idata


def run(on_progress: Optional[callable] = None) -> dict:

    def _prog(msg: str) -> None:
        log.info("ESTIMATOR: %s", msg)
        if on_progress:
            on_progress(msg)

    _prog("Reading candidate Cases (signals + dist_stats) from Cognee...")
    cases = cognee.read_cases(candidates_only=True)
    _prog(f"Read {len(cases)} Cases. Fitting two-component mixture (NUTS/nutpie)...")
    if not cases:
        return {"estimates": [], "count": 0}

    accounts, X, M, idata = estimate(cases)

    theta = idata.posterior["theta"].values.reshape(-1, len(accounts))   # (samples, acct)
    phi_mule = idata.posterior["phi_mule"].mean(("chain", "draw")).values
    phi_legit = idata.posterior["phi_legit"].mean(("chain", "draw")).values
    pi_mean = float(idata.posterior["pi"].mean())

    results = []
    for j, acct in enumerate(accounts):
        p = float(theta[:, j].mean())
        lo, hi = _hdi94(theta[:, j])
        sig = cases[j].get("signals") or {}
        mask = _applicability_mask(cases[j])
        # signal_contributions: learned log Bayes factor each FIRED, applicable
        # signal adds to the mule log-odds — explainable, not a bare score.
        contributions = {"bias": round(float(np.log(pi_mean) - np.log1p(-pi_mean)), 3)}
        for s_idx, name in enumerate(FEATURES):
            if sig.get(name, 0) and mask[s_idx]:
                contributions[name] = round(
                    float(np.log(phi_mule[s_idx]) - np.log(phi_legit[s_idx])), 3)

        cognee.update_case_fields(acct, {
            "p_mule": round(p, 4),
            "credible_interval": [round(lo, 4), round(hi, 4)],
            "signal_contributions": contributions,
        })
        log.info("ESTIMATOR  account=%s  p_mule=%.4f  CI=[%.4f, %.4f]",
                 acct, p, lo, hi)
        results.append({"account": acct, "p_mule": p, "credible_interval": [lo, hi]})

    cognee.add_agent_layer("estimator", "ESTIMATOR posteriors (Agent 2, PyMC mixture):\n"
        + "\n".join(f"- {r['account']}: p_mule={r['p_mule']:.3f}, "
                    f"94% CI={[round(x, 3) for x in r['credible_interval']]}"
                    for r in results))

    import arviz as az
    rhat = float(max(az.rhat(idata)["phi_mule"].max(),
                     az.rhat(idata)["phi_legit"].max()))
    divergences = int(idata.sample_stats["diverging"].sum())
    _prog(f"Estimator complete. {len(results)} posteriors written. "
          f"max r-hat={rhat:.4f}, divergences={divergences}.")
    return {"estimates": results, "count": len(results),
            "max_rhat": rhat, "divergences": divergences}
