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
const FAV_CELLS = new Set(['mc2_fav4_w', 'mc2_fav4_m'])
const isFavPick = p => p.odds != null && p.odds < 0

// TWO BANDS, TWO COLOURS (2026-10-14, user "mark -150 to -200 favorites gold as well"). Same
// cell and same lane -- a women's favourite MC2 rates 4pt+ over the market -- but the bands are
// separately measured and the deeper one is the stronger half, so gold is the brighter colour:
//     -100..-150  n=28  19-9   67.9% hit vs 55.5% needed  +22.31%  t 1.40  -> yellow
//     -150..-200  n=23  18-5   78.3% hit vs 63.2% needed  +23.50%  t 1.73  -> gold
// The badge carries the band and the n so the two are never read as one number.
const FAV_BANDS = [
  { lo: -150, hi: -100, tag: 'FAV −100/150', col: YELLOW, rgba: '227,179,65',
    note: '-100..-150: +22.31% on 28 (19-9), 67.9% hit against 55.5% needed, t 1.40.' },
  { lo: -200, hi: -150, tag: 'FAV −150/200', col: GOLD, rgba: '255,215,0',
    note: '-150..-200: +23.50% on 23 (18-5), 78.3% hit against 63.2% needed, t 1.73 -- the stronger half.' },
]
const favBandOf = p => (p.odds == null || p.odds >= 0) ? null
  : (FAV_BANDS.find(b => p.odds >= b.lo && p.odds <= b.hi) || null)

const CELLS = [
  ['🟡 MC2 4pt+ FAV · WOMEN −100..−200', 'mc2_fav4_w', 'MC2 rates this WOMENS favourite 4+ points above the de-vigged market, priced -100..-200. Forward +26.72% on 24 (18-6). On forward + corrected recon: +22.85% on 51 (37-14, 72.5% hit against 59.0% needed, t 2.16) -- positive in BOTH windows (fwd +26.72%/24, recon +19.40%/27) and BOTH bands (-100..-150 +22.31%/28, -150..-200 +23.50%/23). The MENS half of the same cut is -9.21% on 74, and every womens favourite in that range is -3.64%, so this is not a generic favourite effect. The only favourite cell in this project to clear t=2. STILL THIN: 51 bets, and the gender split and 4pt threshold were both found by scanning this data.'],
  ['🟡 MC2 4pt+ FAV · men (control)', 'mc2_fav4_m', 'The MENS half of the same cut, kept visible as the control that justifies the womens cell: +1.63% on 25 forward, -9.21% on 74 pooled. NOT a take -- it is here so the split keeps being tested on screen instead of assumed.'],
  ['🟤 MC2 6pt+ DOG · all prices', 'mc2_dog6_all',
   'MC2 six or more points over the market on the dog, ANY price (2026-10-14, your ask). The forward ladder is why the bar is 6 and not 4: 3-4pt -1.9% on 27, 4-6pt -4.2% on 45, then 6-8pt +14.1% on 48 and 8pt+ +6.9% on 207. Both genders positive.'],
  ['🟤 MC2 4pt+ DOG · all prices', 'mc2_dog4_all',
   'MC2 four or more points over the market on the dog, ANY price. The 4pt sibling of the 6pt cell, added 2026-10-14 because the WOMENS ladder at +100..+150 peaks at 4pt (+13.15% on 91) and dies at 6pt (+3.07% on 68), the reverse of the mens, which climbs to 10pt. This lane feeds the womens pink mark. Its displayed record is a REPLAY of the frozen log, not a forward test -- the rule was written today.'],
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
//     +200..+250  men     22   7-15   +6.86%     0.21    (+3.11% / 37)   +1.51% / 87    PINK
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
  { lo: 100, hi: 150, g: 'm', tag: 'MC2 4pt+ M', cells: new Set(['mc2_dog4_all']), tip: 'MEN, +100..+150. MC2 four or more points over the de-vigged market on the dog. PINK IS GATED ON THE FORWARD RECORD ONLY (your call): the frozen pre-match log decides, the corrected recon is shown for contrast and does not. Forward +27.48% on 48 (28-20, 58.3% hit against 45.7% needed, t 1.77). The corrected recon agrees at +7.20% on 85, and blind mens dogs in this band are +7.39% on 291, so MC2 adds about 20 points forward. THE STRONGEST of the five pink cells: the only one where the forward ROI, the recon and the blind baseline all point the same way. On the board as a whole this is the best gender x band cell there is, +22.36% on 161 at t 2.61.' },
  { lo: 100, hi: 150, g: 'w', tag: 'MC2 4pt+ W', cells: new Set(['mc2_dog4_all']), tip: 'WOMEN, +100..+150. MC2 four or more points over the de-vigged market on the dog. PINK IS GATED ON THE FORWARD RECORD ONLY (your call): the frozen pre-match log decides, the corrected recon is shown for contrast and does not. Forward +21.95% on 38 (21-17, 55.3% hit against 45.3% needed, t 1.23). Corrected recon +6.85% on 53, also positive. Blind womens dogs in this band are -8.81% on 200, so the entire edge is MC2 selecting inside a LOSING band -- real, but it dies the moment MC2 drifts. Note the womens ladder peaks at 4pt and falls to +3.07% at 6pt, the reverse of the mens, which climbs all the way to +23.27% at 10pt.' },
  { lo: 150, hi: 200, g: 'w', tag: 'MC2 4pt+ W', cells: new Set(['mc2_dog4_all']), tip: 'WOMEN, +150..+200. MC2 four or more points over the de-vigged market on the dog. PINK IS GATED ON THE FORWARD RECORD ONLY (your call): the frozen pre-match log decides, the corrected recon is shown for contrast and does not. Forward +37.73% on 30 (15-15, 50.0% hit against 36.6% needed, t 1.50), and every rung from 2pt to 6pt is about the same forward. READ THE OTHER WINDOW: the corrected recon is -10.33% on 46 and negative at every rung. Blind womens dogs in the band are +8.38% on 111, so part of this is the price rather than MC2. In on the forward rule alone. The MENS half of this band is the worst cell on the board at -25.39% forward on 36, and it is excluded from the tab entirely.' },
  { lo: 200, hi: 250, g: 'm', tag: 'MC2 4pt+ M', cells: new Set(['mc2_dog4_all']), tip: 'MEN, +200..+250. MC2 four or more points over the de-vigged market on the dog. PINK IS GATED ON THE FORWARD RECORD ONLY (your call): the frozen pre-match log decides, the corrected recon is shown for contrast and does not. Forward +6.86% on 22 (7-15, 31.8% hit against 30.8% needed, t 0.21). THE THINNEST EDGE OF THE FIVE -- under seven points at t 0.21 is barely distinguishable from the blind band, which is +1.51% on 87. What recommends it is that both windows agree (recon +3.11% on 37) and that the deduped board cell is +32.43% on 30. The womens half of this band is excluded from the tab (-23.00% forward on 21).' },
  { lo: 250, hi: 300, g: 'w', tag: 'MC2 4pt+ W', cells: new Set(['mc2_dog4_all']), tip: 'WOMEN, +250..+300. MC2 four or more points over the de-vigged market on the dog. PINK IS GATED ON THE FORWARD RECORD ONLY (your call): the frozen pre-match log decides, the corrected recon is shown for contrast and does not. Forward +47.80% on 20 (8-12, 40.0% hit against 27.0% needed, t 1.18), the best forward ROI of the five. CAVEAT: blind womens dogs in this band are ALREADY +24.24% on 51, so a large part of this is the price and not MC2, and the corrected recon half is only +4.00% on 25. Long womens dogs are the one place this log says the market is persistently wrong; MC2 sharpens that rather than creating it. The MENS half of this band is excluded from the tab: -16.11% forward on 18, against a blind baseline of -40.36% on 58 (t -2.21), the most clearly dead cell on the board.' },
]

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
      if (!genderOK(cel.c, genderOf(p))) continue
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
      if (!genderOK(cel.c, genderOf(p))) continue
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

export default function DogPicksPanel({ query }) {
  const [rec, setRec] = useState(null)
  const [open, setOpen] = useState(null)
  const [mode, setMode] = useState('today')
  useEffect(() => {
    const go = () => fetch('/api/tennis/track-record').then(r => r.json())
      .then(d => setRec(d.ab25 || null)).catch(() => {})
    go()
    const id = setInterval(go, 120000)
    return () => clearInterval(id)
  }, [])
  const st = (rec && rec.study) || {}
  const q = (query || '').trim().toLowerCase()

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
    return { label, key, note, c, cShown, hidden, picks: c.picks || [], t: tstat(cShown) }
  }).filter(x => x.c && (x.c.n || x.picks.length))

  // TODAY: every unsettled pick, grouped by match, so a dog several cells agree on is visible
  // an unsettled pick whose match started long ago never got a result -- it is a gap in the
  // log, not an upcoming bet, so it does not belong on a picks list. Everything from six hours
  // ago onward is kept, which covers in-play matches without dragging in last week's orphans.
  const CUTOFF = Date.now() - 6 * 3600 * 1000
  const badBG = badBandGenders(cells)          // gender x band combinations that lose forward
  const byMatch = {}
  for (const cel of cells) {
    for (const p of cel.picks) {
      if (p.won != null || p.settled) continue
      if (whenMs(p) < CUTOFF) continue
      if (!priceOK(p) || !leagueOK(p)) continue   // nothing above +300, no ITF men
      const g = genderOf(p)
      if (!genderOK(cel.c, g)) continue       // this gender's half of the cell loses money
      if (badBG.has(bandKey(p))) continue     // ...and this gender x price band loses money
      const k = `${p.pick}|||${p.opp}`
      if (!byMatch[k]) byMatch[k] = { p, g, cells: [] }
      byMatch[k].cells.push(cel)
    }
  }
  // live + upcoming only -- finished picks are skipped by the `p.won != null` test above
  let stacked = Object.values(byMatch)
  if (q) {
    stacked = stacked.filter(s => (`${s.p.pick} ${s.p.opp} ${s.p.tournament || ''}`).toLowerCase().includes(q))
  }
  stacked.sort((a, b) => (whenMs(a.p) - whenMs(b.p)) || (b.cells.length - a.cells.length))

  // when the list spans more than one local day, each row gets its date so the order reads
  const multiDay = new Set(stacked.map(x => dayLabel(whenMs(x.p)))).size > 1

  // FINISHED picks for the history view: deduped to one row per dog, newest day first, and
  // grouped by day so each day carries its own record and P/L.
  const finished = dedupe(cells, isFinished).sort((a, b) => whenMs(b) - whenMs(a))
  // the same women-only rule for the history rows
  const favHist = (p) => (genderOf(p) === 'w'
    && histCells(p).some(c => c.key === 'mc2_fav4_w')) ? favBandOf(p) : null
  const histCells = (p) => cells.filter(cel => genderOK(cel.c, genderOf(p))
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
        rather than settled edges. Cells overlap heavily; the dollar figures are <i>not</i> additive. Everything is ordered <b>earliest start to latest</b>, and nothing above <b>+300</b> is shown — above that price the archive runs −17% to −18% at any model margin. <b style={{ color: PINK }}>{PINK_TAG}Pink</b> = <b>MC2 4pt+ over the market on the dog</b>, gender-specific, in the bands whose <b>forward</b> record is positive — the frozen pre-match log decides, the corrected recon is shown but does not. Five cells: <b>+100..+150</b> men +27.48%/48 (the strongest — forward, recon and blind baseline all agree) and women +21.95%/38; <b>+150..+200</b> women +37.73%/30 (recon −10.33% — forward only); <b>+200..+250</b> men +6.86%/22 (thinnest, t 0.21); <b>+250..+300</b> women +47.80%/20, though blind dogs there are already +24.24%. Anything whose forward record is negative is not merely unmarked, it is <b>off the tab entirely</b> — see the excluded line below. Thresholds and gender splits were all found by scanning this same data. <b style={{ color: YELLOW }}>⭐ Yellow (−100..−150) and 🥇 gold (−150..−200) = a FAVOURITE</b>, kept visually and numerically separate from the dogs: MC2 4pt+ over the market on a <b>women’s</b> favourite at −100..−200 — +22.85% on 51 (t 2.16), positive in both windows and both bands, against −9.21% for the men’s half. <b>ITF men is excluded</b>: it is the only league with a negative dog ROI here (−26.2% on 27, against WTA +21.0%, ATP challenger +11.6%, ATP tour +11.4%, ITF women +14.4%). Per-cell ROI and t below are still full-sample.
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
              const wCell = cells.find(c => c.key === 'mc2_fav4_w')
              const mCell = cells.find(c => c.key === 'mc2_fav4_m')
              if (!wCell && !mCell) return null
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
                    <span style={{ color: YELLOW }}>🟡 −100..−150</span>
                    <span style={{ color: 'var(--text-tertiary)' }}>{' / '}</span>
                    <span style={{ color: GOLD }}>🥇 −150..−200 (the stronger half)</span>
                    <span style={{ color: 'var(--text-tertiary)' }}>
                      {' — FAVOURITES, separate from every dog number above. MC2 4pt+ over the market. '}
                      {'Yellow +22.31%/28 t 1.40 · gold +23.50%/23 t 1.73 · combined +22.85%/51 t 2.16.'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginBottom: 14 }}>
                    {bx(wCell, 'women (the take)')}
                    {bx(mCell, 'men (control)')}
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
      </div>

      {mode === 'today' ? (
        stacked.length ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {stacked.map((s, i) => {
              const n = s.cells.length
              const col = n >= 3 ? '#3fb950' : n === 2 ? '#e3b341' : 'var(--text-secondary)'
              const pr = pinkRule(s.p, s.cells.map(c => c.key))
              // a FAVOURITE pick -- yellow, and never pink, so the two can never be confused
              // WOMEN ONLY (2026-10-14). mc2_fav4_m is the CONTROL, never a take, and painting a
              // mens favourite with the womens colours also handed it the womens tooltip.
              const fb = (isFavPick(s.p) && s.g === 'w'
                && s.cells.some(c => c.key === 'mc2_fav4_w')) ? favBandOf(s.p) : null
              const yel = !!fb
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
                      <span title={fb.note + '  ' + ((cells.find(c => c.key === 'mc2_fav4_w') || {}).note || '')}
                        style={{ fontSize: 10, fontWeight: 800, color: fb.col,
                          border: '1px solid ' + fb.col + '99', borderRadius: 6, padding: '0 5px' }}>
                        {'⭐ ' + fb.tag}
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
                    <span style={{ fontSize: 10, color: 'var(--text-tertiary)', marginLeft: 'auto' }}>
                      {s.p.tournament} · {s.p.surface} · {String(s.p.league || '').toUpperCase()}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginTop: 6 }}>
                    {s.cells.map((cel, j) => (
                      <span key={j} title={`${cel.note}  [record shown is the ${s.g === 'w' ? "WOMEN'S" : "MEN'S"} half of this cell, which is what applies to this match]`} style={{
                        fontSize: 9, padding: '1px 6px', borderRadius: 7,
                        border: '1px solid rgba(63,185,80,0.35)', color: '#3fb950',
                      }}>
                        {cel.label} <span style={{ color: 'var(--text-tertiary)' }}>
                          {(() => {
                            const d = genderRec(cel.c, s.g)
                            return d.n ? `${s.g.toUpperCase()} ${d.roi_pct > 0 ? '+' : ''}${Math.round(d.roi_pct)}%/${d.n}` : `${s.g.toUpperCase()} new`
                          })()}
                        </span>
                      </span>
                    ))}
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
              <div key={cel.key} className="mono" title={cel.note}
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
