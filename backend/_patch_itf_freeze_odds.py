"""FREEZE THE PRICE ON MERGED ITF CARDS (2026-10-14).

User: "make sure itf markets don't move on main board it moved for kuzmova".

WHAT WAS HAPPENING. The board re-fetches /api/tennis/itf every five minutes and rebuilt the merged
list from scratch each time, so an ITF card showed whatever the feed said at that moment. ITF
markets are thin and move hard, so a card seen at +102 could read something else minutes later --
and worse, the MARK itself could appear or vanish, because the band test is on the price: +102 is
inside +100..+150 and +98 is not. The card the user evaluated was not the card that stayed there.

THE FIX. The first price an ITF match is seen at is the price it keeps. A ref holds each merged
match by fixture_id; on every later poll the stored `live_odds` is kept and only the volatile
fields -- status and score -- are refreshed, so a live match still updates its score while the
number it was marked at stays put.

Qualification is frozen with it: a match that qualified stays on the board at its original price
even if the feed later moves it out of band. That is the point -- the mark described a price that
existed, and a card should not silently rewrite itself under the user.

Matches that go completed drop out, as everywhere else on the board.

NOT APPLIED to /api/tennis/today cards. Those are the main feed and are expected to track the
market; only the merged ITF cards are frozen, because they are the ones that arrive from a slow
side-channel and get marked on arrival.
"""
import io
import os

P = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "TennisSection.jsx"))
s = io.open(P, encoding="utf-8").read()
assert "itfFrozen" not in s, "already patched"

OLD = """  const [itfBoardExtra, setItfBoardExtra] = useState([])
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
  }, [])"""
NEW = """  const [itfBoardExtra, setItfBoardExtra] = useState([])
  // THE PRICE IS FROZEN AT FIRST SIGHT (2026-10-14, user "make sure itf markets don't move on main
  // board it moved for kuzmova"). ITF markets are thin and move hard, and the band test is ON THE
  // PRICE -- +102 is inside +100..+150 and +98 is not -- so rebuilding the list each poll let a
  // card change its number, and its mark, under the user. The first price a match is seen at is
  // the price it keeps; only status and score refresh, so a live match still updates its score.
  // Qualification freezes with it: a card that qualified stays at the price it qualified at.
  const itfFrozen = useRef(new Map())
  useEffect(() => {
    let dead = false
    const go = () => fetch('/api/tennis/itf').then(r => r.json()).then(d => {
      if (dead) return
      const store = itfFrozen.current
      const live = new Set()
      for (const m of (d.matches || [])) {
        const id = m.fixture_id
        if (id == null) continue
        if (m.status === 'completed') { store.delete(id); continue }
        live.add(id)
        const had = store.get(id)
        if (had) {
          // keep the frozen price (and therefore the mark); refresh only what should move
          store.set(id, { ...had, status: m.status, score: m.score })
        } else if (mc2DogMarked(m)) {
          store.set(id, m)
        }
      }
      for (const id of [...store.keys()]) if (!live.has(id)) store.delete(id)
      setItfBoardExtra([...store.values()])
    }).catch(() => {})
    go()
    const id = setInterval(go, 300000)   // 5 min; these cards change slowly and the call is heavy
    return () => { dead = true; clearInterval(id) }
  }, [])"""
assert s.count(OLD) == 1, "the ITF fetch block was not found"
s = s.replace(OLD, NEW)

# make sure useRef is imported
import re
m = re.search(r"import React, \{([^}]*)\} from 'react'", s)
assert m, "could not find the React import"
names = [x.strip() for x in m.group(1).split(',') if x.strip()]
if 'useRef' not in names:
    names.append('useRef')
    s = s[:m.start()] + "import React, { %s } from 'react'" % ', '.join(names) + s[m.end():]

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched TennisSection.jsx")
print("   itfFrozen refs: %d" % s.count("itfFrozen"))
print("   useRef imported: %s" % ("useRef" in re.search(r"import React, \{([^}]*)\}", s).group(1)))
print("RESULT: OK")
