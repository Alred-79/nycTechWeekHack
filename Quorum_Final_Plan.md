# Quorum — Final Build Plan

**M² · M-AGENTS** · Track 02 — Fraud Watch · vibeFORWARD · June 7, 2026
**Dataset:** Crestline Community Bank — `track02_fraud_watch.csv` (5,000 transactions · 294 accounts · 90 days)
**Ground truth:** a 9-account ring moving **\$161,750.90** to the cent; probable 10th `AC-0012`; `AC-0004`/`AC-0008` are seeded-but-absent (the "~12" hint). Device-sharing is a **planted decoy** — not a signal.

---

## TL;DR — the MVP, in plain English

> Quorum is a triage screen for a fraud analyst. You load a bank's transactions; instead of 294 accounts to check, Quorum hands you about ten. For each one it shows a confidence score, the plain-English reasons it was flagged, and how much money it touched. It **escalates the accounts it's sure about, sends the one it isn't sure about to a human instead of guessing, and ignores the fake "shared-device" trap planted in the data**. One click downloads a regulator-ready memo that reconciles to the exact \$161,750.90 the ring moved. Under the hood, four agents pass a shared case file through Cognee — each one reads what the last found and adds a new layer of understanding on top.

That paragraph is the whole demo. Everything below is how we build it and prove it.

---

## 1. What the product does

1. **Loads** the 5,000-transaction file.
2. **Collapses** it to a review queue of ~10 accounts (from 294), auto-clearing everything else.
3. For each surfaced account, **shows**: a calibrated mule probability with an uncertainty band, the specific signals that fired, the money it moved, the laundering typology, and the escalate/clear/review decision *with the cost arithmetic behind it*.
4. **Abstains** — routes genuinely ambiguous accounts (`AC-0012`) to a human review lane instead of forcing a call.
5. **Resists the decoy** — does not flag the device-sharing accounts the dataset planted to mislead.
6. **Exports** a SAR-ready case memo per ring (downloadable), with a dollar reconciliation and a "closing rule" the bank can deploy to catch this pattern automatically next time.

## 2. The one idea we're betting on

**Calibrated abstention via Bayesian decision theory — the agent that knows when to say "I don't know."**

Most Track 02 teams will ship a risk-score table and will flag the device decoy. Quorum's differentiator is that it (a) produces *calibrated* probabilities with uncertainty, (b) turns those into actions by minimizing expected loss rather than thresholding a raw score, and (c) **declines to act when the evidence is genuinely ambiguous**, routing to a human instead. That is the one behavior rules and black-box scores cannot offer, and it is verifiable against the answer key.

**What we cut to protect it** (see §11): real-time replay and the Bayesian cadence model are *stretch*; the email digest, case-disposition workflow, and four-eyes approval are *not built* this sprint. Scope is narrow on purpose.

## 3. The data we build against (real numbers, not assumptions)

- **250** of 5,000 transactions are account-to-account (`AC→AC`); the other **4,750** are merchant payments. The ring is exactly those 250 transfers and they sum to **\$161,750.90**.
- **Three independent structures:** `AC-0001→AC-0002` (\$27.0k); hub `AC-0005`→`AC-0006` (\$27.7k) and `AC-0005`→relay `AC-0009`→`AC-0007` (\$26.2k→\$29.1k); `AC-0010`→relay `AC-0011`→`AC-0003` (\$26.8k→\$24.9k, compressed into 24 days in May).
- **Five discriminating signals:** under-threshold amounts (\$402–\$899, none ≥ \$1,000); fresh Feb-2026 account cohort; pure sinks that never originate any transaction (`AC-0002/0003/0006/0007`); near-constant automation cadence (~42 fires per edge); relay/layering roles (`AC-0009/0011`).
- **The decoy:** `AC-0045/0127/0131/0192` share devices but are **not** ring members. Shared identity is noise here.
- **The boundary case:** `AC-0012` — Feb cohort, but only 12 small merchant purchases and no transfers. Low-but-uncertain. Belongs in *review*.

## 4. Architecture — four agents over one shared Cognee memory

Four agents, each a distinct module that **reads its inputs from Cognee, does real computation, and writes an enriched layer back**. The handoffs are not messages — they mutate a shared **case object** per account that visibly grows as the pipeline runs. This is the spine that earns criterion 2.

### 4.1 The shared case object (this is how the agents learn from each other)

A single `Case` node per account lives in the Cognee ontology and accretes fields. Each agent **requires** the previous agent's fields to do its job — a provable dependency, not an asserted one.

```
After Agent 1 (Detector):
  Case{ account, role, signals{under_threshold, fresh_cohort, zero_merchant,
        cadence_regularity, relay_depth}, is_candidate, decoy_suspect,
        dist_stats{account_age_dist, amount_dist} }

After Agent 2 (Estimator):   + p_mule, credible_interval[lo,hi],
                               signal_contributions{...}, sampler_health

After Agent 3 (Adjudicator): + action{escalate|clear|review},
                               E_loss_escalate, E_loss_clear, EVPI, quorum,
                               decisive_signals[]

After Agent 4 (Reporter):    + memo_ref, typology, dollar_contribution,
                               closing_rule
```

The ontology also holds `Account → Device / IP / MerchantCategory / OpenDate` and `Transaction` edges, so Agent 4 can trace any flag back through the graph (evidence lineage).

### 4.2 Agent 1 — Detector (deterministic graph + signal extraction)

Reads the raw transactions. Isolates the 250 `AC→AC` edges from the 4,750 merchant payments, builds the Cognee ontology, derives each account's topological role (source/relay/sink) via graph analysis, computes the five signals, and **explicitly tags the device-sharing accounts as `decoy_suspect`** (shared device but isolated in the transfer graph). Crucially, it also writes **empirical distribution stats** (account-age distribution, amount distribution) to Cognee — the raw material Agent 2 will learn its thresholds from. *Visible reason:* which structural patterns matched.

### 4.3 Agent 2 — Estimator (PyMC Bayesian signal fusion → calibrated probability)

Reads Agent 1's signals **and distribution stats** from Cognee. Two things make this defensible and make it *learn* from Agent 1 rather than hardcode:

- **Data-driven thresholds.** "Fresh cohort" is defined relative to Agent 1's empirical account-age distribution (an outlier on the recency tail), not a magic "30 days." "Under threshold" is read off the amount distribution. The model learns the boundaries from upstream data — which is also why outputs aren't hardcoded.
- **Skeptical decoy prior.** The device-sharing feature gets a tight prior near zero, so identity co-occurrence cannot dominate. The decoy accounts, lacking the behavioral signals, stay low.

It fits a **logistic signal-fusion model** (continuous latent, NUTS + `nutpie`) → posterior `P(account is a mule)` with a credible interval per account. The three regimes that fall out:

| Account type | Posterior | Interval | Why |
|---|---|---|---|
| The 9 ring accounts | ≈ 0.97 | tight | all signals fire |
| Clean accounts + decoys | ≈ 0.005–0.02 | tight | behavioral signals absent |
| `AC-0012` | ≈ 0.06 | **wide [0.01, 0.22]** | one signal (cohort), little evidence |

One **ArviZ calibration check** (r-hat, divergences, posterior-predictive) confirms the intervals are honest. *Visible reason:* per-account signal contributions + calibration metrics.

### 4.4 Agent 3 — Adjudicator (Bayesian decision theory + abstention)

Reads Agent 2's posteriors. For each account, computes the expected loss of *escalate* vs *clear* under an explicit cost matrix, derives the threshold τ, and computes the Value of Information of a human review (math in §5). **Decisions are deterministic** (argmin expected loss) so there is no "the model said so." It escalates the confident nine, **abstains on `AC-0012`** (wide interval straddles τ → high EVPI → review), clears the rest including the decoys, and records the `decisive_signals` (the ones that moved the decision most). *Visible reason:* the actual expected-loss numbers, EVPI, and quorum status — logged, not narrated.

### 4.5 Agent 4 — Reporter (LLM narrative grounded in the computed case file)

Reads the full enriched case object + ontology. Uses an LLM (Groq/Anthropic) to write a human narrative **strictly grounded in the computed values** — it phrases the reasons, it does not invent them. Produces per ring:

- **SAR memo** — mapped to the real FinCEN narrative structure (who/what/when/where/why/how), with the posterior plot, ring subgraph, signals that fired, and verdict in signable language.
- **Dollar reconciliation** — \$161,750.90 traced edge-by-edge against the \$161,751 target (the credibility anchor).
- **Typology** — structuring + layering + relay, sourced from Geodo research.
- **Closing rule** — the system's **learned artifact**: the `decisive_signals` from Agent 3 compiled into a deployable query (`AC→AC transfers where account_age_at_first_txn is a recency outlier AND every amount < \$1,000 AND zero merchant outflow`). Each caught ring writes the rule that catches the next one.

### 4.6 How each handoff visibly improves on the last (criterion 2, made literal)

- Agent 2 **cannot run** without Agent 1's `signals` and `dist_stats` — the model's feature matrix *is* Agent 1's output; remove it and Agent 2 errors. (Provable dependency.)
- Agent 3 **consumes** Agent 2's posterior + interval to choose an action; with only Agent 1's raw signals it could not weigh cost or abstain.
- Agent 4 **consumes** the entire chain to produce the memo and to compile the closing rule from Agent 3's `decisive_signals`.
- Each layer is strictly higher-level than the last: structure → calibrated probability → cost-optimal action → human artifact + learned rule. In the demo we query the Cognee `Case` node after each agent and show the new fields appearing live.

## 5. The math (what a PyMC judge will probe)

For account *i*: posterior over mule probability θᵢ; `pᵢ = E[θᵢ]`, interval `[θ_lo, θ_hi]`.

**Cost matrix.** clear a true mule → `C_FN` (large); escalate a clean account → `C_FP`; correct actions ≈ 0; review → fixed `C_rev`, resolving the case.

**Decision without review.** `E[loss|escalate] = (1−pᵢ)·C_FP`, `E[loss|clear] = pᵢ·C_FN`. Escalate iff `pᵢ > τ` where the **loss-justified threshold** is

> `τ = C_FP / (C_FP + C_FN)`

— derived from costs, not picked. *Example:* `C_FN=4,750`, `C_FP=250`, `C_rev=150` → `τ = 0.05`. (Costs are tunable via Geodo SAR-penalty research; the FN≫FP asymmetry is the AML reality.)

**Value of Information.** `EVPI(i) = min[(1−pᵢ)·C_FP, pᵢ·C_FN]`. Review when `EVPI(i) > C_rev`, integrated over the posterior. A straddling interval (`AC-0012`: [0.01, 0.22] crosses τ=0.05) → high EVPI → human. A one-sided interval has **quorum** → act and log why.

**Caseload.** At n=294 this is allocation, not a knapsack: **9 escalate · ~1 review · ~284 auto-clear** (>99% of accounts, >95% of volume cleared).

## 6. The product surface (cold-operable in 3 minutes)

A **Streamlit** app — chosen because it produces an operable triage UI fast, renders ArviZ/matplotlib plots natively, and gives `st.download_button` for the memo. Three screens:

1. **Queue** — a sortable table of the ~10 surfaced accounts: account, probability (with a small interval bar), top reason, money touched, action chip (Escalate / Review). The 284 cleared accounts are hidden behind a "show cleared" toggle.
2. **Case detail** — click a row: posterior plot, the signals that fired, the expected-loss arithmetic, the typology, the ring subgraph, and a **Download SAR memo** button. The `AC-0012` and decoy cases are reachable for the demo beats.
3. **Pipeline view** (small) — the Cognee `Case` object for a chosen account shown after each agent, fields accreting — the criterion-2 proof.

No login, no persistence, single file in / queue out. A judge who has never seen it can clear three cases and download a memo without help.

## 7. What makes us unique

- **It abstains.** Routes `AC-0012` to review instead of guessing — a calibrated "I don't know."
- **It doesn't fall for the trap.** Resists the planted device decoy via a skeptical prior; most teams won't.
- **Decisions are derived, not thresholded.** τ and the review band come from an explicit cost structure.
- **It reconciles to the cent.** \$161,750.90, edge by edge — verifiable against the hidden key.
- **The agents demonstrably build on each other** — provable field dependency in Cognee, not an assertion.
- **It learns a rule.** The closing rule turns this case into automatic future detection.

## 8. Success conditions → judging criteria

| Our Step-0 success condition | Verified by | Judging criterion |
|---|---|---|
| All 9 ring accounts surfaced; never silently cleared; total = \$161,750.90 | `test_recall`, `test_no_silent_clear`, `test_dollar_reconciliation` | 1 Agents that work · 3 Matches brief |
| Decoy accounts NOT escalated | `test_decoy_resistance` | 1 · 5 Explainable |
| `AC-0012` routed to review | `test_abstention` | 3 · 5 |
| Each agent's output provably consumed by the next, via Cognee | `test_cognee_handoff` + live pipeline view | 2 Real collaboration |
| Every surfaced case shows signals + posterior + interval + cost math | `test_explainability` | 5 Explainable |
| Judge clears 3 cases + downloads a memo in < 3 min unaided | cold-operability rehearsal (§9) | 4 End user can use it |
| Outputs computed, not canned | `test_not_hardcoded`, `test_calibration` | 1 Agents that work |

Target: 15/25 to qualify; this maps to a credible 22–25.

## 9. Test plan (the credibility engine)

A `pytest` suite that runs the full pipeline on the real file and asserts against the known ring. **It doubles as the demo's proof** — run it live; green is the argument.

| Test | Asserts | Defends |
|---|---|---|
| `test_recall` | the 9 ring accounts all have `action ∈ {escalate, review}` | 1, 3 |
| `test_no_silent_clear` | none of the 9 has `action == clear` | 1, 3 |
| `test_dollar_reconciliation` | `abs(sum(ring_transfers) − 161750.90) < 0.01` | 1, 3 |
| `test_decoy_resistance` | `AC-0045/0127/0131/0192` all `action == clear` | 1, 5 |
| `test_abstention` | `AC-0012.action == review` **and** `θ_lo < τ < θ_hi` | 3, 5 |
| `test_caseload` | `escalate + review ≤ 12`; `clear_ratio > 0.95` | 1, 3 |
| `test_cognee_handoff` | `Case` lacks `p_mule` after Agent 1, **has** it after Agent 2; lacks `action` before Agent 3, has it after | 2 |
| `test_not_hardcoded` | inject ring signals into a clean account → its `p_mule` rises > 0.5 (model computes, not canned) | 1 |
| `test_explainability` | every surfaced case has all of `{signals_fired, p_mule, credible_interval, E_loss_escalate, E_loss_clear}` — zero bare scores | 5 |
| `test_calibration` | `max r-hat < 1.01` and `divergences == 0` | 1 |

Plus a **cold-operability rehearsal**: a teammate who didn't build the UI must clear 3 cases and download a memo in under 3 minutes, timed, the afternoon of. If they can't, the UI is too complex — cut, don't add.

## 10. Build order & time budget (fully buildable)

- **First 20 min:** lock cost figures `C_FN/C_FP/C_rev` (Geodo SAR-penalty anchors) → compute τ; confirm the nine + `AC-0012` against your own analysis; write the test stubs first (they encode the spec).
- **Agent 1 + ontology + Cognee wiring (trivial payloads first):** ~1.5 h. Get the handoff demonstrably live before anything else.
- **Agent 2 signal-fusion model + calibration:** ~1.5 h. Small, continuous-latent, fast with `nutpie`.
- **Agent 3 decision/EVPI/abstention:** ~30 min (arithmetic on posteriors).
- **Agent 4 memo + reconciliation + closing rule + model card:** ~1.5 h.
- **Streamlit UI (3 screens):** ~1.5 h.
- **Run the test suite green; Trupeer + brief polish:** remaining time, scripted around the decoy + abstention beats.
- **Stretch only if all green:** replay mode, then cadence model.

## 11. Scope fences

- **MVP (must ship):** load file → queue of ~10 → case detail with reasons + posterior → download SAR memo with \$161,750.90 reconciliation. The decoy and `AC-0012` cases reachable.
- **Core (planned):** all four agents over Cognee, the Bayesian model + calibration, decision theory + abstention, the test suite, the closing rule, the model card, the pipeline view.
- **Stretch (only if core is green, droppable):** real-time **replay** (windowed re-scoring showing the day each chain crosses τ + the May changepoint alert) — gated, does not affect the win; then a Bayesian **cadence/changepoint** model (in core, cadence is just a feature).
- **Not building (roadmap line only):** email digest; case-disposition workflow; four-eyes/maker-checker; KYC/sanctions screening; integrations to BSA E-Filing or any GRC platform; immutable hash-chained audit infra.

## 12. Stack, roles, mandatory compliance

- **PyMC** (+ ArviZ, nutpie) — signal-fusion posterior, calibration, decision theory. PyMC special-prize target; §5 + the model card are the pitch.
- **Cognee** (mandatory) — the semantic ontology / shared case-object spine; the criterion-2 evidence.
- **Geodo** (mandatory, Domain-Expert-owned) — FinCEN SAR structure, FATF typologies (structuring/layering), SAR-penalty figures for the cost matrix.
- **Trupeer** (mandatory) — 5-min video, scripted around the decoy + abstention beats.
- **Streamlit** — the cold-operable UI.
- **Roles:** Builder (agents + Cognee + Streamlit), Designer (brief + UI + the queue/detail screens), Domain Expert (Geodo + memo narrative + dollar reconciliation + model card), Presenter (Trupeer + stage). Team of 4–6; no solo submission.
- **API key:** Groq free tier / Anthropic (for Agent 4's narrative only).

## 13. Demo script (3-minute cold path)

1. Open on all 5,000 transactions — a wall of noise. One action: queue collapses to ~10; 284 accounts and 4,750 merchant payments cleared.
2. Open a ring account: posterior + interval, the signals that fired, the expected-loss numbers, the dollar contribution, the typology.
3. **Decoy beat:** pull up `AC-0045` — "shares a device, the obvious flag" — and show its probability staying low because the behavioral signals are absent. *It didn't fall for the trap.*
4. **Abstention beat:** open `AC-0012` — wide interval straddling τ, no quorum, routed to a human with the EVPI that justified the review.
5. **Criterion-2 beat:** show the Cognee `Case` node for `AC-0001` after each agent — fields accreting from signals → probability → action → memo.
6. Download the SAR memo with the \$161,750.90 reconciliation and the closing rule.
7. **Run `pytest` live** — the suite goes green against the answer key.

Closing line: *"Every other tool ranks risk — and most of them just flagged the decoy. Quorum surfaces the nine, refuses to guess on the tenth, ignores the trap, learns the rule that catches it next time, and shows you the math behind every call."*

---

## Appendix — Model Card (SR 11-7 style, the cheap compliance win)

A one-page artifact Agent 4 emits; deeply impressive for ~20 minutes of work.

- **Model:** Bayesian logistic signal-fusion (PyMC), continuous latent, NUTS/nutpie.
- **Intended use:** triage support for an AML analyst; advisory, human-in-the-loop. Not an autonomous filing system.
- **Inputs (features):** under-threshold amount, fresh-cohort recency (learned from data), zero-merchant behavior, cadence regularity, relay depth. Device-sharing included with a deliberately skeptical prior.
- **Outputs:** calibrated `P(mule)` with a credible interval per account; not a bare score.
- **Validation:** r-hat < 1.01, zero divergences, posterior-predictive check; acceptance tests against a known-ring benchmark (recall, decoy resistance, abstention, dollar reconciliation).
- **Known limitations:** trained/validated on one synthetic benchmark; the device-sharing feature is intentionally down-weighted because shared identity was a decoy in this data and may behave differently elsewhere; abstention depends on cost figures that must be set per institution.
- **Governance:** every decision is logged with its expected-loss arithmetic and the signals that drove it (audit trail via Cognee); uncertain cases are escalated to a human rather than auto-decided (responsible-AI human-in-the-loop).
- **Frameworks referenced:** BSA / FinCEN SAR (filing + narrative structure), FATF typologies, SR 11-7 (model risk management).
