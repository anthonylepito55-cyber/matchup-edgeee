# OPP1 Phase-0 Coverage Report (2026-10-19) — GATES FAILED, STOPPED

Run `20261019T004731Z` under spec v2 §6. **1,444 API calls, 1,911 credits** (budget 25,000;
ceiling untouched; remaining at end 12,671,594 per the API's own headers). Every request, raw
response, parameter set, timestamp and usage header retained immutably in
`backend/data_cache/theoddsapi_hist/phase0/20261019T004731Z/` (`raw/` + `ledger.jsonl` +
`weekly.csv`, `events.csv`, `pinnacle_sample.csv`, `phase0_summary.json`). No model fitted, no
feature computed, no outcome inspected, Phase 5 untouched (run entirely on the local machine).

One probe correction is itself part of the record: `/v4/historical/sports` does not exist
(404, zero-cost — first run retained); the census was rebuilt on `/historical/sports/{key}/events`
(1 credit/call), which is why the evidence now includes exact event commence-times.

## Gate results (preregistered denominators)

| gate | numerator / denominator | result | threshold | verdict |
|---|---|---|---|---|
| weekly coverage **2025** | 21 / 51 weeks (weeks with ≥20 completed tour+challenger matches in the TennisRatio reference that have ≥1 vendor snapshot with ≥2 books) | **41.2%** | ≥60% | **FAIL** |
| weekly coverage **2026** | 27 / 41 | 65.9% | ≥60% | pass |
| weekly coverage 2024H2 | 7 / 26 | 26.9% | informational | — |
| Pinnacle presence (T\*−45 min, stratified 36 events across 5 half-years) | two-way quote 33/36; **fresh (≤24 h) 33/36** | **91.7%** | ≥70% tour | pass (where covered) |
| match mapping to our frozen log | 27 unique + 7 ambiguous of **1,267** settled tour+challenger log rows in covered weeks | **≈2.7% (lower bound)** | ≥70% | **FAIL as specified** |
| cost | 1,911 of 25,000 | — | abort ceilings | pass |

## Why it failed — the structural finding

The vendor's tennis universe is **48 per-tournament keys covering premier events only** — Slams,
Masters/1000s, premier 500s (top keys by events: WTA/ATP US Open, Australian Open, Cincinnati,
Italian Open…). **No challenger keys, no ITF keys exist in the catalog.** Consequences:

- Weeks are covered only when a premier tournament is running → 2025 coverage 41%.
- Our frozen log's population is challenger/ITF-heavy → of 1,267 log rows in covered weeks, almost
  none occur at vendor-covered tournaments. The 2.7% is a lower bound (one snapshot/week
  undersamples), but no sampling density fixes a universe mismatch: the vendor cannot map to the
  board's slate.
- Where the vendor **does** cover, quality is excellent: ~5-min grid (verified 10-11 and again in
  this run's snapshots), Pinnacle two-way and fresh in 92% of T\*-window samples across all five
  half-years, zero sample errors, and history runs 2024-07 → now (events confirmed in every month
  probed).

Missingness categories (all counted in the CSVs): 63/120 weeks no tennis key; 1/57 covered weeks
returned a snapshot with <2 books; 3/36 Pinnacle samples lacked a two-way quote; 0 API failures
after retries.

## Verdict and options (decision is yours — nothing proceeds)

Per safeguard 10 and spec v2: **the experiment as designed — market-path features on OUR log
population — cannot be powered by this vendor. Stopped.** The six feature families, the
statistical protocol, T\* rules, and Tier-2 freezing commitments remain frozen and unused.

Options, strictly for your review (none started):

1. **Re-scope the study population to premier-tour matches only** (the vendor's actual universe).
   A legitimate but *different* question — "does the market path add information at
   Slams/Masters?" — with an estimated few thousand matches over 2024-07→now (A: exact count
   needs the full pull), i.e. the spec's 8,000-match dev minimum likely **cannot** be met and
   would need a preregistered power revision (spec v3 for your review, not a quiet relaxation).
2. **A different history vendor** for challenger/ITF-tier odds (research task; none verified).
3. **Grow our own grid**: the OpticOdds snapshot store has been accruing ~60s-resolution quotes
   on exactly our population since 2026-10-11 (plus the Phase-5 3s burst stream on tennis).
   In ~3–6 months it supports the same experiment on the right population with no vendor risk —
   at the cost of waiting.

Safeguard confirmations: Period A state, services, scanner, model rules, lanes, and the Oct 31
checkpoint are untouched (this run never contacted the EC2 box); features/protocol unchanged;
no development split was instantiated because no development data exists to split.
