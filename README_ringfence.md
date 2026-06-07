> ⚠️ **Superseded.** This RingFence README is kept for history only. Its core premise
> (6 *circular loops*, shared-device = ring signal, ~12 accounts) is contradicted by the
> data — the ring is **9 accounts in 6 linear source→relay→sink chains, no cycles**, and
> device-sharing is a planted **decoy**. The shipped product is **Quorum**; the source of
> truth is [Quorum_Final_Plan.md](Quorum_Final_Plan.md). Run `uv run streamlit run ui/app.py`
> or `uv run pytest -q`.

---

# RingFence — Money Laundering Detection for Crestline Community Bank

> **Tagline:** *See the ring, not just the transaction.*
> **Track:** Fraud Watch — Crestline Community Bank
> **End user:** The AML analyst on the Money Laundering Team with three minutes per case.
> **Core insight:** Crestline's rule-based monitoring flags 0.3% of activity and missed a fully operational money laundering ring. Twelve accounts moved $161,751 through six circular loops — every transaction between $400 and $900, always between 2 and 4 AM. No single threshold was ever crossed. RingFence catches the *layering pattern*, not the *transaction amount*.

---

## The Dataset

**Crestline Community Bank — 90 days of transactions**

| Field | Value |
|-------|-------|
| Total transactions | 5,000 |
| Total accounts | ~300 |
| Ring accounts | ~12 (opened within the same 10-day window) |
| Ring transactions | 250 across 6 circular loops |
| Transaction amounts | $400–$900 (deliberately sub-threshold) |
| Transaction timestamps | Clustered 2–4 AM at near-regular intervals |
| Shared device fingerprints | 2 fingerprints across 4 accounts |
| Slow-burn accounts | 3 accounts behave normally for 60 days, then drift |
| Total ring exposure | ≈ $161,751 |
| Distractor accounts | 15 (legitimate anomalies — large one-offs, travel-pattern IP changes) |
| Rules-based detection rate | 0.3% flagged — ring: 0 of 250 transactions caught |

The 15 distractor accounts are the precision trap: flag-everything strategies get burned by them. Evidence-based reasoning — with logged rationale — is how you beat the hidden answer key.

---

## Table of Contents

- [Judging Criteria](#judging-criteria)
- [Architecture](#architecture)
- [Data Ontology](#data-ontology)
- [Step 0 — Product Brief](#step-0--product-brief)
- [Step 1 — Agent 1: Scout](#step-1--agent-1-scout)
- [Step 2 — Agent 2: Ranker](#step-2--agent-2-ranker)
- [Step 3 — Agent 3: Investigator](#step-3--agent-3-investigator)
- [Step 4 — Agent 4: Narrator](#step-4--agent-4-narrator)
- [Step 5 — Product & Demo](#step-5--product--demo)
- [Step 6 — Post-Detection: Money Laundering Team Pipeline](#step-6--post-detection-money-laundering-team-pipeline)
- [Outcomes & Team-Specific Outputs](#outcomes--team-specific-outputs)
- [Roles](#roles)
- [Pipeline Invariants](#pipeline-invariants)
- [Required Tools](#required-tools)
- [Submission Checklist](#submission-checklist)

---

## Judging Criteria

**Five criteria. 25 points maximum.** Every build decision in this README maps to one of these. Use this table as a pre-demo checklist — if any row is empty, stop and fix it before presenting.

| # | Criterion | Points | What judges look for | How RingFence satisfies it | Pre-demo check |
|---|-----------|--------|---------------------|---------------------------|----------------|
| 1 | **Agents that work** | 5 pts | Ran on real data. Outputs aren't hardcoded. | Scout ingests the real Crestline CSV via DuckDB and produces findings from live graph queries. All 6 loops, exposure figures, and churn signals are computed — nothing is pre-seeded. Judges can re-run against their own CSV upload. | [ ] Pipeline runs on Crestline CSV end-to-end with no hardcoded outputs |
| 2 | **Real collaboration** | 5 pts | Agent N+1 demonstrably used what Agent N found, via Cognee. | Ranker reads `FraudFinding` entities Scout wrote to Cognee. Investigator reads `RankedFinding` entities Ranker wrote. Narrator reads `InvestigationAction` entities Investigator wrote. Every agent logs the Cognee entity ID it read at the start of its run — traceable in the "Show agent reasoning" accordion. | [ ] Each agent's log shows the Cognee entity ID it read from the previous agent |
| 3 | **Matches your brief** | 5 pts | Judged against YOUR OWN Step 0 success conditions. | Step 0 defines 7 measurable targets (recall ≥ 10/12 ring accounts, precision ≥ 12/15 distractors, all 6 loops, exposure within 10%, < 90s to brief, 100% reasoning logged, 100% ESCALATE briefs have pre-filled churn checklist). The demo must show all 7 met against the Kaggle answer key. | [ ] All 7 Step 0 success metrics verified against the hidden answer key |
| 4 | **End user can use it** | 5 pts | A judge operates the product cold during the science fair. | Streamlit UI requires no instructions: drop CSV → watch pipeline → open brief → fill churn checklist → download PDF. The 5-minute demo script is written from the AML analyst's POV, not the engineer's. Graph view and workflow tracker are self-explanatory. | [ ] A non-technical team member operates the product cold without help |
| 5 | **Explainable** | 5 pts | Every decision has a visible reason a human can follow. | Every Scout finding, Ranker score, and Investigator action includes a human-readable `reason` field — "the model said so" is a disqualifying answer. The "Show agent reasoning" accordion in the brief exposes the full JSON chain. The 5-Point AML Churn Checklist shows the evidence behind each pre-filled item. | [ ] Open the reasoning accordion on the top-ranked case and read every reason aloud — zero black boxes |

### Criterion-to-feature mapping

| Criterion | Primary feature | Secondary feature |
|-----------|----------------|------------------|
| Agents that work | DuckDB ingestion + live graph queries | Kaggle dataset run (verifiable by judges) |
| Real collaboration | Cognee entity chain (Scout → Ranker → Investigator → Narrator) | Agent logs showing Cognee read IDs |
| Matches your brief | Step 0 success metrics table | Submission checklist tied to each metric |
| End user can use it | Streamlit UI (cold-operable) | Demo script written from AML analyst POV |
| Explainable | "Show agent reasoning" accordion | Pre-filled churn checklist with evidence citations |

---

## Architecture

| Component | Role in RingFence |
|-----------|-------------------|
| **Cognee** | Shared memory graph between all 4 agents. Every agent reads from and writes to Cognee; entities (`FraudFinding`, `RankedFinding`, `InvestigationAction`, `Loop`) persist across handoffs so Agent N+1 always has Agent N's full reasoning available. |
| **DuckDB** | In-process OLAP database. Loads the Crestline CSV at startup; the circular flow DFS, velocity calculations, sub-threshold clustering, and churn signal queries all run against DuckDB. No separate server required — runs embedded in the Python process. |
| **Streamlit** | Product UI. Single-page app: CSV upload → live agent progress bar → case queue → case brief (interactive churn checklist) → graph view → post-detection workflow tracker → team-specific output downloads. |

### Why DuckDB
DuckDB runs fully in-process, executes analytical SQL at sub-second speeds on the 5,000-row Crestline dataset, and supports the self-join graph queries used by the circular flow detector. At production scale (500k+ transactions), partitioning by month handles the same queries without an infrastructure change. No Docker, no server, no connection string — just `import duckdb`.

### Data flow

```
Crestline CSV
      ↓  load at startup
  DuckDB  (raw transaction store + all analytical queries)
      ↓  Scout reads via SQL
  Agent 1: Scout  →  writes FraudFinding + Loop entities
      ↓
  Cognee  (memory graph)
      ↓  Ranker reads
  Agent 2: Ranker  →  writes RankedFinding entities
      ↓
  Cognee
      ↓  Investigator reads
  Agent 3: Investigator  →  writes InvestigationAction entities
      ↓
  Cognee
      ↓  Narrator reads full chain
  Agent 4: Narrator  →  outputs 4 team packages + PDF brief
      ↓
  Streamlit UI  (case queue, brief, graph, workflow tracker, downloads)
```

---

## Data Ontology

RingFence builds a typed ontology from the raw transaction data at ingestion. Every entity is stored in DuckDB for fast querying and mirrored into Cognee as a graph node so agents can traverse relationships semantically.

### Entity definitions

**Account**
```
account_id              string     Primary key
account_open_date       date       Coordinated-opening detector input
account_age_days_at_tx  int        Computed per transaction; dormancy baseline
kyc_stated_occupation   string     From KYC records — compared against behavior
kyc_expected_volume_usd float      From KYC records — deviation flags KYC misalignment (churn check 5)
behavioral_baseline     dict       Scout-computed: avg amount, timing, counterparties (days 1–60)
behavioral_drift_score  float      Scout-computed: std-dev deviation from baseline (days 61–90)
ring_membership         list[str]  Loop IDs this account appears in (populated by Scout)
```

**Transaction**
```
transaction_id          string     Primary key
timestamp               datetime   Velocity, timing clustering, interval regularity
sender_account          FK         → Account
receiver_account        FK         → Account
amount_usd              float      Sub-threshold clustering, churn check 1 & 2
device_fingerprint      FK         → Device
ip_subnet               FK         → IPRegion
```

**Device**
```
device_fingerprint      string     Primary key  (FP-A, FP-B in Crestline dataset)
accounts_using_device   list[FK]   → Account;  len > 1 = shared-device signal
first_seen              datetime
last_seen               datetime
shared_across_accounts  bool       Computed; true for FP-A and FP-B
```

**IPRegion**
```
ip_subnet               string     Primary key
region                  string     Coarse geographic area
country                 string
accounts_from_subnet    list[FK]   → Account
region_change_flag      bool       True if account's subnet changes mid-dataset (travel pattern)
```

**Loop** *(Scout-created, written to Cognee)*
```
loop_id                 string     scout-loop-001 … scout-loop-006
cycle_path              list[str]  Ordered account IDs: ["acc_A","acc_B","acc_C","acc_A"]
transaction_ids         list[str]  All transactions in this loop
total_value_usd         float      Sum of all amounts in loop
time_span_hours         float      First to last transaction in loop
amount_std_dev          float      Lower = more deliberate structuring
velocity_hours          float      Avg arrival-to-departure time per account in loop
net_balance_change      float      ≈ 0.00 for confirmed circular flows (churn check 2)
```

**MerchantCategory** ⚠ *Not confirmed in the Crestline dataset — Builder must verify this field exists in the downloaded CSV before relying on it*
```
merchant_category_code  string     MCC (e.g., 6012 = financial institutions)
merchant_category_name  string
transactions            list[FK]   → Transaction
expected_for_kyc        bool       True if MCC is consistent with stated occupation/profile
```

### Cognee graph relationships

```
Account  ──transacts_with──>  Account   (via Transaction edges, directed)
Account  ──uses──>            Device
Account  ──originates_from──> IPRegion
Account  ──member_of──>       Loop
Loop     ──contains──>        Transaction
```

Agents traverse this graph: Scout builds it, Ranker scores nodes, Investigator expands edges, Narrator reads paths end-to-end to write the narrative.

---

## Step 0 — Product Brief

**Status:** [ ] written and signed off by whole team

### Who it's for
An AML analyst on Crestline Community Bank's Money Laundering Team. Their monitoring system flags 0.3% of transactions and missed a 12-account ring that laundered $161,751 in 90 days through circular layering. They have a case queue every morning and about three minutes per case to decide: escalate to the BSA Officer, apply the churn checklist, or clear. RingFence shows them the layering graph behind the numbers and hands off a pre-filled churn checklist so the first three minutes are spent deciding, not searching.

### What it does (one sentence)
RingFence runs four agents over 90 days of Crestline transaction data to identify the coordinated money laundering ring that rule-based monitoring missed, rank its sub-rings by exposure and evasion sophistication, deliver a one-page signed case brief, and hand off a structured workflow to the Money Laundering Team for SAR filing and account action.

### What success looks like
| Metric | Target | Why this target |
|--------|--------|-----------------|
| Ring accounts identified (recall) | ≥ 10 of 12 | Judges verify against hidden answer key |
| Distractor accounts NOT flagged (precision) | ≥ 12 of 15 | Penalizes flag-everything; precision matters |
| Circular loops identified | All 6 of 6 | Total exposure only accurate if all loops found |
| Exposure estimate accuracy | Within 10% of $161,751 | Dollar figure is in the answer key |
| Time from CSV upload to first brief | < 90 seconds | AML queue starts at 8 AM |
| Agent reasoning logged | 100% of decisions | Zero black-box outputs — judging requirement |
| Churn checklist pre-filled per case | 100% of ESCALATE cases | Saves analyst 10+ min of manual calculation |

### What we will NOT build
- Real-time streaming ingestion (batch only — CSV upload)
- A full AML case management system (no tickets, SLAs, or assignment queues)
- Model retraining or feedback loops (inference pipeline only)
- Auth, roles, or multi-tenancy (single analyst session for the demo)
- Anything that writes back to Crestline's production systems

---

## Step 1 — Agent 1: Scout

**Role:** Ingest 5,000 Crestline transactions, construct a directed transaction graph, and surface the structural patterns that betray the hidden money laundering ring.

**Status:**
- [ ] Dataset downloaded and column schema mapped
- [ ] Directed transaction graph built (nodes = accounts, edges = transactions with amount + timestamp)
- [ ] All five detectors implemented and tested against known ring structure
- [ ] Findings written to Cognee with schema below

### Dataset columns to map (confirm on download)
Expected fields: `transaction_id`, `timestamp`, `sender_account`, `receiver_account`, `amount_usd`, `device_fingerprint`, `ip_subnet`, `account_opened_date`, `account_age_days_at_tx`.

### What Scout detects

**1. Circular flows (primary signal)**
Directed graph cycles where money leaves account A, passes through B → C → … → and returns to A. Constrained to a configurable time window.

- *Crestline-specific parameters:* search for cycles of length 3–8 (the 6 loops use ~12 accounts); time window 72 hours.
- *Why this catches the ring:* the ring runs 6 distinct loops. Each loop is a graph cycle and a textbook layering pattern. No single transaction in any loop exceeds $900, so no threshold fires — but the cycles are structurally obvious.

**2. Sub-threshold clustering (secondary signal)**
Accounts whose transaction amounts cluster tightly in a band well below any plausible alert threshold, with ≥ 5 transactions in a 7-day window.

- *Crestline-specific parameters:* flag accounts where ≥ 80% of outbound amounts fall in a $400–$900 band AND transaction count ≥ 5 in 7 days.
- *Why this catches the ring:* the 250 ring transactions all land in the $400–$900 range. This is deliberate structuring — a classic placement-to-layering transition where amounts are calibrated to stay below the monitoring floor.

**3. Shared device fingerprints across accounts**
Two or more distinct accounts sharing a device fingerprint or IP subnet.

- *Crestline-specific parameters:* flag any device fingerprint appearing on ≥ 2 accounts. The dataset contains exactly 2 such fingerprints spanning 4 accounts.
- *Why this catches the ring:* device reuse across accounts is a strong synthetic identity signal and confirms coordinated operation rather than coincidental behavior.

**4. Coordinated dormancy-then-drift (slow-burn signal)**
Accounts with ≥ 60 days of normal behavior that then show a sudden behavioral shift — amount range changes, timing changes, new counterparties appear.

- *Crestline-specific parameters:* baseline 60 days; flag accounts where post-day-60 behavior deviates by ≥ 2 standard deviations on amount, timing, or counterparty novelty.
- *Why this catches the ring:* 3 of the 12 ring accounts were seeded to look normal for 60 days before drifting — a deliberate legitimacy-building phase before activation.

**5. Coordinated account opening (cluster signal)**
Accounts opened within a short shared window that later transact with each other.

- *Crestline-specific parameters:* flag clusters of ≥ 3 accounts opened within a 10-day window that subsequently transact directly with each other.
- *Why this catches the ring:* all 12 ring accounts were opened within the same 10-day window. This is the strongest single structural tell in the dataset — a pre-built transfer network assembled before any laundering began.

### Reasoning format (logged per finding)
```json
{
  "finding_id": "scout-001",
  "type": "circular_flow",
  "accounts_involved": ["acc_047", "acc_112", "acc_203", "acc_061"],
  "evidence": {
    "cycle_path": ["acc_047 -> acc_112", "acc_112 -> acc_203", "acc_203 -> acc_061", "acc_061 -> acc_047"],
    "loop_index": 1,
    "transaction_count": 40,
    "time_span_hours": 71.2,
    "total_value_usd": 26840.00,
    "amount_range_usd": [412, 897],
    "timestamps_clustered_at": "02:00–04:00 local",
    "interval_regularity": "near-regular (~6h between transactions)",
    "velocity_hours_arrival_to_departure": 5.8,
    "net_balance_change_usd": 0.00
  },
  "why_missed_by_rules": "No single transaction exceeded $900. No account appeared on watchlist. Sub-threshold structuring — Crestline alert floor likely $1,000+.",
  "corroborating_signals": ["coordinated_opening: all 4 accounts opened within same 10-day window", "device_fingerprint: acc_047 and acc_112 share fingerprint FP-A"],
  "confidence": 0.94
}
```

### Cognee write schema
```
Entity: FraudFinding
  finding_id: str          # scout-001, scout-002, ...
  type: enum               # circular_flow | sub_threshold_cluster | shared_device | dormancy_drift | coordinated_opening
  accounts_involved: list[str]
  evidence: dict           # includes velocity_hours_arrival_to_departure, net_balance_change_usd
  corroborating_signals: list[str]
  why_missed_by_rules: str
  confidence: float
  status: enum             # new → ranked → actioned → narrated
  loop_index: int | null   # 1–6 for circular_flow findings
```

---

## Step 2 — Agent 2: Ranker

**Role:** Read all Scout findings from Cognee and produce a ranked list, worst-first, with a written rationale for every rank position. Distractor accounts must not appear in the top 10.

**Status:**
- [ ] Reads all `FraudFinding` records (status = "new") from Cognee
- [ ] Scores each finding on five dimensions (see below)
- [ ] Writes `RankedFinding` records back to Cognee
- [ ] Distractor precision test: none of the 15 known distractor patterns (large one-offs, travel IPs) score above 50
- [ ] Zero findings ranked without a written `rank_rationale`

### Scoring rubric (each dimension 0–20, total 0–100)

| Dimension | What it measures | Crestline signal |
|-----------|-----------------|-----------------|
| **Circular loop confirmation** | Is this finding part of a confirmed graph cycle? | Loop findings score 20; cluster findings without loop score ≤ 10 |
| **Corroborating signal count** | How many independent signals overlap? | Each additional signal (shared device, coordinated opening, dormancy drift) adds 5, max 20 |
| **Exposure magnitude** | Total value moving through this sub-ring | $161,751 total; proportional score per loop based on loop's share |
| **Evasion deliberateness** | How tight is the amount clustering? | Std deviation of amounts in loop: lower = more deliberate = higher score |
| **Recency** | When did the last transaction in this finding fire? | Last 24h = 20; last 7 days = 10; older = 5 |

### Optional: Bayesian scoring with PyMC

Instead of point-estimate scores (e.g., "evasion deliberateness = 18/20"), PyMC enables the Ranker to produce **posterior distributions** over each dimension. This surfaces uncertainty: a finding with score 18 ± 2 is very different from one scored 18 ± 9.

```python
import pymc as pm

with pm.Model() as ranker_model:
    # Prior: evasion deliberateness given std_dev of transaction amounts
    evasion_score = pm.Beta("evasion_score", alpha=amount_std_dev_alpha, beta=amount_std_dev_beta)
    # Likelihood: observed clustering tightness
    obs = pm.Normal("obs", mu=evasion_score * 20, sigma=2, observed=observed_score)
    trace = pm.sample(500, tune=200, progressbar=False)

# Report median + 94% HDI instead of a single number
median_score = float(trace.posterior["evasion_score"].median())
hdi = pm.hdi(trace.posterior["evasion_score"], hdi_prob=0.94)
```

Use PyMC when the dataset is small (5,000 rows) and you want principled uncertainty quantification. Use point estimates when speed matters more than calibration. The Ranker supports both modes via a `--scoring-mode bayesian|point` flag.

### Distractor filter (run before scoring)
Before scoring, Ranker explicitly checks each finding against distractor patterns:
- Single large one-off purchase with no circular flow → mark `distractor_candidate = true`
- IP subnet change with no shared device fingerprint and no circular flow → mark `distractor_candidate = true`
- Any `distractor_candidate = true` finding is scored but capped at 40 and labeled `LIKELY_LEGITIMATE_ANOMALY`.

This is the precision gate. Without it, the 15 distractors inflate false positives and tank the answer-key score.

### Reasoning format (logged per ranking)
```json
{
  "finding_id": "scout-001",
  "rank": 1,
  "total_score": 94,
  "distractor_candidate": false,
  "score_breakdown": {
    "circular_loop_confirmation": 20,
    "corroborating_signal_count": 20,
    "exposure_magnitude": 18,
    "evasion_deliberateness": 18,
    "recency": 18
  },
  "rank_rationale": "Ranked #1 because this is a confirmed 4-account circular loop (loop 1 of 6), corroborated by shared device fingerprint FP-A across acc_047 and acc_112 AND coordinated account opening (all 4 opened within the same 10-day window). The amount standard deviation is $147 — tight clustering indicating deliberate sub-threshold structuring. The last transaction fired 14 hours ago. Only recency and exposure fall slightly below maximum — the loop accounts for an estimated $26,840 of the $161,751 total (16.6% share)."
}
```

### Cognee write schema
```
Entity: RankedFinding
  finding_id: str
  rank: int
  total_score: int
  distractor_candidate: bool
  score_breakdown: dict
  rank_rationale: str        # required — human-readable, no "model said so"
  ranked_at: datetime
```
Update parent `FraudFinding.status` → `"ranked"`.

---

## Step 3 — Agent 3: Investigator

**Role:** For each top-ranked finding, run cross-reference checks against the full Crestline dataset and decide on an explicit, logged action. The 15 distractor accounts are the test of this agent's precision.

**Status:**
- [ ] Reads top-ranked `RankedFinding` records from Cognee (score ≥ 50, not `distractor_candidate`)
- [ ] Runs all five cross-reference checks per finding (see below)
- [ ] Takes one of three actions with an explicit written reason
- [ ] Correctly routes all 6 loops to ESCALATE and all 15 distractors to CLEAR or SNOOZE
- [ ] "The model said so" appears zero times in any log

### Cross-reference checks

**1. Account opening cluster check**
Query Cognee for other accounts opened within 10 days of any account in this finding. If ≥ 3 more accounts are found, this confirms coordinated onboarding — the strongest structural signal in the Crestline dataset.

**2. Loop membership overlap**
Check if any account in this finding appears in another Scout finding. Accounts appearing in ≥ 2 loops are hub nodes — they are the connective tissue of the ring and should be prioritized in the escalation narrative.

**3. Device fingerprint cluster expansion**
If a shared fingerprint is present, pull all accounts sharing that fingerprint from the transaction dataset. Fingerprint FP-A spans 2 accounts; fingerprint FP-B spans 2 different accounts. If a new loop finding shares a fingerprint with a previously actioned finding, these loops are part of the same ring.

**4. Behavioral baseline comparison (slow-burn accounts)**
For each account in the finding, compare transactions in days 1–60 vs. days 61–90. Accounts with normal early behavior that drift in the final 30 days are the 3 seeded slow-burn accounts — their drift confirms deliberate ring activation, not random anomaly.

**5. Distractor disqualification check**
Confirm the finding does NOT match a distractor pattern: single large purchase without loop membership, or IP change without fingerprint overlap and without loop membership. If it matches, override action to `CLEAR` regardless of score.

### Action taxonomy

| Action | Trigger condition |
|--------|-----------------|
| `ESCALATE` | Score ≥ 70 AND circular loop confirmed AND ≥ 1 cross-reference hit |
| `AUTO_FLAG` | Score 50–69 OR loop not confirmed but ≥ 2 corroborating signals |
| `CLEAR` | Distractor disqualification check fires, OR score < 50 with 0 corroborating signals |
| `SNOOZE_48H` | Score 50–69 with only 1 corroborating signal and no loop confirmation |

### Reasoning format (logged per action)
```json
{
  "finding_id": "scout-001",
  "action": "ESCALATE",
  "action_reason": "Score 94. Circular loop confirmed (loop 1 of 6). Cross-reference hits: (1) all 4 accounts opened in the same 10-day window as 8 other ring-candidate accounts — coordinated onboarding confirmed; (2) acc_112 also appears in scout-004 (loop 3) — hub node, ring connective tissue; (3) shared device fingerprint FP-A links acc_047 and acc_112 to a second fingerprint cluster (FP-B: acc_203, acc_061) found in scout-002. Distractor check: PASS — this is a 40-transaction circular flow, not a one-off anomaly. Total estimated exposure for this loop: $26,840.",
  "cross_reference_hits": [
    "coordinated_opening: 4 accounts in same 10-day cohort of 12",
    "hub_node: acc_112 in scout-001 and scout-004",
    "fingerprint_expansion: FP-A (acc_047, acc_112) linked to FP-B (acc_203, acc_061) via loop"
  ],
  "distractor_check": "PASS",
  "investigated_at": "2026-06-07T14:32:00Z"
}
```

### Cognee write schema
```
Entity: InvestigationAction
  finding_id: str
  action: enum               # ESCALATE | AUTO_FLAG | CLEAR | SNOOZE_48H
  action_reason: str         # required, explicit — no "model said so"
  cross_reference_hits: list[str]
  distractor_check: enum     # PASS | FAIL
  investigated_at: datetime
```
Update parent `FraudFinding.status` → `"actioned"`.

---

## Step 4 — Agent 4: Narrator

**Role:** Consolidate the full chain from Cognee (all 6 loop findings → rankings → actions) into a single case brief for Crestline's Money Laundering Team. The brief must be signable, downloadable, and include a pre-filled AML churn checklist so the analyst's first three minutes are spent deciding, not calculating.

**Status:**
- [ ] Reads all ESCALATE `InvestigationAction` records from Cognee and their full upstream chain
- [ ] Aggregates the 6 loops into a single ring narrative (total exposure: ≈ $161,751)
- [ ] Pre-fills the 5-Point AML Churn Checklist using Scout evidence
- [ ] Generates 4 team-specific output packages (AML, Compliance, DBA/Dev, Management) — see [Outcomes & Team-Specific Outputs](#outcomes--team-specific-outputs)
- [ ] Brief matches the template below
- [ ] All 4 team packages downloadable from the Streamlit UI
- [ ] Domain Expert has reviewed and signed off on narrative quality and regulatory language
- [ ] Geodo research on real-world structuring cases woven into the "Pattern Context" section

### Brief template

```
RINGFENCE CASE BRIEF — CRESTLINE COMMUNITY BANK / MONEY LAUNDERING TEAM
Case ID: RF-2026-RING-001     Severity: CRITICAL     Generated: 2026-06-07 14:32 UTC
AML Analyst: _______________  BSA Officer: _____________  Review deadline: ___________

━━━ THE SHORT VERSION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Twelve accounts — all opened within the same 10-day window — have moved an
estimated $161,751 through six circular loops over 90 days. Every transaction was
between $400 and $900. Every transaction ran between 2 and 4 AM. Crestline's
monitoring caught zero of the 250 ring transactions. This is active layering.

━━━ WHAT WE FOUND ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Pattern type:        6 circular flows (confirmed) + coordinated account opening
Money laundering phase: Layering (funds cycling through accounts to obscure origin)
Ring accounts:       ~12 (see account list below)
Total transactions:  250 ring transactions within 5,000 total
Time window:         90 days (full dataset window)
Transaction amounts: $400–$900 per transaction (sub-threshold structuring)
Transaction timing:  2:00–4:00 AM at near-regular ~6-hour intervals
Device fingerprints: 2 shared fingerprints across 4 accounts (FP-A, FP-B)
Slow-burn accounts:  3 accounts with 60+ days normal behavior before ring activation
Total exposure:      ≈ $161,751 across all 6 loops

Why rules missed it: No single transaction exceeded Crestline's alert threshold.
                     No account was on the watchlist. Sub-threshold structuring
                     ($400–$900) and off-hours timing prevented all rule triggers.

━━━ THE SIX LOOPS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Loop  Accounts          Transactions  Est. Value   Confidence
  1   A → B → C → A         40        $26,840       94%
  2   A → D → E → F → A     45        $29,100       91%
  3   B → G → H → B         38        $24,920       93%
  4   C → I → J → C         42        $27,350       90%
  5   D → K → L → D         41        $26,140       92%
  6   F → G → I → K → F     44        $27,401       89%
                            ───        ───────
  TOTAL                     250       $161,751

Hub nodes (appear in multiple loops — freeze first):
  acc_B (loops 1, 3)  acc_D (loops 2, 5)  acc_F (loops 2, 6)
  acc_G (loops 3, 6)  acc_I (loops 4, 6)  acc_K (loops 5, 6)

━━━ 5-POINT AML CHURN CHECKLIST (pre-filled by RingFence) ━━━━━━━━━━━━━━━━━━━━━

Use this checklist to support SAR narrative drafting and EDD documentation.
Each item is pre-filled from agent evidence. AML analyst confirms or overrides.

1. VELOCITY — Are funds consistently withdrawn/transferred within hours of arrival?
   RingFence finding: Average time from arrival to outbound transfer is ~5.8 hours
   across all 6 loops. Near-regular ~6-hour intervals, timed 2–4 AM.
   Status: [ ] CONFIRMED  [ ] NOT CONFIRMED  [ ] NEEDS REVIEW
   Analyst note: _______________________________________________

2. NET VALUE — Does the account balance regularly return to near-zero after cycling?
   RingFence finding: Circular flows return funds to origin account — net balance
   change per completed loop ≈ $0.00 (minus transaction fees absorbed by the ring).
   Hub accounts show repeated near-zero resets after each cycle completion.
   Status: [ ] CONFIRMED  [ ] NOT CONFIRMED  [ ] NEEDS REVIEW
   Analyst note: _______________________________________________

3. ECONOMIC RATIONALITY — Is there an obvious commercial or personal purpose, or
   is the user absorbing systematic transaction fees with no visible logic?
   RingFence finding: No identifiable commercial purpose. The ring is absorbing
   transaction fees on 250 transactions with zero net economic gain. All accounts
   show zero payroll, vendor, or consumer-spend activity during ring activation.
   Status: [ ] CONFIRMED  [ ] NOT CONFIRMED  [ ] NEEDS REVIEW
   Analyst note: _______________________________________________

4. ROUND-TRIPPING — Are funds moving in circular patterns between the same entities?
   RingFence finding: 6 confirmed directed graph cycles. This is the core finding.
   Money explicitly returns to the originating account in every loop.
   Hub accounts (B, D, F, G, I, K) appear in 2+ loops — confirmed round-trip nexus.
   Status: [ ] CONFIRMED  [ ] NOT CONFIRMED  [ ] NEEDS REVIEW
   Analyst note: _______________________________________________

5. KYC ALIGNMENT — Does this transaction volume radically deviate from the
   customer's stated profile, occupation, or historical baseline?
   RingFence finding: 3 slow-burn accounts showed normal behavior for 60 days then
   drifted sharply (≥ 2 std dev on amount, timing, counterparty). All 12 accounts
   show 2–4 AM activity with no consumer or business purpose pattern.
   Stated customer profiles have NOT been pulled yet — AML analyst must confirm.
   Status: [ ] CONFIRMED  [ ] NOT CONFIRMED  [ ] NEEDS REVIEW
   Analyst note: _______________________________________________

CHURN CHECKLIST SUMMARY:  ___ / 5 items confirmed
SAR Indicator score:       CRITICAL (5/5) / HIGH (4/5) / MEDIUM (3/5) / LOW (<3/5)

━━━ SCORING SUMMARY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

All 6 loops scored ≥ 89/100. All 6 actioned: ESCALATE.
15 distractor accounts reviewed. All 15 cleared (no loop membership).

━━━ PATTERN CONTEXT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This pattern is consistent with documented layering operations at community
banks (see: Geodo research — Liberty Reserve indictment 2013; FinCEN structuring
advisory FIN-2014-A005). Key indicators present in this case:
  - Amounts deliberately held below likely monitoring threshold (~$1,000)
  - Off-hours timing (2–4 AM) to reduce human review likelihood
  - Coordinated account opening to establish a pre-built transfer network
  - Slow-burn onboarding: 3 accounts established legitimacy before activation
  - Circular flows returning funds to origin — layering, not placement
  - Fee absorption with no economic rationale — classic churn signature

SAR filing threshold: $5,000 for single transaction; $25,000 aggregate 30-day
exposure per account. At least 4 hub accounts exceed the $25,000 aggregate
threshold and require a SAR filing under 31 CFR § 1020.320.

━━━ WHAT TO DO IN THE NEXT 3 MINUTES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[ ] Complete the 5-Point Churn Checklist above (items 1–4 are pre-filled;
    item 5 requires pulling KYC files for all 12 ring accounts)
[ ] Freeze outbound transfers on hub accounts (B, D, F, G, I, K) immediately —
    the ring is still active
[ ] Confirm which accounts exceed $25,000 aggregate 30-day exposure for SAR
[ ] Escalate to BSA Officer — proceed to Post-Detection Pipeline (Step 6 below)
[ ] Preserve transaction logs before any account closure (evidence chain)

━━━ AGENT REASONING AUDIT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Every decision made by the RingFence pipeline is logged and exportable.
See "Show agent reasoning" in the product UI to audit the full chain:
Scout findings (6) → Ranker scores (6) → Investigator actions (6) → this brief.

━━━ AML ANALYST SIGN-OFF ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Reviewed by: ___________________    Date: ___________    
Churn checklist: ___ / 5 confirmed  Action taken: ___________________________
BSA Officer notified: [ ] Yes  [ ] No    SAR filed: [ ] Yes  [ ] No  [ ] Pending
Proceeding to Post-Detection Pipeline: [ ] Yes  [ ] No
```

### Geodo research targets (Domain Expert owns these)
- [ ] Liberty Reserve indictment (2013) — circular flow layering at scale, regulatory language
- [ ] FinCEN advisory FIN-2014-A005 — structuring red flags at community banks specifically
- [ ] FinCEN SAR filing requirements (31 CFR § 1020.320) — threshold amounts, filing window
- [ ] Research the "2–4 AM off-hours" pattern — documented AML evasion technique vs. automated bot artifact
- [ ] Research coordinated account opening as a BSA red flag — how many institutions flag same-window account clusters?
- [ ] Research churn/layering fee absorption as a SAR indicator — FinCEN guidance on economic irrationality

---

## Step 5 — Product & Demo

**Status:**
- [ ] UI built (see spec below)
- [ ] Demo script written and rehearsed (AML analyst POV, not engineer POV)
- [ ] Trupeer recording completed (≤ 5 minutes)
- [ ] Demo runs on the Crestline dataset — judges can verify against the hidden answer key

### UI spec

**Screen 1 — Upload**
Drop zone for the Crestline CSV. A four-stage progress bar lights up sequentially:
`Scout: Building graph` → `Ranker: Scoring findings` → `Investigator: Cross-referencing` → `Narrator: Writing briefs`
Each stage shows elapsed time. When Scout completes, a live counter shows "N ring candidates found." This is the hook — the AML analyst sees the pipeline working in real time.

**Screen 2 — Case Queue**
Table sorted by Ranker score descending.
Columns: `Case ID | Severity | Loop Count | Accounts | Est. Exposure | Churn Score | Action | Generated`
Color coding: red = ESCALATE, yellow = AUTO_FLAG, green = CLEAR, grey = SNOOZE.
A summary banner at the top: *"6 loops confirmed. ~12 ring accounts. ≈$161,751 exposure. 15 distractors cleared."*

**Screen 3 — Case Brief**
The full Narrator brief rendered in clean, print-ready layout.
The 5-Point AML Churn Checklist is interactive — checkboxes the analyst fills in before downloading.
"Download PDF" button top-right (captures the filled checklist state).
Expandable "Show agent reasoning" accordion — reveals the raw JSON log from Scout, Ranker, and Investigator for every decision.

**Screen 4 — Graph View**
Force-directed graph: nodes = accounts, edges = transactions, edge weight = transaction amount.
The 6 circular loops are visually obvious — each loop is a distinct cycle in the graph.
Hub nodes (B, D, F, G, I, K) are visually prominent (larger, darker).
Accounts sharing a device fingerprint are connected with a dashed edge in a different color.
Hover on any node: account ID, opening date, loop membership, total volume, churn velocity.
Hover on any edge: transaction ID, amount, timestamp.

**Screen 5 — Post-Detection Workflow**
After the analyst signs off on the brief, a step-by-step workflow tracker opens (mirrors Step 6 below).
Each stage has a status toggle (Not Started / In Progress / Complete) and a notes field.
The BSA Officer's name and SAR deadline are displayed prominently.

### Demo script (AML analyst POV — 5 minutes)

```
0:00 — "I'm on the Money Laundering Team at Crestline Community Bank.
        This morning my monitoring system flagged 17 transactions.
        It missed 250. Here's how I found the other 250."

0:20 — Upload the Crestline CSV. Watch the pipeline run.
       "Scout is building a transaction graph across 300 accounts.
        Ranker is scoring what it finds. Investigator is cross-referencing.
        Narrator is writing the brief with a pre-filled churn checklist.
        90 seconds, start to finish."

1:30 — Case queue appears. "My system flagged nothing. RingFence found
        active layering. Let me open the brief."

1:45 — Read the SHORT VERSION aloud:
       "Twelve accounts, all opened in the same 10-day window.
        $161,751 through six circular loops. Every transaction
        $400 to $900. Every transaction 2 to 4 AM. My rules
        caught zero of 250 transactions. This is active layering."

2:15 — Scroll to the AML Churn Checklist. "This is why this product
        exists. RingFence pre-fills my churn checklist from the agent
        evidence. Velocity: 5.8 hours arrival to transfer. Net value:
        returns to zero every loop. Economic rationality: absorbing
        fees with no purpose. Round-tripping: six confirmed circular flows.
        I just have to confirm KYC alignment and I'm done."

2:50 — Check item 5, add a note. "KYC mismatch confirmed — accounts
        stated as personal savings, running $161k in circular transfers.
        Five of five. This is a SAR."

3:10 — Switch to Graph View. "This is the ring. You can see all six
        loops. The big nodes are the hubs. They're the ones I freeze first."

3:40 — Open the 'Show agent reasoning' accordion.
       "Every decision is logged. Why ESCALATE? Score 94, circular loop
        confirmed, coordinated opening, shared fingerprint. Nothing is
        'the model said so'."

4:10 — Download the PDF. "I sign it. BSA Officer gets it. SAR drafted.
        Post-detection workflow starts. Next case."

4:30 — "Crestline's rules flagged 0.3% of activity and missed
        everything. RingFence found the ring in 90 seconds, pre-filled
        the AML churn checklist, and handed the Money Laundering Team
        a signed brief and a step-by-step workflow. We give them the
        three minutes back."
```

---

## Step 6 — Post-Detection: Money Laundering Team Pipeline

**What happens after RingFence flags a ring.** This is the human workflow that begins the moment the AML analyst downloads the signed case brief. RingFence hands off here; the Money Laundering Team takes over.

```
RINGFENCE OUTPUT (signed brief + pre-filled churn checklist)
          ↓
  Stage 1: AML Triage               [AML Analyst — ≤ 3 min]
          ↓
  Stage 2: Enhanced Due Diligence   [AML Analyst + Compliance — 1–2 hr]
          ↓
  Stage 3: SAR Filing Decision      [BSA Officer — same business day]
          ↓
  Stage 4: Account Action           [Compliance + Legal — 24–48 hr]
          ↓
  Stage 5: Law Enforcement Referral [BSA Officer + Legal — if warranted]
          ↓
  Stage 6: Case Closure + Rule Update [Compliance — within 5 business days]
```

---

### Stage 1 — AML Triage

**Owner:** AML Analyst
**Time budget:** ≤ 3 minutes
**Input:** RingFence case brief (PDF) with pre-filled 5-Point AML Churn Checklist
**Auto follow-ups generated:** Upon triage decision, RingFence automatically creates follow-up task packages for each downstream team (see [Outcomes & Team-Specific Outputs](#outcomes--team-specific-outputs)) and surfaces them in the Streamlit post-detection workflow screen.

#### 5-Point Money Laundering Churn Checklist

The churn checklist is the analyst's primary decision tool at triage. RingFence pre-fills items 1–4 from agent evidence. The analyst confirms or overrides each item and completes item 5 (KYC Alignment) manually.

| # | Check | Question | Pass Condition | Pre-filled? |
|---|-------|----------|---------------|-------------|
| 1 | **Velocity** | Are funds consistently withdrawn or transferred within minutes/hours of arrival? | Avg arrival-to-departure < 24h across ≥ 3 accounts | Yes — Scout logs `velocity_hours_arrival_to_departure` per loop |
| 2 | **Net Value** | Does the account balance regularly return to near-zero after high-volume cycling? | Net balance change per completed loop ≈ $0 (±5%) | Yes — circular flows return to origin; Scout logs `net_balance_change_usd` |
| 3 | **Economic Rationality** | Is there an obvious commercial or personal purpose, or is the user absorbing systematic transaction fees with no visible logic? | Zero identifiable business purpose + net fee absorption confirmed | Yes — Scout flags accounts with no payroll/vendor/consumer activity during ring period |
| 4 | **Round-Tripping** | Are funds moving in circular patterns between the same entities or related accounts? | Any confirmed directed graph cycle | Yes — this is Scout's primary finding; 6 loops confirmed |
| 5 | **KYC Alignment** | Does this transaction volume radically deviate from the customer's stated profile, occupation, or historical baseline? | Volume in days 61–90 vs. stated KYC profile shows ≥ 2× deviation | **No — analyst must pull KYC files and confirm manually** |

**Triage decision:**

| Churn Score | Decision |
|-------------|----------|
| 5 / 5 confirmed | **PROCEED** → Stage 2 EDD immediately |
| 4 / 5 confirmed | **PROCEED** → Stage 2 EDD, note the unconfirmed item |
| 3 / 5 confirmed | **HOLD** → Request additional account data before proceeding |
| < 3 / 5 confirmed | **REFER BACK** → Return to RingFence for re-analysis; document reasoning |

**Triage checklist:**
- [ ] Churn checklist items 1–4 confirmed or overridden with written rationale
- [ ] KYC files pulled for all 12 ring accounts (item 5)
- [ ] Triage decision recorded with supporting notes
- [ ] BSA Officer notified if proceeding to Stage 2

---

### Stage 2 — Enhanced Due Diligence (EDD)

**Owner:** AML Analyst + Compliance Officer
**Time budget:** 1–2 hours
**Input:** Stage 1 triage decision (PROCEED) + RingFence brief

**EDD checklist:**
- [ ] Pull full KYC files for all 12 ring accounts — verify identity documents, stated occupation, expected transaction volume
- [ ] Check all 12 accounts against OFAC SDN list, FinCEN 314(a) list, and internal watchlist
- [ ] Screen for Politically Exposed Persons (PEPs) and adverse media across all account holders
- [ ] Verify beneficial ownership — who actually controls the hub accounts (B, D, F, G, I, K)?
- [ ] Pull all shared identity signals: matching addresses, phone numbers, email domains, SSN fragments across the 12 accounts
- [ ] Quantify fee absorption: calculate total transaction fees paid by ring accounts with zero economic benefit — document as evidence of economic irrationality
- [ ] Request correspondent bank records if any ring account has external wire activity
- [ ] Document every finding with source, date, and analyst name

**EDD output:** Completed EDD memo → forwarded to BSA Officer for Stage 3

---

### Stage 3 — SAR Filing Decision

**Owner:** BSA Officer
**Time budget:** Same business day as Stage 2 completion
**Input:** RingFence brief + completed EDD memo
**Hard deadline:** SAR must be filed within **30 calendar days** of the date suspicious activity was identified

**SAR decision checklist:**
- [ ] Review RingFence brief + EDD memo in full
- [ ] Determine SAR filing basis: circular layering pattern confirmed (31 CFR § 1020.320)
- [ ] Identify which accounts meet the $25,000 aggregate 30-day threshold (≥ 4 hub accounts expected)
- [ ] Draft SAR narrative using RingFence brief as source material — the "WHAT WE FOUND" and "THE SIX LOOPS" sections map directly to SAR fields
- [ ] File or No-File decision with **written rationale in both cases**
- [ ] If filing: submit SAR to FinCEN via BSA E-Filing within the 30-day window
- [ ] **⚠ Do NOT notify the subject of the SAR filing** — tipping-off prohibition under 31 U.S.C. § 5318(g)(2); criminal penalty applies

**SAR narrative source mapping:**

| SAR Field | RingFence Source |
|-----------|-----------------|
| Subject name/account | Ring accounts table + KYC files from EDD |
| Amount involved | $161,751 total exposure (verified against Kaggle answer key) |
| Date range | 90-day dataset window |
| Type of suspicious activity | Layering via circular fund flows |
| Description of activity | "THE SIX LOOPS" section of brief |
| Why activity is suspicious | 5-Point Churn Checklist results |
| Prior SARs filed | Cross-reference from BSA case management system |

---

### Stage 4 — Account Action

**Owner:** Compliance Officer + Legal
**Time budget:** Within 24–48 hours of SAR filing decision
**Critical constraint:** Do NOT close accounts until SAR is filed (evidence chain must be preserved)

**Account action checklist:**
- [ ] **Freeze outbound transfers** on all 6 hub accounts (B, D, F, G, I, K) — these are the ring's pumps; shutting them stops the layering
- [ ] **Restrict inbound transfers** on spoke accounts if the ring is still actively receiving funds
- [ ] Issue a **legal hold** on all transaction records, device logs, IP logs, and account onboarding documents for all 12 ring accounts — do not purge under any retention policy
- [ ] **Do not close accounts** until SAR is filed and Legal confirms (premature closure destroys evidence chain and can alert the subject)
- [ ] **Do not contact the customer** about the freeze or investigation without explicit Legal approval — tipping-off risk
- [ ] After SAR is filed: Legal to advise on account closure timeline and customer communication (if any)
- [ ] Document every action with timestamp, operator name, and authorization

---

### Stage 5 — Law Enforcement Referral

**Owner:** BSA Officer + Legal
**Timing:** After SAR filed; concurrent with or following Stage 4
**Trigger threshold (all three required):**
- Total exposure > $25,000 AND
- Circular flows confirmed (≥ 1 loop) AND
- Synthetic identity indicators present (shared device, coordinated opening, or shared KYC documents)

**If threshold met:**
- [ ] Prepare referral package: RingFence brief + EDD memo + SAR confirmation number + evidence inventory
- [ ] Identify referral channel:
  - FBI Financial Crimes Unit — primary for bank fraud and money laundering
  - DEA — if transaction patterns suggest drug proceeds (timing, geography, counterparties)
  - IRS Criminal Investigation (IRS-CI) — if tax evasion is indicated by unreported income
- [ ] Establish chain of custody for all evidence before transfer
- [ ] **Do NOT independently contact the subject** — law enforcement will manage subject contact
- [ ] Coordinate with legal on any grand jury subpoena or warrant response procedures

---

### Stage 6 — Case Closure + Rule Update

**Owner:** Compliance Officer
**Time budget:** Within 5 business days of SAR filing
**Purpose:** Close the case cleanly and prevent the next ring from hiding in the same blind spot.

**Closure checklist:**
- [ ] Document the full investigation timeline: detection timestamp → triage → EDD → SAR → account action → referral
- [ ] Record all account actions taken with timestamps and operator names
- [ ] Close the case in the BSA case management system with case ID cross-referenced to SAR confirmation number
- [ ] **Rule update debrief:** which of the 5 churn signals would a new monitoring rule have caught earliest?
  - Velocity (5.8h avg) → Would a "same-day cycling" rule have fired?
  - Net value (near-zero resets) → Would a "balance oscillation" rule have fired?
  - Economic rationality → Can fee-absorption with no offsetting revenue be automated?
  - Round-tripping → Could circular flow detection be built into the core monitoring system?
  - KYC deviation → Would a behavioral baseline alert on the slow-burn drift have fired at day 65?
- [ ] Draft monitoring rule proposal for each signal that a rule could have caught
- [ ] Submit rule proposals to the fraud engineering team for review

---

### Post-Detection Status Tracker

Use this table to track where each ESCALATE case stands across the pipeline.

| Stage | Owner | Status | Deadline | Notes |
|-------|-------|--------|----------|-------|
| 1 — AML Triage | AML Analyst | [ ] Not Started / [ ] In Progress / [ ] Complete | ≤ 3 min after receipt | Churn checklist score: ___ / 5 |
| 2 — Enhanced Due Diligence | AML Analyst + Compliance | [ ] Not Started / [ ] In Progress / [ ] Complete | Within 2 hr of triage | OFAC/PEP/KYC complete |
| 3 — SAR Filing Decision | BSA Officer | [ ] Not Started / [ ] In Progress / [ ] Complete | Same business day as EDD | SAR confirmation #: _______ |
| 4 — Account Action | Compliance + Legal | [ ] Not Started / [ ] In Progress / [ ] Complete | Within 48 hr | Accounts frozen: 6 hub accounts |
| 5 — LE Referral | BSA Officer + Legal | [ ] N/A / [ ] In Progress / [ ] Complete | After SAR filed | Referral channel: _______ |
| 6 — Closure + Rule Update | Compliance | [ ] Not Started / [ ] In Progress / [ ] Complete | Within 5 business days | Rule proposals submitted: Y/N |

---

## Outcomes & Team-Specific Outputs

Agent 4 (Narrator) generates four output packages from the same pipeline run — one per stakeholder team. All four are downloadable from the Streamlit UI after an ESCALATE decision.

| Team | Primary question | RingFence output | Auto follow-up |
|------|-----------------|-----------------|----------------|
| **AML** | "Who did this and what does their behavior look like?" | Behavior Profile + Ring Narrative + Churn Checklist | EDD task list, SAR draft scaffold |
| **Compliance** | "How do we prevent this next time?" | Rule Gap Analysis + Mitigation Suggestions | Monitoring rule proposals for engineering |
| **DBA / Dev** | "What do we fix right now?" | Technical Action Items + Schema Recommendations | Indexed schema change tickets |
| **Management** | "What happened and what's the dollar exposure?" | 1-paragraph executive summary, plain language | None — informational only |

---

### AML Package — Behavior Profile

**Audience:** AML analysts and investigators on the Money Laundering Team
**Purpose:** Translate the graph evidence into a people-centered narrative — not just "12 accounts formed 6 loops" but "12 people coordinated to build a transfer network before any of them made a suspicious move"

**Contents:**
- Ring narrative in plain language (the "SHORT VERSION" from the case brief)
- Per-account behavioral profile for each hub node (B, D, F, G, I, K): when they joined, how they behaved for 60 days, when they activated, relationships to other ring members
- Identity overlap map: which accounts share device fingerprints, IP subnets, or KYC signals
- Pre-filled 5-Point AML Churn Checklist with agent-sourced evidence for items 1–4
- Auto-generated follow-ups: EDD task list (which accounts to pull KYC for first), SAR draft scaffold with ring facts pre-populated

**Example behavior profile entry:**
```
acc_B — Hub Node (Loops 1 and 3)
Opened:          Day 3 of the 10-day coordinated opening window
Days 1–60:       8 transactions, avg $245, payroll-pattern timing (Fridays)
Day 61 drift:    Began receiving from acc_A at 2–4 AM; outbound to acc_G same session
Post-activation: 78 transactions in 30 days, avg $682, zero consumer spend
Device:          Shares FP-A with acc_A — same device used to open both accounts
KYC stated:      "Retail employee, expected monthly volume $500"
Actual (day 61–90): $38,400 outbound
Behavior read:   60-day legitimacy-building phase followed by hub activation.
                 The payroll pattern in days 1–60 was cover, not income.
```

---

### Compliance Package — Mitigation Suggestions

**Audience:** Compliance Officer and BSA Officer
**Purpose:** Provide concrete, future-oriented suggestions so the next coordinated ring doesn't hide in the same blind spots

**Contents:**
- Rule gap analysis: for each of the 5 churn signals, does a current Crestline monitoring rule cover it? (expected: 0 of 5)
- Proposed monitoring rules, each with a threshold recommendation and expected false-positive rate:

| Proposed Rule | Signal it covers | Recommended threshold | Est. FP rate |
|---------------|-----------------|----------------------|-------------|
| Same-day cycling alert | Velocity | Arrival-to-departure < 6h, ≥ 3 transactions/week | Low — most legitimate accounts don't cycle same-day |
| Balance oscillation alert | Net Value | Balance resets to ±5% of zero after inbound cluster | Low — only churn patterns produce consistent zero-resets |
| Circular flow detector | Round-Tripping | Any directed graph cycle of length 3–8 within 72h | Medium — tune by minimum total value (e.g., > $5,000) |
| Coordinated opening alert | KYC Alignment | ≥ 4 accounts opened within 10-day window, transacting with each other | Low — rare in legitimate onboarding |
| KYC volume deviation alert | KYC Alignment | 30-day volume > 3× KYC-stated expected volume | Medium — flag for manual review, not auto-block |

- Off-hours multiplier: add a ×1.5 score weight to all rule outputs for transactions between 12 AM–5 AM
- **Bayesian threshold recommendations (PyMC):** rather than hard thresholds (e.g., "flag if balance reset < 5%"), the Compliance Package optionally runs a PyMC model over the Crestline dataset to estimate the posterior distribution of the threshold that maximizes precision/recall tradeoff — outputs a credible interval (e.g., "threshold 4.2%–6.8% at 94% HDI") so Compliance can choose a conservative or aggressive cutoff with stated uncertainty
- SAR narrative template (pre-filled from this case) for use in future similar filings
- Auto-generated follow-up: formatted rule proposal document ready for submission to the fraud monitoring engineering team

---

### DBA / Dev Package — Technical Action Items

**Audience:** Database administrators and backend developers
**Purpose:** Surface data quality issues found during the pipeline run and provide specific, present-tense fixes — not "consider improving performance" but "add this index"

**Contents:**
- **Data quality findings** (flagged at ingestion time):
  - Null or missing device fingerprints: list of affected transaction IDs
  - Timestamp anomalies (out-of-order, gaps > 7 days): list
  - Account ID formatting inconsistencies: list
  - Schema coverage: flags if Merchant Category Code (MCC) is absent from the CSV ⚠

- **Present-tense technical fixes:**
  - `CREATE INDEX ON transactions(sender_account, timestamp)` — the circular flow DFS runs this join 250+ times per full-dataset query; without it, query time scales O(n²)
  - `CREATE INDEX ON transactions(receiver_account, timestamp)` — same reason, inbound direction
  - `ALTER TABLE accounts ADD COLUMN behavioral_baseline JSON` — currently recomputed on every Scout run; materializing it cuts Scout runtime by ~40%
  - Add `net_balance_change_usd` as a DuckDB computed column at ingestion — currently recalculated per churn-check query

- **Schema recommendations for future data collection:**
  - Add `merchant_category_code` (MCC) to transaction records — enables economic rationality checks without a KYC lookup per transaction ⚠ *(confirm field availability with data team)*
  - Add `onboarding_channel` (branch / mobile / web) to account records — coordinated online onboarding is a stronger synthetic identity signal than coordinated dates alone
  - Add `beneficiary_name_hash` for wire transfers — enables beneficial ownership network graph without storing PII in plaintext

- **Scale projections:**
  - 5,000 rows (Crestline demo): full pipeline < 90 seconds, DuckDB in-process sufficient
  - 500,000 rows (small community bank): add monthly partitions on `timestamp`, index on `amount_usd`
  - 5,000,000 rows (regional bank): migrate circular flow DFS from DuckDB self-joins to a dedicated graph database (Kuzu or Neo4j)

- **Auto-generated follow-up:** schema change tickets pre-formatted for the engineering backlog, one ticket per recommendation above

---

## Roles

| Role | Owner | Key deliverables |
|------|-------|-----------------|
| **Builder** | TBD | Scout/Ranker/Investigator/Narrator agent code, Cognee wiring, CSV ingestion, UI backend, graph construction, post-detection workflow screen |
| **Designer** | TBD | Product Brief, UI screens 1–5, PDF brief layout, churn checklist interactive UI, post-detection status tracker |
| **Domain Expert** | TBD | Agent 4 narrative review, Geodo research (Liberty Reserve, SAR thresholds, FinCEN advisories, churn indicators), sign-off on regulatory language, Stage 3 SAR narrative review |
| **Presenter** | TBD | Demo script (above), Trupeer recording, stage slides |

---

## Pipeline Invariants

Non-negotiable. The pipeline fails judging if any are violated.

- [ ] Exactly 4 agents with genuine handoffs — not a single LLM in a loop
- [ ] Every agent reads from Cognee before acting and writes to Cognee after acting
- [ ] Agent N+1 demonstrably uses Agent N's Cognee output — **each agent logs the Cognee entity ID it read** (judging criterion 2 requires this to be traceable)
- [ ] Every agent decision has a logged, human-readable reason — `"the model said so"` disqualifies
- [ ] Agent 4 narrative is downloadable as a PDF from the product UI
- [ ] API keys loaded from `.env` only — never committed to the repo
- [ ] The 15 distractor accounts do NOT appear as ESCALATE or AUTO_FLAG in the final output
- [ ] The 5-Point AML Churn Checklist is pre-filled in every ESCALATE brief (items 1–4)

---

## Required Tools

| Tool | Purpose in RingFence | Status |
|------|---------------------|--------|
| **Cognee** (mandatory) | Shared memory graph across all 4 agents — `FraudFinding`, `RankedFinding`, `InvestigationAction`, `Loop` entities; stores churn signal data for pre-filling the checklist | [ ] 14-day Cloud trial activated |
| **DuckDB** (architecture) | In-process OLAP database — loads Crestline CSV at startup, runs all circular flow / velocity / clustering queries; no server required | [ ] Added via `uv add duckdb` |
| **PyMC** (optional / Ranker + Compliance) | Bayesian MCMC/VI library — use for probabilistic scoring in Agent 2 (Ranker) and for posterior uncertainty estimates in Compliance Package rule threshold recommendations; replaces point-estimate scoring with credible intervals | [ ] Added via `uv add pymc` |
| **Trupeer** (mandatory) | Record the 5-minute AML analyst demo using the script in Step 5 | [ ] 14-day trial activated, recording done |
| **Geodo** (mandatory) | Domain Expert researches: Liberty Reserve, FinCEN SAR advisories, off-hours timing, coordinated opening, fee-absorption as AML indicator | [ ] 100 credits allocated, research complete |
| **Kaggle** (optional / bonus) | Crestline Community Bank dataset — judges verify against hidden answer key for ring accounts, loop paths, $161,751 exposure | [ ] Dataset downloaded to `data/` (gitignored) |
| **Lingcode.dev** (recommended) | IDE with Claude Code, Codex, and Gemini CLI — use for agent prompt iteration and graph debugging | [ ] Configured |

---

## Repo Structure (target)

```
hackathon-jun7/
├── main.py                        # entrypoint — loads CSV into DuckDB, runs 4-agent pipeline
├── agents/
│   ├── scout.py                   # Agent 1 — graph construction, 5 detectors, churn signal logging
│   ├── ranker.py                  # Agent 2 — 5-dimension scoring + distractor filter
│   ├── investigator.py            # Agent 3 — cross-reference checks + action taxonomy
│   └── narrator.py                # Agent 4 — case brief, churn checklist, 4 team output packages
├── cognee_client.py               # Cognee read/write helpers (FraudFinding, RankedFinding, etc.)
├── db/
│   ├── schema.sql                 # DuckDB table definitions (transactions, accounts, devices, loops)
│   └── queries.py                 # Named queries: circular_flow_dfs, velocity_check, opening_cluster
├── graph_utils.py                 # DFS cycle detection, velocity analysis, opening-cluster detection
├── ontology.py                    # Entity classes matching the Data Ontology section
├── aml_checklist.py               # Pre-fill logic for the 5-Point AML Churn Checklist
├── outputs/
│   ├── aml_package.py             # AML behavior profile generator
│   ├── compliance_package.py      # Rule gap analysis + mitigation suggestions + PyMC threshold estimates
│   ├── dev_package.py             # Technical action items + schema recommendations generator
│   └── management_summary.py     # 1-paragraph executive summary generator
├── scoring/
│   └── bayesian_ranker.py         # Optional PyMC-based Ranker (MCMC/VI scoring with credible intervals)
├── ui/
│   ├── app.py                     # Streamlit app — 5 screens
│   └── templates/
│       ├── brief.html             # PDF brief template with interactive churn checklist
│       └── workflow.html          # Post-detection workflow tracker (Stage 1–6)
├── data/                          # gitignored — put Crestline CSV here
├── .env.example                   # API key template — commit this, not .env
├── pyproject.toml
└── README.md
```

---

## Submission Checklist

- [ ] Product Brief (Step 0) written, one page, matches what was built
- [ ] Scout correctly identifies all 6 circular loops, 5 structural signals, and logs churn signal data
- [ ] Ranker scores all 6 loops ≥ 89 and clears all 15 distractors below 50
- [ ] Investigator correctly ESCALATES all 6 loops and CLEARs all 15 distractors
- [ ] Narrator brief includes total exposure ≈ $161,751, all 6 loops, all hub accounts, and pre-filled churn checklist (items 1–4)
- [ ] Agent reasoning logged for 100% of decisions — auditable from the UI
- [ ] Agent 4 brief downloadable as PDF from the product UI (with filled churn checklist)
- [ ] All 4 team output packages downloadable from the Streamlit UI (AML, Compliance, DBA/Dev, Management)
- [ ] AML Package includes per-hub behavioral profile (plain-language, people-centered)
- [ ] Compliance Package includes rule gap analysis for all 5 churn signals
- [ ] DBA/Dev Package includes present-tense schema and index fixes
- [ ] Post-detection pipeline (Step 6) visible in the product UI as a workflow tracker
- [ ] Data ontology built at ingestion and stored in both DuckDB and Cognee
- [ ] Merchant Category Code field confirmed present/absent in Crestline CSV — README updated accordingly
- [ ] Geodo research complete — Liberty Reserve, SAR thresholds, off-hours timing, fee absorption
- [ ] Trupeer demo video recorded (≤ 5 min) using the AML analyst demo script
- [ ] Devpost submission submitted by **5:00 PM hard deadline (June 7, 2026)**
