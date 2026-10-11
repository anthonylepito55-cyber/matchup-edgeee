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

## 3. What it cannot replace — the part that matters

**Three gaps, and two of them are the most important stats we have.**

1. **Serve / return pressure points — absent.** These produce `c_sp` and `c_rp`, and
   `c_rp_diff_p1` is **Model C's single biggest driver** (it was 3.5× the next term on the
   Brengle match). TennisRatio builds them from 32 clutch-by-score columns that this feed has
   no equivalent for. **Not derivable.**
2. **hold% / break% — not reliably derivable.** The feed gives break points *converted*
   (= breaks of serve) but no service-game count, and reconstructing service games from the set
   scores fails because we cannot know who served first in each set (25% inside tolerance).
   Per the match study, hold% is the single most decisive in-match stat (94.0% of 167k matches),
   so a wrong hold% is worse than none.
3. **`unforcedErrors` and `winners` — fields exist, null everywhere**, including Shanghai
   Masters, China Open and Wuhan. Confirms the earlier source audit. Do not reopen the UE line
   on this feed.

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

## 6. My recommendation

**Do not wire it for model features yet.** It cannot supply the two stats the models lean on
hardest (pressure points, hold%), so it would not let a fresh match be priced — it would only
make the serve-side columns arrive sooner, while C still waits on TennisRatio.

**What is worth doing now, cheaply:** the ingest fix shipped tonight already closed the
*who-won* lag (0–7 day one-sidedness 78.7% → 32.2%), and Polymarket/TennisExplorer already give
95–100% same-day results. So the remaining gap is narrower than it looked this morning.

**The question that decides it:** can Model C be made to work without pressure points? If a
pressure-free variant of C holds up in a walk-forward, then this feed becomes a genuine same-day
pricing path and a paid tier is justified. If it cannot, the feed is a convenience, not an
upgrade, and the free results-only tier is all it is worth.

I can run that test — refit C without `c_sp`/`c_rp` and compare — on existing data, for no
API quota at all. Say the word.
