"""BAND CELLS USE THE TAB'S OWN BASIS, AND BOTH-NEGATIVE CELLS LEAVE (2026-10-14).

User, on two band cells showing M -6%/25 and W -20%/20: "remove these from the dog board
completely since they're negative if there is any".

TWO CHANGES, and the first one matters more than the ask.

1. A BUG I INTRODUCED THIS MORNING. splitByBand summed a lane's picks in a price band with NO
   league or price filter, while every other number on this tab excludes ITF men and anything
   above +300. So the band cells were scored on a basis the tab does not use, and it flipped a
   sign:

       mc2_dog6_all +200..+250 men   incl ITF men   -5.96% / 25   <- what was displayed
                                     excl ITF men  +11.95% / 21   <- the tab's own basis
       mc2_dog4_all +200..+250 men   incl ITF men  -11.30% / 30
                                     excl ITF men   +2.35% / 26

   Four ITF-men picks were turning a positive cell negative -- and mc2_dog6_all at +200..+250 is
   a PINK source, so the board was contradicting its own mark. splitByBand now applies leagueOK
   and priceOK, exactly like dedupe().

2. THE RULE ASKED FOR: a cell whose every settled gender is negative is dropped from the tab
   entirely. Until now such a cell still occupied a row with its losing total while both halves
   showed the gender gate's cross -- visible, unusable, and misleading. A gender with no settles
   is unknown rather than negative and does not block the cell.

Note the two cells that prompted this survive the rule, because after fix 1 they are not
negative for both genders. That is the right outcome: they were a display bug, not a dead cell.
"""
import io
import os

P = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "DogPicksPanel.jsx"))
s = io.open(P, encoding="utf-8").read()
assert "allGendersNegative" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:80])
    s = s.replace(old, new)


# ---- 1. the band split must use the tab's own basis ----
rep("""    const ps = (cel.picks || []).filter(p => p.odds != null && p.odds >= lo && p.odds <= hi)""",
    """    // SAME BASIS AS THE REST OF THE TAB (fix, 2026-10-14): no ITF men, nothing above +300.
    // Without this the band cells were scored on a different population and flipped signs --
    // mc2_dog6_all +200..+250 men read -5.96% with four ITF-men picks in it and +11.95% without,
    // while being a PINK source, so the board contradicted its own mark.
    const ps = (cel.picks || []).filter(p => p.odds != null && p.odds >= lo && p.odds <= hi
      && priceOK(p) && leagueOK(p))""")

# ---- 2. drop a cell that is negative for every gender that has settles ----
rep("""const SPLIT_BY_BAND = new Set(['mc2_dog4_all', 'mc2_dog6_all'])""",
    """const SPLIT_BY_BAND = new Set(['mc2_dog4_all', 'mc2_dog6_all'])

// A CELL THAT LOSES FOR EVERY GENDER LEAVES THE TAB (2026-10-14, user: "remove these from the
// dog board completely since they're negative"). Until now such a cell still held a row with its
// losing total while both halves wore the gender gate's cross -- visible, unusable, misleading.
// A gender with NO settles is unknown, not negative, so it does not block the cell.
const allGendersNegative = (c) => {
  const seen = ['m', 'w'].map(g => genderRec(c, g)).filter(d => d && d.n)
  return seen.length > 0 && seen.every(d => (d.roi_pct || 0) <= 0)
}""")

rep("""    .flatMap(x => (SPLIT_BY_BAND.has(x.key) ? splitByBand(x) : [x]))""",
    """    .flatMap(x => (SPLIT_BY_BAND.has(x.key) ? splitByBand(x) : [x]))
    .filter(x => !allGendersNegative(x.c))""")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched DogPicksPanel.jsx")
print("   leagueOK in splitByBand : %s" % ("priceOK(p) && leagueOK(p)" in s))
print("   allGendersNegative refs : %d" % s.count("allGendersNegative"))
print("RESULT: OK")
