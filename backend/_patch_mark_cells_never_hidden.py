"""A CELL THE BOARD MARKS FROM IS NEVER HIDDEN BY ITS BLENDED RECORD (2026-10-14).

User: "a few mc2 6p+ dogs that should be highlighted still" -- men's MC2 dogs at +100..+150 were
never painting.

THE BUG. genderOK hides a cell for a gender whose ALL-PRICE record is negative. mc2_dog4_all is
-3.04% on 185 for men across every price, so the cell was hidden for men entirely -- including at
+100..+150, where it is +27.48% on 48. The pink rule for men +100..+150 reads that cell, so it
could never fire. Jerome Kym +118 was in the cell's pick list and still came out unpainted.

The marks are BAND-specific; the gate was ALL-PRICE. A cell can be bad overall and good in one
band, which is the entire finding of the last few hours.

THE FIX: a cell named by a pink or gold rule is exempt from genderOK and from the thin-cell floor.
Those two gates exist to stop a losing or unreadable cell putting picks on the list on its own;
they should not override a rule that was written against a measured band. Everything else still
applies in full -- the price cap, the league gate, the gender x band board gate, and the rule's own
band and gender test, which is what actually decides the paint.

CONSEQUENCE, stated rather than hidden: a mark-source cell can now also appear as a BADGE on cards
outside its marked band (an mc2_dog4_all badge on a men's +200..+250 card, say). It is a badge, not
a mark -- the pink rule still only fires inside its own band.
"""
import io
import os

P = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "DogPicksPanel.jsx"))
s = io.open(P, encoding="utf-8").read()
assert "MARK_CELLS" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:80])
    s = s.replace(old, new)


rep("const MIN_CELL_N = 25",
    """// MARK_CELLS (2026-10-14, user "a few mc2 6p+ dogs that should be highlighted still").
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
  'mc2_fav4_w', 'mc2_fav4_m',
])
const MIN_CELL_N = 25""")

rep("""      if (!genderOK(cel.c, g)) continue       // this gender's half of the cell loses money
      if (!cellThick(cel.c, g)) continue      // ...and this gender's half is too small to read""",
    """      // a cell the board marks from is judged by its RULE's band, not by its blended record
      if (!MARK_CELLS.has(cel.key)) {
        if (!genderOK(cel.c, g)) continue     // this gender's half of the cell loses money
        if (!cellThick(cel.c, g)) continue    // ...and this gender's half is too small to read
      }""")

rep("""      if (!genderOK(cel.c, genderOf(p))) continue
      if (!cellThick(cel.c, genderOf(p))) continue   // too few settles for this gender to read
      if (bad.has(bandKey(p))) continue        // this gender x band loses money forward""",
    """      if (!MARK_CELLS.has(cel.key)) {
        if (!genderOK(cel.c, genderOf(p))) continue
        if (!cellThick(cel.c, genderOf(p))) continue  // too few settles for this gender to read
      }
      if (bad.has(bandKey(p))) continue        // this gender x band loses money forward""")

rep("""  const histCells = (p) => cells.filter(cel => genderOK(cel.c, genderOf(p))
    && cellThick(cel.c, genderOf(p))""",
    """  const histCells = (p) => cells.filter(cel => (MARK_CELLS.has(cel.key)
      || (genderOK(cel.c, genderOf(p)) && cellThick(cel.c, genderOf(p))))""")

rep("""      if (!genderOK(cel.c, genderOf(p))) continue
      if (!cellThick(cel.c, genderOf(p))) continue
      const k = `${p.date}|||${p.pick}|||${p.opp}`""",
    """      if (!MARK_CELLS.has(cel.key)) {
        if (!genderOK(cel.c, genderOf(p))) continue
        if (!cellThick(cel.c, genderOf(p))) continue
      }
      const k = `${p.date}|||${p.pick}|||${p.opp}`""")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched DogPicksPanel.jsx")
print("   MARK_CELLS guards: %d" % s.count("MARK_CELLS.has(cel.key)"))
print("RESULT: OK")
