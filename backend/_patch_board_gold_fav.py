"""THE VALIDATED FAVOURITE CELLS PAINT GOLD ON THE BOARD (2026-10-15).

User, listing the five readable/thin positive favourite cells from the full $25-tab sweep:
"make sure these are all marked gold on the board".

    readable  mc2_fav4_w  all          21-8   +22.91%  t 1.63
    readable  mc2_fav4_m  all          18-11   +5.09%  t 0.33
    thin      mc2_fav4_w  -150..-200   10-2   +30.39%  t 1.81
    thin      mc2_fav4_w  -100..-150   11-6   +17.64%  t 0.84
    thin      mc2_fav4_m  -100..-150    9-5   +14.57%  t 0.64

WHAT WAS ALREADY TRUE. The board's mc2Mark ALREADY applies these exact cells -- the gender x band
split (`_favLo = gHL === 'w' ? -200 : -150`), the 4pt+ gate over the de-vigged market, the
favClearsPrice EV check and the auto-unmark. Every row in that list is already marked. It was
simply painted HL_BROWN, while the Dog picks tab paints the same cells GOLD. So this is a colour
correction that makes the two surfaces agree, not a new rule, and no card starts or stops being
marked because of it.

WHAT CHANGES: a favourite card whose mark is one of these cells now paints gold (#ffd700, the Dog
tab's own GOLD) and its chip reads gold. Dog marks keep brown. Precedence is unchanged -- the
favourite branch already sat where it sat; only the treatment it resolves to is different.

THE ONE ITEM NOT COVERED, stated rather than quietly skipped: "mc2_fav4_m all" also contains the
men's -150..-200 slice, which is -3.76% on 15 forward. `_favLo = -150` for men excludes it, which
is deliberate -- it is forward-negative, and it is the band the user had me remove from the tab on
2026-10-14 ("i only wanted man 100 to 150"). Marking the men's lane "all" would put it back. Left
off; one word and it goes in.
"""
import io
import os

F = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "TennisSection.jsx"))
s = io.open(F, encoding="utf-8").read()
assert "HL_GOLDFAV" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:80])
    s = s.replace(old, new)


# ---- the treatment ----
rep("""  const HL_BLACK = {""",
    """  // GOLD FOR THE VALIDATED FAVOURITE CELLS (2026-10-15, user "make sure these are all marked
  // gold on the board"). #ffd700 is the Dog picks tab's own GOLD, so the two surfaces now agree
  // on colour as well as on rule -- the board was already applying these exact gender x band
  // cells, it just painted them brown. Dog marks stay brown.
  const HL_GOLDFAV = {
    bg: 'rgba(255,215,0,0.14)',
    border: '1px solid rgba(255,215,0,0.95)',
    rail: '#ffd700',
    glow: '0 0 16px rgba(255,215,0,0.30)',
  }
  const HL_BLACK = {""")

# ---- mark the favourite cells so the colour layer can tell them apart ----
rep("""      return { cell: gHL === 'w' ? 'FAV 4pt+ W -100/200' : 'FAV 4pt+ M -100/150',
               lane: _favLane, who: fav1 ? match.player_1 : match.player_2,
               od: favAm, amt: Math.round(1000 * over) / 10, live: rec(_favLane),
               recon: !!m2.recon }""",
    """      return { cell: gHL === 'w' ? 'FAV 4pt+ W -100/200' : 'FAV 4pt+ M -100/150',
               // isFav drives the GOLD treatment below: these are the cells the Dog picks tab
               // marks gold (2026-10-15), and the board must not disagree with it on colour.
               isFav: true,
               lane: _favLane, who: fav1 ? match.player_1 : match.player_2,
               od: favAm, amt: Math.round(1000 * over) / 10, live: rec(_favLane),
               recon: !!m2.recon }""")

# ---- the colour chain ----
rep("""        : (mc2Mark && !mc2Mark.recon && !mc2Mark.avoid) ? HL_BROWN : HL_ORANGE""",
    """        : (mc2Mark && !mc2Mark.recon && !mc2Mark.avoid)
          ? (mc2Mark.isFav ? HL_GOLDFAV : HL_BROWN) : HL_ORANGE""")

io.open(F, "w", encoding="utf-8", newline="").write(s)
print("patched TennisSection.jsx")
for k in ("HL_GOLDFAV", "isFav: true", "mc2Mark.isFav"):
    print("   %-16s %d" % (k, s.count(k)))
print("RESULT: OK")
