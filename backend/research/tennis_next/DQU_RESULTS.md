# DQU — Data Completeness & Prediction Uncertainty: implementation and results

**Nothing deployed. No new production flag is active.** The frozen D_rest artifact, its
coefficients, its calibrator, the live beta ledgers, the official 16-week trial and every
production prediction are byte-identical before and after this work — asserted by test T7,
which hashes each file around a full pipeline run.

Modules: `dqu_snapshots.py`, `dqu_coverage.py` (M1), `dqu_features.py` (M2),
`dqu_replay.py` (M3), `dqu_report.py` (M4), `dqu_tests.py`.
Data: `dqu_data/m1_coverage.json`, `m3_replay.json`, `m4_report.json`.

---

## 1. ACTUAL SNAPSHOT COVERAGE

Only full-breadth captures (1,760 players) qualify. Three exist:

| label | watermark | rows | players | sha256 (first 16) |
|---|---|---|---|---|
| S0 | 2026-09-28 | 613,330 | 1,760 | `59e2950c76e1c877` |
| S2 | 2026-10-19 | 618,700 | 1,760 | `1afca41ed27028bd` |
| S3 | 2026-10-20 | 618,866 | 1,760 | `6197deff194ced9b` |

The checkout's `all_match_logs.parquet` holds 157 players and is **deliberately excluded**:
registering it would halve every player history and read as sparse data rather than a
broken file. The registry asserts both the expected watermark and a 1,000-player floor, so
a file swapped underneath this system fails loudly.

**This is the binding limitation of the entire study.** Two usable epochs, 21 days apart.
Everything below is bounded by it.

---

## 2. INGESTION LAG (M1)

S0 measured against S3, by how old a match was when S0 was taken. Wilson 95% intervals:

| match age | present/final | complete | 95% CI |
|---|---|---|---|
| 0 d | 1 / 129 | **0.8%** | [0.1%, 4.3%] |
| 1 d | 10 / 101 | **9.9%** | [5.5%, 17.3%] |
| 2 d | 57 / 86 | **66.3%** | [55.8%, 75.4%] |
| 3 d | 76 / 120 | **63.3%** | [54.4%, 71.4%] |
| 4 d | 154 / 175 | 88.0% | [82.3%, 92.0%] |
| 5 d | 188 / 215 | 87.4% | [82.3%, 91.2%] |
| 6 d | 188 / 188 | 100.0% | [98.0%, 100.0%] |
| 7–21 d | — | 94–100% | — |

By level at 1 / 3 / 5 days: ATP 20% / 63% / 92% (n=10/8/13); Challengers 6% / 59% / 95%
(n=72/32/42); Futures 20% / 65% / 84% (n=15/74/151); WTA 0% / 50% / 100% (n=2/4/7). The
per-level cells at 1 day are too thin to rank levels against each other — the pooled curve
is the result, the level split is indicative only.

**Convergence is at ~6 days.** A match played yesterday is in the archive about one time
in ten.

**Limits, which bound every figure above.** Completeness is measured against a later
*capture*, not against truth, so a match absent from both is invisible and every number is
an **upper bound**. One pair is one observation of the ingest, not a distribution over
weeks; a tournament-calendar effect cannot be separated from a lag effect. The curve is
defined only out to the 21-day gap between watermarks, and is pooled over players.

---

## 3. FEATURE DEFINITIONS (M2)

Computed from **one** genuine snapshot, rows dated strictly `< D`. Three kinds, kept apart
so a retrospective quantity cannot drift onto a live card:

**measured_asof** — facts about the snapshot in hand, computable live:
`n_surface_52w` (matches on this surface in the trailing 364 days, per player);
`ess_surface_52w`, effective sample size `(Σw)² / Σw²` with 120-day half-life decay, so 20
matches of which 18 are old counts for far less than 20 recent ones;
`days_since_last_archived_match`; `elo_only`; `serve_return_rows`; `prior_n`;
`cold_start` (`min(prior_n) < 5`); `archive_age_days`.

**proxy** — inference about what is missing, from draw logic alone, computable live:
`missing_result_risk` / `missing_result_flag` (`tsm_proxy.unresolved_recent`).

**truth_only** — computable only against a later capture, used to validate the proxies,
**never a live feature**: `actual_missing_recent`, `actual_missing_flag`.

**Coverage is never VERIFIED** (requirement 4). `coverage_state` is one of
`known_incomplete` (the proxy or a later capture establishes a missing result), `unknown`
(the honest default), or `known_complete` — which only a later capture can establish, so
live code cannot produce it. Test T3 asserts no live-computable row ever claims it.

---

## 4. CHRONOLOGICAL VALIDATION (M3)

3,008 genuine as-of predictions. The model sees one real capture; S3 supplies outcomes and
truth-only diagnostics. An assertion refuses to run if the snapshot contains anything on or
after the earliest prediction date, so as-of purity is enforced rather than assumed.

Two regimes, **never pooled**:

- **FAITHFUL — n=545**, archive 1–3 days stale, matching the live `FRESH_DAYS` regime.
  The only rows that justify a statement about live behaviour.
  Overall: accuracy 72.5%, Brier 0.1868, log loss 0.5564, calibration slope 1.00.
- **SENSITIVITY — n=2,463**, archive 4–21 days stale, i.e. more degraded than a live pass
  ever runs. Overall: accuracy 68.0%, Brier 0.2039, calibration slope 0.84.

Per requirement 8, no historical match was reconstructed from M1's average curve. M1
measures; M3 replays real captures. They are never mixed.

---

## 5. DOES EACH SIGNAL PREDICT LARGER ERROR OR WORSE CALIBRATION?

A signal must clear **both** a date-clustered bootstrap **and** an empirical null of 300
meaningless flags at matched prevalence — and must beat *every* null draw, roughly
p < 1/301, which absorbs the ~22 tests run here without a separate multiplicity correction.

### FAITHFUL regime (n=545) — the live-relevant evidence

| signal | kind | n flagged | Brier diff [95% CI] | beats all 300 null draws | verdict |
|---|---|---|---|---|---|
| `missing_result_flag` | proxy | 112 | **+0.0826** [+0.0332, +0.1153] | yes (max null 0.0717) | **PREDICTS WORSE** |
| `elo_only` | measured | 214 | −0.0546 [−0.0740, −0.0377] | yes (max null 0.0467) | predicts *better*, confounded |
| `actual_missing_flag` | truth_only | 330 | +0.0212 [+0.0088, +0.0297] | no | fails |
| `cold_start` | measured | 35 | −0.0293 [−0.0950, +0.0277] | no | no effect |
| `NEGATIVE_CONTROL_parity` | control | 274 | +0.0162 [−0.0276, +0.0455] | no | correctly fails |
| `NEGATIVE_CONTROL_random37` | control | 192 | +0.0273 [−0.0056, +0.0462] | no | correctly fails |
| ess / n_surface / days_since / sr_rows / prior_n | measured | — | — | — | n too small to split |

**The validated result.** `missing_result_flag` predicts larger error *and* far worse
calibration:

| | n | Brier | log loss | accuracy | calibration slope |
|---|---|---|---|---|---|
| flagged | 112 | 0.2524 | 0.7346 | 60.7% | **0.237** |
| clean | 433 | 0.1698 | 0.5103 | 75.5% | 1.288 |

A slope of 0.24 means probabilities on flagged fixtures are wildly over-extreme — a stated
85% behaves nothing like 85%. It survives within-tier pooling (+0.0545), so it is not a
tier artefact.

The effect is a **step, not a gradient**: risk 0 → Brier 0.1698 (n=433); risk 1 → 0.2525
(n=58); risk 2 → 0.2480 (n=24); risk 3+ → 0.2557 (n=30). The existing `> 0` binarisation is
therefore the right call and the unbounded count adds nothing.

### SENSITIVITY regime (n=2,463) — what it can and cannot say

**A negative control beat the strictest bar here** (`random37`, +0.0227 Brier, above its
own null maximum of 0.0220). So **no claim at effect sizes up to ~0.023 Brier is
distinguishable from noise in this regime**, and the bootstrap interval that called it
significant was too narrow: resampling dates adds no variance to a contrast balanced
*within* every date. This is reported, not patched over — it is what the control is for.

Above that floor: `elo_only` (−0.0545) and `cold_start` (−0.1094) are 2.5× and 5× the
demonstrated noise. `missing_result_flag` shows **no effect** here (+0.0093) — expected,
since at 4–21 days stale 2,258 of 2,463 fixtures have missing data and the flag loses all
contrast.

### Stratified (faithful, requirement 10)

By tier: ITF-men Brier 0.1486 / acc 81.2% (n=170); ITF-women 0.1873 / 71.6% (n=109);
WTA 0.1832 / 69.6% (n=46); Challenger 0.2078 / 69.1% (n=178); ATP 0.2550 / 57.1% (n=42).
By surface: Clay 0.1681 (n=123), Hard 0.1922 (n=422).
By band: 50–60 → 0.2435; 60–70 → 0.2207; 70–80 → 0.2103; 80–85 → 0.1163; 85–90 → 0.0777;
90–95 → 0.1199. Monotone apart from the top cell, which is thin (n=37).

---

## 6. WHICH WARNINGS ARE OBJECTIVELY JUSTIFIED

Per requirement 5, an objective warning stands on being **true**, whether or not it
predicts error. These are facts about the data in hand:

- **`elo_only`** — there is genuinely no serve/return model for this fixture. True by
  construction. It should stay. Its error *direction* is the opposite of intuition and is
  largely tier confounding (within-tier, only Challenger −0.017 and ITF-women −0.042 have
  enough rows on both sides; 72% of ITF-men fixtures are Elo-only against 4% of ATP, and
  ITF is the more predictable tier). It is an honest statement of what is missing, not a
  reliability signal, and must never be shown as "this prediction is worse".
- **`calibrator_saturated`** — a displayed 100% is a frozen isotonic knot, not a credible
  probability. True by construction; unmeasurable here (0 occurrences).
- **`n_surface_52w` / `ess_surface_52w`** — "this player has 3 clay matches on record" is
  true and worth showing. **Unvalidated as an error predictor**: n=545 cannot support a
  dev/eval threshold split, so these are reported as facts only.
- **`coverage_state: unknown`** — the honest default, and the audit's central point: a
  fresh archive watermark does not mean recent results are present.

---

## 7. WHICH PREDICTIVE SIGNALS FAIL VALIDATION

- **`actual_missing_recent` / `actual_missing_flag`** — fails despite being ground truth,
  because it fires on 330 of 545 fixtures (61%) and is too blunt to discriminate. The
  draw-logic **proxy outperforms the truth it approximates** by selecting the severe cases.
- **`cold_start`** — no detectable effect in the faithful regime (n=35 flagged).
- **`ess_surface_52w`, `n_surface_52w`, `days_since_last_max`, `serve_return_rows_min`,
  `prior_n_min`** — no usable dev/eval threshold at n=545. **Not refuted — untested.**
- **Everything marginal in the sensitivity regime** — a negative control cleared the same
  bar, so those cells are unusable.
- **`missing_result_risk` as a magnitude** — the gradient is flat above 1. Only the binary
  flag carries signal.

---

## 8. TEST RESULTS

**32 passed, 1 failed** (`dqu_tests.py`).

Passing: ESS identities (equals n for uniform weights, below n when concentrated, monotone
in decay, 0 not NaN on empty); as-of purity (future rows change nothing before the cutoff,
appear after it, cutoff strictly `<`); missing-data behaviour (no history → zeros, exact
surface filter); coverage labelling (no `VERIFIED` state, no live row claims
`known_complete`); split-period stability (both halves scoreable in both regimes);
reproducibility (deterministic inventory, seed-stable bootstrap); M1 internals (Wilson
intervals stay in [0,1] at both ends, every cell carries a CI, completeness rises with
age); **isolation — frozen artifact, beta paper ledger, beta settle ledger, official exp2
ledger and the production snapshot all byte-identical after a full run**.

**The failure is a real finding, left failing on purpose:**
`sensitivity / NEGATIVE_CONTROL_random37 does not separate error` — it did
(+0.0227 Brier). That is the basis for section 5's conclusion about the sensitivity regime.
Suppressing it would have hidden the one thing the controls were there to catch.

---

## 9. LIMITATIONS

1. **Two snapshot epochs, 21 days apart.** Everything rests on this. The faithful regime is
   545 rows over three dates (Sep 29 – Oct 1, plus 2 rows on Oct 20).
2. **M1 reports upper bounds** — completeness is measured against a later capture, not truth.
3. **The sensitivity regime cannot support claims below ~0.023 Brier**, demonstrated by its
   own negative control.
4. **Thin-data signals are untested, not refuted.** n=545 is too small for a dev/eval
   threshold split, which requirement 11 demands and which I did not weaken to get a result.
5. **Tier confounds the measured_asof signals** — 72% of ITF-men fixtures are Elo-only
   against 4% of ATP, and ITF is the more predictable tier.
6. **The faithful regime's calibration slope is 1.00 overall**, so D_rest is well calibrated
   on fresh data in aggregate; the collapse to 0.24 is specific to flagged fixtures.
7. **Nothing here is forward evidence.** These are replays on historical captures, not live
   settled predictions. The beta ledger still has 0 settled matches.
8. The one Oct-20 faithful cell contributes 2 rows; today's matches are largely unsettled.

---

## 10. THE ONE RECOMMENDATION, FOR YOUR DECISION

`missing_result_flag` is the only signal that earned a verdict in the only regime that
speaks to live behaviour. It predicts +0.0826 Brier, −14.8 points of accuracy, and a
calibration collapse from 1.29 to 0.24, on 112 of 545 fixtures, beating all 300 null draws
and surviving within-tier pooling.

It is **already computed and already displayed** on the beta tab as
`missing_result_risk_N`. Nothing needs to be built to use it. What this study establishes
is that it deserves to be read as *"this probability is not trustworthy"* rather than as a
footnote — and that the four flags beside it have not earned the same standing.

**No new production flag has been activated. Awaiting your decision on which, if any,
should reach the live board.**
