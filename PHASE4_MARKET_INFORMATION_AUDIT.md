# Phase 4 — Market-Relative Information Audit (2026-10-18)

**Question:** does any existing head carry predictive information beyond the market?
**Answer: no.** Thirteen heads, seven non-market features, and a regularized four-family
combination were each tested in a chronological walk-forward against the recalibrated market on
identical, price-valid rows. **Not one adds out-of-sample information** (every log-loss delta ≤ 0
or within noise); the only statistically notable result is MC5 actively *hurting* when combined
(t = −2.35). C75's famous 56%→39% error is fully explained: its deviation from the market is
noise, and the overconfidence grows monotonically with how far it disagrees. Per the Step 6 rule
— no credible probability improvement → no betting-strategy evaluation — and the recommendation
is explicitly **against building new selection rules from these heads.**

Baseline preserved: commit `02ab0ea`, reports and lanes untouched, Oct 31 checkpoint not used for
any choice here. Engine: `backend/_phase4_market_info.py`; outputs `reports/phase4/phase4_heads.csv`
(per-signal results) and `phase4_oos_rows.csv` (per-row OOS deltas).

---

## 1. Design and baselines (identical, valid, point-in-time rows)

- Population: the 1,729 Phase-2-clean settled rows (Sept 6 – Oct 18); per head, its genuine
  frozen reads only (reconstructions excluded).
- **Market probability, verified:** proportional de-vig `i1/(i1+i2)` of the frozen book prices —
  the same construction every lane uses. Stated limitations: single book (FanDuel-dominant),
  proportional allocation does not correct favourite–longshot bias, median overround 6.5%, and
  the frozen price ≈ the close (median 0.81pp from Pinnacle's close, measured 10-11).
- A: market-only, recalibrated per training window (`y ~ logit(p_mkt)`).
  B: each head alone. C: `y ~ logit(p_mkt) + logit(p_head)` (and `+ z(feature)` for row features),
  L2-regularized, **expanding-window**: first 40% of rows is the minimum train set, the rest is 5
  sequential test folds, every model refit only on earlier rows; calibration always fitted on
  earlier data only.
- Metric: paired per-row OOS log-loss delta (market+head minus market-only), with paired t.
  ~19 correlated tests ⇒ bar for "credible" set at t ≥ 3 in advance.

## 2. Incremental information over the market — the core table

Positive Δ = the head adds information. ×1000 log-loss units; full table in `phase4_heads.csv`.

| signal | n OOS | alone AUC | Δlogloss ×1000 | t | verdict |
|---|---|---|---|---|---|
| model_a | 873 | .603 | −0.40 | −0.5 | none |
| model_b | 873 | .636 | −1.00 | −0.5 | none |
| model_c | 870 | .654 | −0.19 | −0.3 | none |
| model_d | 742 | .666 | −0.20 | −0.3 | none |
| c75 | 863 | .662 | −1.63 | −1.6 | none |
| c-utr | 863 | .681 | −1.15 | −1.7 | none |
| G | 327 | .670 | −1.70 | −0.7 | none |
| G2 | 305 | .678 | −1.08 | −1.1 | none |
| X | 668 | .667 | +0.60 | +0.2 | none (coef −0.36: anti-signal after market control) |
| MC2 | 503 | .678 | −2.13 | −1.0 | none |
| MC3 | 252 | .667 | −2.02 | −1.4 | none (low power) |
| **MC5** | 215 | .674 | **−6.28** | **−2.35** | **negative — hurts** |
| MC6 | 161 | .675 | −3.46 | −0.7 | none (low power) |
| s52 serve / return gaps | 1026 | — | +0.02 / −0.27 | +0.0 / −0.8 | none |
| pure-form, UTR edge/momentum | 865/316/309 | — | +0.4 / −0.3 / −3.0 | ≤1.6 | none |
| C serve / return gaps | 463 | — | −0.2 / **+3.1** | −0.6 / +1.0 | none (best point estimate in the audit, still noise) |
| **4-family combo** (MC2+G2+C75+A) | 305 | — | −2.52 | −0.8 | none |

Nothing clears t ≥ 2 positive; nothing comes close to the pre-set t ≥ 3. A respectable standalone
AUC (e.g. c-utr .681) buys nothing once the market is in the regression — the heads are
re-deriving information the price already contains, minus noise.

## 3. C75's 56% → 39% error — anatomy (Step 4)

The error is **not** global mis-scaling, not gender-, level-, surface- or band-specific in origin.
It is a monotone function of **disagreement with the market**:

| C75's dog prob vs market | n | C75 says | market says | **actual** | C75 gap |
|---|---|---|---|---|---|
| 5pt+ UNDER the market | 171 | 31.0% | 41.2% | **48.0%** | **−16.9pt (under!)** |
| 0–5 under | 189 | 35.8% | 38.0% | 36.0% | −0.2pt |
| 0–5 over | 267 | 37.1% | 34.4% | 31.5% | +5.6pt |
| 5–10 over | 280 | 40.4% | 33.0% | 37.5% | +2.9pt |
| 10–20 over | 360 | 45.6% | 31.2% | 32.5% | +13.1pt |
| 20pt+ over | 171 | 51.7% | 25.2% | 29.2% | **+22.5pt** |

Where C75 agrees with the market it is almost perfectly calibrated; wherever it deviates — in
either direction — the truth stays near the market. The deviation is noise. The effect is
amplified where books are thinnest (ITF +15.2pt, clay +15.0pt, +300+ dogs +18.4pt) but exists
everywhere (men +10.9, women +12.6, main tour +8.7). This is the same mechanism Phase 1 proved on
favourites and Phase 3 on dogs, now shown directly.

**Recalibration cannot fix it** (walk-forward, fitted only on earlier data, same OOS rows):
raw C75 Brier .2346 → logistic .2351 → isotonic .2383, market **.2179**. Calibration reshapes
probabilities; it cannot add the discrimination the head lacks — as pre-stated in the brief.

## 4. Pre-specified segments (Step 5)

Incremental Δlogloss by gender / level / surface for MC2, G2, C75, D, computed on the stored OOS
per-row deltas (no refits, no new filters): **no positive cell reaches t = +2 anywhere**; best is
MC2-on-challenger +2.78 (t 0.9, n 164) against ~28 looks. Direction-consistent negatives
(c75-on-challenger t −2.7) carry no actionable meaning either. Small segments (grass, indoor) do
not exist in this window and were not tested.

## 5. Betting value (Step 6)

Skipped by the pre-set rule: no credible, repeatable probability improvement exists to evaluate.
**Recommendation: do not develop new selection rules from these heads.** The exploratory
executable-price ledger that already runs (the Polymarket paper auto-bettor) continues untouched,
and the registered Oct 31 lane checkpoint will close the Phase 3 question on its own terms.

## 6. Retire / retain

- **Retain as benchmarks / display:** MC2 (best-calibrated, slope 1.07), G/G2 (well-calibrated),
  the market itself as the reference probability everywhere.
- **Label "no incremental information" (keep visible, never as bettable signals):** C, C75,
  C-UTR, D, B, MC3, MC6, s52/UTR/pure-form features.
- **Retire from any decision path:** model_a (weakest on every metric, negative combo weight),
  MC5 (significantly harmful in combination), X (negative weight after market control — it
  re-manufactures the market badly).
- Failed hypotheses closed by Phases 1–4: favourite-side value, dog-side value, consensus,
  head-vs-market margin as signal, recalibration-as-rescue.

## 7. Recommended next experiment (with success criterion)

Four phases agree the heads contain no information the close doesn't already hold. The one
edge-shaped thing this project has **measured** and not yet exhausted is *speed and venue*, not
prediction: Pinnacle moves lead the exchanges by 3–6 s (measured 10-11), the OpticOdds scanner
infrastructure already exists, and the paper auto-bettor already books realizable exchange fills.

> **Experiment:** paper-trade top-of-book taking on Kalshi/Polymarket within seconds of a
> qualifying Pinnacle move (existing `oo_scan` signals; no model probabilities involved).
> **Success criterion, set in advance:** on ≥ 200 paper fills, mean CLV vs the Pinnacle close
> ≥ +1.5pp with t ≥ 3, and realized paper ROI > 0. Fewer than that, or weaker, = the experiment
> fails and is closed like the others.

A model-building route remains legitimate only if it brings **new information the market lacks**
(e.g. verified lineup/injury/retirement intel, or true opening-line capture before books sharpen) —
not another blend of the same public stats. No such source is currently ingested; acquiring one is
a data project, not a modelling project.

---
*No prospective claim of profitability is made for anything in this report. Artifacts:
`reports/phase4/phase4_heads.csv`, `reports/phase4/phase4_oos_rows.csv`. Engine committed
separately from the frozen baseline `02ab0ea`.*
