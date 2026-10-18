# Phase 2 — Data Integrity Fixes & Full Lane Re-Audit (2026-10-18)

Scope honoured: **no model, weight, threshold, or filter was changed or tuned.** Both fixes are
row-eligibility flags; every number below is the mechanical consequence of excluding invalid
prices. The Phase 1 baseline file is untouched.

---

## 1. Code changes

One file: `backend/tennis_log.py` (patch script `_patch_phase2_price_guards.py`, backfill &
validation `_phase2_backfill_validate.py`). Deployed to EC2, service restarted.

| change | detail |
|---|---|
| `BAD_ROW_FLAGS` constant | the one list every lane gate now reads: `surface_bad, inplay_suspect, resolve_bad, price_synthetic, price_poststart`. The history of this file is three gates each missing a different flag; there is now a single list to forget. |
| `_apply_price_flags(df)` | computes the two new flags + `price_reject_reason` from immutable row fields; runs on **every new row at insert** and was backfilled over all 2,354 historical rows (persisted columns, atomic write). |
| `price_synthetic` detection | NOT just overround==1: mirrored pair (`p1 == -p2`) OR overround ≤ 1.0001 OR both odds positive OR bookmaker exactly `'Polymarket'`. (`'Polymarket (USA)'` = the real order-book feed, 254 rows, correctly not matched.) |
| `price_poststart` detection | `logged_at >= start_time_utc`, or **either timestamp missing/unparseable** → ineligible, per spec. Original timestamps were already immutable (`logged_at` is written once, never on settle — verified). |
| gates extended | the `bet()` loop; the three `(surface_bad, inplay_suspect, resolve_bad)` tuple gates (G/G2/MC2 blocks); the two conflict-pass gates that checked **surface_bad alone**; the orange band that checked only two flags; and `get_tennis_track_record`, which had **no flag filtering at all**. |

**Source of the synthetic rows (traced):** all 156 are `bookmaker=='Polymarket'` fallback rows
whose single probability is converted to mirrored American odds (`_american(p)`, `_american(1-p)`
in `polymarket_tennis.py` / `polymarket_data.py`) — a fair mark, not a quote.
**Why ~120 reached lanes:** the only price guard (`inplay_suspect`) requires an *opening* price
and >20pp drift — PM fallback rows never have openers; nothing ever looked at overround or
bookmaker; and the "keep the vigged twin" dedupe rule only applies when a vigged twin exists.
When PM was the only source, its de-vigged row was the only row.

One incident during patching: a text anchor matched the prefix of a longer line and spliced a
word; caught by compile check, repaired, verified (`_patch_phase2_price_guards.py` header notes it).

## 2. Validation

All on EC2 against the live log (2,354 rows), script `_phase2_backfill_validate.py`:

| check | result |
|---|---|
| V1 all 156 overround≤1 rows flagged synthetic | **PASS** |
| V2 all 156 mirrored pairs flagged | **PASS** |
| V3 all 157 `'Polymarket'` rows flagged (robust rule caught 1 extra vigged PM row the overround test missed) | **PASS** |
| V4 all 154 post-start rows + 17 unparseable-timestamp rows flagged poststart (171 total) | **PASS** |
| V5 zero FanDuel/DraftKings/Kalshi/`Polymarket (USA)` rows flagged without an independent trigger (no legitimate records rejected) | **PASS** |
| V6 every flagged row carries a reason string | **PASS** |
| V7 after the patched lanes ran: **zero lane picks reference a flagged row** | **PASS** |

Final flag counts: `price_synthetic` 157, `price_poststart` 171, overlap 2.
Exclusion overlap with old flags is small (synthetic∩inplay 14, synthetic∩resolve 9, …) — full
matrix in the validation output; per-row verdicts in `reports/phase2/phase2_row_exclusions.csv`.

## 3. Lane re-audit — before vs after

Snapshots from the live lane code before and after (`phase2_lanes_BEFORE/AFTER/DIFF.csv`,
per-lane metrics incl. win rate, avg odds and ROI ±2se in `phase2_lane_metrics.csv`).

- **213 lanes; 201 changed.** 6,438 settled lane-picks removed (50,702 → 44,264 — lanes overlap,
  so one bad row was counted many times). Aggregate lane P/L moved **−$11,038** (−$39,150 →
  −$50,188): net, the invalid prices had been **flattering** the lane board.
- Eligible settled rows: 2,171 → **1,729** (new guards alone removed 262 settled rows net of old flags).

**Biggest corrections — the former leaderboard family was the main beneficiary:**

| lane | n | ROI before → after |
|---|---|---|
| `c75_dog_100plus` (ex-#1 on the leaderboard) | 343→284 | **+14.9% → +10.0%** |
| `mc_c75_dog` | 296→239 | **+13.3% → +6.2%** |
| `pink_cc75_dog` | 265→220 | +12.8% → +7.2% |
| `x_dog` | 155→129 | −1.0% → −13.3% |
| `mc_c75_all` | 1313→1138 | −1.9% → −5.5% |

**The dog tab's current cells (for contrast, barely moved or improved):**

| lane | ROI before → after |
|---|---|
| `mc6_dog2_all` | −0.5% → **+2.5%** |
| `mc6_dog3_all` | −10.2% → −8.7% |
| `s52_fav_band_dog` | +13.2% → **+16.3%** |
| `mc6_fav6_w` | −13.4% → −10.6% |
| gold/−150 rules (n≤6) | ±5pt, samples too small to read |

Why c75 moved most: its lanes are the oldest and ITF-heaviest, so they accumulated the most
Polymarket-fallback (ITF) rows — 93 of 156 synthetic rows are `itf_women`.

## 4. Favourite findings re-checked (recalculated, not assumed)

Corrected eligible population (n=1,729) vs the removed rows (n=262), kept separate:

| finding | Phase 1 | corrected | removed rows alone |
|---|---|---|---|
| blind favourite ROI | −7.08% /1733 | **−7.20% /1729** | −4.40% /262 |
| market pred vs actual (favs) | 66.5 vs 65.7 | 66.6 vs 65.6 | 65.9 vs 65.6 |
| short favs −100..−150 | −11.6% | **−11.8%** | — |
| women's dogs | −0.07% /740 | **+0.06% /739** | +0.20% /137 |
| model_c favs 4pt+ | −13.9% (act 57.8 vs mkt 62.8) | **−14.0%** (57.7 vs 62.8) | — |
| c75 favs 4pt+ | −17.7% | −17.7% | — |
| mc2 / mc6 favs 4pt+ | −9.2% / −7.6% | −9.2% / −7.6% | — |
| market-free AUC vs market | .60–.68 vs .714 | .60–.68 vs **.707–.723** | — |

**Every Phase 1 conclusion survives the corrections** — expected, because Phase 1's "clean"
population had already excluded this contamination; the reconciliation differences (1,733 vs
1,729 rows, ±0.1pt) are exactly the 17 unparseable-timestamp rows the strict guard now rejects
and 1 extra vigged Polymarket row. What the fix changed is the **lane board**, which had never
excluded these rows.

## 5. Remaining data-quality issues

1. **10 unsettled rows older than 2 days** (Oct 7–14) — settlement gaps, not price issues.
2. **17 unparseable timestamps** — now safely ineligible, but the ingest should normalise them.
3. **Recon share** stays huge for new heads (mc3 77%, mc6 70% of settled rows) — display-only by
   design, but any analysis that drops the flag inherits replay bias.
4. **Training archive**: survivorship (1,760 players, ingested-on-demand) and 0 retirement
   markers in 618k rows — Phase 1 §5, untouched by this phase.
5. PM fallback keeps producing synthetic rows daily; they are now flagged at insert (board still
   displays them; lanes cannot bet them). The paper auto-bettor is unaffected — it already walks
   Polymarket's real order book instead of trusting logged prices.
6. The legacy `/api/tennis/track-record` headline numbers changed (it had no flag filtering);
   the old values are preserved in `phase2_lanes_BEFORE.csv` — nothing was silently overwritten.

## 6. Reliable enough for Phase 3 — and the one question

**Reliable now (survived audit + corrections, consistent mechanism):**
- Favourites are structurally unprofitable here: vig ≈ 4pt of the 4.8pt shortfall, the market's
  favourite probability is accurate, and every head's favourite-side "edge" is anti-predictive
  (recalibration tested and does not rescue it). This is the strongest, most repeatable result.
- Women's dogs sit at break-even blind (+0.06%), the only side carrying a measurable market error.
- The MC family is one signal (ρ .95–.99), C≈C75, G≈G2; model_c is badly miscalibrated
  (slope 0.65) and feeds C75/CMA/X.

**Not reliable:** every positive lane cell. The best survivor (`c75` dogs ≈ +10%, t≈1.3 after
correction) lost a third of its edge to data contamination alone, and all current tab thresholds
were fitted in-sample. Forward windows are days old.

**The single most important Phase 3 question:**

> **Does any dog-side selection rule retain positive ROI on women's dogs out-of-sample — or is
> the corrected c75/MC dog edge another in-sample artefact?**
> Concretely: pre-register the existing rules as they stand today (no re-tuning, per this phase),
> let the already-stamped forward lanes accumulate to ~100 settled bets per cell, and judge at a
> fixed date (the Oct 31 review). Everything else — new features, recalibration, head pruning —
> is downstream of whether any net-of-vig dog edge is real.

---
*Artifacts: `reports/phase2/phase2_lanes_BEFORE.csv`, `phase2_lanes_AFTER.csv`,
`phase2_lanes_DIFF.csv`, `phase2_lane_metrics.csv`, `phase2_row_exclusions.csv` (per-row verdicts
with reasons). None of today's changes are committed to git yet.*
