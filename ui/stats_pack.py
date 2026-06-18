"""
Deterministic stats pack for the ⚖️ Reasoning tab.

Re-runs the Estimator (Agent 2 — pure PyMC/NUTS, seed=0, NO LLM) on the committed
CSV and persists the real posterior summaries, convergence diagnostics, and thinned
posterior samples that the snapshot does NOT carry (the snapshot keeps only the
per-account scalars p_mule / credible_interval / signal_contributions).

Build-time only. The Streamlit app reads ui/stats_pack.json at view time and never
imports pymc. Rebuild after any Estimator change:

    uv run python -m ui.stats_pack

The tab degrades gracefully (documented constants + prior means) if the file is absent.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATS_PACK_PATH = ROOT / "ui" / "stats_pack.json"
DEFAULT_CSV = ROOT / "data" / "track02_fraud_watch.csv"

# Representative accounts whose full (thinned) posterior we keep for real histograms.
ARCHETYPES = {"ring": "AC-0009", "boundary": "AC-0012", "decoy": "AC-0045"}
_THIN = 300  # thinned samples kept per archetype / per φ feature (keeps the JSON small)


def build(csv_path: str | Path = DEFAULT_CSV) -> dict:
    """Run the Estimator once (deterministic) and extract the real posterior pack."""
    import duckdb
    import numpy as np
    import arviz as az

    import cognee_client as cognee
    from agents import ranker, scout
    from db import queries

    con = duckdb.connect()
    queries.load_csv(con, str(csv_path))
    scout.run(con)                                          # writes signals + dist_stats
    cases = cognee.read_cases(candidates_only=True)
    accounts, X, M, idata = ranker.estimate(cases)          # seed=0, full idata
    post = idata.posterior
    feats = list(ranker.FEATURES)

    def _thin(arr) -> list[float]:
        a = np.asarray(arr, dtype=float).reshape(-1)
        step = max(1, a.size // _THIN)
        return [round(float(x), 4) for x in a[::step][:_THIN]]

    # φ posteriors per feature, both classes (samples, feature)
    pm_draws = post["phi_mule"].values.reshape(-1, len(feats))
    pl_draws = post["phi_legit"].values.reshape(-1, len(feats))
    phi = {
        "feature": feats,
        "mule_mean": [round(float(pm_draws[:, i].mean()), 4) for i in range(len(feats))],
        "legit_mean": [round(float(pl_draws[:, i].mean()), 4) for i in range(len(feats))],
        "mule_hdi": [[round(v, 4) for v in ranker._hdi94(pm_draws[:, i])] for i in range(len(feats))],
        "legit_hdi": [[round(v, 4) for v in ranker._hdi94(pl_draws[:, i])] for i in range(len(feats))],
    }
    phi_samples = {feats[i]: {"mule": _thin(pm_draws[:, i]), "legit": _thin(pl_draws[:, i])}
                   for i in range(len(feats))}

    # π posterior (the learned base rate)
    pi_draws = post["pi"].values.reshape(-1)
    pi = {"mean": round(float(pi_draws.mean()), 4),
          "hdi": [round(v, 4) for v in ranker._hdi94(pi_draws)]}

    # θ posterior samples (real, thinned) for the three archetypes
    theta = post["theta"].values.reshape(-1, len(accounts))
    idx = {a: j for j, a in enumerate(accounts)}
    theta_samples = {acct: _thin(theta[:, idx[acct]])
                     for acct in ARCHETYPES.values() if acct in idx}

    # convergence diagnostics
    max_rhat = float(max(az.rhat(idata)["phi_mule"].max(),
                         az.rhat(idata)["phi_legit"].max(),
                         az.rhat(idata)["theta"].max()))
    ess = az.ess(idata)
    min_ess = float(min(float(ess["phi_mule"].min()),
                        float(ess["phi_legit"].min()),
                        float(ess["theta"].min())))
    divergences = int(idata.sample_stats["diverging"].sum())
    accept = None
    for key in ("acceptance_rate", "mean_tree_accept", "accept"):
        if key in idata.sample_stats:
            try:
                accept = round(float(idata.sample_stats[key].mean()), 4)
            except Exception:  # noqa: BLE001 — diagnostic is best-effort
                accept = None
            break

    return {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": ranker._SEED,
        "draws": int(post.sizes["draw"]),
        "chains": int(post.sizes["chain"]),
        "convergence": {
            "max_rhat": round(max_rhat, 4),
            "min_ess": round(min_ess, 1),
            "divergences": divergences,
            "accept_rate": accept,
        },
        "pi": pi,
        "phi": phi,
        "phi_samples": phi_samples,
        "theta_samples": theta_samples,
        "archetypes": ARCHETYPES,
    }


def save(csv_path: str | Path = DEFAULT_CSV, out: str | Path = STATS_PACK_PATH) -> Path:
    Path(out).write_text(json.dumps(build(csv_path)))
    return Path(out)


def load(path: str | Path = STATS_PACK_PATH) -> dict | None:
    """View-time loader — JSON only, never imports pymc. None on miss."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001 — a corrupt pack must degrade, not crash the app
        return None


if __name__ == "__main__":
    out = save()
    pack = load(out) or {}
    conv = pack.get("convergence", {})
    print(f"Stats pack → {out}")
    print(f"  seed={pack.get('seed')} draws={pack.get('draws')} chains={pack.get('chains')}")
    print(f"  max_rhat={conv.get('max_rhat')}  min_ess={conv.get('min_ess')}  "
          f"divergences={conv.get('divergences')}  accept_rate={conv.get('accept_rate')}")
    print(f"  phi features={len(pack.get('phi', {}).get('feature', []))}  "
          f"theta archetypes={list(pack.get('theta_samples', {}))}")
