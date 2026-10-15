"""SPLIT THE TWO ALL-PRICE MC2 CELLS INTO PRICE BANDS (2026-10-14).

User: "can u split up the prices on the dog tab the cells mc2 6pt+ dog and mc2 4pt+".

Those two were the last cells on the tab still reporting one blended number across every price:

    🟤 MC2 6pt+ DOG · all prices    M +6%/155
    🟤 MC2 4pt+ DOG · all prices    M -3%/185

A blend is exactly what hides the structure the rest of this board is built on -- the men's 4pt
cell reads -3% across all prices while being +27% at +100..+150, which is why it was being
suppressed for men until the MARK_CELLS fix this morning. Each lane now appears once per band:

    🟤 MC2 4pt+ DOG · +100..+150        🟤 MC2 6pt+ DOG · +100..+150
    🟤 MC2 4pt+ DOG · +150..+200        ... and so on for +200..+250 and +250..+300

HOW. The split is computed from the lane's OWN pick list -- each band cell holds that lane's picks
whose odds fall in the band, and its record (n, W-L, profit, ROI, gender splits) is summed from
those picks. So nothing new is fetched and the numbers cannot drift from the lane that scores them.

THE ONE TRAP, avoided deliberately: the pink rules match on a cell's `key`, and MARK_CELLS exempts
those same keys from the gender gate. Renaming the split cells would have silently broken both. So
each band cell keeps the ORIGINAL lane key and carries a separate `uid` for React and for display.
Several cells sharing a key is already fine everywhere -- dedupe() keys on the match, not the cell.
"""
import io
import os

P = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "DogPicksPanel.jsx"))
s = io.open(P, encoding="utf-8").read()
assert "splitByBand" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:80])
    s = s.replace(old, new)


# ---- the helper ----
rep("function tstat(c) {",
    """// SPLIT A LANE'S CELL INTO ONE CELL PER PRICE BAND (2026-10-14, user "split up the prices on
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
    const ps = (cel.picks || []).filter(p => p.odds != null && p.odds >= lo && p.odds <= hi)
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

function tstat(c) {""")

# ---- relabel the two cells so the band suffix reads cleanly ----
rep("""  ['🟤 MC2 6pt+ DOG · all prices', 'mc2_dog6_all',""",
    """  ['🟤 MC2 6pt+ DOG', 'mc2_dog6_all',""")
rep("""  ['🟤 MC2 4pt+ DOG · all prices', 'mc2_dog4_all',""",
    """  ['🟤 MC2 4pt+ DOG', 'mc2_dog4_all',""")

# ---- expand them after the cells array is built ----
rep("""    return { label, key, note, c, cShown, hidden, picks: c.picks || [], t: tstat(cShown) }
  }).filter(x => x.c && (x.c.n || x.picks.length))""",
    """    return { label, baseLabel: label, key, note, c, cShown, hidden,
             picks: c.picks || [], t: tstat(cShown) }
  }).filter(x => x.c && (x.c.n || x.picks.length))
    .flatMap(x => (SPLIT_BY_BAND.has(x.key) ? splitByBand(x) : [x]))""")

rep("const MIN_CELL_N = 25",
    """// these two lanes are shown one row PER PRICE BAND rather than as one blended number
const SPLIT_BY_BAND = new Set(['mc2_dog4_all', 'mc2_dog6_all'])
const MIN_CELL_N = 25""")

# ---- React keys: prefer uid where cells are listed ----
s = s.replace("<div key={cel.key}", "<div key={cel.uid || cel.key}")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched DogPicksPanel.jsx")
print("   splitByBand refs : %d" % s.count("splitByBand"))
print("   SPLIT_BY_BAND    : %d" % s.count("SPLIT_BY_BAND"))
print("   uid refs         : %d" % s.count("uid"))
print("RESULT: OK")
