# Prospective evaluation of `missing_result_flag` — PRE-REGISTRATION

**Registered before any settled outcome was inspected.** At the moment of writing the beta
ledger holds 207 predictions, 165 live after withdrawals, and **0 settled**. No outcome has
been read, so nothing below was chosen with knowledge of a result.

This document is frozen by sha256 once committed. The evaluator
(`dqu_prospective.py`) refuses to report unless the registered stopping criterion is met,
and prints this file's hash alongside its results so the two can be checked against each
other.

---

## 1. Hypothesis

Stated in advance and directional, because the historical replay already pointed one way
and a confirmatory test should say so rather than pretend to be agnostic:

> **H1.** Among settled live paper predictions, those carrying `missing_result_risk > 0`
> at prediction time have a **higher** Brier score than those carrying
> `missing_result_risk == 0`.

Secondary, same direction: higher log loss, lower accuracy, and a calibration slope further
from 1.

**H0** is no difference. The test is one-sided for H1's direction; a significant effect in
the *opposite* direction is reported as a refutation of H1, not as a finding.

This is a **confirmatory** test of a historical result (+0.0826 Brier on 545 as-of replayed
fixtures, of which only 186 were outside a previously read window, where the same direction
gave p = 0.34). The prospective data is independent of all of it.

## 2. Population

Every prediction in `beta_paper_ledger/events.jsonl` that:

- is **not** invalidated (the 42 parser-bug withdrawals are excluded — they were priced
  against a player who does not exist);
- has a settlement event in `beta_settle_ledger/events.jsonl` with outcome `p1_won` or
  `p2_won`;
- was written with `beta_version` `TSM-D_rest-BETA-paper/1`.

## 3. Exclusions, fixed in advance

1. **Voids** — retirements recorded as void, cancellations, walkovers. They have no
   outcome to score.
2. **Invalidated predictions** — as above.
3. **Grand Slam fixtures** — the format rule is best-of-5 and the beta's bo5 handling is
   not part of what is being tested here. None are expected in the window.
4. **Nothing else.** In particular, predictions are **not** excluded for low confidence,
   unusual tier, Elo-only status or any other data-quality reason. Excluding on a quality
   flag would bias precisely the comparison being made.

A prediction that cannot be settled is not an exclusion, it is pending, and it keeps the
analysis waiting rather than shrinking it.

## 4. Metrics

Primary: **Brier score difference**, flagged minus unflagged, on the predicted
probability of player 1 against the realised outcome.

Secondary, all reported with the primary and none of them able to overturn it:
log loss difference; accuracy difference; calibration slope and intercept per group, from
a logistic regression of outcome on `logit(p)`.

## 5. Comparison method

- **Effect size with a confidence interval first.** A p-value never appears alone.
- **Uncertainty: tournament-clustered standard errors.** Fixtures in one draw share a
  surface, a player pool and an archive state. Date clustering is also reported, but the
  historical work had only 4 date clusters and that is too few to trust; tournament is the
  primary clustering and the count of clusters is always printed.
- **Empirical null: K = 2,000** meaningless flags at matched prevalence through the
  identical pipeline. K = 300 was shown to give a 7.1% family-wise error rate over 22
  tests and to let a negative control through; 2,000 gives 1.1%.
- **Negative controls** run alongside and must fail. If a control passes, the result is
  reported as inconclusive regardless of what the real flag did.
- **Adjusted model**: OLS of squared error on the flag plus confidence, Elo-only status,
  tier and surface, with the same clustering. The flag must survive adjustment.

## 6. Stopping criterion — ONE look

The analysis is run **once**, when **both** of:

- **≥ 300 settled, non-excluded predictions**, and
- **≥ 60 of them flagged** (`missing_result_risk > 0`).

Until both hold, `dqu_prospective.py` prints progress and the count of what is missing and
**refuses to print any outcome-dependent statistic**. There is no interim analysis, no
optional stopping and no second look at a larger sample if the first look disappoints.

If the criterion is met and the result is not significant, that is the result.

Should a second look ever be wanted, it requires a new pre-registration, an owner approval,
and the alpha spent on the first look carried forward explicitly.

## 7. Decision rule

| outcome at the single look | verdict |
|---|---|
| flagged Brier higher, CI excludes 0, beats all 2,000 nulls, survives adjustment, controls fail | **GO** — `missing_result_flag` may be displayed as a validated reliability warning |
| direction correct but any criterion missed | **LIMITED** — stays an objective warning, no reliability claim |
| no difference, or opposite direction | **REFUTED** — H1 is reported as refuted and the flag stays an objective warning |

In every branch the flag **remains displayed** as the objective statement it is: a recent
result for one of these players is missing from the archive. That is true independently of
whether it predicts error, and requirement 12 keeps the two claims apart.

## 8. What this evaluation may never do

- change the frozen D_rest model, its coefficients or its calibrator;
- change, re-score or re-date any original beta prediction, its probability, its pre-match
  flags, its timestamp or its model version;
- touch the official 16-week prospective trial or its ledger;
- alter production scoring logic or add betting logic;
- retrain anything, or adjust any probability;
- tune a threshold on the prospective data. `missing_result_risk > 0` is fixed here and
  now, and section 5's method is fixed with it.

## 9. Known limitations, recorded in advance

1. The predictions come from one beta pass's fixture universe; they are not a random
   sample of professional tennis.
2. Settlement is supervised and name-matched; a match that cannot be matched stays pending
   and may bias the settled set in an unknown direction. The evaluator reports the
   settled/pending split so this is visible.
3. Flag prevalence in the live set is roughly 7% (12 of 165 at registration), far below the
   21% seen historically. The 60-flagged requirement may therefore take a long time, and
   waiting is the correct behaviour.
4. Tournament clustering cannot absorb the shared archive state within a single day.
