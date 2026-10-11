"""MARK tier_avoid's DOG HALF, AND RAISE THE HIGHLIGHT FLOOR (2026-10-10, user "yes").

TWO CHANGES.

1. tier_avoid_dog becomes a card cell.
   tier_avoid was built as a CONTROL -- the board's own legend calls it "AVOID (tracked) ...
   this lane is supposed to LOSE; it proves the avoid verdict". It has falsified that verdict:
   dog half **+19.1% (n=98), men +17.4% / women +22.1%**. Only the DOG half is marked, because
   its favourite half is +0.9% on n=16 with men-fav -27.3% on n=10, and because every one of
   13 model heads loses on favourites. The cell is "C disagrees with gray AND C is on the dog",
   with the star and gray-hate configs excluded (they are caught earlier in the ladder).
   **This one is LIVE EVIDENCE ONLY -- there is no backtest claim behind it**, which is a
   deliberate departure from the HL_BT = backtest-positive convention, consistent with the
   forward-tests-only rule. The badge says so on the card.

2. The highlight floor rises for FAVOURITE-side cells, 3 -> 25 settles.
   hlOK greenlit any cell on 3 settles in that gender. With all 13 heads losing on favourites
   (-5.0% to -9.1% on n=487+), a favourite cell going green on 3-8 settles is backwards. Dog
   cells keep the 3-settle floor; favourite cells now need 25. Affects cgf_shallow_fav (n=16),
   cgf_premium (n=8), p_close (n=6) and the p_close tiers -- all currently green on tiny
   samples.
"""
import io

FE = "frontend/src/TennisSection.jsx"
BE = "backend/tennis_log.py"


def rep(path, a, b):
    s = io.open(path, encoding="utf-8").read()
    assert s.count(a) == 1, (path, s.count(a), a[:90])
    io.open(path, "w", encoding="utf-8", newline="\n").write(s.replace(a, b))


# ---- 1a. the backend lane ---------------------------------------------------------------
rep(BE,
    '''            if _tk and str(r.get("date") or "") >= "2026-09-30":
                bet(_tk, _ts)''',
    '''            if _tk and str(r.get("date") or "") >= "2026-09-30":
                bet(_tk, _ts)
                # 🟢 THE DOG HALF OF "AVOID" (2026-10-10, user "yes"). tier_avoid exists as a
                # CONTROL that was supposed to LOSE and prove the avoid verdict; instead its
                # dog half runs +19.1% (n=98), men +17.4% / women +22.1%, while its favourite
                # half is +0.9% on n=16 with men-fav -27.3%. Scored separately so the card
                # mark cites the dog-only record rather than the mixed one.
                if _tk == "tier_avoid" and _ts == dog1:
                    bet("tier_avoid_dog", _ts)''')

rep(BE,
    '''              "tier1", "tier2", "tier3", "tier_avoid", "tier_nobet", "fade_a",''',
    '''              "tier1", "tier2", "tier3", "tier_avoid", "tier_avoid_dog", "tier_nobet", "fade_a",''')

# ---- 1b. the card cell ------------------------------------------------------------------
rep(FE,
    """    if (aP !== null && bP !== null && aP !== c1 && bP === c1 && c1 === dog1 && g1 === c1) cells.push({ n: 'FADE-A DOG+GRAY',""",
    """    // 🟢 AVOID-DOG (2026-10-10, user "yes"): the dog half of the ribbon's own AVOID bucket.
    // tier_avoid was built as a control that was SUPPOSED to lose and prove the avoid verdict;
    // its dog half instead runs +19.1% live (n=98), men +17.4% / women +22.1%, against a
    // favourite half of +0.9% (n=16, men-fav -27.3%). So only the dog half is marked. The cell
    // is "C disagrees with gray and C is on the dog"; star and gray-hate configs are caught
    // earlier in the ladder, so excluding hate here is enough. NO BACKTEST behind this one --
    // it is live-record-only, which is why bm/bw read "live only".
    if (!((mdog - gdog) >= 0.02) && c1 !== g1 && c1 === dog1) {
      cells.push({ n: 'AVOID-DOG (live only)', bm: 'live only', bw: 'live only', am: 'no backtest claim', aw: 'no backtest claim', lane: 'tier_avoid_dog' })
    }
    if (aP !== null && bP !== null && aP !== c1 && bP === c1 && c1 === dog1 && g1 === c1) cells.push({ n: 'FADE-A DOG+GRAY',""")

rep(FE,
    """    p_dog_flip: { m: true, w: true },""",
    """    p_dog_flip: { m: true, w: true },
    // 🟢 AVOID-DOG: live-record-only, no backtest claim. Allowed through the gate deliberately
    // (2026-10-10 user sign-off) because the live dog half is +19.1% on n=98 both genders.
    tier_avoid_dog: { m: true, w: true },""")

# ---- 2. the floor ----------------------------------------------------------------------
rep(FE,
    """  const hlWhy = (lane, g) => {
    if (!lane || !HL_BT[lane] || !HL_BT[lane][g]) return 'backtest not positive'
    const c = ((((laneRec && laneRec.study) || {})[lane]) || {})[g] || {}
    if ((c.n || 0) < 3) return `live ${c.n || 0} settles (<3)`""",
    """  // MINIMUM LIVE SETTLES before a cell may colour (2026-10-10, user "yes"). Was a flat 3
  // for everything. Every one of 13 model heads LOSES on favourites (-5.0% to -9.1% on n=487+),
  // so a favourite-side cell turning a card green on 3-8 settles is backwards. Favourite cells
  // now need 25; dog cells keep 3, because there the prior is the other way.
  const HL_MIN_FAV = 25
  const FAV_SIDE = new Set(['cgf_shallow_fav', 'cgf_premium', 'p_close', 'p_close_t1',
                            'p_close_t2', 'p_close_t3', 'pink_wall9_fav'])
  const hlWhy = (lane, g) => {
    if (!lane || !HL_BT[lane] || !HL_BT[lane][g]) return 'backtest not positive'
    const c = ((((laneRec && laneRec.study) || {})[lane]) || {})[g] || {}
    const floor = FAV_SIDE.has(lane) ? HL_MIN_FAV : 3
    if ((c.n || 0) < floor) return `live ${c.n || 0} settles (<${floor}${FAV_SIDE.has(lane) ? ', favourite cell' : ''})`""")
print("shipped: tier_avoid_dog lane + card cell, and a 25-settle floor for favourite cells")
