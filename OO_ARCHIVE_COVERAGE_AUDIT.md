# OpticOdds Quote-Archive Coverage Audit (2026-10-19) — read-only

**Question:** can our own accumulated quote store eventually power the preregistered OPP1
market-path experiment on our *actual* population (challenger/ITF included)?
**Short answer: yes for the men's slate, with four named blockers — the largest being that WTA
and ITF-women are absent from the feed entirely, and F4 is not computable as specified.**

Strictly read-only: no API calls, no credits, no collection changes; Phase 5 state/services,
the Oct 31 checkpoint, frozen lanes and spec v2 untouched. Outputs written to a **new**
directory only. This report is **not committed** (per instruction).

## Files inspected (read-only) and methodology

- `backend/data_cache/oo_snapshots/2026-10-11.parquet … 2026-10-19.parquet` (9 daily files; the
  60s scanner's store; 3,085,458 rows total, **1,107,409 tennis moneyline quote-rows**)
- `backend/data_cache/leadlag_burst/stream_2026-10-19.parquet` (Phase 5's 3s stream — audited
  separately, not mixed in)
- `backend/data_cache/tennisratio/all_match_logs.parquet` (denominator reference)
- `backend/data_cache/tennis_prediction_log.parquet` (linkage/outcome reference)
- Auditor: `backend/_oo_archive_audit.py`; evidence tables in
  `backend/data_cache/oo_archive_audit/` (mirrored to `reports/oo_archive_audit/`:
  `audit_summary.json`, `daily_fixtures.csv`, `fixtures.csv` — 942 per-fixture assessments).
  Method: per-fixture aggregation of both-sidedness, book composition, quotes inside the OPP1
  T\* window `[start−6h, start−30min]`, first-seen depth, re-price receive lag (first-appearance
  of each new venue `quote_ts`), null-timestamp rates, and direct `fixture_id` linkage to the
  frozen log.

## 1. Actual retained span and volume (no extrapolation from row counts)

- **Span: 9 consecutive days, 2026-10-11 → 2026-10-19, no missing days**; one poll outage of
  ~15 min (max poll gap 902s against a 65s median cadence).
- Unique fixtures per day by league (from `daily_fixtures.csv`): ATP 5–59/day,
  challenger 35–145/day, ITF-men 3–222/day — tournament-cycle shaped, 3 calendar weeks spanned.

| league | unique fixtures (9d) | tournament-weeks | reference matches same span (TR archive) |
|---|---|---|---|
| atp | 96 | 3 | ~36* |
| atp_challenger | 415 | 3 | ~378* |
| itf_men | 431 | 3 | ~317* (archive "futures" mixes genders) |
| **wta / itf_women** | **0 — league not in the feed config** | — | ~71* WTA |

\* denominator caveat: the TR archive is player-pool-limited (1,760 ingested players) and its
level labels are coarse, so these are approximate references; apparent >100% coverage on
challengers reflects archive undercounting, not phantom fixtures.

## 2. Quote quality inside the store

| metric | atp | challenger | itf_men |
|---|---|---|---|
| both sides quoted (any book) | 100% | 99.8% | 100% |
| Pinnacle two-sided (any time) | 93.8% | 85.8% | 85.6% |
| exchange two-sided | 100% | 98.1% | 98.8% |
| **any quote in the T\* window** | 83.3% | 81.9% | 98.4% |
| **Pinnacle two-sided in the T\* window** | **65.6%** | **67.7%** | **81.4%** |
| exchange present in T\* window | 83.3% | 81.9% | 96.3% |
| median polls inside the T\* window | 276 | 211 | 200 |
| median first-seen before start | 18.7 h | 18.2 h | 15.0 h |
| median Pinnacle re-prices pre-match | 14 | 9 | 8 |
| null `quote_ts` rate | 0.0% | 0.0% | 0.0% |
| linked to frozen log (`fixture_id`) | 92.7% | 79.5% | **18.6%** |
| settled outcome in log | 60.4% | 63.4% | **17.9%** |

- **Timestamp completeness is perfect** (0 null venue stamps on 1.1M rows).
- **Freshness** (re-price receive lag, medians): exchanges 20–63s (Kalshi 20.1s n=682k, Betfair
  22.7s, Polymarket 63.3s), Novig 133s, BetOnline 719s, **Pinnacle 1,514s**, Circa ~3.3h — the
  known 60s-feed sharp-lag. **For OPP1 this is acceptable**: the experiment's features are the
  *stored path at T\*−30min*, not second-level reaction (that is Phase 5's separate job).
- Burst stream (since Period A start): 992 rows / 8 fixtures at a verified 3.0s cadence — kept
  separate; not needed by OPP1.

## 3. F1–F6 computability at the preregistered T\* (available now vs needs future collection)

**695 fixtures already have a Pinnacle two-sided quote inside the T\* window; 337 of those have a
settled outcome via the log.** Median stored history depth 15.8h pre-start; 95.6% of fixtures
carry ≥2h of history.

| feature | status now |
|---|---|
| F1 open→T\* drift | **computable** — with "open" = first *stored* quote (fixtures enter the poll set ≤48h pre-start; a true market-open earlier than that is not retained — definitional constraint, not a gap in the store) |
| F2 last-2h velocity | **computable** (95.6% of fixtures have ≥2h depth) |
| F3 cross-book dispersion | **limited**: 7 books stored (Pinnacle, BetOnline, Circa + 4 exchanges); the retail group (FanDuel/DraftKings/bet365) is defined in the feed config but **not polled** |
| F4 sharp-vs-soft gap | **NOT computable as specified** — no soft/retail books in the store. The available analogue is sharp-vs-exchange gap. A substitution is a **spec v3 decision for you**, not something this audit changes |
| F5 path extremes | **computable** within the 48h window |
| F6 overround trend | **computable** (two-sided quotes throughout) |

**Needs future collection (not available now):** WTA + ITF-women quotes (one feed-config league
addition — deferred while Period A freezes scanner scope); retail books if F4 is to stay as
specified (adds a third book-group per poll); wider outcome linkage for ITF-men (only 18.6% reach
the board log — outcomes for the rest would come from the TennisExplorer name+date settler, a
processing task, not new quote collection).

## 4. Throughput and the path to OPP1 power (projection, labelled as such)

Measured usable throughput (Pinnacle-two-sided at T\* **and** settled outcome): **337 fixtures /
9 days ≈ 37/day ≈ 1,100/month**, men-only, current linkage. Against spec v2's dev minimum
(8,000 effective matches): **≈7 months at current scope**. With the two future-collection items
(WTA/ITF-W roughly doubling the slate; TE-settler linkage lifting ITF-men from ~18% toward the
challenger ~80%), the horizon compresses to **≈3–4 months** — consistent with the earlier
estimate, now grounded in measured per-day fixture counts rather than record totals.

## 5. Blockers and limitations (honest list)

1. **WTA and ITF-women do not exist in the store** — half the OPP1 target population requires a
   feed-config change that is frozen until Period A allows it.
2. **F4 as preregistered is not computable** from this store (no retail books). Requires either
   adding the retail group to collection or a spec v3 substitution — your call.
3. **ITF-men outcome linkage is 18.6%** via the board log; fixing it is a settlement-processing
   task (TE matcher), already proven elsewhere in the project but not built for this store.
4. **Only 9 days retained** — every number above is early; tournament-cycle composition shifts
   week to week (visible in the daily table). No seasonal claim is possible yet.
5. Denominators from the TR archive are approximate (player-pool-limited, coarse levels).
6. One ~15-minute poll outage exists in the span; it affects cadence tails, not validity.

No predictive performance was calculated or inspected; no features were built; no thresholds
touched. Spec v2 remains frozen; any change (e.g. F4 substitution) belongs to a separately
versioned spec.
