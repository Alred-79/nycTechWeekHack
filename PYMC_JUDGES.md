# 🎲 Quorum × PyMC — Best Use of PyMC

**One line:** PyMC turns a pile of binary fraud signals into a *calibrated, sampled
posterior* — and that posterior, not a threshold, is what decides whether Quorum
**escalates, clears, or refuses to guess.**

PyMC isn't a bolt-on score. It is the load-bearing inference engine in
[agents/ranker.py](agents/ranker.py) (Agent 2, the **Estimator**). Remove it and
Quorum's headline behavior — *calibrated abstention* — disappears.

<p align="center">
  <img src="docs/diagrams/pymc-estimator.png" alt="How PyMC decides — the masked two-component Bayesian mixture, marginalized for NUTS" width="94%">
</p>
<p align="center"><sub>The inference path, end to end: signals + mask in from Cognee → learned priors → masked likelihood → the latent class marginalized into <code>pm.Potential</code> for NUTS → a full posterior <code>p_mule</code> + 94% interval → the Adjudicator's τ decision. Source (editable): <a href="https://excalidraw.com/#json=_mqgu72v9Ci8njNfcLnZ2,EzrnoJoGS0teZJGwrsxFpg">excalidraw.com</a>.</sub></p>

---

## Why a Bayesian model is the *right* tool here (not a flex)

The dataset gives us **no labels** and a tiny, mechanical signal matrix
(14 surfaced accounts × 7 binary signals). The hard questions are about
**uncertainty**, not point accuracy:

- *Is `AC-0012` a dormant mule or a new legit customer?* → we genuinely don't know.
- *Are the device-sharing accounts a ring or a decoy?* → we must not over-flag.

A Bayesian latent-class model answers exactly these: it gives a **probability with
an honest credible interval**, and the interval width *is* the "do we know?" signal.

---

## The model — a real generative likelihood (it learns, nothing is hardcoded)

An **unsupervised two-component mixture** (latent classes: *legit* vs *mule*). The
likelihood conditions on the observed signal matrix, so the class-conditional
fire-rates **φ are learned by NUTS**, not asserted.

```python
with pm.Model(coords={"account": accounts, "feature": FEATURES}):
    pi        = pm.Beta("pi", 1, 9)                      # mules are rare (learned)
    phi_mule  = pm.Beta("phi_mule",  a_mule,  b_mule, dims="feature")   # learned
    phi_legit = pm.Beta("phi_legit", a_legit, b_legit, dims="feature")  # learned

    # Masked product-of-Bernoullis: each account scores only its APPLICABLE signals
    def ll(phi): return pt.sum(M * (X*pt.log(phi) + (1-X)*pt.log1p(-phi)), axis=1)

    log_mix = pt.stack([pt.log(pi)+ll(phi_mule), pt.log1p(-pi)+ll(phi_legit)])
    pm.Potential("obs", pt.sum(pm.math.logsumexp(log_mix, axis=0)))   # marginalize z

    theta = pm.Deterministic("theta",                                  # = P(mule | x)
        pt.exp((pt.log(pi)+ll(phi_mule)) - pm.math.logsumexp(log_mix, axis=0)),
        dims="account")
    idata = pm.sample(nuts_sampler="nutpie", chains=4, target_accept=0.95, random_seed=0)
```

**Three modeling decisions a PyMC judge will appreciate:**

1. **Marginalized discrete latent class** via `pm.Potential` + `logsumexp` — clean
   continuous geometry for NUTS instead of sampling `z` (no discrete-sampler hacks),
   and the membership `P(mule|x)` recovered as a `Deterministic` so it carries a
   full posterior.
2. **Masked likelihood** (the `M` matrix). A pure *sink* structurally **cannot**
   fire `fresh_cohort`/`automation`/`relay_depth`; treating those zeros as evidence
   *against* "mule" wrongly pushed sinks to p≈0.69 with CI≈[0,1]. Masking each
   account to its applicable signals fixed it — sinks → p≈0.998, tight. *(We found
   this with the model's own posterior-predictive check before shipping.)*
3. **Skeptical decoy prior.** `device_shared` gets the **same** weak prior in both
   classes → non-discriminating *by construction*. The planted decoy cannot drive a
   flag; decoy-resistance is a property of the model, not a patch.

---

## The payoff: abstention and decoy-resistance *fall out of the posterior*

Nothing about "review AC-0012" or "clear the decoys" is hand-coded. It emerges:

| Account type | `p_mule` | 94% credible interval | Why |
|---|---|---|---|
| 9 ring accounts | **0.91 – 0.999** | tight | many applicable signals fire |
| Decoys (`AC-0045…`) | **0.0002** | [0.000, 0.001] | only `device_shared`, down-weighted by the prior |
| **`AC-0012`** | **0.23** | **[0.00, 0.86] — widest, straddles τ** | one signal fires; genuinely ambiguous |

Agent 3 then applies **Bayesian decision theory** to that posterior
([agents/investigator.py](agents/investigator.py)): with τ = C_FP/(C_FP+C_FN) = 0.05,
it computes expected loss and the **Value of Perfect Information**. `AC-0012`'s
interval straddles τ and `EVPI > review cost`, so Quorum **abstains and routes it to
a human** — the one move a raw score can't make. The uncertainty the posterior
captured is the thing that triggers the human handoff.

---

## Calibration — we can prove the sampler is trustworthy

Enforced as tests in [tests/test_calibration.py](tests/test_calibration.py):

- **Convergence:** max R̂ = **1.004** (< 1.01) across `phi_mule`, `phi_legit`.
- **Geometry:** **0 divergences** (we *removed* a hard ordering constraint that
  injected ~280 divergences — informative priors pin the labels without it).
- **Identifiability / no label-switching:** the *mule* class keeps higher
  behavioural fire-rates than *legit* on all 6 behavioural features.
- **Posterior-predictive intuition:** the three regimes above are an emergent
  property, re-checked every run.
- **Reproducible:** fixed `random_seed=0` → deterministic, CI-gated results.

---

## Verify it yourself in 30 seconds

```bash
uv run pytest tests/test_calibration.py tests/test_estimator.py -q
#  → sampler healthy (R̂<1.01, 0 divergences), no label-switching,
#    ring>0.9 tight · decoys<0.05 tight · AC-0012 widest & straddling τ

uv run python main.py data/track02_fraud_watch.csv
#  → "Estimator complete. 14 posteriors written. max r-hat=1.004, divergences=0."
```

The posterior + 94% interval render live in the app's **Case detail** tab
([ui/app.py](ui/app.py)); the per-account math is in the SAR memo.

---

## TL;DR for the rubric

| What judges look for | Quorum |
|---|---|
| PyMC used meaningfully, not decoratively | Posterior **decides** escalate/clear/**abstain**; remove it and the product loses its core behavior |
| A real model with a likelihood | Two-component mixture; `φ` **learned** from the signal matrix (no hardcoded weights) |
| Sound inference | NUTS/nutpie · R̂ 1.004 · 0 divergences · no label-switching · seeded |
| Uncertainty that *does something* | Credible-interval width → EVPI → human-in-the-loop abstention |
| Domain-aware modeling | Masked likelihood for inapplicable signals · skeptical decoy prior |

