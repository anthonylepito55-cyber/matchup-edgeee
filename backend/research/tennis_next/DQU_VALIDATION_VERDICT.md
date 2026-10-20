# missing_result_flag — pre-deployment validation

## VERDICT: **LIMITED**

Do not promote it to a prominent reliability warning yet. Keep it displayed exactly as it
is today, as an objective data-quality note. The effect is large, survives every
robustness check I can run, and is almost certainly real — but **the only subset of data
that was never previously read does not independently confirm it**, and with the snapshots
available that cannot be fixed by more analysis.

**Independent validation is not possible with the available snapshots.** Two usable
archive epochs exist. I am not treating the existing replay as independent confirmation.

Nothing deployed, retrained or changed. Frozen model, all ledgers, the official trial and
production are untouched (test T7, hash-verified).
Code: `dqu_validate.py` · data: `dqu_data/validation.json`

---

## 1. The failing negative control — investigated, kept visible, not weakened

The test still fails and I have left it failing. The cause is now understood and it is my
methodology, not the data.

The criterion was "beat the largest of **300** null draws". The maximum of 300 draws is
itself a noisy estimate of the null's tail, and it came in **low**. Re-estimating with
2,000 draws:

| regime | control's Brier diff | max abs over 300 nulls | max abs over 2,000 nulls | empirical p (K=2000) |
|---|---|---|---|---|
| sensitivity | +0.02272 | 0.0220 | **0.0308** | 0.0030 |
| faithful | +0.02733 | 0.0566 | 0.0603 | 0.1235 |

At K=2,000 the control **no longer beats every draw** and correctly fails in both regimes.
It was a tail draw (z = 2.76, 99.85th percentile) that a 300-draw null could not see past.

## 2. Does the test control false discoveries?

Not adequately at K=300. The "beat the max of K nulls" rule is a max-statistic threshold
with per-test α ≈ 1/(K+1); it is **not** a multiplicity correction across signals.

| K | per-test α | expected false positives over the 22 tests run | family-wise error |
|---|---|---|---|
| 300 | 0.0033 | 0.073 | **7.1%** |
| 2,000 | 0.0005 | 0.011 | 1.1% |
| 10,000 | 0.0001 | 0.002 | 0.2% |

**K=300 gave a 7% family-wise error rate, so observing one false positive among 22 tests
was close to expected.** The criterion should be K ≥ 2,000. Re-run at K=2,000 the headline
signal is unaffected: +0.0826, beats all 2,000 draws, empirical p < 0.0005, z = 3.93.

## 3. Were the 545 faithful predictions genuinely as-of?

**No fitting contamination.** From `TSM_PROTOCOL.md` / `TSM_D_REGISTRATION.md`:

- coefficients, standardisation mean/sd **and the isotonic calibrator**: fit on
  **2022-01-01 → 2023-12-31** only
- development evaluation: 2024-01-01 → 2025-06-30
- final test: 2025-07-01 → 2026-09-30, read once, confirmatory, **no refit**

Every replayed match is **2.75 years after the last fitting data**. No feature, coefficient
or calibration knot saw any of it.

**But 359 of the 545 rows (66%) sit inside the final-test window**, which was read once on
2026-10-20. No parameter changed as a result, so this is not leakage in the usual sense —
but those rows are not virgin data. Only **186 rows (Oct 1 and Oct 20) lie outside every
registered window**. Section 9 reports them separately, and that is the finding that
decides this verdict.

## 4. Is the flag knowable before first serve?

Yes, verified four ways:

- the available snapshot contains **0 rows** dated after its own watermark;
- the proxy's player history contains **0 rows** dated on or after the first prediction date;
- its draw-round index contains **0 such rows**;
- re-truncating the history at D changes **0 of 166** sampled answers — but feeding it the
  completed archive changes **23 of 166**, proving it genuinely reads the snapshot rather
  than returning a constant.

The flag uses only the player's own prior matches and the prior rounds of the draw they
came from, all dated before the prediction date, plus the fixture's own tournament name,
which is on the schedule. **No future result and no later draw information.**

## 5. Flagged vs clean, within strata (faithful, n=545)

| stratum | n flag / clean | Brier flagged | Brier clean | diff | 95% CI |
|---|---|---|---|---|---|
| **tier** ATP | 24 / 18 | 0.2973 | 0.1986 | +0.099 | [−0.021, +0.218] |
| Challenger | 31 / 147 | 0.2624 | 0.1962 | +0.066 | [−0.027, +0.159] |
| ITF-men | 30 / 140 | 0.1835 | 0.1411 | +0.042 | [−0.056, +0.141] |
| ITF-women | 18 / 91 | 0.2964 | 0.1657 | **+0.131** | [+0.007, +0.255] |
| WTA | 9 / 37 | — | — | — | too few |
| **surface** Clay | 29 / 94 | 0.2885 | 0.1309 | **+0.158** | [+0.042, +0.273] |
| Hard | 83 / 339 | 0.2398 | 0.1806 | **+0.059** | [+0.008, +0.111] |
| **band** 50–60 | 23 / 90 | 0.2602 | 0.2392 | +0.021 | [−0.009, +0.051] |
| 60–70 | 28 / 107 | 0.2277 | 0.2189 | +0.009 | [−0.055, +0.073] |
| 70–80 | 24 / 98 | 0.2759 | 0.1943 | +0.082 | [−0.020, +0.184] |
| 80–85 | 19 / 56 | 0.1657 | 0.0996 | +0.066 | [−0.063, +0.195] |
| 85–90 / 90–95 / 95+ | 5–7 / 20–32 | — | — | — | too few |

**Every one of the 11 reportable cells points the same way.** Only three clear zero
individually, which is what n of 18–83 per flagged cell buys. The intervals are
unclustered and therefore optimistic.

## 6. Does it survive adjustment?

OLS of squared error on the flag plus controls, date-clustered SE (n=545):

| term | coef | SE | t |
|---|---|---|---|
| **missing_result_flag** | **+0.0801** | 0.0303 | **2.65** |
| confidence | −0.4195 | 0.0917 | −4.57 |
| elo_only | +0.0195 | 0.0086 | 2.26 |
| tier=Challenger / ITF-men / ITF-women / WTA | −0.016 / −0.051 / −0.019 / −0.038 | — | −0.5 / −0.8 / −1.1 / −3.2 |
| surface=Hard | +0.0002 | 0.0293 | 0.01 |

The flag's effect barely moves after adjustment (+0.0826 → **+0.0801**). It is not a proxy
for tier, surface, predicted probability or Elo-only status.

## 7. Is it concentrated in a few dates, tournaments or players?

No. Leave-one-out across every grouping stays positive:

| grouping | groups | LOO min | LOO max | all positive |
|---|---|---|---|---|
| dates | 4 | +0.0685 (drop 09-30) | +0.1096 (drop 10-01) | yes |
| tournaments | 31 | +0.0737 | +0.0952 | yes |
| players | 790 | +0.0725 | +0.0871 | yes |

Removing any single tournament moves the estimate by at most 26% of its value; any single
player, 18%.

## 8. Clustered uncertainty

| clustering | diff | SE | t | 95% CI | clusters |
|---|---|---|---|---|---|
| by date | +0.0826 | 0.0285 | 2.90 | [+0.027, +0.138] | **4** |
| by tournament | +0.0826 | 0.0242 | 3.42 | [+0.035, +0.130] | 31 |

**The date clustering has only 4 clusters.** Cluster-robust SEs need roughly 30–40 groups
to be trustworthy; at G = 4 the t-statistic is not reliable and I would not quote it. The
tournament clustering (G = 31) is the defensible one, and it gives t = 3.42.

The difference survives honest clustered estimation — but the strongest available
clustering is tournament, and fixtures on one day still share an archive state that no
clustering here fully absorbs.

## 9. The result that sets the verdict — the untouched subset

186 faithful rows (Oct 1, Oct 20) lie outside every registered window and have never been
read by any test:

| | n | Brier | accuracy | calibration slope |
|---|---|---|---|---|
| flagged | 42 | 0.2209 | 64.3% | 0.640 |
| clean | 144 | 0.1877 | 70.8% | 0.976 |

diff **+0.0332**, empirical **p = 0.34**.

Same direction on all three measures. **Not significant.** The full-sample +0.0826 is
therefore driven substantially by Sep 29–30, which sit inside the once-read final-test
window. With 42 flagged rows this subset has little power — absence of significance here is
weak evidence against, not evidence of absence — but it is the only independent look
available, and it does not confirm.

---

## What this means

**For: ** a large effect (+0.0826 Brier, −14.8 pts accuracy, calibration slope 1.29 → 0.24),
beating 2,000 null draws at p < 0.0005; stable under adjustment; consistent in sign across
all 11 reportable strata; not concentrated in any date, tournament or player; t = 3.42 under
tournament clustering; a mechanism that is causally sensible — a player whose last result is
missing has the wrong recent form, and form is what D_rest weighs most.

**Against: ** two-thirds of the evidence comes from data read once before; the only
never-read subset returns p = 0.34; the faithful regime spans **four dates**, so date-level
clustering is unreliable; and the fixture population is drawn from the completed archive,
so matches that were scheduled but never archived — walkovers, withdrawals — are absent,
and a flagged player is plausibly more likely to withdraw.

**Recommended path to GO**, neither of which needs new analysis:

1. **Accumulate snapshot epochs.** Each daily archive capture kept from now on adds genuine
   as-of dates at live staleness. Roughly three more weeks of captures would give an
   untouched faithful set several times the current 186 rows. This costs one file a day.
2. **Let the beta ledger settle.** It holds 165 live predictions and 0 settled. Those are
   true forward predictions and carry the flag already. They are the clean test.

Until one of those reports, the flag stays what it is: an **objective, true statement that
a recent result is missing** — which requirement 9 says to preserve regardless — rather than
a validated reliability warning.

**No deployment. Awaiting your review.**
