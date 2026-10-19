# Phase 5 Readiness Report — Period A started (2026-10-19 00:10:06 UTC)

Experiment: PHASE5_LEADLAG_EXPERIMENT_PLAN.md. **Config hash `3a252d79dd5e1da1`** (frozen at
start, stamped into `data_cache/leadlag_state.json` and every signal record; the engine refuses
to run under any other hash). Paper only — no order path exists anywhere in the code.

## Gate results (`backend/_phase5_readiness.py`, run on EC2 before start)

| gate | result | evidence |
|---|---|---|
| R1 scanner untouched | **PASS** | `oo_feed.py` / `oo_scan.py` byte-identical to git HEAD |
| R2 simulator | **PASS** | 13/13 edge cases (`_phase5_sim_tests.py`): stale quote, missed update, suspension gap, partial fill, no liquidity, worse price, mapping error, in-play, size-unknown; fee+slippage arithmetic asserted. Caught one real bug pre-start (NaN price fell through to a fill). |
| R3 production-feed timestamps | INFO (documented limitation) | 60s pipeline re-price receive lag: Pinnacle median minutes-to-hours (fixture-entry + cadence aliasing) vs Kalshi ~20s. EC2 clock 66 ns off NTP. Venue stamp skew ~4.4% of re-prices, p95 ≤7s — can only turn fills into misses; price check is the backstop. |
| R4 coverage | **PASS** | 201–265 fixtures with Pinnacle + an exchange; ~19–22 qualifying moves/day at the frozen 3pp definition |
| R5 venue probes | INFO | Kalshi public API 3/3, ~11–14 ms RTT; Polymarket verified via the CLOB `/book` path the paper auto-bettor already uses |
| R6 pre-start refusal | **PASS** | `run()` records nothing before Period A is started |
| R7 burst verification | **PASS** | availability probe (`reports/phase5/probe_1792365461.jsonl`, 192 clean 3 s cycles): **Pinnacle re-prices readable median 1.8 s / max 2.9 s after their own stamp** (n=22 born in-probe), vs measured venue follow latency 3.5–6.4 s; live smoke run 16/16 cycles |

## Why burst mode is the observation plane (not an optimisation)

A 3-day dry run of the frozen fill rule over the 60-second snapshots produced **zero full
fills** — 65% of signals died as `missed_adjusted`, because the exchanges' stale window is
3–6 s wide and a 65 s cadence cannot observe it. The fill rule was **not** weakened; the
approved, separately-verified burst poller (3 s cadence, 8 nearest fixtures, ~20 calls/min vs
the provider's 8,000/min cap, 10 s socket timeouts after the probe exposed a hang on a dead
connection) supplies the observation density instead. Signal definitions, fees (Kalshi
7·p·(1−p) pp, Polymarket 5·p·(1−p) pp), slippage (1 pp), stake ($25), and all success criteria
are exactly as pre-registered.

## Timestamp discipline (approval item 4)

Every signal record carries, separately and never invented: the venue's own stamp on the moving
Pinnacle quote (`src_move_ts`), when our poller first read it (`recv_ts`), the simulated decision
time (`recv + 3 s`), the first exchange observation at/after decision (`fill_obs_ts`), the
exchange quote's own stamp and age, and a reason string for every miss
(`missed_adjusted / missed_gap / missed_no_market / missed_worse_price / missed_no_liquidity /
mapping_error / skipped_inplay`). Raw burst quotes persist to
`data_cache/leadlag_burst/stream_*.parquet` so every fill is independently reconstructible.

## Limitations on record (reported, not worked around)

1. League coverage is `atp / atp_challenger / itf_men` — WTA is not in the existing scanner's
   league list and adding it would modify the scanner, which is out of scope during Period A.
2. The timing chain is razor-thin by design (~2 s availability + 3 s budget vs ~5.1/6.4 s venue
   follow): a low fill rate is an expected measurement, not a failure.
3. Period A ends at ≥200 valid fills; **Period B is the following window of equal duration**,
   untouched, and must confirm independently before any real-money discussion.
4. The Oct 31 Phase 3 lane checkpoint is independent of this experiment and closes under its
   original rules.
