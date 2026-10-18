// ===========================================================================================
// THIS TAB READS MC6, NOT MC2 (2026-10-16, user call).
//
// The rule is unchanged -- same 4pt/6pt thresholds, same gender x band splits, same +300 cap and
// ITF-men exclusion. Only the HEAD changed, after both were scored with identical input quality
// on 633 identical rows (_mc6_vs_mc2_fair.py):
//
//                   MC2 as-of (fair)    MC6 as-of
//     dogs 6pt      +11.99% / 211       +26.57% / 203   t 2.80
//     TAB RULE      +8.61%  / 277       +23.37% / 281   t 3.35
//
// That comparison exists because MC6's raw advantage was confounded: on its backfilled rows it
// replayed with correct as-of ratings while MC2's value came from states up to four days stale.
// Re-pricing MC2 as-of removed the confound and the lead GREW -- correct ratings made MC2 worse,
// so staleness had been flattering MC2, not MC6.
//
// READ THE SAMPLES. MC6's lanes refuse recon rows, as every money lane here does, so they START
// NEAR EMPTY: n=71/57/9/5 against MC2's 459/396/36/34. The picks are MC6-driven from today; the
// ROI beside them needs about two weeks. MIN_CELL_N stays at 25, so thin cells read as thin
// rather than being promoted early.
//
// MC2's lanes keep scoring underneath. Reverting is these four substitutions inverted.
// ===========================================================================================
import React, { useEffect, useState } from 'react'

// 🐕 DOG PICKS (2026-10-14, user: "make a new tab called dog picks and add all of the picks
// with these cells into that tab as well as 6-4 split dogs, mc2 dog flips, c75 dog flips and
// fade form dogs").
//
// Every pick comes from tennis_log's own lane records (study[lane].picks), which bet() writes
// for each lane named in _PICK_LANES. No predicate is re-implemented here, so the tab cannot
// drift out of lockstep with the lanes that score it -- the one thing that has gone wrong
// repeatedly when board logic and lane logic were written twice.
//
// The ROI and dollar figures are the lane's FORWARD record from the frozen log. They are shown
// without rounding up the uncertainty: `t` is ROI over its own standard error, and at these
// prices a 20-bet cell needs roughly 40 points of ROI to reach t=2. 104 dog cells were measured
// and 4 clear t=2, which is about what 104 lanes on ~1,000 shared games would throw up by
// chance -- so these are candidates, not proven edges, and the tab says so rather than
// implying a green number is a verdict.

// label, lane key, and a one-line note. Ordered by how much evidence each has, not by ROI.
// 🟡 FAVOURITE CELLS (2026-10-14). Flagged fav:true so they are excluded from every dog
// aggregate -- the daily boxes, the price bands and the pink rules all describe dog bets at plus
// prices, and folding a -150 favourite into them would corrupt the numbers used to decide dog
// bets. They get their own box and their own colour.
const YELLOW = '#e3b341'
const GOLD = '#ffd700'
const FAV_CELLS = new Set(['mc6_fav4_w', 'mc6_fav4_m', 'mc6_fav_band_m', 'mc6_fav6_w',
  'mc6_fav150_m', 'mc6_fav150_w'])
const isFavPick = p => p.odds != null && p.odds < 0

// TWO BANDS, ONE COLOUR (2026-10-14). Originally shipped as yellow + gold on the reasoning that
// the deeper band was the stronger half; that was measured again and retracted the same day --
// see ONE_GOLD below. Both bands are gold. Each still carries its own tag and its own n on the
// badge, so the price band is readable and the two are never read as one number.
//     -100..-150  n=28  19-9   67.9% hit vs 55.5% needed  +22.31%  t 1.40
//     -150..-200  n=23  18-5   78.3% hit vs 63.2% needed  +23.50%  t 1.73
// ONE_GOLD (2026-10-14, user "oaky keep both gold"). Both bands are gold now, because they are
// one cell and the two-colour split implied a ranking the numbers do not support:
//
//                    -100..-150        -150..-200
//     pooled         +22.31% / 28      +23.50% / 23      <- 1.2 points apart
//     forward        +21.92% / 12      +31.53% / 12
//     recon          +22.60% / 16      +14.74% / 11      <- the SHALLOW band wins this window
//     blind band      -2.83% / 110      -4.34% / 129
//
// The headline gap is entirely the forward week. On the corrected recon the shallower band is
// better by 8 points. _patch_gold_fav.py called the deeper band "the stronger half" and gave it
// the brighter colour on that basis; that reasoning is retracted. Each half is 12 forward bets
// inside the same seven-day frozen window, which cannot separate them from each other.
//
// The BAND TAGS stay on the badge so the price is still readable, and each band keeps its own
// record in the tooltip -- what goes is the claim, carried by the colour, that one beats the other.
// FAV_GENDER_BANDS (2026-10-14, user "add any positive dog cells or favorite cells to the pink
// or gold highlight"). Gold is now gender x band, on the same forward-only rule as pink, with a
// floor of TEN settled forward bets -- without it this marks cells of one and two bets, three of
// which read 100% hit. MC2 4pt+ over the de-vigged market, forward / (corrected recon):
//
//     -100..-150   women +21.92% /12  (+22.60% /16)   men +18.51% /12  (-30.54% /23)  <- ADDED
//     -150..-200   women +33.17% /13  (+14.74% /11)   men -13.95% /13                 no
//     -200..-250   women -100.0% /1   under floor     men +46.49% /2   under floor
//     -250..-400   women +34.37% /2   under floor     men -21.51% /5                  no
//
// So gold is NOT symmetric: women get both bands, men get the shallow one only. The mens cell is
// marked because the rule is the forward record, but its forward half is its ONLY positive
// evidence -- see its tooltip, which leads with the twelve bets.
const FAV_GENDER_BANDS = [
  { lo: -150, hi: -100, g: 'w', tag: 'FAV −100/150', col: GOLD, rgba: '255,215,0', note: 'WOMEN -100..-150. Forward +21.92% on 12, corrected recon +22.60% on 16 -- the two windows agree almost exactly, which is the most consistent thing on this board. Pooled +22.31% on 28 (19-9, 67.9% hit against 55.5% needed, t 1.40). Same colour as the deeper band because the two are one cell, 1.2 points apart pooled.' },
  { lo: -200, hi: -150, g: 'w', tag: 'FAV −150/200', col: GOLD, rgba: '255,215,0', note: 'WOMEN -150..-200. Forward +31.53% on 12, corrected recon +14.74% on 11. Pooled +23.50% on 23 (18-5, 78.3% hit against 63.2% needed, t 1.73). The higher headline is the forward week; this half is the weaker one on recon, so it is not "the stronger half" and is not coloured as one.' },
  { lo: -150, hi: -100, g: 'm', tag: 'FAV −100/150 ⚠', col: GOLD, rgba: '255,215,0', note: 'MEN -100..-150. ADDED 2026-10-14 under the rule that a positive FORWARD record earns the highlight -- READ THE SAMPLE. Forward +18.51% on TWELVE bets across five days (8-4, 66.7% hit against 56.8% needed, t 0.77). Everything else about it is negative: corrected recon -30.54% on 23, nearly twice the sample; pooled -13.72% on 35 against a blind band of -14.14% on 152, so MC2 adds nothing pooled. There is also NO threshold gradient -- 4pt+ and 6pt+ are the IDENTICAL twelve bets, so not one forward pick sits between 4 and 6 points and the threshold was never really tested here. Three of the twelve are ITF men, the league excluded from the dog side. The womens half of this band is +21.92% forward AND +22.60% on recon, which is what a real cell looks like. Treat this as a watch mark.' },
]
// THE LANE EACH GENDER'S GOLD MARK READS (2026-10-16). One helper because the same pair was
// hardcoded in three places -- markOf, favHist and the live row -- and when the gates moved from
// the 4pt lanes to these, all three kept reading the old ones and no favourite could ever mark.
// Men use a capped 3-6pt BAND (their favourite side is an inverted U), women a >=6pt FLOOR
// (theirs climbs). Different shapes on purpose; see the cell tooltips.
const FAV_LANE = (g) => (g === 'w' ? 'mc6_fav6_w' : 'mc6_fav_band_m')

// A READABLE PRICE TAG, not a gate (2026-10-16). favBandOf used to RESTRICT the mark to
// -100..-200 (women) / -100..-150 (men); with EV>=0 applied that cap was costing money --
// outside it women are +11.40% on 18 and men +18.11% on 27, and the men's cap excluded
// -150..-200, the best band either gender has at +44.60% on 10 (t 2.76). So the gate is now the
// point rule alone and the band only labels the price.
const FAV_PRICE_TAGS = [
  { lo: -150, hi: -100, tag: 'FAV \u2212100/150' },
  { lo: -200, hi: -150, tag: 'FAV \u2212150/200' },
  { lo: -300, hi: -200, tag: 'FAV \u2212200/300' },
  { lo: -500, hi: -300, tag: 'FAV \u2212300/500' },
]
// WHAT EACH MC6 FAVOURITE LANE IS, and what its record actually says. The tooltip is built from
// these, because every MC6 favourite is gold now (2026-10-16, user "i want all favorites mc6 on
// the dog board highlighted gold") and the colour therefore no longer tells you which rule fired
// or whether that rule wins.
const FAV_RULE_NOTES = {
  mc6_fav6_w: 'WOMEN >=6pt FLOOR, EV>=0 at the offered price: +14.79% on 57 (t 1.50) -- -100/150 +17.81%/23, -150/200 +16.36%/19, -200/300 +11.58%/10, -300/500 +1.37%/5, nothing deeper. A floor because the womens favourite side climbs with the margin.',
  mc6_fav_band_m: 'MEN capped 3-6pt BAND, EV>=0 at the offered price: +32.42% on 20 (t 2.41). The EV check matters here -- it removes 14 of the 34 band picks, and without it the band is +24.72% on 34. Capped because the mens favourite side is an inverted U.',
  mc6_fav4_w: 'WOMEN 4pt+ at -100..-200, no EV check: MC6 +11.57% on 50 (t 1.00) -- replay +19.87% on 41, forward -26.26% on 9.',
  mc6_fav4_m: 'MEN 4pt+ at -100..-200, no EV check and no cap: MC6 +12.13% on 48 (t 1.04) -- replay +17.41% on 43, forward -33.25% on 5. (The -9.21% on 74 once quoted for this lane was MC2s record, not MC6s.)',
  mc6_fav150_m: 'MEN -150..-200 RULE: MC6 2-8pt over the market and positive EV at the offered price. Replay +44.80% on 12 (t 3.38); the >=8pt tail it leaves out is -19.34% on 12. Six band shapes were tried before this one, so the t overstates it. The lane records only from 2026-10-17.',
  mc6_fav150_w: 'WOMEN -150..-200 RULE: MC6 6+ points over the market (EV is automatic there). +16.36% on 19 -- replay +23.61% on 14, forward -3.94% on 5. The lane records only from 2026-10-17.',
}
// No MC6 favourite lane has a losing record across both windows, so nothing is flagged.
// The set stays so a lane that turns negative can be listed here in one edit.
const FAV_NEGATIVE = new Set([])

const favMarkOf = (p, keys) => {
  if (p.odds == null || p.odds >= 0) return null
  const fired = (keys || []).filter(k => FAV_CELLS.has(k))
  if (!fired.length) return null
  // -150..-200 HAS ITS OWN RULES (2026-10-17, user "mark those two rules gold"): men 2-8pt + EV,
  // women 6pt+. Inside that band ONLY the pick's own gender's band lane paints gold; every other
  // MC6 favourite there still lists, unmarked. -150 itself is the -100..-150 band, as in the tags.
  if (p.odds >= -200 && p.odds < -150) {
    const g150 = /wta|itf_women/i.test(String(p.league || '')) ? 'w' : 'm'
    if (!fired.includes(g150 === 'w' ? 'mc6_fav150_w' : 'mc6_fav150_m')) return null
  }
  const b = FAV_PRICE_TAGS.find(x => p.odds >= x.lo && p.odds <= x.hi)
  // when EVERY rule that fired has a losing record, say so first -- the colour cannot
  const allBad = fired.every(k => FAV_NEGATIVE.has(k))
  const lead = (allBad
    ? 'CAUTION -- the only MC6 favourite rule that fired on this pick has a LOSING record. Gold here means "MC6 likes this favourite", which you asked to see on every one of them; it does not mean the cell wins. '
    : 'Gold = an MC6 favourite. Every MC6 favourite is marked (your call, 2026-10-16), so the colour says MC6 rates this favourite over the market, NOT that the rule behind it is proven. ')
  const rules = fired.map(k => FAV_RULE_NOTES[k] || k).join('  ')
  const deep = (!b
    ? ' THIS PRICE IS DEEPER THAN -500, WHERE THERE IS NO SAMPLE AT ALL (n=1 men, n=0 women). Clearing EV there needs MC6 above about 93%, the region where a large claimed margin usually means the head misread the match rather than found value. Unmeasured, not endorsed.'
    : '')
  const caveat = ' READ THE SAMPLE: these records are mostly MC6 as-of REPLAY. The forward window opened 2026-10-15 and holds 12 settled womens bets on the 6pt floor and 1 mens bet on the 3-6pt band, and the dog gates on this same head are negative forward (men 2pt -11.37% on 43, women 3pt -10.36% on 44).'
  return {
    tag: (b ? b.tag : 'FAV \u2212500+ \u26a0') + (allBad ? ' \u26a0' : ''),
    col: GOLD, rgba: '255,215,0',
    note: lead + rules + deep + caveat,
  }
}

// gender inlined; genderOf is declared further down this module. KEPT for reference: this was the
// old price GATE, replaced by favMarkOf above. Nothing calls it now.
const favBandOf = (p) => {
  if (p.odds == null || p.odds >= 0) return null
  const g = /wta|itf_women/i.test(String(p.league || '')) ? 'w' : 'm'
  return FAV_GENDER_BANDS.find(b => b.g === g && p.odds >= b.lo && p.odds <= b.hi) || null
}

const CELLS = [
  ['🟡 MC6 4pt+ FAV · WOMEN -100..-200', 'mc6_fav4_w', 'MC6 rates this WOMENS favourite 4+ points above the de-vigged market, priced -100..-200, with no EV check. MC6 record: +11.57% on 50 (t 1.00) -- replay +19.87% on 41, forward -26.26% on 9. (The +22.85% on 51 that used to be quoted here was MC2s record.)'],
  ['🟡 MC6 FAV −150..−200 · MEN 2–8pt', 'mc6_fav150_m',
   'MENS favourites priced -150..-200 where MC6 is 2 to 8 points over the de-vigged market AND the bet is positive EV at the offered price. Replay +44.80% on 12 (t 3.38). Every mens favourite in this band is -13.04% on 115, and the >=8pt tail this rule leaves out is -19.34% on 12 -- the mens favourite side is an inverted U, sharper in this band than anywhere. Without the EV check it is +43.51% on 21 (same ROI, more volume); kept because 14 of 16 negative-EV favourite marks lost live on 2026-10-13. READ THE SAMPLE: six band shapes were scanned to choose 2-8pt, so the t overstates it, and there is ONE forward bet. The lane records only from 2026-10-17, so it opens at n=0.'],
  ['🟡 MC6 FAV −150..−200 · WOMEN 6pt+', 'mc6_fav150_w',
   'WOMENS favourites priced -150..-200 where MC6 is 6+ points over the de-vigged market (every such pick also clears EV). +16.36% on 19 -- replay +23.61% on 14, forward -3.94% on 5. Every womens favourite in this band is -1.46% on 96, about fair. Same floor as the all-price womens gate; the 4-6pt slice the 4pt lane would paint here is flat. >=7pt reads +32.40% on 12 but the whole difference is 7 bets. The lane records only from 2026-10-17, so it opens at n=0.'],
  ['🟡 MC6 FAV 6pt+ · WOMEN', 'mc6_fav6_w',
   'MC6 six or more points over the de-vigged market on a WOMENS favourite, still positive EV at the price offered. A FLOOR, not a band, because the womens favourite side CLIMBS with the margin where the mens decays -- >=4pt +9.3% on 68, >=6pt +14.8% on 57, >=8pt +19.0% on 41, against a baseline of -7.9% on 405. The 4-8pt band first proposed measures -5.2% on 27: for women a cap removes the good half. 6pt rather than 8pt keeps 57 picks instead of 41 for about 4 points of ROI, which on replay-only evidence is the better trade. READ THE SAMPLE: 57 picks, almost all MC6 replay, and it does not clear t=2.'],
  ['🟡 MC6 FAV BAND 3-6pt · MEN', 'mc6_fav_band_m',
   'MC6 between 3 and 6 points over the de-vigged market on a MENS favourite, and still positive EV at the price offered. A BAND rather than a floor because the mens favourite side is an inverted U: backing every mens favourite is -8.5% on 444 (t -2.61), the 3-6pt band is +21.2% on 35 (t 2.07), a plain floor of 3pt is only +10.2% on 88, and the tail above 6pt that the cap removes is +3.0% on 53. A huge claimed margin on a short price usually means the head misread the match rather than found value. Best cells: -150..-200 +44.6% on 10 (t 2.93) and -100..-150 +31.5% on 8. The EV condition is load-bearing -- only 21 of the 35 band picks clear it, so without it a third of the marks would be bets MC6 itself prices as losers. READ THE SAMPLE: 35 picks, 4 forward. Replay evidence, your call.'],
  ['🟡 MC6 4pt+ FAV · MEN -100..-200', 'mc6_fav4_m', 'MC6 rates this MENS favourite 4+ points above the de-vigged market, priced -100..-200, with no EV check and no cap. MC6 record: +12.13% on 48 (t 1.04) -- replay +17.41% on 43, forward -33.25% on 5. It is NOT the losing control it was labelled as: the -9.21% on 74 was MC2s record. In -150..-200 its uncapped tail is the weak part (6pt+ -3.46% on 18).'],
  ['🟦 s52 SEASONAL-BAND DOG · +100..+200', 's52_fav_band_dog', 'Back the market DOG at +100..+200 when the FAVOURITE owns BOTH 52-week seasonal stats, hold% and break% -- a FADE of the seasonal stat leader, not a follow. The sibling cell where the DOG owns both is only +3.40% on 129, which is what makes the direction the finding. THE ONLY CELL ON THIS BOARD CLEARING t=2: +19.80% on 183 (92-91, 50.3% hit, $+905.75, t 2.25), men +13.49% on 94 and women +26.46% on 89 (t 2.04). By band: +100..+150 is +18.11%/119 (men +17.39/66, women +19.00/53) and +150..+200 is +22.94%/64 (men +4.29/28, women +37.44/36). The lane is hard-gated to +100..+200 and that ceiling is earned -- re-run without it, +200..+250 is -14.94% on 65 and +250..+300 is -11.21% on 38. CAVEAT: the frozen window is 39 days and the rule replays inside it, so part of this record is in-sample for the rule itself.'],
  ['🟤 MC6 2pt+ DOG · MEN', 'mc6_dog2_all',
   'MC6 two or more points over the de-vigged market on the dog -- THE MENS GATE (2026-10-16). Mens record on the tab population: +8.22% on 182 (t 0.85), forward +7.22% on 27. By band: +100..+150 +38.64% on 73 (t 3.06; forward +21.64% on 14), +150..+200 -24.22% on 50, +200..+250 +12.53% on 38, +250..+300 -28.10% on 21. The mens edge lives at +100..+150 and alternates above it, which is why only two mens bands are pink. Mostly MC6 as-of REPLAY; the forward window opened 2026-10-15.'],
  ['🟤 MC6 3pt+ DOG', 'mc6_dog3_all',
   'MC6 three or more points over the de-vigged market on the dog -- THE WOMENS GATE (2026-10-16; men moved to 2pt the same day). Womens record on the tab population: +23.62% on 173 (t 2.21), but forward -0.82% on 34. By band: +100..+150 +12.93% on 68 (forward -19.86% on 14), +150..+200 +41.38% on 47, +200..+250 -15.70% on 27, +250..+300 +54.42% on 31. Mostly MC6 as-of REPLAY; the forward half is flat so far.'],
  ['🟤 MC6 6pt+ DOG', 'mc6_dog6_all',
   'MC6 six or more points over the de-vigged market on the dog, any price. Tab population: men +9.77% on 128 (forward +12.95% on 20), women +26.86% on 138 (t 2.19; forward -8.15% on 26). By band, men: +100..+150 +21.69%/52, +150..+200 -4.97%/34, +200..+250 +14.65%/26, +250..+300 -5.62%/16; women: +3.14%/51, +45.74%/38, -1.04%/23, +70.46%/26. (The ladder once quoted here was MC2s, not MC6s.)'],
  ['🟤 MC6 4pt+ DOG', 'mc6_dog4_all',
   'MC6 four or more points over the de-vigged market on the dog, any price. Tab population: men +3.63% on 160 (forward -1.64% on 25), women +27.74% on 160 (t 2.47; forward -9.34% on 29). By band, men: +100..+150 +25.59%/61, +150..+200 -15.80%/45, +200..+250 +6.50%/34, +250..+300 -24.50%/20; women: +15.07%/61, +41.27%/45, -8.96%/25, +65.07%/29. Replay-heavy. (The +13.15% on 91 once quoted here was MC2s.)'],
  ['🟤 MC2 TAKE DOG · unstamped', 'mc2_take_dog_all',
   'Your take rule at the new -6 threshold, counting every frozen row rather than only those after the rule was written. The date-stamped lane (mc2_take_dog) is the in-sample-free version and is much smaller.'],
  ['🧮³ MC3 TAKE DOG · unstamped', 'mc3_take_dog_all',
   'The same rule on MC3, counting every frozen row. MC3 is starved on the stamped lane because 1,326 of its 1,400 rows are recon backfills.'],
  ['🧮⁵ MC5 TAKE DOG · unstamped', 'mc5_take_dog_all',
   'The same rule on MC5. Only 13 of its 565 rows are forward, so this is near-empty and will stay that way for weeks -- shown so it accrues against a recorded rule rather than starting from scratch later.'],
  ['🧊 FADE FORM · dogs', 'pf_c75_dis_dog',
   'c75 pick where the pure-results form overlay points at the OPPONENT, and the pick is the dog. Best t on the board (2.40).'],
  ['🔀 6-4 SPLIT · dogs', 'split64_fade_dog',
   'The 10 heads split exactly 6-4; back the 4-minority when it is the dog. Even across genders (M +27.6 / W +27.7).'],
  ['⚄ c75 DOG FLIP', 'mc_c75_dog',
   'c75 puts the market underdog past 50% and picks it outright. The largest honest sample of any flip (no recon rows).'],
  ['🟤 MC2 DOG FLIP', 'mc2_dog_flip',
   'MC2 puts the market dog past 50%. The LANE is only days old (MC2_LIVE_FROM 2026-10-13), so n here is tiny; across the whole forward log MC2 flips are +14.3% on 84.'],
  ['🐕 c75 DOG +100 up', 'c75_dog_100plus',
   'Every c75 dog priced +100 or longer. Biggest dollar earner on the board and the deepest sample.'],
  ['🎾 RETURNER DOG (W)', 'returner_dog_w',
   'Women, dog wins the return-pressure gap. Highest ROI of any dog cell, on only 25 settles.'],
  ['🎯 ALL-ROUND DOG (W)', 'allround_dog_w',
   'Women, dog better on serve AND return pressure. 22 settles.'],
  ['⚄ c50+c75 DOG · no D', 'cc75_nod_dog',
   'Both C-MC variants back the dog and Model D does NOT. 77 settles.'],
  ['⭐ STAR DOG (resolver 1)', 'cr1_stardog',
   'The conflict-resolver tier-1 star dog. 52 settles.'],
  ['⚄ c50+c75 DOG', 'cc75_dog', 'Both C-MC variants back the dog, D ignored.'],
  ['🩷 FADE-B DOG (M)', 'pink_fadeb_dog_m', 'Men, pink fade-B dog watch cell.'],
  ['🩷 MC2 DOG (pink)', 'pink_mc2_dog', 'The pink MC2 dog watch cell.'],
  ['⛔ TIER-AVOID · dogs', 'tier_avoid_dog',
   'The dog side of cards the board labels AVOID. Counter-intuitive and worth watching: the avoid applies to the favourite, and the dog has paid.'],
  ['Ⓓ D-MA DOG', 'dma_dog', 'Model D market-aware picks the dog.'],
  ['🟤 MC2 DOG BAND', 'mc2_dog_band', 'MC2 dog inside the +100..+250 price band.'],
  ['⚪ C+GRAY DOG late', 'cgray_dog_late', 'C and the gray line on the dog, later rounds.'],
  ['🔁 OVERLAY DOG', 'ovl_dog', 'The overlay dog cell.'],
  ['⚔ FIGHT MC4 DOG', 'fight_mc4_dog', 'MC4 disagrees with the market on the dog.'],
]

// SPLIT A LANE'S CELL INTO ONE CELL PER PRICE BAND (2026-10-14, user "split up the prices on
// the dog tab the cells mc2 6pt+ dog and mc2 4pt+"). A blended all-price number hides exactly the
// structure this board runs on -- the men's 4pt lane reads -3% across all prices while being +27%
// at +100..+150.
//
// Records are summed from the lane's OWN picks, so they cannot drift from the lane that scores
// them. Each band cell KEEPS THE LANE KEY (the pink rules and MARK_CELLS match on it) and carries
// a separate uid for React and display; dedupe() keys on the match, so a shared key is harmless.
function splitByBand(cel) {
  const out = []
  for (const [lab, lo, hi] of BANDS) {
    // SAME BASIS AS THE REST OF THE TAB (fix, 2026-10-14): no ITF men, nothing above +300.
    // Without this the band cells were scored on a different population and flipped signs --
    // mc2_dog6_all +200..+250 men read -5.96% with four ITF-men picks in it and +11.95% without,
    // while being a PINK source, so the board contradicted its own mark.
    const ps = (cel.picks || []).filter(p => p.odds != null && p.odds >= lo && p.odds <= hi
      && priceOK(p) && leagueOK(p))
    if (!ps.length) continue
    const mk = (sub) => {
      const done = sub.filter(p => p.won != null)
      const wins = done.filter(p => p.won).length
      const profit = done.reduce((a, p) => a + (p.pnl || 0), 0)
      return { n: done.length, wins, profit_usd: Math.round(profit * 100) / 100,
               staked_usd: 25 * done.length,
               roi_pct: done.length ? Math.round(1000 * profit / (25 * done.length)) / 10 : 0,
               pending: sub.length - done.length }
    }
    const men = ps.filter(p => genderOf(p) === 'm')
    const women = ps.filter(p => genderOf(p) === 'w')
    const c = { ...mk(ps), m: mk(men), w: mk(women), m_dog: mk(men), w_dog: mk(women),
                dog: mk(ps), fav: mk([]), m_fav: mk([]), w_fav: mk([]) }
    out.push({ ...cel, uid: `${cel.key}@${lab}`, label: `${cel.baseLabel} · ${lab}`,
               c, cShown: c, hidden: [], picks: ps, t: tstat(c) })
  }
  return out
}

function tstat(c) {
  const n = c && c.n, w = c && c.wins, roi = c && c.roi_pct
  if (!n || w == null || roi == null || n < 2) return null
  const r = roi / 100
  if (w <= 0) return null
  const gain = (r * n + (n - w)) / w          // implied average winning payout
  const varr = (w * gain * gain + (n - w)) / n - r * r
  if (!(varr > 0)) return null
  return r / (Math.sqrt(varr) / Math.sqrt(n))
}

const usd = v => `${v < 0 ? '-' : '+'}$${Math.abs(v || 0).toFixed(2)}`

// PRICE CAP (2026-10-14, user "And remove anything over +300"). Applies to every pick list and
// to every aggregate on this tab. It is also where the measured evidence stops: above +300 the
// archive runs -17% to -18% at any model margin, and the board's own +250..+300 cell was capped
// at 300 for the same reason.
const MAX_AM = 300
const priceOK = p => p.odds != null && p.odds <= MAX_AM

// LEAGUE GATE (2026-10-14, user "Okay remove all itf men"). ITF men is the only league whose
// dog ROI is negative on this tab's own basis: -26.15% on 27 (9-18, -$176.50, t -1.30) against
// WTA +20.98%, ATP challenger +11.56%, ATP tour +11.43% and ITF women +14.39%. It was also the
// half dragging collapsed ITF down to +1.66% while ITF women alone is +14.39%.
//
// 27 bets is not a settled verdict, so this is a lean the user called rather than a proven dead
// cell -- though it fits the ITF stats audit, where 91% of ITF players have no stat context and
// the heads are working from nearly nothing. The LANE records underneath still include ITF men,
// so the per-cell ROI and t columns stay full-sample and this is one constant to reverse.
// PINK_FORWARD_ONLY (2026-10-14, user: "only mark positive cells pink gender specifc / for
// mc2", then "by add all the positive ones i meant forward test postiive ones btw").
//
// THE GATE IS THE FORWARD RECORD ALONE -- the frozen pre-match log. The corrected recon is
// reported in every tooltip but does not decide, which is the standing rule for this project.
// That admits two cells whose recon half is bad; both say so on the card.
//
// MC2 4pt+ over the de-vigged market on the dog, by gender x band. Lane discipline
// (surface_bad / resolve_bad / inplay_suspect / void out, ITF men out), $25 flat. Numbers and
// method: backend/_patch_pink_forward_only.py and backend/_dog_band_ladder.py.
//
// PINK_BAND_FIXED 2026-10-14: my scan scripts tested each band with `lo <= odds <= hi`
// INDEPENDENTLY, so every dog priced at a round boundary (+150/+200/+250) was counted in two
// bands. bandOf here has always assigned one band per pick, first match wins, so the board was
// right and the scan was wrong. Fixing it flipped men +250..+300 from +5.24% to -16.11% forward,
// and that pink rule is gone. Corrected, all MC2 4pt+ on the dog, forward (recon in brackets):
//
//     band        gender  n   W-L    FORWARD      t      (recon)         blind band
//     +100..+150  men     48  28-20  +27.48%     1.77    (+7.20% / 85)   +7.39% / 291   PINK
//     +100..+150  women   38  21-17  +21.95%     1.23    (+6.85% / 53)   -8.81% / 200   PINK
//     +150..+200  men     36  10-26  -25.39%    -1.27    (-17.98% / 53)  -17.12% / 145  no
//     +150..+200  women   30  15-15  +37.73%     1.50    (-10.33% / 46)  +8.38% / 111   PINK
//     +200..+250  men     18   7-11  +30.61%     0.79    (-0.00% / 35)   +3.99% / 88    PINK
//                 ^ this cell alone uses the 6pt lane (2026-10-14, user "yes men 200 to
//                 250 6 pt"). At 4pt it was +6.86%/22 t 0.21 with BOTH windows positive;
//                 at 6pt the forward is four times better but the recon goes exactly flat.
//                 6pt is not better anywhere else -- women +100..+150 falls +21.95 -> +7.77.
//     +200..+250  women   21   5-16  -23.00%    -0.77    (+85.42% / 12)  -1.74% / 66    no
//     +250..+300  men     18   4-14  -16.11%    -0.44    (-46.86% / 22)  -40.36% / 58   no
//     +250..+300  women   20   8-12  +47.80%     1.18    (+4.00% / 25)   +24.24% / 51   PINK
//
// ONE THRESHOLD, NOT ONE PER CELL: 4pt is forward-positive in every cell that is forward-positive
// at all, so nothing is tuned per band. It is also the more inclusive of the two lanes that exist
// -- at 6pt the same six cells are all positive too, but on 16-41 bets instead of 21-48. The two
// excluded cells are negative at EVERY rung from 2pt to 10pt.
//
// WEAKEST ADMISSIONS, flagged on their own badges: men +250..+300 (forward +5.24%/21 against a
// recon of -43.74% and a blind band of -28.54% -- the most violent disagreement on the board);
// women +250..+300 (blind band already +31.89%, recon exactly 0.00%); men +200..+250 (t 0.21).
//
// Display only: no lane, no board mark, nothing filtered out.
const PINK = '#f778ba'
const PINK_TAG = '\u{1F9E1} '
const PINK_RULES = [
  { lo: 100, hi: 150, g: 'm', tag: 'MC6 2pt+ M', cells: new Set(['mc6_dog2_all']), tip: 'MEN, +100..+150. MC6 two or more points over the de-vigged market on the dog. MC6 record: +38.64% on 73 (46-27, t 3.06) -- replay +42.68% on 59, forward +21.64% on 14 (8-6). Blind mens dogs in this band are +14.75% on 141, and +28.55% on 20 forward -- so forward, MC6 is not yet beating simply backing every dog here. The strongest MC6 dog cell on replay; the forward half is far too small to confirm it.' },
  { lo: 100, hi: 150, g: 'w', tag: 'MC6 3pt+ W', cells: new Set(['mc6_dog3_all']), tip: 'WOMEN, +100..+150. MC6 three or more points over the de-vigged market on the dog. MC6 record: +12.93% on 68 (35-33, t 0.96) -- replay +21.43% on 54, but FORWARD -19.86% on 14 (5-9). Blind womens dogs here are -1.96% on 162 overall and +7.40% on 35 forward. THE WEAKEST PINK CELL: its forward half is negative and below the blind band. If it is still non-positive at 25 forward settles the tab drops it automatically.' },
  { lo: 150, hi: 200, g: 'w', tag: 'MC6 3pt+ W', cells: new Set(['mc6_dog3_all']), tip: 'WOMEN, +150..+200. MC6 three or more points over the de-vigged market on the dog. MC6 record: +41.38% on 47 (24-23, t 2.02) -- replay +49.21% on 39, forward +3.25% on 8 (3-5). Blind womens dogs here are +24.68% on 75 but -34.94% on 17 forward, so forward MC6 is well ahead of the blind band, on a tiny sample. The MENS half of this band loses for MC6 at every gate (2pt -24.22% on 50) and is off the tab.' },
  { lo: 200, hi: 250, g: 'm', tag: 'MC6 2pt+ M', cells: new Set(['mc6_dog2_all']), tip: 'MEN, +200..+250. MC6 two or more points over the de-vigged market on the dog. MC6 record: +12.53% on 38 (13-25, t 0.49) -- replay +10.18% on 33, forward +28.00% on 5. Blind mens dogs here are +3.35% on 51. The signal is MC6 agreeing with the dog at all -- when it does NOT, the dog is -45.42% on 12 -- and margin size adds little until about 10pt. Positive but unproven: a watch mark.' },
  { lo: 250, hi: 300, g: 'w', tag: 'MC6 3pt+ W', cells: new Set(['mc6_dog3_all']), tip: 'WOMEN, +250..+300. MC6 three or more points over the de-vigged market on the dog. MC6 record: +54.42% on 31 (13-18, t 1.64) -- replay +60.61% on 23, forward +36.62% on 8 (3-5). Blind womens dogs here are already +17.66% on 44 and +48.30% on 10 forward, so much of this is the price rather than MC6, and forward MC6 is BEHIND the blind band. The mens half is -28.10% on 21 at 2pt and is off the tab.' },

  // s52 SEASONAL-BAND DOG (2026-10-14, user "mark both men and women dogs +100 to +200 with ...
  // s52_fav_band_dog ... pink"). The only cell on the board clearing t=2: +19.80% on 183, t 2.25,
  // with BOTH genders forward-positive (men +13.49%/94, women +26.46%/89). The lane is itself
  // hard-gated to +100..+200 and that ceiling is earned -- without it +200..+250 is -14.94%/65
  // and +250..+300 is -11.21%/38. Listed AFTER the MC2 rules so the MC2 tooltip wins where a
  // pick qualifies under both; the s52 cell still appears in the pick's badge list either way.
  // MENS RULE STOPS AT +150 (2026-10-14, user "lets remove that band then until it gets more
  // games"). It could never paint anyway -- the board band gate drops men +150..+200 -- so the
  // rule no longer claims a range it cannot deliver. Mens +100..+150 is +17.39%/66; the held
  // back +150..+200 half is +4.29%/28, the weakest quarter of the cell, inside a band that is
  // -6.57%/84 deduped. Nothing is deleted: the lane keeps scoring it and it returns on its own
  // if that band turns positive. WOMEN keep the full +100..+200, where their half is strongest
  // (+37.44%/36 at +150..+200 against +19.00%/53 at +100..+150).
  { lo: 100, hi: 150, g: 'm', tag: 's52 BAND M', cells: new Set(['s52_fav_band_dog']), tip: 'MEN, +100..+150 ONLY, s52 SEASONAL-BAND DOG -- back the dog when the FAVOURITE owns both 52-week hold% and break%. This half is +17.39% on 66 forward. THE +150..+200 HALF IS HELD BACK (your call, 2026-10-14, "until it gets more games"): it is the weakest quarter of the cell at +4.29% on 28, and the whole mens +150..+200 band is -6.57% on 84 deduped across the tab, so the board gate drops it before pink is even considered. Nothing is deleted -- the lane keeps scoring those picks and they reappear on their own if that band turns positive. The cell overall is the only one on this board clearing t=2 (+19.80%/183, t 2.25), but that is carried by the womens half, which keeps the full +100..+200 range.' },
  { lo: 100, hi: 200, g: 'w', tag: 's52 BAND W', cells: new Set(['s52_fav_band_dog']), tip: 'WOMEN, +100..+200, s52 SEASONAL-BAND DOG -- back the dog when the FAVOURITE owns both 52-week hold% and break%. Womens half +26.46% on 89 (46-43, 51.7% hit against ~40% needed, t 2.04) -- the strongest gender half of the strongest cell on the board. Unlike the mens half it is carried by the DEEP band: +37.44% on 36 at +150..+200 against +19.00% on 53 at +100..+150. Note the lane records a 39-day window and replays inside it.' },
  // c75 DOG FLIP (2026-10-14, user "lets do c75 flips men and women and also check +150 to 200").
  // The check is why this is two band-specific rules rather than one range: at +150..+200 the
  // genders go OPPOSITE ways, so marking both across +100..+200 would have painted the two
  // negative halves. Measured on the lane's own picks, ITF men excluded:
  //                   MEN                      WOMEN
  //   +100..+150   +22.88%/65  t 1.73       -23.53%/47  t -1.59
  //   +150..+200   -26.27%/15                +10.68%/22 t  0.38
  // A flip has no margin to tune, so the band is the only parameter chosen. The womens cell is
  // THIN (22 bets, t 0.38) and its badge says so; its blended lane number is further flattered by
  // a FOUR-bet +200..+250 cell at +140.75%, which is not marked.
  { lo: 100, hi: 150, g: 'm', tag: 'c75 FLIP M', cells: new Set(['mc_c75_dog']), tip: 'MEN, +100..+150, c75 DOG FLIP -- Model C75 puts the market underdog past 50% and picks it outright, and you back the dog at the frozen price. +22.88% on 65 (37-28, 56.9% hit, t 1.73) against a blind mens dog baseline of about -1%. A flip has NO margin to tune, so the price band is the only choice made here, and the mens record collapses outside it: -26.27% on 15 at +150..+200 and -100% on 2 at +250..+300. Both C heads read the same thing -- requiring c50 to agree as well gives +22.24% on 55, no better -- so this is one signal, not two.' },]

const pinkRule = (p, cellKeys) => {
  if (p.odds == null || p.odds < 0) return null       // favourites are yellow/gold, never pink
  // gender inlined rather than calling genderOf, which is declared further down this module
  const g = /wta|itf_women/i.test(String(p.league || '')) ? 'w' : 'm'
  const keys = [...(cellKeys || [])]
  for (const r of PINK_RULES) {
    if (r.g !== g) continue
    if (p.odds >= r.lo && p.odds <= r.hi && keys.some(k => r.cells.has(k))) return r
  }
  return null
}

const DROP_LEAGUES = new Set(['itf_men'])
const leagueOK = p => !DROP_LEAGUES.has(String(p.league || '').toLowerCase())

// PRICE BANDS (2026-10-14, user ask). The four bands the user bets in, in order.
const BANDS = [
  ['+100..+150', 100, 150],
  ['+150..+200', 150, 200],
  ['+200..+250', 200, 250],
  ['+250..+300', 250, 300],
]
const bandOf = od => (od == null ? null : (BANDS.find(([, lo, hi]) => od >= lo && od <= hi) || [null])[0])

// EVERY NUMBER ON A CARD IS GENDER x BAND (2026-10-14, user: "make sure it's gender specific").
// A gender-wide record is not specific enough on this tab, because every gate here is defined on
// gender x price band and the two disagree hard: the men's MC2 4pt lane is -3.04% over all prices
// and +30.6% at +100..+150, and the women's c75 flip lane blends to +7.84% while its +100..+150
// half is -23.53% on 47. Summed from the cell's OWN picks on the tab's population (no ITF men,
// nothing above +300) so it cannot drift from the lane that scores it, or from splitByBand.
function bandGenderRec(cel, g, odds) {
  const b = bandOf(odds)
  if (!b) return { n: 0, band: null }
  const lo = (BANDS.find(x => x[0] === b) || [])[1]
  const hi = (BANDS.find(x => x[0] === b) || [])[2]
  const ps = (cel.picks || []).filter(p => p.odds != null && p.odds >= lo && p.odds <= hi
    && priceOK(p) && leagueOK(p) && genderOf(p) === g)
  const done = ps.filter(p => p.won != null)
  const profit = done.reduce((a, p) => a + (p.pnl || 0), 0)
  return { band: b, n: done.length, wins: done.filter(p => p.won).length,
           pending: ps.length - done.length, profit_usd: profit,
           per_bet: done.length ? profit / done.length : 0,
           roi_pct: done.length ? Math.round(1000 * profit / (25 * done.length)) / 10 : 0 }
}

// the card's headline: its best gender x band cell, readable cells ahead of thin ones. ROI rank is
// NOT confidence rank -- the top two cells on this tab are also its two smallest samples -- so the
// sort puts anything with >= MIN_CELL_N settles ahead of everything thinner regardless of ROI.
function bestRec(s) {
  let best = null
  for (const cel of s.cells) {
    const d = bandGenderRec(cel, s.g, s.p.odds)
    if (!d.n) continue
    const thick = d.n >= MIN_CELL_N
    if (!best || (thick !== best.thick ? thick
      : d.per_bet > best.d.per_bet)) best = { cel, d, thick }
  }
  return best
}

// NOTHING FORWARD-NEGATIVE ON THE BOARD (2026-10-14, user: "make sure nothing that falls into
// negative forward test is marked or on the board in dog tab").
//
// genderOK already drops a CELL for a losing gender. This is the other axis: the gender x PRICE
// BAND combination, measured on the boards OWN deduped pick list -- one row per dog per day,
// which is what betting the tab would actually return. Forward only.
//
//     +100..+150  men   +22.36% (161, t 2.61)      women   +4.66% (100, t 0.43)
//     +150..+200  men    -9.30% ( 66, t -0.59) <-- women  +39.53% ( 55, t 2.14)
//     +200..+250  men   +37.84% ( 31, t 1.30)      women   +6.67% ( 30, t 0.24)
//     +250..+300  men   +23.89% ( 27, t 0.71)      women  +52.75% ( 24, t 1.43)
//
// COMPUTED, NOT HARDCODED: the records are rebuilt from the live lane payload on every render and
// anything at or below zero is dropped, so this follows the data instead of freezing todays
// answer. The records are built BEFORE the gate is applied, so it cannot feed on itself.
// Accept the consequence: a combination near zero can flip in or out on one result, and men
// +150..+200 at t -0.59 is a losing record rather than a settled verdict -- which is the bar the
// user set.
//
// This is a DIFFERENT population from the pink gate, and where the two disagree that is correct:
// pink is measured on the MC2 4pt+ subset only. A pick can be on the board without being pink.
const bandKey = p => {
  const b = bandOf(p.odds)
  return b ? `${/wta|itf_women/i.test(String(p.league || '')) ? 'w' : 'm'}|${b}` : null
}
function badBandGenders(cells) {
  const seen = new Map()
  for (const cel of cells) {
    if (FAV_CELLS.has(cel.key)) continue
    for (const p of cel.picks) {
      if (!priceOK(p) || !leagueOK(p)) continue
      if (!MARK_CELLS.has(cel.key)) {
        if (!genderOK(cel.c, genderOf(p))) continue
        if (!cellThick(cel.c, genderOf(p))) continue
      }
      const k = `${p.date}|||${p.pick}|||${p.opp}`
      if (!seen.has(k)) seen.set(k, p)
    }
  }
  const tot = {}
  for (const p of seen.values()) {
    const k = bandKey(p)
    if (!k || p.won == null) continue
    if (!tot[k]) tot[k] = { n: 0, w: 0, profit: 0 }
    tot[k].n += 1
    tot[k].w += p.won ? 1 : 0
    tot[k].profit += (p.pnl || 0)
  }
  const bad = new Map()
  for (const [k, v] of Object.entries(tot)) {
    const roi = 100 * v.profit / (25 * v.n)
    if (roi <= 0) bad.set(k, { ...v, roi })
  }
  return bad
}

// A DOG PICK COUNTED ONCE. The cells overlap heavily -- the same dog can carry nine badges --
// so summing cell records would multiply one bet into nine. These aggregates key on the match
// itself, take the pick once, and use its own P/L, which is what betting the tab would return.
function dedupe(cells, filterFn) {
  const out = new Map()
  const bad = badBandGenders(cells)
  for (const cel of cells) {
    if (FAV_CELLS.has(cel.key)) continue      // favourites never enter the dog maths
    for (const p of cel.picks) {
      if (!priceOK(p) || !leagueOK(p)) continue
      if (!MARK_CELLS.has(cel.key)) {
        if (!genderOK(cel.c, genderOf(p))) continue
        if (!cellThick(cel.c, genderOf(p))) continue  // too few settles for this gender to read
      }
      if (bad.has(bandKey(p))) continue        // this gender x band loses money forward
      if (filterFn && !filterFn(p)) continue
      const k = `${p.date}|||${p.pick}|||${p.opp}`
      if (!out.has(k)) out.set(k, p)
    }
  }
  return [...out.values()]
}
function agg(ps) {
  const done = ps.filter(p => p.won != null)
  const w = done.filter(p => p.won).length
  const profit = done.reduce((a, p) => a + (p.pnl || 0), 0)
  const staked = 25 * done.length
  return { n: done.length, w, l: done.length - w, profit,
           roi: staked ? (100 * profit / staked) : null, pending: ps.length - done.length }
}

// GENDER-SPECIFIC (2026-10-14, user: "Make sure they're gender specific picks if one gender is
// negative dog roi I don't want it"). Every cell on this board has split by gender, often
// hard -- mc2_dog_band is men +20.3% / women -1.0%, cgray_dog_late men +22.1% / women -8.4% --
// so a blended number hides a losing half. A cell is shown for a gender only when THAT gender's
// dog ROI is above zero, and the badge reports that gender's record rather than the blend.
//
// A gender with no settles yet is not negative, it is unknown, so it is kept and labelled
// "new": suppressing it would hide every cell on its first pick of a gender. Once it settles
// into negative territory it drops out on its own.
const genderOf = p => (/wta|itf_women/i.test(String(p.league || '')) ? 'w' : 'm')

// THIN CELLS STOP COUNTING (2026-10-14, user "remove matches like this" on a card whose only two
// cells were 6-4 SPLIT W +17%/12 and D-MA DOG W +6%/23). A cell is ignored for a gender whose
// record has fewer than MIN_CELL_N settles, and a card left with no qualifying cell drops off the
// list entirely.
//
// A SAMPLE floor rather than an ROI floor: at dog prices a 12-bet cell carries a standard error
// near 40 points, so +17% on 12 is not distinguishable from zero. An ROI floor would keep that
// cell and drop a 200-bet cell at +8%, which is backwards.
//
// 25 is roughly where a dog cell's standard error falls under ~25 points, and the smallest floor
// that removes the card this came from. It does NOT affect the gender gate, the band gate or the
// pink/gold rules, and a thin cell still shows in the "by cell" list with its own numbers.
// MARK_CELLS (2026-10-14, user "a few mc2 6p+ dogs that should be highlighted still").
// genderOK hides a cell whose ALL-PRICE record for a gender is negative. mc2_dog4_all is -3.04%
// on 185 for men across every price, so it was hidden for men entirely -- including at +100..+150
// where it is +27.48% on 48 -- and the pink rule that reads it could never fire.
//
// The marks are BAND-specific; that gate is ALL-PRICE. A cell can be bad overall and good in one
// band, which is the whole finding of this session. So a cell named by a pink or gold rule is
// exempt from genderOK and from the thin-cell floor. Every other gate still applies: the price
// cap, the league gate, the gender x band board gate, and the rule's own band + gender test,
// which is what actually decides the paint.
//
// Consequence: a mark-source cell can also appear as a BADGE outside its marked band. It is a
// badge, not a mark.
const MARK_CELLS = new Set([
  ...PINK_RULES.flatMap(r => [...r.cells]),
  'mc6_fav4_w', 'mc6_fav4_m',
  // the men's 3-6pt favourite BAND (2026-10-16, user call) -- marks gold like the others
  'mc6_fav_band_m',
  // the women's >=6pt favourite FLOOR (2026-10-16, user call)
  'mc6_fav6_w',
  // the -150..-200 favourite rules (2026-10-17, user call)
  'mc6_fav150_m', 'mc6_fav150_w',
])
// these two lanes are shown one row PER PRICE BAND rather than as one blended number
const SPLIT_BY_BAND = new Set(['mc6_dog2_all', 'mc6_dog3_all', 'mc6_dog4_all', 'mc6_dog6_all'])

// A CELL THAT LOSES FOR EVERY GENDER LEAVES THE TAB (2026-10-14, user: "remove these from the
// dog board completely since they're negative"). Until now such a cell still held a row with its
// losing total while both halves wore the gender gate's cross -- visible, unusable, misleading.
// A gender with NO settles is unknown, not negative, so it does not block the cell.
const allGendersNegative = (c) => {
  const seen = ['m', 'w'].map(g => genderRec(c, g)).filter(d => d && d.n)
  return seen.length > 0 && seen.every(d => (d.roi_pct || 0) <= 0)
}
const MIN_CELL_N = 25
const cellThick = (c, g) => {
  const d = genderRec(c, g)
  return !d.n || d.n >= MIN_CELL_N
}

// EVERYTHING ON THIS TAB IS ORDERED EARLIEST -> LATEST (2026-10-14, user "I want it in order
// from earliest time to latest" / "All the dog tab"), by the match's own start time rather than
// by conviction or by ROI, so the list reads the way the day actually runs.
const fmtPT = (utc) => {
  if (!utc) return ''
  try {
    const d = new Date(utc)
    if (isNaN(d)) return ''
    return d.toLocaleTimeString('en-US', { timeZone: 'America/Los_Angeles', hour: 'numeric', minute: '2-digit' }).replace(' ', '') + ' PT'
  } catch (e) { return '' }
}
// SORT ON A PARSED TIMESTAMP, not on the string. The log carries two stamp formats
// ("2026-10-14T10:00:00Z" and "2026-10-14T03:47:22.075256+00:00") and comparing those
// lexically puts the fractional ones first within the same second -- the first version of this
// sort did exactly that and the list came out scrambled.
// A pick is LIVE when its match has started and has no result yet, UPCOMING when it has not
// started, and FINISHED once it settles (2026-10-14, user "show me which dog games are live" /
// "get rid of the finished ones with a dog history tab"). The betting list keeps only live and
// upcoming, so it stays a list of things you can still act on.
const isFinished = p => p.won != null
const isLive = p => !isFinished(p) && whenMs(p) <= Date.now()
const whenMs = p => {
  const t = Date.parse(p.start || '')
  if (!isNaN(t)) return t
  const d = Date.parse(`${p.date || ''}T23:59:59Z`)   // no stamp -> end of its own day
  return isNaN(d) ? 8.64e15 : d
}
// a date label, shown only when the match is not on the same local day as the next one, so the
// chronological list stays readable when it spans the UTC rollover
const dayLabel = (ms) => {
  try {
    return new Date(ms).toLocaleDateString('en-US', { timeZone: 'America/Los_Angeles', month: 'numeric', day: 'numeric' })
  } catch (e) { return '' }
}
// ALL_GENDER_SPECIFIC (2026-10-14, user "make sure everything ur checking is gender specific").
// c.m / c.w blend a cell's DOG and FAVOURITE picks; c.m_dog / c.w_dog are the dog-side only.
// This tab is a dog board, so the dog-side record is the right one. Verified on live data: for
// every dog cell here the two are identical (these cells only ever record dog picks), so no gate
// was wrong -- except ovl_dog, which has NO m_dog/w_dog at all, so a blind switch would silently
// disable its gate. Hence prefer the dog-side record and fall back.
const genderRec = (c, g) => {
  const d = (c || {})[g + '_dog']
  if (d && d.n) return d
  return (c || {})[g] || {}
}
const genderOK = (c, g) => {
  const d = genderRec(c, g)
  if (!d.n) return true                       // no settles for this gender -> unknown, not bad
  return (d.roi_pct || 0) > 0
}

// ===================================================================== THE PICK ENGINE
// (2026-10-17) Lifted VERBATIM out of the component so the Dog tab and the server-side
// auto-bet bot run one code path: the component calls these, and frontend/src/
// dogEngineEntry.js bundles this same file for Node (dist/dog_engine.cjs). Change the
// rules here and both move together.
export const markOf = (x) => (isFavPick(x.p)
  ? favMarkOf(x.p, x.cells.map(c => c.key))
  : pinkRule(x.p, x.cells.map(c => c.key)))

export function buildCells(st) {
  // THE HEADLINE IS THE SHOWN GENDERS, NOT THE BLEND. A cell whose men's half is hidden must not
  // still report the men's dollars in its green number -- that is a figure for bets the tab is
  // not listing. cShown sums only the genders that pass genderOK; hidden names which one is out.
  const cells = CELLS.map(([label, key, note]) => {
    const c = st[key] || {}
    const shown = ['m', 'w'].filter(g => genderOK(c, g))
    const hidden = ['m', 'w'].filter(g => !genderOK(c, g))
    let cShown = c
    if (hidden.length) {
      const parts = shown.map(g => genderRec(c, g)).filter(d => d && d.n)
      if (parts.length) {
        const n = parts.reduce((a, d) => a + d.n, 0)
        const wins = parts.reduce((a, d) => a + (d.wins || 0), 0)
        const profit_usd = parts.reduce((a, d) => a + (d.profit_usd || 0), 0)
        cShown = { ...c, n, wins, profit_usd,
                   roi_pct: Math.round(1000 * profit_usd / (25 * n)) / 10 }
      }
    }
    return { label, baseLabel: label, key, note, c, cShown, hidden,
             picks: c.picks || [], t: tstat(cShown) }
  }).filter(x => x.c && (x.c.n || x.picks.length))
    .flatMap(x => (SPLIT_BY_BAND.has(x.key) ? splitByBand(x) : [x]))
    .filter(x => !allGendersNegative(x.c))
  return cells
}

export function buildStacked(cells, nowMs) {
  // TODAY: every unsettled pick, grouped by match, so a dog several cells agree on is visible
  // an unsettled pick whose match started long ago never got a result -- it is a gap in the
  // log, not an upcoming bet, so it does not belong on a picks list. Everything from six hours
  // ago onward is kept, which covers in-play matches without dragging in last week's orphans.
  const CUTOFF = nowMs - 6 * 3600 * 1000
  const badBG = badBandGenders(cells)          // gender x band combinations that lose forward
  const byMatch = {}
  for (const cel of cells) {
    for (const p of cel.picks) {
      if (p.won != null || p.settled) continue
      if (whenMs(p) < CUTOFF) continue
      if (!priceOK(p) || !leagueOK(p)) continue   // nothing above +300, no ITF men
      const g = genderOf(p)
      // a cell the board marks from is judged by its RULE's band, not by its blended record
      if (!MARK_CELLS.has(cel.key)) {
        if (!genderOK(cel.c, g)) continue     // this gender's half of the cell loses money
        if (!cellThick(cel.c, g)) continue    // ...and this gender's half is too small to read
      }
      // ...but NO cell survives a readable, non-positive record on its own gender x band. The
      // MARK_CELLS exemption above exists so a lane with a negative BLEND can still mark its good
      // band; it was also letting the reverse through -- the women's c75 flip at +100..+150, -23.53%
      // on 47, listed unpainted because the lane blend is positive (2026-10-14, user "make sure
      // it's gender specific"). Fewer than MIN_CELL_N settles is unknown, not negative.
      {
        const bg = bandGenderRec(cel, g, p.odds)
        if (bg.n >= MIN_CELL_N && (bg.roi_pct || 0) <= 0) continue
      }
      if (badBG.has(bandKey(p))) continue     // ...and this gender x price band loses money
      const k = `${p.pick}|||${p.opp}`
      if (!byMatch[k]) byMatch[k] = { p, g, cells: [] }
      byMatch[k].cells.push(cel)
    }
  }
  // live + upcoming only -- finished picks are skipped by the `p.won != null` test above
  let stacked = Object.values(byMatch)

  // BOTH SIDES OF ONE MATCH (2026-10-14, user "this has the opponent of the highlighted / remove
  // the non highlighted in these cases"). The dog cells and the favourite cells are independent,
  // so a match can appear twice -- one head likes the dog, another likes the favourite. Printing
  // both is worse than useless: they are opposite bets on one match, so backing the list as shown
  // guarantees a loser.
  //
  // If a match has more than one entry and at least one is MARKED (pink for a dog, gold for a
  // favourite), the unmarked entries go. If NONE is marked, or several are, both stay -- the tab
  // has no basis for choosing between them and should not pretend otherwise.
  //
  // The history and the aggregates are deliberately untouched: they record what the cells did, and
  // dropping one side of a settled pair would misstate that.
  const sameMatchKey = (x) => [String(x.p.date || ''),
    ...[String(x.p.pick || ''), String(x.p.opp || '')].sort()].join('|||')
  const sides = new Map()
  for (const x of stacked) {
    const k = sameMatchKey(x)
    if (!sides.has(k)) sides.set(k, [])
    sides.get(k).push(x)
  }
  stacked = stacked.filter((x) => {
    const grp = sides.get(sameMatchKey(x)) || []
    if (grp.length < 2) return true
    return grp.some(y => markOf(y)) ? !!markOf(x) : true
  })
  return stacked
}

// \u{1F916} AUTO-BET, PAPER (2026-10-17, user "automatically bet on the dog tab highlights pick on
// Polymarket"). tennis_autobet.py runs this tab's own pick engine every 10 minutes and paper-fills
// each pink/gold pick against Polymarket's live order book shortly before the match. This view is
// read-only; there is no live order path anywhere in the app.
export function AutoBetView({ auto }) {
  if (!auto) {
    return <div className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>loading the paper auto-bet record...</div>
  }
  const bets = auto.bets || []
  const am = o => (o == null ? '' : (o > 0 ? '+' + o : String(o)))
  const col = b => (b.result === 'won' ? '#3fb950' : b.result === 'lost' ? '#f85149'
    : b.status === 'filled' ? 'var(--text)' : 'var(--text-tertiary)')
  const label = (b) => {
    if (b.result) return b.result.toUpperCase() + (b.pnl != null ? ' ' + usd(b.pnl) : '')
    if (b.status === 'filled') return 'FILLED · open'
    if (b.status === 'waiting') return 'waiting · ' + (b.last_reason || '')
    if (b.status === 'conflict') return 'skipped · both sides marked'
    if (b.status === 'missed') return 'missed · never at our price'
    return b.status
  }
  return (
    <div className="mono" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ fontSize: 10.5, color: 'var(--text-secondary)', padding: '8px 12px', borderRadius: 8,
        border: '1px solid var(--line)', background: 'var(--panel)', lineHeight: 1.5 }}>
        <b style={{ color: YELLOW }}>PAPER MODE {'—'} no real orders are placed.</b>{' '}
        Every 10 minutes the bot takes this tab{"'"}s pink and gold picks and, in the {auto.window_min} minutes
        before each match, buys ${auto.stake} against Polymarket{"'"}s live order book {'—'} never above the
        price this tab judged the pick at {'—'} paying Polymarket{"'"}s sports taker fee
        ({auto.fee_rate} {'×'} p {'×'} (1{'−'}p) per share). When both sides of one match are
        marked, neither is bet. Settles from the same log as the lanes. Last run {auto.last_run ? fmtPT(auto.last_run) : 'never'}.
        <div style={{ marginTop: 6, fontSize: 12, fontWeight: 800, color: (auto.pnl || 0) >= 0 ? '#3fb950' : '#f85149' }}>
          {auto.settled
            ? `${auto.wins}-${auto.settled - auto.wins} · ${usd(auto.pnl)} on $${auto.staked} staked (fees included) · ${auto.roi_pct}% ROI`
            : 'no settled paper bets yet'}
          <span style={{ fontWeight: 400, color: 'var(--text-tertiary)', marginLeft: 8 }}>{auto.open} open</span>
        </div>
      </div>
      {bets.map((b, i) => (
        <div key={i} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'baseline', fontSize: 11,
          padding: '6px 12px', borderRadius: 7, border: '1px solid var(--line)' }}>
          <span style={{ color: 'var(--text-tertiary)', minWidth: 92 }}>{fmtPT(b.start) || b.date}</span>
          <span style={{ color: b.kind === 'gold' ? GOLD : PINK, fontWeight: 800 }}>{b.kind === 'gold' ? '\u{1F947}' : PINK_TAG}</span>
          <b>{b.pick}</b>
          <span style={{ color: 'var(--text-tertiary)' }}>vs {b.opp}</span>
          <span>tab {am(b.board_odds)}</span>
          {b.avg_american != null ? (
            <span>filled {am(b.avg_american)} {'·'} ${(b.cost || 0).toFixed(2)} + ${(b.fee || 0).toFixed(2)} fee</span>
          ) : (b.last_book && b.last_book.best_ask != null ? (
            <span style={{ color: 'var(--text-tertiary)' }}>best ask {b.last_book.best_ask} vs our limit {b.last_book.limit}</span>
          ) : null)}
          <span style={{ marginLeft: 'auto', fontWeight: 800, color: col(b) }}>{label(b)}</span>
        </div>
      ))}
    </div>
  )
}

export default function DogPicksPanel({ query }) {
  const [rec, setRec] = useState(null)
  const [open, setOpen] = useState(null)
  const [mode, setMode] = useState('today')
  const [order, setOrder] = useState('edge')   // 'edge' = best gender x band $/bet first
  // the paper auto-bet record (2026-10-17) -- its own view, polled like the picks
  const [auto, setAuto] = useState(null)
  useEffect(() => {
    const go = () => fetch('/api/tennis/autobet').then(r => r.json()).then(setAuto).catch(() => {})
    go()
    const id = setInterval(go, 120000)
    return () => clearInterval(id)
  }, [])
  useEffect(() => {
    const go = () => fetch('/api/tennis/track-record').then(r => r.json())
      .then(d => setRec(d.ab25 || null)).catch(() => {})
    go()
    const id = setInterval(go, 120000)
    return () => clearInterval(id)
  }, [])
  const st = (rec && rec.study) || {}
  const q = (query || '').trim().toLowerCase()

  const cells = buildCells(st)

  // gender x band combinations that lose forward -- also computed inside buildStacked;
  // kept here because the render prints the excluded line from it
  const badBG = badBandGenders(cells)
  // the pick list itself, shared with the server-side auto-bet engine. The
  // both-sides-of-a-match dedupe now happens in there, before the search and sort.
  let stacked = buildStacked(cells, Date.now())
  if (q) {
    stacked = stacked.filter(s => (`${s.p.pick} ${s.p.opp} ${s.p.tournament || ''}`).toLowerCase().includes(q))
  }
  // HIGHEST ROI FIRST BY DEFAULT (2026-10-14, user: "focus on the highest roi picks to take").
  // Ranked on $/bet of the best gender x band cell, readable samples ahead of thin ones, so the
  // order on screen matches the number printed on the card. The pill flips back to start time.
  const byTime = (a, b) => (whenMs(a.p) - whenMs(b.p)) || (b.cells.length - a.cells.length)
  if (order === 'edge') {
    stacked.sort((a, b) => {
      const x = bestRec(a), y = bestRec(b)
      if (!x || !y) return (!x && !y) ? byTime(a, b) : (x ? -1 : 1)
      if (x.thick !== y.thick) return x.thick ? -1 : 1
      return (y.d.per_bet - x.d.per_bet) || byTime(a, b)
    })
  } else {
    stacked.sort(byTime)
  }

  // (both-sides-of-a-match dedupe: see buildStacked)

  // when the list spans more than one local day, each row gets its date so the order reads
  const multiDay = new Set(stacked.map(x => dayLabel(whenMs(x.p)))).size > 1

  // FINISHED picks for the history view: deduped to one row per dog, newest day first, and
  // grouped by day so each day carries its own record and P/L.
  const finished = dedupe(cells, isFinished).sort((a, b) => whenMs(b) - whenMs(a))
  // the same women-only rule for the history rows
  const favHist = (p) => favMarkOf(p, histCells(p).map(c => c.key))
  const histCells = (p) => cells.filter(cel => (MARK_CELLS.has(cel.key)
      || (genderOK(cel.c, genderOf(p)) && cellThick(cel.c, genderOf(p))))
    && cel.picks.some(x => x.date === p.date && x.pick === p.pick && x.opp === p.opp))
  const histDays = []
  for (const p of finished) {
    const d = dayLabel(whenMs(p))
    if (!histDays.length || histDays[histDays.length - 1].d !== d) histDays.push({ d, ps: [] })
    histDays[histDays.length - 1].ps.push(p)
  }

  const pill = (on, label, onClick) => (
    <button onClick={onClick} className="mono" style={{
      padding: '4px 12px', borderRadius: 12, fontSize: 11, cursor: 'pointer',
      border: `1px solid ${on ? '#3fb950' : 'var(--line)'}`,
      background: on ? 'rgba(63,185,80,0.13)' : 'transparent',
      color: on ? '#3fb950' : 'var(--text-secondary)', fontWeight: on ? 700 : 400,
    }}>{label}</button>
  )

  if (!rec) {
    return <div className="mono" style={{ padding: 18, color: 'var(--text-tertiary)', fontSize: 12 }}>loading dog cells…</div>
  }

  return (
    <div style={{ padding: '4px 0 20px' }}>
      <div className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 10 }}>
        <b style={{ color: '#3fb950' }}>🐕 DOG PICKS</b> — every dog cell with a positive forward record, and the
        picks each one is on, <b>gender-gated</b>: a cell only appears for a gender whose own dog ROI is
        above zero, and each badge shows that gender’s record rather than the blend. Records come straight from the lanes that score them, so nothing here can disagree
        with the $25 tab. <b>Read the t column, not the ROI</b>: at dog prices a 20-bet cell needs about 40 points
        of ROI to reach t=2, so a big number on a small sample is variance. Of 104 dog cells measured, 4 clear
        t=2 — roughly what 104 lanes on ~1,000 shared games produce by chance — so treat these as candidates
        rather than settled edges. Cells overlap heavily; the dollar figures are <i>not</i> additive. Everything is ordered <b>earliest start to latest</b>, and nothing above <b>+300</b> is shown — above that price the archive runs −17% to −18% at any model margin. <b style={{ color: PINK }}>{PINK_TAG}Pink</b> = <b>MC6 over the market on the dog</b> -- <b>men at 2pt+, women at 3pt+</b> -- gender-specific, in the bands where that gender is positive. Five cells (MC6 own record, mostly as-of replay; forward opened 2026-10-15): <b>+100..+150</b> men +38.64% on 73 (t 3.06; forward +21.64% on 14) and women +12.93% on 68 (forward <b>-19.86%</b> on 14, the weakest cell); <b>+150..+200</b> women +41.38% on 47 (t 2.02); <b>+200..+250</b> men +12.53% on 38 (t 0.49, a watch mark); <b>+250..+300</b> women +54.42% on 31, though blind womens dogs there are already +17.66%. Forward, none of the five yet beats simply backing every dog in its band. Also pink: the <b>s52 seasonal-band dog</b> — back the dog when the FAVOURITE owns both 52-week hold% and break%, i.e. fade the seasonal stat leader. <b>Women +100..+200</b>; <b>men +100..+150 only</b>, the deeper men’s half held back until it has more games (+4.29% on 28, inside a band that is −6.57% on 84 deduped and already gated off the tab). The only cell on this board clearing <b>t = 2</b> (+19.80% on 183; men +13.49%/94, women +26.46%/89). Its own +200 ceiling is earned: re-run without it, +200..+250 is −14.94%/65 and +250..+300 is −11.21%/38. Also pink: the <b>c75 dog flip</b> — C75 puts the market underdog past 50% and picks it outright — <b>men at +100..+150 only</b> (+22.88% on 65, t 1.73). The men’s record collapses outside that band (−26.27% at +150..+200) and the women’s half is −23.53% at +100..+150, so neither is marked. Anything whose forward record is negative is not merely unmarked, it is <b>off the tab entirely</b> — see the excluded line below. Thresholds and gender splits were all found by scanning this same data. <b style={{ color: GOLD }}>🥇 Gold = a FAVOURITE MC6 likes</b>, kept visually and numerically separate from the dogs. <b>Every</b> MC6 favourite lane paints gold at any price (your call, 2026-10-16): the gates -- <b>women a &gt;=6pt floor</b> (+14.79% on 57, t 1.50; their favourite side climbs with the margin) and <b>men a capped 3-6pt band</b> (+32.42% on 20, t 2.41; theirs is an inverted U) -- both with <b>positive EV at the offered price</b>, plus the 4pt lanes at -100..-200 (women +11.57% on 50, men +12.13% on 48, no EV check). Gold says MC6 rates the favourite over the market, not that the rule is proven: hover the badge for which rules fired. <b>At −150..−200 only the band rules paint gold</b> (2026-10-17): men 2–8pt with positive EV (+44.80% on 12, replay) and women 6pt+ (+16.36% on 19). <b>Read the sample:</b> READ THE SAMPLE: these records are mostly MC6 as-of REPLAY. The forward window opened 2026-10-15 and holds 12 settled womens bets on the 6pt floor and 1 mens bet on the 3-6pt band, and the dog gates on this same head are negative forward (men 2pt -11.37% on 43, women 3pt -10.36% on 44). A cell whose record for that gender has <b>fewer than 25 settles</b> no longer counts — at dog prices a 12-bet cell has a standard error near 40 points, so it cannot be read — and a card left with no qualifying cell drops off this list (it still appears under <i>by cell</i>). When <b>both sides of one match</b> qualify and only one carries a mark, the unmarked side is dropped from this list — they are opposite bets, so showing both guarantees a loser (the history keeps both). <b>ITF men is excluded</b>: it is the only league with a negative dog ROI here (−26.2% on 27, against WTA +21.0%, ATP challenger +11.6%, ATP tour +11.4%, ITF women +14.4%). Per-cell ROI and t below are still full-sample.
      </div>
      {(() => {
        // DAILY RECORD + ROI and the PRICE-BAND SPLIT (2026-10-14, user asks). Both are over
        // DEDUPED picks -- one row per dog, not one per cell -- so they say what betting this
        // tab actually returned rather than counting a nine-badge dog nine times.
        const all = dedupe(cells)
        const days = [...new Set(all.filter(p => p.won != null).map(p => dayLabel(whenMs(p))))]
        const byDay = new Map()
        for (const p of all) {
          if (p.won == null) continue
          const d = dayLabel(whenMs(p))
          if (!byDay.has(d)) byDay.set(d, [])
          byDay.get(d).push(p)
        }
        const dayKeys = [...byDay.keys()].sort((a, b) => {
          const pa = byDay.get(a)[0], pb = byDay.get(b)[0]
          return whenMs(pa) - whenMs(pb)
        })
        const recent = dayKeys.slice(-4)
        const box = (label, a, hint) => (
          <div key={label} title={hint} style={{
            padding: '7px 12px', borderRadius: 8, background: 'var(--panel)', minWidth: 118,
            border: `1px solid ${a.n && a.roi > 0 ? 'rgba(63,185,80,0.45)' : 'var(--line)'}`,
          }}>
            <div style={{ fontSize: 9, color: 'var(--text-tertiary)', fontWeight: 700, letterSpacing: '0.04em' }}>{label}</div>
            {a.n ? (
              <>
                <div style={{ fontSize: 14, fontWeight: 800, color: a.profit >= 0 ? '#3fb950' : '#f85149' }}>{usd(a.profit)}</div>
                <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                  {a.w}-{a.l} · {a.roi > 0 ? '+' : ''}{a.roi.toFixed(1)}%
                </div>
              </>
            ) : <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 3 }}>{a.pending ? `${a.pending} pending` : 'none'}</div>}
          </div>
        )
        return (
          <>
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 700, marginBottom: 5 }}>
              DAILY — one row per dog, deduped across cells, $25 flat, ≤ +{MAX_AM}, no ITF men
            </div>
            <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginBottom: 12 }}>
              {recent.map(d => box(d, agg(byDay.get(d)), `Every deduped dog pick that settled on ${d}.`))}
              {box('ALL TIME', agg(all), 'Every deduped dog pick on this tab, all days.')}
            </div>
            {(() => {
              // the favourite cells get their own line, never mixed into the dog totals
              const fp = []
              const seenF = new Set()
              for (const cel of cells) {
                if (!FAV_CELLS.has(cel.key)) continue
                for (const p of cel.picks) {
                  if (!leagueOK(p)) continue
                  const k = `${cel.key}|${p.date}|${p.pick}`
                  if (seenF.has(k)) continue
                  seenF.add(k)
                  fp.push([cel, p])
                }
              }
              // the two GATES the tab marks on, then the 4pt pair as controls (2026-10-16)
              const wCell = cells.find(c => c.key === 'mc6_fav6_w')
              const mCell = cells.find(c => c.key === 'mc6_fav_band_m')
              const wOld = cells.find(c => c.key === 'mc6_fav4_w')
              const mOld = cells.find(c => c.key === 'mc6_fav4_m')
              const m150 = cells.find(c => c.key === 'mc6_fav150_m')
              const w150 = cells.find(c => c.key === 'mc6_fav150_w')
              if (!wCell && !mCell && !wOld && !mOld) return null
              const bx = (cel, lab) => {
                if (!cel) return null
                const c = cel.c
                return (
                  <div key={lab} title={cel.note} style={{
                    padding: '7px 12px', borderRadius: 8, background: 'var(--panel)', minWidth: 150,
                    border: `1px solid ${lab.indexOf('women') >= 0 ? 'rgba(227,179,65,0.7)' : 'var(--line)'}`,
                  }}>
                    <div style={{ fontSize: 9, color: YELLOW, fontWeight: 700, letterSpacing: '0.04em' }}>{lab}</div>
                    {c.n ? (
                      <>
                        <div style={{ fontSize: 14, fontWeight: 800, color: (c.profit_usd || 0) >= 0 ? '#3fb950' : '#f85149' }}>{usd(c.profit_usd)}</div>
                        <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                          {c.wins}-{c.n - c.wins} · {c.roi_pct > 0 ? '+' : ''}{c.roi_pct}%{c.pending ? ` · ${c.pending} pend` : ''}
                        </div>
                      </>
                    ) : <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 3 }}>0 settled</div>}
                  </div>
                )
              }
              return (
                <>
                  <div style={{ fontSize: 10, fontWeight: 700, marginBottom: 5 }}>
                    <span style={{ color: GOLD }}>{'🥇 EVERY MC6 FAVOURITE IS GOLD, AT ANY PRICE'}</span>
                    <span style={{ color: 'var(--text-tertiary)' }}>
                      {' -- FAVOURITES, separate from every dog number above. Gold means MC6 rates this '}
                      {'favourite over the market (your call, 2026-10-16); hover the badge for which rules fired. '}
                      {'The two GATES: WOMEN a >=6pt floor + EV, +14.79% on 57 (t 1.50); MEN a capped 3-6pt '}
                      {'band + EV, +32.42% on 20 (t 2.41). The 4pt lanes (no EV, -100..-200) are +11.57% on 50 '}
                      {'women and +12.13% on 48 men. The old -100..-200 price gate is gone: outside it the gates '}
                      {'are +8.18% on 15 women and +33.07% on 12 men. '}
                      {'AT -150..-200 ONLY THE BAND RULES PAINT GOLD (2026-10-17): MEN 2-8pt + EV (+44.80% on 12, '}
                      {'replay) and WOMEN 6pt+ (+16.36% on 19); other MC6 favourites in that band list unmarked. '}
                      {'Both lanes record only from 2026-10-17, so they open at n=0. '}
                      {'READ THE SAMPLE: these records are mostly MC6 as-of REPLAY. The forward window opened 2026-10-15 and holds 12 settled womens bets on the 6pt floor and 1 mens bet on the 3-6pt band, and the dog gates on this same head are negative forward (men 2pt -11.37% on 43, women 3pt -10.36% on 44). Below -500 there is no sample.'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginBottom: 14 }}>
                    {bx(wCell, 'women \u2265 6pt (the take)')}
                    {bx(mCell, 'men 3\u20136pt (the take)')}
                    {bx(wOld, 'women 4pt')}
                    {bx(mOld, 'men 4pt')}
                    {bx(m150, 'men \u2212150..\u2212200 2\u20138pt')}
                    {bx(w150, 'women \u2212150..\u2212200 6pt+')}
                  </div>
                </>
              )
            })()}
            {badBG.size ? (
              <div style={{ fontSize: 10, color: '#f85149', fontWeight: 700, marginBottom: 9,
                padding: '6px 10px', borderRadius: 7, border: '1px solid rgba(248,81,73,0.45)',
                background: 'rgba(248,81,73,0.07)' }}>
                {'\u26d4 EXCLUDED \u2014 forward-negative gender \u00d7 band, dropped from the list, the history and every total: '}
                {[...badBG.entries()].map(([k, v]) => {
                  const [g, b] = k.split('|')
                  return `${g === 'w' ? 'women' : 'men'} ${b} (${v.roi > 0 ? '+' : ''}${v.roi.toFixed(2)}% on ${v.n}, ${v.w}-${v.n - v.w}, ${usd(v.profit)})`
                }).join(' \u00b7 ')}
              </div>
            ) : null}
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 700, marginBottom: 5 }}>
              BY PRICE BAND — all days, deduped, one band per pick · M/W shown because the gate works on gender × band
            </div>
            <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginBottom: 14 }}>
              {BANDS.map(([lab]) => {
                const inb = all.filter(p => bandOf(p.odds) === lab)
                const gm = agg(inb.filter(p => genderOf(p) === 'm'))
                const gw = agg(inb.filter(p => genderOf(p) === 'w'))
                const line = (g, a, col) => (
                  <span style={{ color: !a.n ? 'var(--text-tertiary)' : a.roi > 0 ? '#3fb950' : '#f85149' }}>
                    {g} {a.n ? `${a.roi > 0 ? '+' : ''}${a.roi.toFixed(0)}%/${a.n}` : '—'}
                  </span>
                )
                return (
                  <div key={lab}>
                    {box(lab, agg(inb), `Every deduped dog pick priced ${lab}, one band per pick.`)}
                    <div className="mono" style={{ fontSize: 9, fontWeight: 700, display: 'flex',
                      gap: 7, justifyContent: 'center', marginTop: 3 }}>
                      {line('M', gm)}{line('W', gw)}
                    </div>
                  </div>
                )
              })}
            </div>
          </>
        )
      })()}
      <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
        {pill(mode === 'today', `live + upcoming (${stacked.length})`, () => setMode('today'))}
        {pill(mode === 'hist', `history (${finished.length})`, () => setMode('hist'))}
        {pill(mode === 'cells', `by cell (${cells.length})`, () => setMode('cells'))}
        {pill(mode === 'auto', `\u{1F916} auto-bet \u00b7 paper${auto ? ` (${(auto.bets || []).length})` : ''}`, () => setMode('auto'))}
      </div>

      {mode === 'auto' ? (
        <AutoBetView auto={auto} />
      ) : mode === 'today' ? (
        stacked.length ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div className="mono" style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 10,
              color: 'var(--text-tertiary)', marginBottom: 2 }}>
              <span>order</span>
              {pill(order === 'edge', 'best ROI first', () => setOrder('edge'))}
              {pill(order === 'time', 'start time', () => setOrder('time'))}
              <span style={{ marginLeft: 6 }}>
                every record below is this pick’s <b>gender × price band</b>, not the lane blend ·
                readable cells (≥{MIN_CELL_N} settles) rank above thin ones
              </span>
            </div>
            {stacked.map((s, i) => {
              const n = s.cells.length
              const col = n >= 3 ? '#3fb950' : n === 2 ? '#e3b341' : 'var(--text-secondary)'
              const pr = pinkRule(s.p, s.cells.map(c => c.key))
              // a FAVOURITE pick -- yellow, and never pink, so the two can never be confused
              // no gender gate and no price gate any more: any MC6 favourite lane paints gold,
              // and the badge tooltip names which rules fired and whether they win
              // EVERY MC6 favourite is gold now, at any price (2026-10-16, user call)
              const fb = isFavPick(s.p) ? favMarkOf(s.p, s.cells.map(c => c.key)) : null
              const yel = !!fb
              const br = bestRec(s)      // the card's own gender x band headline
              return (
                <div key={i} className="mono" style={{
                  padding: '9px 13px', borderRadius: 8,
                  background: fb ? `rgba(${fb.rgba},0.10)` : pr ? 'rgba(247,120,186,0.10)' : 'var(--panel)',
                  border: `1px solid ${fb ? `rgba(${fb.rgba},0.85)` : pr ? 'rgba(247,120,186,0.85)'
                    : n >= 3 ? 'rgba(63,185,80,0.55)' : 'var(--line)'}`,
                  boxShadow: fb ? `0 0 16px rgba(${fb.rgba},0.30)`
                    : pr ? '0 0 14px rgba(247,120,186,0.22)' : undefined,
                }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
                    <span style={{ color: 'var(--text-tertiary)', fontSize: 10, fontWeight: 700, minWidth: 92 }}>
                      {multiDay ? `${dayLabel(whenMs(s.p))} ` : ''}{fmtPT(s.p.start) || s.p.date}
                    </span>
                    {isLive(s.p) ? (
                      <span title="Started and not settled yet -- this match is in progress."
                        style={{ fontSize: 9, fontWeight: 800, color: '#f85149', border: '1px solid #f8514988', borderRadius: 6, padding: '0 5px' }}>
                        {'● LIVE'}
                      </span>
                    ) : null}
                    <span style={{ color: col, fontWeight: 800, fontSize: 10, minWidth: 54 }}>
                      {n} cell{n === 1 ? '' : 's'}
                    </span>
                    {fb ? (
                      /* this comment must be a plain block comment, not a braced
                         JSX one, because it sits inside the parenthesised fb expression. */
                      <span title={fb.note}
                        style={{ fontSize: 10, fontWeight: 800, color: fb.col,
                          border: '1px solid ' + fb.col + '99', borderRadius: 6, padding: '0 5px' }}>
                        {'⭐ ' + fb.tag}
                      </span>
                    ) : null}
                    {/* MC6'S VERDICT ON THE SAME BET (2026-10-16, user "make sure to show it on
                        the dogs tab"). Same chip as the board's. Gold now comes from MC6's own lanes
                        (2026-10-17) and every EV-checked gold rule requires this number >= 0, so a
                        cross can only appear where a 4pt lane (no EV check) painted the card. Favourites only, matching the board: every
                        pick carries mc6_ev, but badging every dog row too would bury the signal.
                        NOT A GATE -- nothing is hidden and no cell or record changes. */}
                    {fb && s.p.mc6_ev != null ? (
                      <span style={{
                        fontSize: 9.5, fontWeight: 800, padding: '0 5px', borderRadius: 5,
                        color: s.p.mc6_ev >= 0 ? '#3fb950' : '#f0883e',
                        border: `1px solid ${s.p.mc6_ev >= 0 ? 'rgba(63,185,80,0.55)' : 'rgba(240,136,62,0.65)'}`,
                        background: s.p.mc6_ev >= 0 ? 'rgba(63,185,80,0.10)' : 'rgba(240,136,62,0.12)',
                      }}
                        title={`MC6 ON THIS SAME BET: ${s.p.mc6_ev >= 0 ? '+' : ''}${Math.round(1000 * s.p.mc6_ev) / 10}% EV at the OFFERED price.\n\n`
                          + `${s.p.mc6_ev >= 0
                              ? 'MC6 AGREES this is a positive-EV bet at the price offered.'
                              : 'MC6 IS OVER THE MARKET BUT NOT BY ENOUGH TO PAY THE VIG: at its own number this bet loses money at the price offered. This card is gold through a 4pt lane, which has no EV check -- the EV-checked rules (women 6pt+, men 3-6pt, the -150..-200 rules) would not have fired on it.'}\n\n`
                          + `THIS IS NOT A GATE. Nothing is hidden and the mark has not changed; it shows MC6's own EV at the offered price beside the mark.\n\n`
                          + `Every EV-checked gold rule already requires this number to be positive, so a cross can only appear on a card that went gold through a 4pt lane.`}>
                        {`MC6 ${s.p.mc6_ev >= 0 ? '\u2713' : '\u2717'} ${s.p.mc6_ev >= 0 ? '+' : ''}${Math.round(1000 * s.p.mc6_ev) / 10}%`}
                      </span>
                    ) : null}
                    {pr && !yel ? (
                      <span title={pr.tip} style={{ fontSize: 10, fontWeight: 800, color: PINK,
                        border: '1px solid ' + PINK + '88', borderRadius: 6, padding: '0 5px' }}>
                        {PINK_TAG}{pr.tag}
                      </span>
                    ) : null}
                    <span style={{ fontSize: 13, fontWeight: 700, color: fb ? fb.col : pr ? PINK : 'var(--text-primary)' }}>{s.p.pick}</span>
                    <span style={{ fontSize: 11, color: '#3fb950', fontWeight: 700 }}>
                      {s.p.odds != null ? (s.p.odds > 0 ? `+${s.p.odds}` : s.p.odds) : ''}
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>over {s.p.opp}</span>
                    {br ? (
                      <span title={`BEST CELL ON THIS CARD, measured on ${s.g === 'w' ? "WOMEN'S" : "MEN'S"} `
                        + `${br.d.band} only -- ${br.cel.label}: ${br.d.wins}-${br.d.n - br.d.wins}, `
                        + `${br.d.roi_pct > 0 ? '+' : ''}${br.d.roi_pct}% ROI, $${br.d.per_bet.toFixed(2)} per `
                        + `$25 bet.${br.thick ? '' : ` ONLY ${br.d.n} SETTLES -- below the ${MIN_CELL_N}`
                        + ` floor, so this ROI cannot be read as a forecast and the card ranks below`
                        + ` every readable one.`} This is what the list is sorted on.`}
                        style={{ fontSize: 10, fontWeight: 800, padding: '0 5px', borderRadius: 6,
                          color: br.d.per_bet >= 0 ? '#3fb950' : '#f85149',
                          border: `1px solid ${br.d.per_bet >= 0 ? 'rgba(63,185,80,0.5)' : 'rgba(248,81,73,0.5)'}`,
                          opacity: br.thick ? 1 : 0.62 }}>
                        {`${br.d.per_bet >= 0 ? '+' : '−'}$${Math.abs(br.d.per_bet).toFixed(2)}/bet`}
                        <span style={{ color: 'var(--text-tertiary)', fontWeight: 600 }}>
                          {` ${s.g.toUpperCase()} ${br.d.band} · ${br.d.roi_pct > 0 ? '+' : ''}${br.d.roi_pct}%/${br.d.n}${br.thick ? '' : ' thin'}`}
                        </span>
                      </span>
                    ) : null}
                    <span style={{ fontSize: 10, color: 'var(--text-tertiary)', marginLeft: 'auto' }}>
                      {s.p.tournament} · {s.p.surface} · {String(s.p.league || '').toUpperCase()}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginTop: 6 }}>
                    {s.cells.map((cel, j) => {
                      // GENDER x BAND, not the gender-wide blend (2026-10-14). The blend is the
                      // wrong number here: the men's MC2 4pt lane reads -3.04% across all prices
                      // and +30.6% in the band these picks are actually in.
                      const d = bandGenderRec(cel, s.g, s.p.odds)
                      const thin = d.n > 0 && d.n < MIN_CELL_N
                      return (
                        <span key={j} title={`${cel.note}\n\n[the record shown is `
                          + `${s.g === 'w' ? "WOMEN'S" : "MEN'S"} ${d.band || 'this band'} ONLY, which is `
                          + `the basis every gate on this tab uses -- not this cell's gender-wide blend`
                          + `${d.n ? `. ${d.wins}-${d.n - d.wins}, $${d.per_bet.toFixed(2)} per $25 bet` : ''}`
                          + `${thin ? `, and at ${d.n} settles it is below the ${MIN_CELL_N} floor` : ''}]`} style={{
                          fontSize: 9, padding: '1px 6px', borderRadius: 7,
                          border: '1px solid rgba(63,185,80,0.35)', color: '#3fb950',
                          opacity: thin ? 0.6 : 1,
                        }}>
                          {cel.label} <span style={{ color: 'var(--text-tertiary)' }}>
                            {d.n ? `${s.g.toUpperCase()} ${d.roi_pct > 0 ? '+' : ''}${Math.round(d.roi_pct)}%/${d.n}${thin ? ' thin' : ''}`
                              : `${s.g.toUpperCase()} new`}
                          </span>
                        </span>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="mono" style={{ fontSize: 12, color: 'var(--text-tertiary)', padding: 12 }}>
            no unsettled dog-cell picks right now{q ? ' matching that search' : ''}.
          </div>
        )
      ) : mode === 'hist' ? (
        histDays.length ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {histDays.map((grp, gi) => {
              const a = agg(grp.ps)
              return (
                <div key={gi}>
                  <div className="mono" style={{ display: 'flex', alignItems: 'baseline', gap: 9, marginBottom: 4 }}>
                    <span style={{ fontSize: 11, fontWeight: 800, color: 'var(--text-primary)' }}>{grp.d}</span>
                    <span style={{ fontSize: 12, fontWeight: 800, color: a.profit >= 0 ? '#3fb950' : '#f85149' }}>{usd(a.profit)}</span>
                    <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                      {a.w}-{a.l}{a.roi != null ? ` · ${a.roi > 0 ? '+' : ''}${a.roi.toFixed(1)}%` : ''}
                    </span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                    {grp.ps.slice().sort((x, y) => whenMs(x) - whenMs(y)).map((p, i) => (
                      <div key={i} className="mono" style={{
                        display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap',
                        padding: '5px 11px', borderRadius: 7,
                        background: favHist(p) ? `rgba(${favHist(p).rgba},0.09)`
                          : pinkRule(p, histCells(p).map(c => c.key)) ? 'rgba(247,120,186,0.09)' : 'var(--panel)',
                        border: `1px solid ${favHist(p) ? `rgba(${favHist(p).rgba},0.65)`
                          : pinkRule(p, histCells(p).map(c => c.key)) ? 'rgba(247,120,186,0.6)'
                          : p.won ? 'rgba(63,185,80,0.3)' : 'var(--line)'}`,
                      }}>
                        <span style={{ fontSize: 10, color: 'var(--text-tertiary)', minWidth: 52 }}>{fmtPT(p.start)}</span>
                        <span style={{ fontSize: 11, fontWeight: 800, minWidth: 14, color: p.won ? '#3fb950' : '#f85149' }}>
                          {p.won ? 'W' : 'L'}
                        </span>
                        <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>{p.pick}</span>
                        <span style={{ fontSize: 10, color: '#3fb950', fontWeight: 700 }}>
                          {p.odds != null ? (p.odds > 0 ? `+${p.odds}` : p.odds) : ''}
                        </span>
                        <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>over {p.opp}</span>
                        {p.score ? <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>{p.score}</span> : null}
                        <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
                          {histCells(p).length} cells
                        </span>
                        <span style={{ fontSize: 11, fontWeight: 700, marginLeft: 'auto', color: (p.pnl || 0) >= 0 ? '#3fb950' : '#f85149' }}>
                          {p.pnl == null ? '' : usd(p.pnl)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="mono" style={{ fontSize: 12, color: 'var(--text-tertiary)', padding: 12 }}>no settled dog picks yet.</div>
        )
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          {cells.sort((a, b) => (b.t || -9) - (a.t || -9)).map((cel) => {
            const c = cel.cShown || cel.c          // the genders actually listed, not the blend
            const isOpen = open === cel.key
            const pos = (c.roi_pct || 0) > 0
            return (
              <div key={cel.uid || cel.key} className="mono" title={cel.note}
                onClick={() => setOpen(isOpen ? null : cel.key)}
                style={{
                  padding: '10px 14px', borderRadius: 8, background: 'var(--panel)',
                  border: `1px solid ${pos ? 'rgba(63,185,80,0.4)' : 'var(--line)'}`,
                  cursor: cel.picks.length ? 'pointer' : 'default',
                }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: pos ? '#3fb950' : 'var(--text-secondary)', minWidth: 190 }}>
                    {cel.label}
                  </span>
                  <span style={{ fontSize: 14, fontWeight: 700, color: (c.profit_usd || 0) >= 0 ? '#3fb950' : '#f85149' }}>
                    {usd(c.profit_usd)}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                    {c.n ? `${c.wins}-${c.n - c.wins} · ${c.roi_pct > 0 ? '+' : ''}${c.roi_pct}%` : '0 settled'}
                    {c.pending ? ` · ${c.pending} pending` : ''}
                  </span>
                  {cel.hidden && cel.hidden.length ? (
                    <span title={'This headline counts only the gender(s) listed on the tab. '
                      + cel.hidden.map(g => g === 'w' ? 'Women' : 'Men').join(' and ')
                      + ' excluded: negative dog ROI.'}
                      style={{ fontSize: 9, fontWeight: 700, color: '#f85149',
                        border: '1px solid rgba(248,81,73,0.45)', borderRadius: 5, padding: '0 4px' }}>
                      {cel.hidden.map(g => g === 'w' ? 'W' : 'M').join('/') + ' excluded'}
                    </span>
                  ) : null}
                  <span style={{
                    fontSize: 10, fontWeight: 700,
                    color: cel.t == null ? 'var(--text-tertiary)' : cel.t >= 2 ? '#3fb950' : cel.t >= 1.5 ? '#e3b341' : 'var(--text-tertiary)',
                  }}>
                    {cel.t == null ? '' : `t ${cel.t.toFixed(2)}`}{cel.t != null && cel.t >= 2 ? ' ✓2se' : ''}
                  </span>
                  <span style={{ fontSize: 10, marginLeft: 'auto', display: 'flex', gap: 7 }}>
                    {['m', 'w'].map(g => {
                      const d = genderRec(cel.c, g)
                      const ok = genderOK(cel.c, g)
                      return (
                        <span key={g} title={ok
                          ? `${g === 'w' ? 'Women' : 'Men'}: shown on this tab.`
                          : `${g === 'w' ? 'Women' : 'Men'}: HIDDEN -- this gender's dog ROI is negative, so its picks are not listed.`}
                          style={{ color: !d.n ? 'var(--text-tertiary)' : ok ? '#3fb950' : '#f85149', fontWeight: 700 }}>
                          {g.toUpperCase()} {d.n ? `${d.roi_pct > 0 ? '+' : ''}${Math.round(d.roi_pct)}%/${d.n}` : '—'}
                          {d.n && !ok ? ' ✕' : ''}
                        </span>
                      )
                    })}
                    <span style={{ color: 'var(--text-tertiary)' }}>
                      {cel.picks.length ? `${cel.picks.length} picks${isOpen ? ' ▾' : ' ▸'}` : ''}
                    </span>
                  </span>
                </div>
                {isOpen && cel.picks.length ? (
                  <div style={{ marginTop: 8, borderTop: '1px solid var(--line)', paddingTop: 6, maxHeight: 320, overflowY: 'auto' }}>
                    {cel.picks.filter(p => priceOK(p) && leagueOK(p)).slice().sort((a, b) => whenMs(a) - whenMs(b)).map((p, i) => (
                      <div key={i} title={genderOK(cel.c, genderOf(p)) ? undefined : 'this gender’s half of the cell is negative, so picks like this are not listed on the today tab'}
                        style={{ fontSize: 10, display: 'flex', gap: 7, padding: '2px 0', color: 'var(--text-secondary)', opacity: genderOK(cel.c, genderOf(p)) ? 1 : 0.4 }}>
                        <span style={{ color: 'var(--text-tertiary)', minWidth: 58 }}>{p.date}</span>
                        <span style={{ color: 'var(--text-tertiary)', minWidth: 52 }}>{fmtPT(p.start)}</span>
                        <span style={{ minWidth: 14, fontWeight: 700, color: p.won == null ? '#e3b341' : p.won ? '#3fb950' : '#f85149' }}>
                          {p.won == null ? '…' : p.won ? 'W' : 'L'}
                        </span>
                        <span style={{ flex: 1 }}>{p.pick} <span style={{ color: 'var(--text-tertiary)' }}>vs {p.opp}</span></span>
                        <span style={{ color: 'var(--text-tertiary)', minWidth: 42 }}>
                          {p.odds != null ? (p.odds > 0 ? `+${p.odds}` : p.odds) : ''}
                        </span>
                        <span style={{ minWidth: 56, textAlign: 'right', color: p.pnl == null ? 'var(--text-tertiary)' : p.pnl >= 0 ? '#3fb950' : '#f85149' }}>
                          {p.pnl == null ? '' : usd(p.pnl)}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
