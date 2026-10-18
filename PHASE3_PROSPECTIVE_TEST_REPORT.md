# Phase 3 — Prospective Validation of Dog-Side Edges (2026-10-18)

**Question:** does any existing underdog rule retain positive ROI on genuinely unseen matches?
**Answer so far: no.** Prospectively, three of the four frozen lanes are negative and the fourth
is +4% ± 26 — indistinguishable from zero. Every lane underperforms blind dogs on its own window,
holds no closing-line value, and the collapse from replay to prospective is itself statistically
significant for the headline lane (t = −2.7). Formal verdict below; the pre-registered window
still runs to Oct 31. No threshold, model, or lane was changed in this phase.

---

## 1. Git status

- **Commit `02ab0ea88bc90229db0d648e7cef0e26bddc9bdd`** on `main`: Phase 2 guards, both phase
  reports, the audit/validation scripts, the five Phase 2 CSVs, and the production tennis files
  those changes live in (which necessarily carried their earlier uncommitted work — MC6, dog-tab
  gates, auto-bettor; noted in the commit message). Secrets sweep run before staging: clean.
  Excluded deliberately: 287 scratch `_*.py` experiment files, model artifacts, dumps, and
  `.claude/settings.local.json`.
- The committed `tennis_log.py` is **byte-identical (md5) to the deployed EC2 copy**, and the
  Phase 2 validation suite was re-run after the commit: **V1–V7 all pass**.
- Caveat, stated rather than hidden: `origin/main` is ahead of local — EC2 runs hourly
  `mlb-autopush` timers that commit/push its own artifacts. The Phase 3 baseline is therefore the
  **local commit hash**, not a push; reconciling the two lineages is a separate chore and was not
  attempted mid-phase.

## 2. Frozen lane definitions (read from the committed code, not from memory)

Shared eligibility: both odds present; none of `BAD_ROW_FLAGS` (incl. the Phase 2 price flags).
The three bet-loop lanes additionally require **Model C and C-MA to be present** on the row — a
hidden dependency worth knowing. Rule-birth dates are from the dated comments in the code.

| lane | born | rule |
|---|---|---|
| `c75_dog_100plus` | 10-08 | C75 ≥ 50% on the market dog, dog ≥ +100, any league/gender |
| `mc_c75_dog` | 10-06 | C75's pick is the market dog, **any** dog price, not `mc_c_recon` |
| `mc6_dog2_all` | 10-16 | MC6 (genuine reads only, which exist from 10-15) ≥ 2pt over the de-vigged market on the dog, any price |
| `s52_fav_band_dog` | 10-11 | dog +100..+200 where the favourite owns **both** 52-week stat gaps (own pass; needs the four s52 columns, not Model C) |

**Independence — measured, not assumed:** `c75_dog_100plus` and `mc_c75_dog` share **Jaccard
0.88** of their prospective selections — they are one lane with two names (same head, the only
differences are the +100 floor and a recon guard). mc6 overlaps the c75 pair at 0.10–0.11, s52 at
0.03–0.06. **Effective independent candidates ≈ 3**, which is how multiple comparisons are
treated below.

## 3. Forward-test protection

Selections were **re-derived independently from the frozen log** using the rules above and
reconciled against the live lane records before anything was reported — all four match exactly
(284 / 239 / 159 / 225). Every selection row preserves: fixture id, `logged_at` (write-once,
verified in Phase 2), pick and side, executable odds, model and market probabilities, lane and
rule-birth version, all price-validity flags, outcome and settlement status —
`reports/phase3/phase3_selections.csv` (1,061 rows). Synthetic and post-start prices are
excluded by the Phase 2 guards; no missing prediction was backfilled; pre-birth rows are reported
**separately as replay**, never mixed into the prospective window.

## 4. Results

Stake $25 flat; CIs: Wilson for win rate, ±1.96·se for ROI. Pending/void shown, never as losses.

| lane | window | n (W-L) | win% [95% CI] | avg dog | ROI ± CI | P/L | pending |
|---|---|---|---|---|---|---|---|
| c75_dog_100plus | replay (pre 10-08) | 123 (64-59) | 52.0 [43–61] | +168 | **+34.4% ±25** | +$1,056 | — |
| | **prospective** | **161 (63-98)** | 39.1 [32–47] | +147 | **−8.7% ±18** | **−$349** | 26 |
| mc_c75_dog | replay (pre 10-06) | 55 (29-26) | 52.7 [40–65] | +165 | +36.7% ±40 | +$504 | — |
| | **prospective** | **184 (76-108)** | 41.3 [34–49] | +148 | **−2.9% ±17** | −$134 | 26 |
| mc6_dog2_all | replay (pre 10-16) | 73 (24-49) | 32.9 | +238 | +10.3% ±57 | +$188 | 1 |
| | **prospective** | **86 (29-57)** | 33.7 [25–44] | +243 | **−4.2% ±32** | −$91 | **77** |
| s52_fav_band_dog | replay (pre 10-11) | 137 (71-66) | 51.8 [44–60] | +141 | +24.1% ±20 | +$826 | — |
| | **prospective** | **88 (38-50)** | 43.2 [33–54] | +143 | **+4.1% ±26** | +$91 | 19 |

- **Replay → prospective degradation:** c75_dog_100plus −43.0pt (**t = −2.71**, significant);
  mc_c75_dog −39.6pt (t = −1.78); s52 −20.0pt (t = −1.20). The pattern is one-directional across
  all four.
- **Calibration of the selecting heads on their own prospective picks:** C75 tells its dogs
  56.2% — they win **39.1%** (+17.1pt overconfident; Brier .269 vs the market's .232 on the same
  picks). MC6: 42.6% claimed vs 33.7% actual (+8.9pt; Brier .225 vs market .214). The market
  out-predicts the selecting head **on the very rows the head chose**.
- **CLV:** ≈ zero everywhere (mean +0.1 to +0.4pp vs the opening line, medians slightly
  negative). The lanes are not beating the close; there is no late-information story.
- **Market benchmark:** blind women's dogs over the same window are **+5.3% /392** (from 10-06)
  — every model lane *underperforms* taking all women's dogs indiscriminately. (Blind itself is
  ≈1se from zero, so it is not an edge either.)

## 5. The women's underdog hypothesis

Prospective, women only:

| lane | n | ROI ± CI | ITF | tour+chall | +100..+150 | +151..+200 |
|---|---|---|---|---|---|---|
| c75_dog_100plus | 68 | **−18.7% ±30** | −11.0% /31 | −25.2% /37 | **−42.9% /40** | +8.5% /19 |
| mc_c75_dog | 80 | −8.1% ±28 | +1.2% /41 | −18.0% /39 | −32.0% /46 | +6.6% /22 |
| s52_fav_band_dog | 45 | +4.3% ±37 | −2.0% /20 | +9.3% /25 | −10.4% /27 | +26.4% /18 |
| mc6_dog2_all | 32 | −25.9% ±58 | −18.4% /11 | −29.9% /21 | −52.2% /9 | +34.2% /6 |

- **Concentration:** fragile everywhere. c75's women total −12.7u while its five best matches
  contributed +12.1u; one tournament (W35 Monastir) is +6.0u of it. s52's +1.9u total sits under
  +9.6u from its top five. Remove a handful of matches and every lane is deeply negative.
- The band pattern (short women's dogs terrible, +151..+200 positive) is exactly the kind of
  post-hoc subgroup Step 6 forbids acting on: 4 lanes × 4 bands × 2 genders ≈ 32 looks with ~3
  independent lanes; a couple of +ve cells at n≤22 is the expected noise.

**Verdict: not supported.** Three of four point estimates are negative; the only positive one is
0.3se from zero; every lane trails blind women's dogs; the heads are overconfident on their own
selections; CLV is nil; and the replay edge collapsed out-of-sample with the headline lane's
collapse statistically significant. Formally the CIs are wide (±17–37pt), so the hypothesis is
**rejected-leaning-inconclusive rather than proven dead** — but nothing here supports betting it,
and "the corrected historical edge was an in-sample artifact" is currently the best-supported
explanation.

## 6. No mid-test optimization

Nothing was tuned, retrained, re-thresholded, filtered, or subgrouped. The band/ITF splits above
are reporting, not new rules. The pre-registered window still closes at the **Oct 31 review**
(~100 settled per cell or the date, whichever first) — this report is the mid-window reading, not
an early stop: the stop/continue decision stays at the pre-registered checkpoint.

## 7. Recommendation for the next phase

1. **Do not build a new model to chase dog ROI yet** — the evidence says the current heads'
   dog-side margins are overconfidence, not information (same mechanism Phase 1 proved on the
   favourite side). New-model work should target the measured deficit — calibration and AUC vs
   the market — not lane ROI, which at these sample sizes cannot be the objective function.
2. **Let the window close on Oct 31** and judge the four lanes on the full prospective sample at
   these exact definitions. mc6_dog2_all carries 77 pending picks — a large open position in
   information terms; settle before judging it.
3. The honest live benchmark continues to accrue on its own: the **paper auto-bettor** records
   realizable Polymarket fills of the tab's picks — its ledger is the executable-price truth the
   lanes approximate.
4. If Oct 31 confirms this reading, the Phase 4 question is not "which dog rule" but **"can any
   head be made better-calibrated than the market on any segment at all"** — because without
   that, no selection rule downstream can be real.

---
*Artifacts: `reports/phase3/phase3_selections.csv` (per-selection audit trail);
`reports/phase2/` CSVs unchanged. Baseline commit `02ab0ea`.*
