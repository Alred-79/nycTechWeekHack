# Quorum — Demo Script (≈3-minute cold path)

> Quorum is a calibrated triage screen for an AML analyst. It surfaces the ring,
> refuses to guess on the one genuinely ambiguous account, ignores the planted
> decoy, reconciles to the cent, and shows the math behind every call.

---

**0:00 — The problem.**
I'm an AML analyst at Crestline Community Bank. This file has 5,000 transactions
across ~300 accounts. Somewhere inside is a coordinated ring that never crossed
an alert threshold — our rules caught none of it. I have about three minutes per
case. Watch what Quorum hands me.

**0:20 — Load the file (Queue screen).**
I drop the Crestline CSV. Four agents run over one shared Cognee memory:
Detector → Estimator → Adjudicator → Reporter. In under a second, 298 accounts
collapse to a queue of **14**, and of those only **9 escalate, 1 goes to review,
4 are cleared.** Everything else was auto-cleared. Ring exposure: **$161,750.90**,
reconciled.

**0:50 — Open a ring account (Case detail).**
Here's AC-0009, a relay. The posterior says **p = 0.999** with a tight credible
interval, far above the threshold τ = 0.05. I can see *why*: the signals that
fired — under-threshold amounts, fresh-cohort onboarding, automated cadence,
relay role — and the **expected-loss arithmetic** behind the ESCALATE. No bare
score. The ring subgraph shows the source → relay → sink chains; there are no
loops — the money fans into sinks and stops.

**1:30 — The decoy beat.**
Now AC-0045. It **shares a device** with three other accounts — the obvious flag,
and the trap most tools fall for. Quorum's skeptical prior keeps it at
**p = 0.005**: the behavioural signals are absent and it's isolated in the
transfer graph. **CLEARED. It didn't fall for the trap.**

**2:00 — The abstention beat.**
AC-0012. Fresh-cohort like the ring, but no transfers — genuinely ambiguous.
**p = 0.057, credible interval [0.004, 0.458] — it straddles τ.** Quorum computes
that a human review pays for itself (EVPI = $235.67 > review cost) and routes it
to **REVIEW** instead of guessing. That's the calibrated "I don't know."

**2:30 — The handoff beat (Pipeline view).**
Same account, traced through Cognee: the Detector wrote `signals`; the Estimator
**added** `p_mule` + interval; the Adjudicator **added** the action and the
expected-loss math; the Reporter **added** the memo and the learned rule. Each
agent literally builds on the last — the fields accrete on one Case node.
Then I click **Build Cognee graph**: the enriched cases are ingested into the
real **Cognee** SDK (add → cognify, Gemini-backed) and I ask it in plain English
— *"which accounts are relays in the ring?"* — and it answers from the graph.

**2:50 — Download the memo.**
One click: a regulator-ready SAR memo (who/what/when/where/why/how) that
reconciles edge-by-edge to **$161,750.90**, plus the **closing rule** Quorum
learned — a deployable query that catches this pattern automatically next time.

**3:00 — Proof.**
`uv run pytest -q` — the suite runs the full pipeline against the data and goes
green: all 9 ring accounts escalated, decoys cleared, AC-0012 routed to review,
dollars reconciled to the cent.

> Closing line: *"Every other tool ranks risk — and most just flag the decoy.
> Quorum surfaces the nine, refuses to guess on the tenth, ignores the trap, and
> shows you the math behind every call."*
