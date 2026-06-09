<!-- ░░░ HERO ░░░ -->
<p align="center">
  <img src="docs/diagrams/hero.png" alt="Quorum — Calibrated AML Triage" width="100%">
</p>

<h1 align="center">Quorum</h1>

<p align="center">
  <b>Calibrated anti-money-laundering triage.</b><br/>
  <i>Five agents. One shared memory. A real Bayesian brain — and the math behind every call.</i>
</p>

<p align="center">
  <img alt="agents" src="https://img.shields.io/badge/agents-5_with_real_handoffs-5fd0e0?style=flat-square&labelColor=0a0c11">
  <img alt="brain" src="https://img.shields.io/badge/brain-PyMC_·_NUTS_mixture-8ab4ff?style=flat-square&labelColor=0a0c11">
  <img alt="memory" src="https://img.shields.io/badge/memory-Cognee_knowledge_graph-34d6a4?style=flat-square&labelColor=0a0c11">
  <img alt="grounding" src="https://img.shields.io/badge/grounding-geodo.ai_MCP-f7b733?style=flat-square&labelColor=0a0c11">
  <img alt="runtime" src="https://img.shields.io/badge/runs-offline_·_no_keys-ff5468?style=flat-square&labelColor=0a0c11">
</p>

<!-- Once your app is live, replace the link below with your https://<name>.streamlit.app URL -->
<p align="center">
  <a href="https://share.streamlit.io/deploy?repository=Alred-79/nycTechWeekHack&branch=main&mainModule=ui/app.py">
    <img src="https://static.streamlit.io/badges/streamlit_badge_black_white.svg" alt="Open in Streamlit">
  </a>
</p>

---

## The problem, in one breath

Every year an estimated **\$800B–\$2T** is washed through the banking system — ~**2–5% of world GDP** — and **less than 1%** is ever caught. The hard cases don't look like crime. They look like **boredom**: dozens of fresh accounts moving money *just under* every reporting threshold, fanning it through relays, pooling it in a quiet sink. Rules engines drown the analyst in false positives and still miss the ring. The analyst has **three minutes a case**.

**Quorum finds the ring, refuses to guess on the one genuinely ambiguous account, ignores the planted decoy — and shows its arithmetic for every decision.**

<!-- ░░░ THE HAYSTACK ░░░ -->
<p align="center">
  <img src="docs/diagrams/constellation2.png" alt="5,000 transactions — the ring hidden in the noise" width="100%">
</p>
<p align="center"><sub><b>The haystack.</b> 5,000 transactions · 294 accounts. The dim cloud is normal banking; the red chains are the laundering ring — money-flow edges lit. Fully interactive: open <code>ui/quorum_constellation.html</code> in any browser (no server, no internet).</sub></p>

<!-- ░░░ THE NEEDLE ░░░ -->
<p align="center">
  <img src="docs/diagrams/constellation1.png" alt="Zoom to the ring — AC-0005 escalated at 99.5%" width="100%">
</p>
<p align="center"><sub><b>The needle.</b> Click any node and the case opens inline — role, posterior, dollars, signals fired. Here the source pumps <b>\$53,896</b> across 83 transfers into two relays at <b>p = 99.5%</b>.</sub></p>

---

## Architecture — a real pipeline, not one LLM in a loop

Five specialist agents in a **Find → Rank → Act → Ground → Explain** relay. They never call each other — every handoff goes **through Cognee**: each agent *accretes* fields onto a shared `Case` node, and **the next agent refuses to run if the upstream fields are missing.** Collaboration is a hard data dependency, not a vibe.

```mermaid
flowchart TB
    CSV[("Crestline CSV<br/>5k txns · ~300 accounts")] --> DB["DuckDB<br/>in-process SQL"]
    DB --> COG

    subgraph COG["🧠 COGNEE — shared memory · fields accrete agent-by-agent"]
        direction LR
        CASE["Case::AC-####<br/><i>one node per account</i>"]
        MKT["MarketContext::RING<br/><i>geodo.ai-grounded entity</i>"]
    end

    GEO["🌐 geodo.ai MCP<br/>live GTM + market intel"]

    A1["1 · DETECTOR — FIND<br/>structural graph · roles · 7 signals<br/><b>writes</b> signals, dist_stats"]
    A2["2 · ESTIMATOR — RANK<br/>PyMC 2-component mixture · NUTS<br/><b>writes</b> p_mule, credible_interval"]
    A3["3 · ADJUDICATOR — ACT<br/>Bayesian decision theory · τ, EVPI<br/><b>writes</b> action, decisive_signals"]
    A4["4 · DOMAIN EXPERT — GROUND<br/>queries geodo.ai + FinCEN/OCC<br/><b>writes</b> MarketContext"]
    A5["5 · REPORTER — EXPLAIN<br/>$ reconciliation · SAR memo · closing rule<br/><b>writes</b> typology, memo_ref"]

    COG --> A1 --> COG
    COG --> A2 --> COG
    COG --> A3 --> COG
    COG --> A4 --> COG
    COG --> A5 --> COG
    GEO -.-> A4

    A5 --> OUT["📄 SAR memo · $161,750.90 reconciled<br/>+ learned closing rule"]

    GATE["⛔ each agent RAISES if upstream<br/>fields are missing — the handoff is<br/>a provable data dependency"]
    A2 -.-> GATE

    classDef cog fill:#0f2a2e,stroke:#5fd0e0,color:#e7ebf3;
    classDef agent fill:#141923,stroke:#8ab4ff,color:#e7ebf3;
    classDef geo fill:#1a2233,stroke:#5fd0e0,color:#5fd0e0;
    classDef out fill:#0f2620,stroke:#34d6a4,color:#e7ebf3;
    classDef gate fill:#2a1418,stroke:#ff5468,color:#ffd0d6;
    class CASE,MKT cog;
    class A1,A2,A3,A4,A5 agent;
    class GEO geo;
    class OUT out;
    class GATE gate;
```

<!-- ░░░ THE PAYOFF ░░░ -->
<p align="center">
  <img src="docs/diagrams/dashboard.png" alt="The product — KPIs and a fully-reasoned case dossier" width="100%">
</p>
<p align="center"><sub>~300 accounts → a queue of 14 in under a second. Every verdict carries its posterior, its expected-loss ledger (<b>argmin decides</b>), its signed signal contributions, and a decision log. No bare score anywhere.</sub></p>

---

## Three pillars

### 🧠 PyMC — a probabilistic brain, not a scorecard

The data has **no labels**, so the Estimator doesn't classify — it *infers*. It posits two latent classes (**legit** vs **mule**), each with its own vector of signal fire-rates `φ`, and lets **PyMC's NUTS sampler (`nutpie`, 4 chains)** learn the rates, the mixing weight, and every account's posterior probability of being a mule — with an honest credible interval.

<p align="center">
  <img src="docs/diagrams/pymc-estimator.png" alt="The masked two-component Bayesian mixture" width="74%">
</p>

Three pieces of real Bayesian engineering — each is why a demo moment lands:

- **`logsumexp` marginalizes the hidden class analytically.** NUTS can't sample discrete latents, so the class is integrated out in log-space and fed to `pm.Potential` as an exact marginal log-likelihood — the textbook-correct way to fit a mixture under HMC (R-hat + divergences checked every run).
- **A masked likelihood: missing ≠ innocent.** A pure *sink* physically cannot fire `automation` or `fresh_cohort`; an applicability mask `M` zeroes those out so they count as **missing data, not evidence of innocence**. That's why sinks stay confident *and* why the lone ambiguous account comes back honestly uncertain with a wide, τ-straddling interval.
- **A skeptical decoy prior.** `device_shared` gets the **same weak prior in both classes** — identity co-occurrence is non-discriminating *by construction*, so the planted decoy can't be driven to a flag. Decoy resistance is a property of the model, not an `if` statement.

The Adjudicator turns that posterior into a **cost-optimal action** — never a bare threshold:

```
τ = C_FP / (C_FP + C_FN) = 250 / (250 + 4750) = 0.05
abstain → REVIEW  ⟺  the 94% interval straddles τ  AND  EVPI > review cost
```

Every signal is **learned from the data**, not hardcoded — and the Detector's three independent fingerprints all isolate the *same* ring:

<p align="center">
  <img src="docs/diagrams/fingerprints.png" alt="Three learned fingerprints — automation, burst cohort, structuring" width="100%">
</p>

### 🕸️ Cognee — the memory that makes the collaboration real

Two layers: an **operational handoff store** where one `Case` node accretes fields agent-by-agent (and a downstream agent throws if the upstream fields are absent), and a **semantic knowledge graph** where every agent contributes a tagged layer and a single `cognify()` builds a Gemini-backed graph carrying full multi-agent provenance — queryable in plain English. It degrades gracefully to the fast local store with no key, so the pipeline is never blocked.

```mermaid
flowchart LR
    subgraph L1["LAYER 1 · operational handoff store — one Case node accretes fields"]
        direction TB
        C0["Case::AC-0009"]
        C1["+ signals<br/>+ dist_stats"]
        C2["+ p_mule<br/>+ credible_interval"]
        C3["+ action<br/>+ EVPI · decisive_signals"]
        C4["+ typology<br/>+ closing_rule · memo_ref"]
        C0 -->|Detector| C1 -->|Estimator| C2 -->|Adjudicator| C3 -->|Reporter| C4
        MC["MarketContext::RING<br/><i>2nd entity — Domain Expert</i>"]
        MC -. "read by Reporter" .-> C4
    end

    GATE["⛔ Estimator RAISES if signals absent ·<br/>Adjudicator RAISES if p_mule absent<br/><b>handoff = enforced data dependency</b>"]
    C1 -.-> GATE

    subgraph L2["LAYER 2 · semantic knowledge graph"]
        direction TB
        ADD["each agent → add(node_set=<br/>['quorum','agent:detector', …])"]
        CG["cognify() — one Gemini-backed<br/>graph build with full provenance"]
        Q["natural-language search<br/><i>'which accounts are relays?'</i>"]
        ADD --> CG --> Q
    end

    C4 ==> ADD

    classDef case fill:#0f2a2e,stroke:#34d6a4,color:#e7ebf3;
    classDef mc fill:#1f1430,stroke:#b48aff,color:#e7ebf3;
    classDef kg fill:#141923,stroke:#5fd0e0,color:#e7ebf3;
    classDef gate fill:#2a1418,stroke:#ff5468,color:#ffd0d6;
    class C0,C1,C2,C3,C4 case;
    class MC mc;
    class ADD,CG,Q kg;
    class GATE gate;
```

### 🌐 Geodo — grounding the verdict in the real market

The **Domain Expert (Agent 5)** reads the ring's `decisive_signals` and queries the live **[geodo.ai](https://geodo.ai) MCP** through a hard safety gate — read-only tools only, outreach permanently blocked. It pulls the segment, personas and labor-cost rate that source the cost matrix, then matches the ring to a **real, dated SAR-failure enforcement action** against a peer institution. One verified fact powers both the SAR memo and the business case, written into Cognee as `MarketContext`.

```mermaid
flowchart TB
    RING["Adjudicated ring<br/>decisive_signals"] --> DE["Domain Expert · Agent 5"]
    DE --> GC["geo_client — safety gate"]
    GC --> AL["ALLOWLIST<br/>read-only · cached"]
    GC -. "outreach — NEVER" .-> DN["DENYLIST<br/>blocked"]
    AL --> MCP["🌐 geodo.ai MCP"]
    MCP --> R1["GTM Researcher<br/>ICP · personas · $50–80/hr rate"]
    REG["verified FinCEN / OCC<br/>enforcement registry"] --> MATCH["match by signal_tags"]
    DE --> MATCH
    MATCH --> WHY["the 'why now'<br/>a peer penalised for THIS failure"]
    R1 --> MKT["MarketContext<br/>segment · buyer_thesis · ROI"]
    WHY --> MKT
    MKT ==> COG["Cognee entity"] ==> REP["Reporter → SAR memo + business case"]

    classDef de fill:#1f1430,stroke:#b48aff,color:#e7ebf3;
    classDef geo fill:#1a2233,stroke:#5fd0e0,color:#5fd0e0;
    classDef reg fill:#2a2414,stroke:#f7b733,color:#f7e0a0;
    classDef block fill:#2a1418,stroke:#ff5468,color:#ffd0d6;
    classDef out fill:#0f2620,stroke:#34d6a4,color:#e7ebf3;
    class DE,GC de;
    class AL,MCP,R1 geo;
    class REG,MATCH,WHY reg;
    class DN block;
    class MKT,COG,REP out;
```

<p align="center">
  <img src="docs/diagrams/geodoAI.png" alt="geodo.ai Digital Twin — grounding and MCP tool calls" width="100%">
</p>

---

## Stack & run

**Python 3.14 · `uv`** — `DuckDB` (in-process SQL) · **`PyMC` + `nutpie` + `ArviZ`** (the mixture & diagnostics) · **`Cognee`** (shared memory + cognified graph) · **`geodo.ai` MCP** (market grounding) · **`Streamlit`** (the analyst product).

```bash
uv sync
uv run streamlit run ui/app.py                 # the product — opens straight into the demo
uv run main.py data/track02_fraud_watch.csv    # the raw 5-agent pipeline, reasoning logged
```

External layers are **bring-your-own-key and degrade gracefully** — with no Gemini or geodo.ai key the pipeline still runs end-to-end from the committed snapshot and caches. Keys never touch the repo.

---

<p align="center">
  <b>Every other tool ranks risk — and most just flag the decoy.</b><br/>
  Quorum surfaces the nine, refuses to guess on the tenth, ignores the trap, and shows you the math behind every call.
</p>
