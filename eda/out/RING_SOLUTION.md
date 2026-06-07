# Track 02 — Fraud Watch: the ring (EDA conclusion)

**Dataset:** Crestline Community Bank — 5,000 txns, 294 accounts, 90 days
(2026-03-03 → 2026-06-01). Columns: `txn_id, account_id, counterparty_id,
amount, timestamp, merchant_category, device_id, ip_region, account_open_date`.
No nulls. Hint: ~12-account ring, exposure ≈ $161,751, no single alert tripped.

## The smoking gun

Normal transactions pay **merchants** (`MR-####`, 4,750 txns). The ring does
**account-to-account internal transfers** (`counterparty_id` is an `AC-####`,
250 txns). Those 250 internal transfers total **$161,750.90** — matching the
$161,751 hint to the dollar.

Two independent fingerprints isolate the same 250 txns:
1. **Counterparty is an `AC-` account**, not an `MR-` merchant.
2. **Timestamp second == `:00`** — all 250 ring txns land exactly on `:00`
   seconds (synthetic injection marker). Only ~1.7% would be `:00` by chance.

## Why no alert fired

Per-transfer amounts average ~$640 and never approach the $10,000 CTR /
structuring line — there are **zero** "just-under-threshold" txns in
[900,1000], [2700,3000], [4500,5000]. The ring hides in volume, not size:
many small transfers, repeated 41–42 times per edge over the 90 days.

## Ring membership & money flow

9 distinct accounts (hint said "~12"), 6 directed edges:

| sender   | →  | receiver | total      | txns |
|----------|----|----------|-----------:|-----:|
| AC-0001  | →  | AC-0002  | $26,985.76 | 42 |
| AC-0005  | →  | AC-0006  | $27,736.13 | 42 |
| AC-0005  | →  | AC-0009  | $26,160.09 | 41 |
| AC-0009  | →  | AC-0007  | $29,120.71 | 42 |
| AC-0010  | →  | AC-0011  | $26,819.97 | 42 |
| AC-0011  | →  | AC-0003  | $24,928.24 | 41 |

Ring accounts: **AC-0001, AC-0002, AC-0003, AC-0005, AC-0006, AC-0007,
AC-0009, AC-0010, AC-0011**. Note layering chains (AC-0005→AC-0009→AC-0007;
AC-0010→AC-0011→AC-0003). All ring accounts were opened in a tight
2026-02-10 → 2026-02-18 window (burst-created mules), each single-device /
single-region.

## Signals for the agent pipeline (Find → Rank → Act → Explain)

- **Find (Agent 1):** flag txns where `counterparty_id` starts with `AC-`
  (internal transfer) and/or `timestamp.second == 0`.
- **Rank (Agent 2):** score accounts by internal-transfer $ concentration,
  counterparty concentration (`n_cp <= 3` at high volume), and account-open
  burst clustering.
- **Act (Agent 3):** freeze/flag the 9 accounts; trace layering chains.
- **Explain (Agent 4):** narrate the chain + the "$161,751 across 250
  sub-threshold internal transfers" story.

## Dead ends (documented so we don't re-chase)

- **Shared devices:** only 2 devices shared across accounts (~$3k) — NOT the
  ring. Ring accounts each use a single distinct device.
- **Just-under-threshold structuring:** none present; ring evades via volume.
