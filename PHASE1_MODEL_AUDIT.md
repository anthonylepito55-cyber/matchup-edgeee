# Phase 1 — Model Audit & Baseline Report (2026-10-18)

Everything below was measured today on the live server's frozen prediction log
(2,354 rows, Sept 6 → Oct 18) and the 618,507-row training archive. No model was
changed. Scripts: `_audit1_integrity.py` … `_audit4_dogs_dup.py` on EC2.

**The clean population used for every number:** 1,733 settled rows after dropping
wrong-surface (148), wrong-player (15), in-play-price (34), void (38), synthetic
prices (156) and post-start captures (154) — see §5. "Forward" always means a
head's genuine pre-match reads; its as-of reconstructions are excluded from its
own numbers.

---

## 1. Inventory

- **48 production modules** (plus 504 scratch `_*.py` experiment files).
- **Live heads on the log:** A, B, C, D (+ `-ma` market blends), C-MC family
  (c50/c75/cutr), G, G2, X (stacker), MC2, MC3, MC5, MC6, P (betting model,
  not logged as a probability), plus UTR/pure-form/s52 signal columns.
- **Training:** A/B/C/D refit from `_tennis_model_a_build.py`; MC2/3/5/6 states
  rebuilt nightly (08:10 UTC timer, confirmed fresh today — archive staleness 0 days).
- **Pipelines:** TennisRatio archive (training + 52w stats), OpticOdds/Polymarket
  (prices), TennisExplorer (settlement), RapidAPI (same-day stats), Goalserve
  (quarantined trial).

## 2a. Duplicated signals — the board has ~4 independent models, not 13

Correlation of head probabilities on identical forward rows:

| cluster | internal ρ | effectively |
|---|---|---|
| MC2 · MC3 · MC5 · MC6 | .95–.99 | **one signal** |
| C · C75 (and CMA, X at .88) | .95 | **one signal** |
| G · G2 | .94 | **one signal** |
| A, B, D | .5–.8 to everything | semi-independent |

Any rule that counts "how many heads agree" is mostly counting the same signal
several times — consistent with every consensus test this project has run coming
back negative.

**Contradictions:** A and C pick opposite winners on **31%** of cards; C vs MC6
23%; MC2 vs MC6 9.5%. A is the outlier head (lowest AUC too — see §6).

## 2b. Leakage — training is clean; the danger is elsewhere

- `_tennis_model_a_build.py` uses `.shift(1)` before every rolling window →
  **training features are point-in-time. No leakage found in A/B/C/D training.**
- The retired tour model's harness (`tennis_features.py`) is a correct
  chronological pass. MC-family states are sequential by construction.
- **No model consumes a post-match column** (`ue_*`, `aces`, `df`, `sgames`,
  `score` are read only by the log/post-mortem display).
- The real leakage surface is **reconstructed rows**: mc3 is 77% recon, mc6 70%,
  G 69%, mc2 48%. These are display-only by design, and lanes skip them — but any
  analysis that forgets the flag inherits replay bias. (It happened twice this
  week in my own scripts.)

## 2c. Overfitting — measured, not hypothetical

- Every tab threshold (2pt/3pt gates, 3–6pt band, 2–8pt band, gender splits) was
  **scanned on the same frozen window it is reported on**.
- Where forward data has arrived, replay numbers have not held: men's 2pt dog gate
  **+38.6% replay → −14.9% forward** (+100..+150); women's 3pt **+21.4% → −19.9%**.
- Half-split test (§3) shows the same: rules fitted on half the data degrade on
  the other half.

## 3. Why favourite bets lose — answered

Blind favourites, clean population (n=1,733): **−7.08% ROI**.

| | win% |
|---|---|
| needed to break even at the offered price | 70.5% |
| the market's own de-vigged prediction | 66.5% |
| **actual** | **65.7%** |

- **≈ 4.0pt of the 4.8pt gap is the vig.** The market's fair estimate is nearly
  exactly right (66.5 predicted vs 65.7 actual).
- **≈ 0.8pt is real market error against favourites** — favourites win slightly
  *less* often than fair, so there is no favourite-side mispricing to harvest.
- **Model selection makes it worse, not better.** Favourites a head rates 4pt+
  above the market win less often than even the market's estimate:

| head says fav is underpriced by 4pt+ | head% | market% | **actual%** | ROI |
|---|---|---|---|---|
| model_c | 74.0 | 62.8 | **57.8** | −13.9% |
| c75 | 68.4 | 59.1 | **51.5** | −17.7% |
| model_a | 66.5 | 58.1 | **51.9** | −16.0% |
| mc2 | 68.5 | 59.9 | **57.9** | −9.2% |
| mc6 | 71.9 | 62.1 | **61.2** | −7.6% |

So it is **not** poor odds selection on top of good winner prediction — the
"edge" filter actively selects matches where the model is wrong and the market is
right. **Recalibration does not fix it** (honest half-split: model_c −16.7%,
c75 −14.8%, mc2 −20.0% after recalibrating on the first half). The favourite-side
margin is an error detector, not value. MC6 is the least bad.

By price: short favourites are the worst (−100..−150: −11.6%) and the loss shrinks
with depth (below −500: −4.1%) — the opposite of where the board's gold rules
concentrate.

**Dogs, for contrast:** blind −4.25%; **women's dogs −0.07%** (market error +1.6pt
covers most of the vig) vs men's −7.4%; above +300 −10.9% (the tab's cap is right).
The only quadrant where selection has any headroom is women's dogs.

## 4. Pre-match information only?

Yes for training and the live serving path (profiles are "as of now" when pricing
future matches). Three price-side violations existed and are quantified in §5;
they are data problems, not model problems.

## 5. Data integrity

| check | result |
|---|---|
| duplicate (date, player-pair) rows | **0** (the Oct-13 fix is holding) |
| unsettled backlog >2 days | 10 rows (Oct 7–14) |
| settled-but-no-winner | 38 — all voids, correct |
| **synthetic prices** | **156 rows (6.6%) have overround exactly 1.0000** — mirrored pairs like −147/+147. These are de-vigged (Polymarket-style) numbers, not offered prices; ~120 are unflagged and reach the lanes. ROI on them is not realisable. |
| **post-start prices** | **154 rows logged after match start, 0 flagged.** The in-play guard needs an opening price AND >20pp drift, so it misses them; a plain `logged_at > start_time_utc` check catches all 154. (`logged_at` is written once, never on settle — verified.) |
| both-negative pairs (−110/−110) | 65 — normal pick'em quotes, **not** an error (my part-1 check misread these) |
| overround | median 1.065, sane |
| survivorship in training | the archive holds only **1,760 players** (ingested on demand) — training over-represents players who reach our boards; opponents outside the pool enter only via rank proxies |
| retirements in training | the archive carries **0** retirement markers in 618k rows (TennisRatio strips them); ~4% of rows are mislabeled as full-effort matches. `tennis_score.py` infers them structurally but the archive rows themselves are uncorrected. |
| selection bias in the log | the log is board-driven: WTA 801 / Challenger 754 / ATP 366 / ITF-W 300 / ITF-M 133, hard-court heavy (72%). Baselines generalise only to this mix. |

## 6. Calibration

Slope <1 = overconfident. Forward rows, clean population:

| head | n | AUC | slope | verdict |
|---|---|---|---|---|
| market | — | **.714** | — | the benchmark |
| mc2 | 841 | .679 | **1.07** | well calibrated |
| g / g2 | 546/510 | .669/.677 | 0.99/0.97 | well calibrated |
| mc6 | 270 | .674 | 0.86 | mildly overconfident |
| c75 | 1442 | .662 | 0.94 | ok slope, weak AUC |
| d | 1240 | .666 | 0.81 | overconfident |
| b | 1458 | .635 | 0.90 | weak |
| **model_c** | 1454 | .654 | **0.65** | **badly overconfident** — predicts 84% → wins 74%; predicts 15% → wins 27% |
| **model_a** | 1458 | **.602** | 0.76 (0.46 on first half) | weakest head on both counts |

The 80/80 test: only MC2 and G/G2 pass it. model_c fails at both tails by 10–13pt,
and model_c feeds C75, CMA and X — so one miscalibrated model is upstream of three
board signals.

**No head beats the market on identical rows.** Best market-free AUC .679 vs
market .714; every Brier is worse than the market's.

## 7. Baseline segments (clean, forward)

Favourite-side ROI / n:
- **Gender:** men −6.8%/993 · women −7.5%/740 (dogs: men −7.4% · **women −0.1%**)
- **Level:** tour −8.3%/851 · challenger −6.6%/617 · ITF −4.2%/265
- **League:** WTA −8.8% · ATP −7.4% · Chall −6.6% · ITF-M −6.2% · ITF-W −3.2%
- **Surface:** hard −7.6%/1264 · clay −5.6%/469 (grass/carpet: none in window)
- **Odds band:** −100..−150 −11.6% → below −500 −4.1% (monotone improvement with depth)
- **Week:** +9.8 → +0.7 → −5.8 → −3.7 → −11.6 → −8.0 (%, Sept 7 → Oct 12; favourites
  have underperformed the market's own estimate in both October weeks)

---

## What Phase 2 should fix first (no model changes made)

1. **Price integrity before anything else:** flag `overround ≤ 1.0` and
   `logged_at > start` rows like `surface_bad` (one lane-filter line each) and
   re-read the lane records. ~270 rows currently pollute every ROI on the board.
2. **Stop betting model-selected favourites.** §3 shows the favourite-side margin
   is anti-predictive for every head and recalibration doesn't rescue it. The gold
   rules' positive cells are replay; the mechanism measured here points the other way.
3. **Treat the four families as four votes** (MC, C, G, A/B/D) anywhere agreement
   is counted.
4. **Recalibrate or demote model_c** (slope 0.65) before trusting any rule built
   on its margins — c75, CMA and X inherit it.
5. Keep selection work where the headroom is: **women's dogs** (market error
   +1.6pt, blind ≈ break-even).
