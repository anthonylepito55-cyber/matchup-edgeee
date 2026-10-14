"""MERGE ITF INTO THE MAIN BOARD, BUT ONLY WHERE MC2 MARKS THE DOG (2026-10-14).

User: "can u mix the itf board into the main board but just on picks that mc2 likes on the dog tab".

ITF is a SEPARATE ENDPOINT (/api/tennis/itf), not a filtered slice of /today -- the main board
never had the data. So this fetches it and folds in the qualifying matches.

ONLY the ones carrying an MC2 DOG mark come across, using the same gender x price band rules the
Dog picks tab and the board brown marks use:

    men   +100..+150  4pt+        women +100..+150  4pt+
    women +150..+200  4pt+        men   +200..+250  6pt+
    women +250..+300  4pt+

155 ITF matches in today's feed, 42 carry MC2 at all, and only the subset meeting a band rule is
merged -- so this adds a handful of cards, not a second board.

LOADED IN THE BACKGROUND, deliberately. /api/tennis/itf takes up to ~30s on a cold cache and the
user has just asked for the site to load FASTER. The board renders immediately from /today and the
ITF cards appear when the fetch lands; nothing waits on it, and a failure is swallowed so a slow or
broken ITF feed can never block the board.

ITF MEN ARE EXCLUDED, matching the Dog picks tab, which drops them because ITF men is the only
league with a negative dog ROI there (-26.15% on 27). The user anchored this on "picks that mc2
likes on the dog tab", so the tab's own gates are the ones applied. If ITF men should come too,
that is the one constant ITF_MEN_ON_BOARD.
"""
import io
import os

P = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "TennisSection.jsx"))
s = io.open(P, encoding="utf-8").read()
assert "itfBoardExtra" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:80])
    s = s.replace(old, new)


# ---- the predicate, at module scope beside the other board constants ----
rep("const SHOW_MODEL_P = false",
    """const SHOW_MODEL_P = false

// ITF ON THE MAIN BOARD (2026-10-14, user "mix the itf board into the main board but just on
// picks that mc2 likes on the dog tab"). ITF is its own endpoint, so the board never had the
// data; only matches carrying an MC2 DOG mark are folded in, on the same gender x band rules the
// Dog picks tab and the brown board marks use.
//
// ITF men are excluded, matching the tab, which drops them as the only league with a negative dog
// ROI there (-26.15% on 27). Flip ITF_MEN_ON_BOARD to include them.
const ITF_MEN_ON_BOARD = false
const ITF_DOG_CELLS = [
  { g: 'm', lo: 100, hi: 150, pt: 0.04 },
  { g: 'w', lo: 100, hi: 150, pt: 0.04 },
  { g: 'w', lo: 150, hi: 200, pt: 0.04 },
  { g: 'm', lo: 200, hi: 250, pt: 0.06 },
  { g: 'w', lo: 250, hi: 300, pt: 0.04 },
]
// true when MC2 marks the DOG on this match under the board's own rules
function mc2DogMarked(m) {
  const mc2 = m && m.mc2
  const lo = m && m.live_odds
  if (!mc2 || mc2.p1_prob == null || !lo) return false
  if (!ITF_MEN_ON_BOARD && String(m.league || '').toLowerCase() === 'itf_men') return false
  const am = (v) => { const n = Number(v); return isNaN(n) ? null : n }
  const o1 = am(lo.player_1), o2 = am(lo.player_2)
  if (o1 == null || o2 == null) return false
  const dec = (o) => (o > 0 ? 1 + o / 100 : 1 + 100 / Math.abs(o))
  const d1 = dec(o1), d2 = dec(o2)
  const mk1 = (1 / d1) / ((1 / d1) + (1 / d2))
  const dog1 = mk1 < 0.5
  const dogAm = dog1 ? o1 : o2
  const mkFav = Math.max(mk1, 1 - mk1)
  const mcFav = dog1 ? 1 - mc2.p1_prob : mc2.p1_prob
  const over = mcFav - mkFav                      // negative = MC2 is over on the DOG
  const g = (m.league === 'wta' || m.league === 'itf_women') ? 'w' : 'm'
  return ITF_DOG_CELLS.some(c => c.g === g && dogAm >= c.lo && dogAm <= c.hi && over <= -c.pt)
}""")

# ---- fetch it in the background and merge ----
rep("""  const all = data?.matches ?? []""",
    """  // ITF, fetched in the BACKGROUND so the board never waits on it -- /api/tennis/itf can take
  // ~30s cold, and a slow or failing ITF feed must not hold up /today. Only MC2-marked dogs merge.
  const [itfBoardExtra, setItfBoardExtra] = useState([])
  useEffect(() => {
    let dead = false
    const go = () => fetch('/api/tennis/itf').then(r => r.json()).then(d => {
      if (dead) return
      const keep = (d.matches || []).filter(m => m.status !== 'completed' && mc2DogMarked(m))
      setItfBoardExtra(keep)
    }).catch(() => {})
    go()
    const id = setInterval(go, 300000)   // 5 min; these cards change slowly and the call is heavy
    return () => { dead = true; clearInterval(id) }
  }, [])
  const all = [...(data?.matches ?? []), ...itfBoardExtra]""")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched TennisSection.jsx")
print("   mc2DogMarked refs : %d" % s.count("mc2DogMarked"))
print("   itfBoardExtra refs: %d" % s.count("itfBoardExtra"))
print("RESULT: OK")
