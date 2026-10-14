"""THIN CELLS STOP COUNTING (2026-10-14).

User: "remove matches like this" -- a card carrying only `6-4 SPLIT W +17%/12` and
`D-MA DOG W +6%/23`, i.e. two cells whose gender records are too small to mean anything. Chosen
rule: ignore any cell whose record FOR THAT GENDER has fewer than MIN_CELL_N settles; a card left
with no qualifying cell disappears from the tab.

WHY A SAMPLE FLOOR RATHER THAN AN ROI FLOOR. At dog prices a 12-bet cell has a standard error
around 40 points, so +17% on 12 is indistinguishable from zero -- the problem is the sample, not
the number. An ROI floor would keep a 12-bet cell reading +40% while dropping a 200-bet cell
reading +8%, which is backwards.

MIN_CELL_N = 25. At dog prices that is roughly where a cell's standard error falls under about
25 points, and it is the smallest floor that removes the card the user pointed at. Named constant,
one place to change.

WHAT THIS DOES NOT TOUCH: the per-cell gender gate (a losing gender is still hidden regardless of
n), the gender x band board gate, and the pink/gold rules. All three are independent. A thin cell
also still appears in the "by cell" list with its own numbers -- it simply stops putting picks on
the live list and stops counting toward a card's cell tally.
"""
import io
import os

P = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "DogPicksPanel.jsx"))
s = io.open(P, encoding="utf-8").read()
assert "MIN_CELL_N" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:80])
    s = s.replace(old, new)


rep("""const genderOf = p => (/wta|itf_women/i.test(String(p.league || '')) ? 'w' : 'm')""",
    """const genderOf = p => (/wta|itf_women/i.test(String(p.league || '')) ? 'w' : 'm')

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
const MIN_CELL_N = 25
const cellThick = (c, g) => {
  const d = genderRec(c, g)
  return !d.n || d.n >= MIN_CELL_N
}""")

# the live list
rep("""      if (!genderOK(cel.c, g)) continue       // this gender's half of the cell loses money
      if (badBG.has(bandKey(p))) continue     // ...and this gender x price band loses money""",
    """      if (!genderOK(cel.c, g)) continue       // this gender's half of the cell loses money
      if (!cellThick(cel.c, g)) continue      // ...and this gender's half is too small to read
      if (badBG.has(bandKey(p))) continue     // ...and this gender x price band loses money""")

# the deduped aggregates and the history
rep("""      if (!genderOK(cel.c, genderOf(p))) continue
      if (bad.has(bandKey(p))) continue        // this gender x band loses money forward""",
    """      if (!genderOK(cel.c, genderOf(p))) continue
      if (!cellThick(cel.c, genderOf(p))) continue   // too few settles for this gender to read
      if (bad.has(bandKey(p))) continue        // this gender x band loses money forward""")

# the badge list on each card
rep("""  const histCells = (p) => cells.filter(cel => genderOK(cel.c, genderOf(p))""",
    """  const histCells = (p) => cells.filter(cel => genderOK(cel.c, genderOf(p))
    && cellThick(cel.c, genderOf(p))""")

# and the record used to build the band gate, so it describes the same population
rep("""      if (!genderOK(cel.c, genderOf(p))) continue
      const k = `${p.date}|||${p.pick}|||${p.opp}`
      if (!seen.has(k)) seen.set(k, p)""",
    """      if (!genderOK(cel.c, genderOf(p))) continue
      if (!cellThick(cel.c, genderOf(p))) continue
      const k = `${p.date}|||${p.pick}|||${p.opp}`
      if (!seen.has(k)) seen.set(k, p)""")

# legend
rep("<b>ITF men is excluded</b>",
    "A cell whose record for that gender has <b>fewer than 25 settles</b> no longer counts — at dog "
    "prices a 12-bet cell has a standard error near 40 points, so it cannot be read — and a card "
    "left with no qualifying cell drops off this list (it still appears under <i>by cell</i>). "
    "<b>ITF men is excluded</b>")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched DogPicksPanel.jsx")
print("   cellThick call sites: %d" % s.count("cellThick("))
print("RESULT: OK")
