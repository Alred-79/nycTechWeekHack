# cogneev2 — Option 1: make Cognee the inter-agent bus (structured DataPoints)

**Status:** future work. The shipped design is **Option 2** (see [cognee_client.py](cognee_client.py)):
each of the four agents writes a tagged layer to Cognee via `add()` during the run,
and a single `cognify()` unifies them into the knowledge graph
([cognee_graph.json](cognee_graph.json) is persisted for the UI). That makes
*writes* genuinely multi-agent and Cognee load-bearing for the graph.

What Option 2 does **not** do: the exact, per-field **reads** between agents still
go through the fast local store (`_LocalStore`) — Agent 3 reads `p_mule` from the
JSON store, not from Cognee. Option 1 closes that last gap: the `Case` becomes a
**typed Cognee entity** that each agent reads and writes directly, so the handoff
is literally "Agent N+1 reads Agent N's Cognee record."

## Why this is harder (and why it's deferred)
- Cognee's fast retrieval path is **semantic** (`search`) and requires `cognify`,
  which is slow on the Gemini free tier (~1–20 min). Doing it between every agent
  is infeasible. Option 1 therefore needs Cognee's **structured/graph data API**
  (exact node fetch by id), not `search`.
- The pipeline needs **deterministic, exact** reads (the decision math and the 42
  gates depend on it). Any Cognee read path must return the exact stored fields,
  reproducibly — no LLM in the read loop.

## The design — typed `DataPoint`, exact get/update by id

Cognee 1.x supports typed entities via `cognee.low_level.DataPoint` (Pydantic).
Model the `Case` as a DataPoint and use the graph engine for exact reads/writes,
keeping `cognify`/`search` only for the analyst-facing semantic layer.

```python
from cognee.low_level import DataPoint
from cognee.infrastructure.databases.graph import get_graph_engine

class CaseDP(DataPoint):
    account: str
    role: str | None = None
    signals: dict = {}
    p_mule: float | None = None
    credible_interval: list | None = None
    action: str | None = None
    # … the rest of the Case fields …
    metadata: dict = {"index_fields": ["account"]}   # exact lookup key

async def write_case_dp(case: CaseDP):
    engine = await get_graph_engine()
    await engine.add_node(case)              # upsert by id (deterministic)

async def read_case_dp(account: str) -> dict:
    engine = await get_graph_engine()
    node = await engine.get_node(f"Case::{account}")   # exact fetch, no LLM
    return node
```

Then each agent's `cognee_client` calls (`write_case`, `read_case`,
`update_case_fields`) route to `write_case_dp` / `read_case_dp` instead of the
JSON `_LocalStore`. The handoff is now end-to-end through Cognee.

## Migration plan (incremental, keeps gates green)
1. Add the `CaseDP` DataPoint + async get/update helpers behind a flag
   (`QUORUM_COGNEE_BUS=1`), defaulting **off** so the JSON store (and the 42
   tests) keep working unchanged.
2. Make `cognee_client.write_case/read_case/update_case_fields` dispatch to the
   DataPoint backend when the flag is on, JSON otherwise — identical interface,
   so the agents don't change.
3. Wrap the async calls so the synchronous agent code is unaffected (a small
   `asyncio.run` shim, or run the whole pipeline in one event loop).
4. Keep `cognify()` + `search()` as the analyst semantic layer (Option 2),
   now reading the same graph the agents wrote to.
5. Re-run `uv run pytest -q` with the flag on; the handoff test
   ([tests/test_cognee_handoff.py](tests/test_cognee_handoff.py)) now proves
   accretion **inside Cognee**, not the JSON shim.

## Risks
- **Latency / event-loop管理:** exact graph reads are fast, but every agent step
  now awaits the graph engine; run the pipeline inside a single event loop rather
  than `asyncio.run` per call (binds DB connections to one loop).
- **Determinism:** the graph engine must return byte-identical fields; verify the
  decision math and reconciliation still hit $161,750.90 to the cent with the bus on.
- **Backend choice:** the default local graph (NetworkX/Kuzu) is fine for the demo;
  for scale, point Cognee at a persistent graph DB — but that's beyond the hackathon.

Until this lands, be precise in the pitch: *Option 2 — every agent writes its
findings into Cognee and the graph is built from all four; the deterministic
field-reads remain in-process for the decision math.*
