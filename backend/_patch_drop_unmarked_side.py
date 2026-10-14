"""WHEN BOTH SIDES OF A MATCH ARE LISTED, KEEP ONLY THE MARKED ONE (2026-10-14).

User: "this has the opponent of the highlighted / remove the non highlighted in these cases" --
Biolay -111 carrying a gold favourite mark, and Paszun +111, the same match, directly underneath
with no mark.

Both sides can qualify because the dog cells and the favourite cells are independent: one head
likes the dog, another likes the favourite. Showing both is worse than useless -- they are
opposite bets on one match, so backing the list as printed guarantees one loser.

THE RULE: group the live list by MATCH (date + the two names, order-independent). If a match has
more than one entry and at least one of them is MARKED -- pink for a dog, gold for a favourite --
drop the unmarked entries. If none is marked, or if several are, nothing is dropped and both sides
stay visible, because then the tab has no basis for choosing between them.

Deliberately NOT applied to the history or the aggregates: those are a record of what the cells
actually did, and silently removing one side of a settled pair would misstate it.
"""
import io
import os

P = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "DogPicksPanel.jsx"))
s = io.open(P, encoding="utf-8").read()
assert "sameMatchKey" not in s, "already patched"

OLD = """  stacked.sort((a, b) => (whenMs(a.p) - whenMs(b.p)) || (b.cells.length - a.cells.length))"""
NEW = """  stacked.sort((a, b) => (whenMs(a.p) - whenMs(b.p)) || (b.cells.length - a.cells.length))

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
  const markOf = (x) => (isFavPick(x.p)
    ? ((x.cells.some(c => c.key === (x.g === 'w' ? 'mc2_fav4_w' : 'mc2_fav4_m')))
        ? favBandOf(x.p) : null)
    : pinkRule(x.p, x.cells.map(c => c.key)))
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
  })"""
assert s.count(OLD) == 1, "the sort line was not found"
s = s.replace(OLD, NEW)

s = s.replace("<b>ITF men is excluded</b>",
              "When <b>both sides of one match</b> qualify and only one carries a mark, the unmarked "
              "side is dropped from this list — they are opposite bets, so showing both guarantees a "
              "loser (the history keeps both). <b>ITF men is excluded</b>", 1)

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched DogPicksPanel.jsx")
print("   markOf / sameMatchKey present:", "sameMatchKey" in s and "markOf" in s)
print("RESULT: OK")
