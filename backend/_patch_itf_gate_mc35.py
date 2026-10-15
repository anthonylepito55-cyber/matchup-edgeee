"""THE ITF BOARD GATE READS MC2, MC3 AND MC5 (2026-10-15).

User: "i want mc3 and mc5 added to the itf brown picks".

mc2DogMarked() hard-coded m.mc2. It becomes mcDogMarks(), which runs the SAME gender x band cell
test over each of MC2, MC3 and MC5 and returns the list of heads that mark the dog -- so a card
qualifies for the board if ANY of the three marks it, and the card can say which did.

Why ANY rather than ALL: requiring all three would be a consensus gate, and MC5 is MC3 plus
extras while MC3 is MC2 plus fixes, so they agree by construction -- an ALL gate would mostly
just re-mark MC2's own cards while quietly dropping the ones where the newer heads see something
MC2 does not. ANY keeps the cards MC2 already brought and adds the heads' own.

Stated plainly: the cells themselves were measured on MC2's forward record. MC3 and MC5 have
almost no forward record of their own (~92 and ~31 rows before this patch, none of it ITF), so
their marks here are the user's call, not a validated edge, and the badge says which head fired
so the two can be told apart on the board rather than blending into one brown mark.
"""
import io
import os

F = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "TennisSection.jsx"))
s = io.open(F, encoding="utf-8").read()
assert "mcDogMarks" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


rep("""// true when MC2 marks the DOG on this match under the board's own rules
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
}""",
    """// WHICH OF MC2 / MC3 / MC5 MARK THE DOG HERE (2026-10-15, user "i want mc3 and mc5 added to the
// itf brown picks"). Was mc2DogMarked(), hard-coded to m.mc2. Returns the list of heads that mark,
// so a card reaches the board if ANY of the three does and can still say which.
//
// ANY, not ALL, on purpose: MC5 is MC3 plus extras and MC3 is MC2 plus fixes, so they agree by
// construction -- an ALL gate would mostly re-mark MC2's own cards while dropping exactly the ones
// where a newer head sees something MC2 misses, which is the only reason to add them.
//
// Honest about what this is: the gender x band cells were measured on MC2's FORWARD record. MC3 and
// MC5 have almost none of their own (~92 and ~31 rows, and none on ITF until the backend patch that
// accompanies this), so an MC3/MC5-only mark is the user's call rather than a measured edge. The
// badge names the head so the board does not blend them into one undifferentiated brown mark.
const MC_HEADS = [['MC2', 'mc2'], ['MC3', 'mc3'], ['MC5', 'mc5']]
function mcDogMarks(m) {
  const lo = m && m.live_odds
  if (!m || !lo) return []
  if (!ITF_MEN_ON_BOARD && String(m.league || '').toLowerCase() === 'itf_men') return []
  const am = (v) => { const n = Number(v); return isNaN(n) ? null : n }
  const o1 = am(lo.player_1), o2 = am(lo.player_2)
  if (o1 == null || o2 == null) return []
  const dec = (o) => (o > 0 ? 1 + o / 100 : 1 + 100 / Math.abs(o))
  const d1 = dec(o1), d2 = dec(o2)
  const mk1 = (1 / d1) / ((1 / d1) + (1 / d2))
  const dog1 = mk1 < 0.5
  const dogAm = dog1 ? o1 : o2
  const mkFav = Math.max(mk1, 1 - mk1)
  const g = (m.league === 'wta' || m.league === 'itf_women') ? 'w' : 'm'
  const out = []
  for (const [tag, key] of MC_HEADS) {
    const h = m[key]
    if (!h || h.p1_prob == null) continue
    const over = (dog1 ? 1 - h.p1_prob : h.p1_prob) - mkFav   // negative = head is over on the DOG
    if (ITF_DOG_CELLS.some(c => c.g === g && dogAm >= c.lo && dogAm <= c.hi && over <= -c.pt)) {
      out.push(tag)
    }
  }
  return out
}
// kept as a thin wrapper so existing call sites read the same
function mc2DogMarked(m) { return mcDogMarks(m).length > 0 }""")

# the merge store should remember which heads fired, for the badge
rep("""        } else if (mc2DogMarked(m)) {
          store.set(id, m)
        }""",
    """        } else {
          const marks = mcDogMarks(m)
          if (marks.length) store.set(id, { ...m, mc_marks: marks })
        }""")

io.open(F, "w", encoding="utf-8", newline="").write(s)
print("patched TennisSection.jsx")
for k in ("mcDogMarks", "MC_HEADS", "mc_marks"):
    print("   %-14s %d" % (k, s.count(k)))
print("RESULT: OK")
