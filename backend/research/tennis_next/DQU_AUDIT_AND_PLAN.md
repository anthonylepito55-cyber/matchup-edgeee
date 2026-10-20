# Data Completeness & Prediction Uncertainty Engine — audit and proposed design

**Status: PROPOSAL. Nothing implemented, nothing deployed.** No change to the frozen
D_rest artifact, its coefficients, its probabilities, the official 16-week trial, or any
production prediction. Every number below was measured today against real data; where a
thing is unmeasured this document says so.

---

## PART 1 — AUDIT OF WHAT ALREADY EXISTS

### 1.1 The five flags in `tsm_beta.score_fixtures`

| flag | condition | fires on today's 165 live predictions |
|---|---|---|
| `archive_Nd_stale` | archive watermark older than `FRESH_DAYS = 3` | **0** |
| `missing_result_risk_N` | `tsm_proxy.fixture_unresolved` > 0 | **12** |
| `no_serve_return_data` | no Markov serve/return model, so Elo-only | **0** |
| `cold_start` | `min(prior_n1, prior_n2) < 5` | **0** |
| `calibrator_saturated` | isotonic output at the 1.0 / 0.0 knot | **0** |

`data_quality` is the OR of these: `NO_KNOWN_DATA_ISSUE` (153) or
`DATA-QUALITY-UNVERIFIED` (12).

The naming is already honest — it says *no problem was detected*, not *verified*. The
problem is not the wording. It is that **four of the five flags never fire**, so 93% of
predictions are stamped clean by a test that, in practice, only asks one question.

### 1.2 The measurement that matters: the archive is not complete when we predict

Two genuine archive snapshots exist on disk: a capture whose newest match is **2026-09-28**,
and production's current archive (2026-10-20, 1,760 players, 618,866 rows). Treating the
later one as ground truth gives the completeness of the earlier one *at its own watermark*:

| match age at capture | rows present / final | complete |
|---|---|---|
| 0 days | 1 / 223 | **0.4%** |
| 1 day | 13 / 165 | **7.9%** |
| 2 days | 68 / 149 | **45.6%** |
| 3 days | 97 / 194 | **50.0%** |
| 4 days | 193 / 278 | 69.4% |
| 5 days | 252 / 315 | 80.0% |
| 6+ days | — | ~100% |

2,887 rows dated before the watermark arrived afterwards. The curve holds across levels
(at 3 days: ATP 56%, WTA 50%, Challengers 40%, Futures 53%), so this is an ingest-latency
property, not a tour-coverage one.

**Consequence.** `archive_Nd_stale` compares the archive's *newest* row to today. The
nightly ingest keeps that watermark fresh, so the flag reads clean — while the last five
days of every player's history, the part the form features weigh most, is between 0% and
80% present. The one check aimed at recency is structurally blind to the thing it is
named after.

### 1.3 What `missing_result_risk` does and does not cover

`tsm_proxy.unresolved_recent` is sound and leak-free: it infers a *certain* missing result
from draw logic (a player whose last archived match was a non-final win is now entered
elsewhere, so the loss that ended that run is missing; or the old draw has advanced past
the player's last recorded round). It uses only rows dated `< prediction_date`.

Its limits, all structural:

- it detects **absence inferable from a knockout draw**, which is a subset of absence;
- it is silent for a player whose last archived match was a **loss** (the run ended
  correctly) even if later matches at a new event are missing;
- it is silent outside the 21-day `ACTIVE_WINDOW_DAYS`;
- it produces an **unbounded integer count**, consumed as `> 0`. A risk of 5 and a risk
  of 1 are the same flag.

### 1.4 Sample size is recorded but never used

Each record already carries `availability.stat_n_p1/p2` (serve/return rows) and
`prior_n_p1/p2` (Elo prior matches). Nothing reads them except the `< 5` cold-start test.
There is no surface-specific count, no effective sample size, no down-weighting, and no
distinction between 6 matches and 600 — both pass.

### 1.5 Nothing has ever been validated against outcomes

The beta has **0 settled matches**, so no flag has been tested against error or
calibration. `tsm_proxy_eval.py` validates the proxy against *later-arriving data*
(did the flagged rows really have missing results, and how far did probabilities move)
— that is detection accuracy, not error prediction. Requirements 10–12 are entirely
unmet today, and cannot be met from the beta ledger for months.

### 1.6 No arbitrary score exists yet — and that is worth protecting

There is no composite reliability number anywhere in the beta path. Requirement 9 is
currently satisfied by absence. Any score introduced must earn its keep against outcomes
before it is displayed as anything other than a raw input.

### 1.7 Scope note on the local checkout

`backend/data_cache/tennisratio/all_match_logs.parquet` here is a 157-player subset.
Production holds the real 1,760-player archive. All backtesting must run against the
production archive, as this audit did.

---

## PART 2 — WHAT IS GENUINELY MISSING

Against the 15 requirements:

| # | requirement | state | gap |
|---|---|---|---|
| 1 | surface-specific history per player | **missing** | counts are all-surface |
| 2 | missing/delayed results, independently verifiable | **partial** | draw-logic only; no per-player recency-vs-completeness test |
| 3 | relevant match count + effective sample size | **partial** | raw counts recorded, ESS absent, unused |
| 4 | Elo-only / missing serve-return flags | **present** | fine; currently 0 |
| 5 | calibration saturation | **present** | fine; currently 0 |
| 6 | uncertainty from sparse history | **missing** | nothing quantifies it |
| 7 | verified vs unknown coverage | **partial** | binary; no per-player coverage estimate |
| 8 | display alongside predictions | **partial** | reasons shown; no magnitude, no expected error |
| 9 | no arbitrary scores | **satisfied by absence** | must stay that way |
| 10 | chronological OOS backtest | **missing** | never run |
| 11 | do flags predict larger error? | **missing** | never tested |
| 12 | report by tour/surface/band/DQ | **missing** | never produced |
| 13 | ledger immutability | **present** | append-only, hash-chained, verified |
| 14 | no change to trial/model/production | **present** | must be preserved |
| 15 | no unauthorized scraping/betting | **present** | must be preserved |

The honest summary: **items 4, 5, 13, 14, 15 are done. Items 1, 2, 3, 6, 7 are weak or
absent. Items 10, 11, 12 — the ones that decide whether any of this is real — have never
been attempted.**

---

## PART 3 — PROPOSED IMPLEMENTATION

Four modules, none of which touch the model, the artifact, the trial or production.

### M1 `dqu_coverage.py` — the completeness curve as a measured object

Rebuild the Part-1.2 table from any two archive snapshots, by match age, tour, level and
surface. Output: a frozen, versioned table `P(row present | age, level)`. This is the only
part that is already empirically grounded, and everything else depends on it.

### M2 `dqu_features.py` — per-prediction, as-of, leak-free

For each fixture, computed strictly from rows dated `< prediction_date`:

- `n_surface` — matches on this surface in the trailing 52 weeks, per player
- `ess_surface` — effective sample size with exponential recency decay, `(sum w)^2 / sum w^2`
- `days_since_last_archived_match`, per player
- `expected_missing_recent` — **from M1**, the number of that player's recent matches the
  curve says should exist but are not present
- `coverage_known` — true only when the player's last archived match is old enough that
  M1 puts completeness above a stated threshold; otherwise **unknown**, never "verified"
- existing `elo_only`, `calibrator_saturated`, `missing_result_risk` carried through
  unchanged

No composite score. These are inputs, not a verdict.

### M3 `dqu_replay.py` — chronological out-of-sample predictions

For each past date D: rebuild state through D−1 with the existing `FwdState` (already
proven bit-exact), score every archive match on D with the **frozen** artifact, attach M2
features computed as of D, and record the actual result. Strictly walk-forward; no
refitting; the artifact is read-only.

Expected scale: the archive holds roughly 2,000–3,000 completed matches in the last 90
days across 1,760 players — enough for banded analysis, not enough for fine cells. Exact
n to be reported before any conclusion is drawn.

**The leakage trap this must avoid, stated explicitly:** the archive is both the feature
source and the outcome source, so a replay run on today's archive sees a *completed* past
that the model never had. M3 must therefore reconstruct features from the **snapshot as it
stood**, which is why M1's curve — not today's archive — defines what was visible. Where
the two snapshots cannot establish this, the date is excluded rather than approximated.

### M4 `dqu_report.py` — the verdict

Per requirements 11–12: log loss, Brier, calibration slope and |p − outcome| split by
tour, surface, confidence band and each DQ feature, with week-clustered bootstrap CIs.

---

## PART 4 — TESTS

**Correctness**

1. As-of purity: every M2 feature recomputed with the full archive must differ from the
   as-of value on at least one known-delayed fixture, and a deliberate future-dated row
   must change nothing.
2. ESS: equals n for uniform weights; falls below n for decayed weights; monotone in decay.
3. M1 round-trip: the published curve reproduces the Part-1.2 table from the same inputs.
4. M3 bit-exactness: replaying a date already in the ledger reproduces the ledger's
   probability exactly.
5. Ledger untouched: chain head before and after a full run is identical.
6. Artifact untouched: SHA-256 of the frozen artifact unchanged.

**Validation — the gate that decides whether this ships**

7. Do the flags predict larger error? For each feature, error in flagged vs unflagged
   rows, reported with CIs. **Pre-registered: if a flag does not separate error at
   p < 0.05 with n ≥ 300, it is reported as refuted and not displayed as a reliability
   signal.**
8. Calibration by DQ cell: slope and intercept per cell; a cell that is already
   well-calibrated needs no uncertainty widening.
9. Negative control: a deliberately meaningless flag (hash of player name, parity) must
   fail test 7. If it passes, the methodology is broken, not the flag.
10. Stability: split the replay in half chronologically; a flag that only works in one
    half is not shipped.

---

## PART 5 — WHAT I AM NOT PROPOSING

- No change to D_rest, its coefficients, its probabilities or its calibrator.
- No widening of displayed probabilities. If an uncertainty estimate survives Part 4 it
  is displayed **beside** the probability, never folded into it.
- No composite "reliability score" unless tests 7–10 pass, and then only labelled with
  its measured error separation and n.
- No new scraping. M1 uses two archive snapshots already on disk; M3 uses the production
  archive read-only. No betting automation of any kind.
- No activation of the official 16-week trial.

---

## PART 6 — HONEST EXPECTATION

The completeness curve (Part 1.2) is real and already measured, so M1 and M2 will produce
genuine, defensible numbers. Whether those numbers **predict error** is an open empirical
question that Part 4 is designed to be able to answer *no* to. Given that the live flags
currently fire on 12 of 165 rows, the most likely outcome is that one or two features
(`expected_missing_recent`, `ess_surface`) separate error and the rest do not. I would
rather report that than ship five flags that look thorough.

**Awaiting your approval before any implementation.**
