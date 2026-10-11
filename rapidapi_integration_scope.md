# Wiring the RapidAPI tennis feed — verification result and scope

**2026-10-10.** You asked whether any of the API keys you sent deliver matches faster than
TennisRatio. One does, clearly. This is what it can and cannot replace, verified field by field,
and what wiring it would actually involve.

---

## 1. The speed gain is real

Host `tennis-api-atp-wta-itf.p.rapidapi.com`, your `.rapidapi_key`. The in-session MCP server
hits the same API and returns *"not subscribed"* — that is the MCP's credential, not yours.

| | RapidAPI (your key) | TennisRatio | Polymarket / TennisExplorer |
|---|---|---|---|
| matches on the day | **142 completed by 19:03 UTC** | **8%** | 42% (still playing) |
| 2026-10-09 completed | **225** (ATP 128 + WTA 97), complete | 75% of our 85 | 98% |
| **stat line same day** | **yes** | 5% today, 38% after 2 days | none |
| levels | tour + Challenger + **ITF** (M15/W15/W35/W50) | all | all |
| extras | set scores, **closing odds**, court, round, player IDs | — | scores |

---

## 2. Field verification — what reconciles against TennisRatio

Same match, same player, both sources. **Caveat: the free tier returned HTTP 429 mid-run, so
this is only 4 matches / 8 player-rows.** Treat the verdicts as provisional.

| field | mean abs diff | within tolerance | verdict |
|---|---|---|---|
| 1st serve won% | 0.05 | 100% | **reconciles** |
| 2nd serve won% | 0.00 | 100% | **reconciles** |
| aces | 0.00 | 100% | **reconciles** |
| double faults | 0.00 | 100% | **reconciles** |
| 1st serve in% | 0.53 (max 3.10) | 75% | close, off-by-one counts |
| BP saved% | 1.04 (max 8.33) | 88% | close, off-by-one counts |
| BP converted% | 1.04 (max 8.33) | 88% | close, off-by-one counts |
| return vs 1st% *(derived from opponent)* | 0.61 (max 4.86) | 88% | **the identity works** |
| hold% *(derived from score + breaks)* | 1.51 | 25% | **fails — see below** |

The derived return-side numbers work because of the head-to-head identity: your return-vs-1st is
the complement of your opponent's 1st-serve-won, and both players arrive in one call.

---

## 3. REVISED — the blockers turned out not to be blockers

**Section 3 originally said the feed could not replace TennisRatio because it lacks pressure
points and hold%. An ablation on 2026-10-10 refuted that, and this section replaces it.**

Model C refit on the shipped walk-forward recipe, identical rows, with each missing family
removed:

| variant | features | AUC | logloss | C dog ROI | 2026 ROI |
|---|---|---|---|---|---|
| full (shipped) | 35 | 71.20% | 0.6198 | +14.2% | +6.3% |
| − pressure | 33 | 71.23% | 0.6196 | +14.6% | +6.9% |
| − pressure, hold/break | 31 | 71.22% | 0.6196 | **+15.5%** | +7.6% |
| **API-feasible (−9 game-count features)** | **26** | **71.19%** | **0.6198** | **+14.6%** | **+7.1%** |

Dropping all nine game-count features costs **AUC −0.01pt, logloss +0.0000, dog ROI +0.4pt.**
C's features are heavily redundant: the serve/return point percentages already carry what hold%,
break% and pressure express — the same head-to-head identity measured in the match study, where
a player's hold% is the complement of the opponent's break%.

I had called `c_rp_diff_p1` Model C's biggest driver. That was inferred from one large feature
value on the Brengle match, never measured, and it was wrong.

**Still missing and still unavailable:** `unforcedErrors` and `winners` (null everywhere). That
line stays closed.

**Untested:** Model D, the Monte-Carlo layers and sUTR were not ablated. D leans on form,
last-10 and level features that come from *results* rather than stat lines, so it is likely
fine, but that is an assumption, not a measurement.

---

## 4. Request budget — this is the binding constraint

Keeping current needs **one stats call per completed match**: ~225/day, plus 2 results calls.
The free tier is **~50/day and rate-limits in bursts** (I hit 429 after roughly 25 calls in a
few minutes). So the free tier covers about **20%** of the need, and only if the calls are
spread out.

Options, cheapest first:

- **Results feed only, no stat lines (~2–4 calls/day).** Gets same-day *who won, set scores and
  closing odds* for 225 matches. Fits the free tier comfortably. Does **not** help model
  features. Mostly duplicates what Polymarket/TennisExplorer already give us at 95–100%.
- **Stat lines for board players only.** Fetch only matches involving players on tomorrow's
  card — roughly 150–280 calls/day. Still needs a paid tier.
- **Full daily stat lines (~230 calls/day).** Needs a paid tier.

---

## 5. If we wire it, the work involved

1. **ID mapping.** The feed uses its own `player1Id` / `matchId`; we key on TennisRatio slugs.
   `tennis_model_a.resolve()` matched the names it was given in testing, but needs a persisted
   id↔slug table plus a miss-list, the same shape as the ITF settlement name matching.
2. **Feature derivation + a dual-source merge.** New rows would carry the serve-side fields and
   *null* pressure points. Model C requires `c_sp`/`c_rp`, so a match with API-only stats cannot
   be priced by C as it stands — the merge has to be explicit about which features each source
   populates, and C needs a defined behaviour when pressure is missing.
3. **Backfill verification at scale.** Section 2 is 8 player-rows. Before trusting it, reconcile
   a few hundred across levels and resolve the off-by-one counts in 1st-serve-in% and the BP
   percentages.
4. **Mirror discipline.** Store both sides of every match, so the new source cannot reintroduce
   the one-sided winner bias that was just fixed. `tennis_archive.assert_mirrored()` covers this.

---

## 6. Revised recommendation

**The feed can price matches, so a paid tier is now justifiable.** That reverses what this
document said before the ablation.

Before spending, three things in order:

1. **Verify the field values at scale.** Section 2 rests on 8 player-rows because the free tier
   returned 429. Reconcile a few hundred across levels and resolve the off-by-one counts in
   1st-serve-in% and the BP percentages. Costs only time and quota.
2. **Ablate Model D, the MC layers and sUTR** the same way. C is clear; the others are assumed.
   Costs no API quota.
3. **Price the tier** against ~225 stats calls/day plus 2 results calls.

If 1 and 2 hold, this becomes a genuine same-day pricing path: the board could price a match a
few hours after the previous one finished, instead of waiting 1–3 days for TennisRatio.
