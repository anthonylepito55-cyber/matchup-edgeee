"""THE BOARD'S BROWN MARKS NOW USE THE DOG TAB'S MC2 GENDER x BAND RULES (2026-10-14).

User: "for the board we only have mc2 signals can u use the same mc2 rules on odds for the board
brown highlights", and separately chose to DROP the three-head agreement gate so the board matches
the tab exactly.

BEFORE: margin-threshold cells with no gender split (dog 3pt+ at +100..+250, long dog 10pt+ at
+200..+250, 8pt+ at +250..+300, dog flip, fav 0-2pt / 2-8pt / >8pt at -100..-250), every one of
them additionally requiring MC2, MC3 and MC5 to agree.

AFTER: exactly the tab's MC2 rules, forward-measured per gender x price band:

    DOGS                               FAVOURITES
    men   +100..+150   4pt+            women -100..-200   4pt+
    women +100..+150   4pt+            men   -100..-150   4pt+
    women +150..+200   4pt+
    men   +200..+250   6pt+
    women +250..+300   4pt+

Forward records behind them (lane discipline, first-match bands):
    men   +100..+150  +27.48%/48    women +100..+150  +21.95%/38
    women +150..+200  +37.73%/30    men   +200..+250  +30.61%/18  (6pt)
    women +250..+300  +47.80%/20
    women fav -100..-200 +22.85%/51 pooled t 2.16    men fav -100..-150 +18.51%/12

WHAT IS DELETED, and why it is not a silent loss:
  * THE AGREEMENT GATE. Only 31 frozen settled rows have all three heads present, so it was
    gating on almost nothing. Dropping it is the user's call and means MORE cards mark.
  * the ungendered bands. men +150..+200 (-25.39%/36) and women +200..+250 (-23.00%/21) were
    inside the old +100..+250 dog cell and are now excluded, which is the point of the split.
  * the 0-2pt and 2-8pt favourite slices, replaced by one 4pt+ test per gender.
  * the mens -150..-200 favourite, which the user removed from the tab earlier today.

KEPT: the NO DOG avoid cell (it warns rather than recommends), the favClearsPrice EV check on
favourites, and mc2Alive, which auto-unmarks a cell whose own lane turns negative.
"""
import io
import os

P = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "TennisSection.jsx"))
s = io.open(P, encoding="utf-8").read()
assert "MC2 BAND RULES (board)" not in s, "already patched"

# ---- 1. replace the DOG rules: from the long-dog cell up to (not incl.) the NO DOG avoid cell
i = s.index("    // THE LONG-DOG CELL: a +200..+250 dog MC2 rates 10pt+ over its price.")
j = s.index("    // the AVOID cell is deliberately NOT gated on agreement")
DOGS = '''    // ---- MC2 BAND RULES (board), 2026-10-14 ----
    // User: "can u use the same mc2 rules on odds for the board brown highlights", and the
    // three-head agreement gate was dropped on the same call so the board matches the Dog picks
    // tab exactly. Those rules are gender x PRICE BAND, forward-measured, because the men's dog
    // edge lives at +100..+150 and dies above it while the women's survives or peaks deeper --
    // three unrelated signal families agree on that, so one ungendered band was hiding both.
    //
    //   men   +100..+150  4pt+   +27.48% / 48        women +100..+150  4pt+  +21.95% / 38
    //   women +150..+200  4pt+   +37.73% / 30        men   +200..+250  6pt+  +30.61% / 18
    //   women +250..+300  4pt+   +47.80% / 20
    //
    // Bands that are NOT marked are forward-negative for that gender and were previously swept
    // in by the old +100..+250 cell: men +150..+200 (-25.39%/36), women +200..+250 (-23.00%/21).
    //
    // `over` is MC2 on the FAVOURITE minus the de-vigged market, so a dog N points over is
    // over <= -N/100. Bands are first-match, so +150 belongs to +100..+150 only.
    const _dogBand = (lo2, hi2) => !isNaN(dogAm) && dogAm >= lo2 && dogAm <= hi2
    const DOG_CELLS = [
      { g: 'm', lo: 100, hi: 150, pt: 0.04, cell: 'DOG 4pt+ M +100/150', lane: 'mc2_dog_band' },
      { g: 'w', lo: 100, hi: 150, pt: 0.04, cell: 'DOG 4pt+ W +100/150', lane: 'mc2_dog_band' },
      { g: 'w', lo: 150, hi: 200, pt: 0.04, cell: 'DOG 4pt+ W +150/200', lane: 'mc2_dog_band' },
      { g: 'm', lo: 200, hi: 250, pt: 0.06, cell: 'DOG 6pt+ M +200/250', lane: 'mc2_dog_long' },
      { g: 'w', lo: 250, hi: 300, pt: 0.04, cell: 'DOG 4pt+ W +250/300', lane: 'mc2_dog_band' },
    ]
    for (const d of DOG_CELLS) {
      if (d.g !== gHL) continue
      if (!_dogBand(d.lo, d.hi)) continue
      if (!(over <= -d.pt)) continue
      if (!mc2Alive(d.lane, gHL, false)) continue
      return { cell: d.cell, lane: d.lane, who: fav1 ? match.player_2 : match.player_1,
               od: dogAm, amt: Math.round(-1000 * over) / 10, live: rec(d.lane),
               recon: !!m2.recon }
    }
'''
s = s[:i] + DOGS + s[j:]

# ---- 2. replace the FAVOURITE rules: from the fav 0-2pt cell to the end of the IIFE
a = s.index("    if (over > 0.08 && !mc2Alive('mc2_fav_deep', gHL, true)) return null")
b = s.index("    return null\n  })()", a)
FAVS = '''    // ---- MC2 FAVOURITE BAND RULES (board), 2026-10-14 ----
    // The same two cells the Dog picks tab marks gold, and nothing else:
    //   women -100..-200  4pt+   +22.85% / 51 pooled, t 2.16, positive in both windows
    //   men   -100..-150  4pt+   +18.51% / 12 forward  (the mens DEEP half is not marked --
    //                            -13.95% / 13, removed from the tab earlier today)
    // The old 0-2pt and 2-8pt slices are gone: one 4pt+ test per gender replaces them.
    //
    // favClearsPrice is KEPT. The margin is measured against the DE-VIGGED market, so "4pt over"
    // can still sit below break-even at the offered price; a mark must not recommend backing a
    // favourite the head itself prices as a losing bet.
    const _favLo = gHL === 'w' ? -200 : -150
    const _favOK = !isNaN(favAm) && favAm <= -100 && favAm >= _favLo
    const _favLane = gHL === 'w' ? 'mc2_fav4_w' : 'mc2_fav4_m'
    if (_favOK && over >= 0.04 && favClearsPrice && mc2Alive('mc2_fav_band', gHL, true)) {
      return { cell: gHL === 'w' ? 'FAV 4pt+ W -100/200' : 'FAV 4pt+ M -100/150',
               lane: _favLane, who: fav1 ? match.player_1 : match.player_2,
               od: favAm, amt: Math.round(1000 * over) / 10, live: rec(_favLane),
               recon: !!m2.recon }
    }
'''
s = s[:a] + FAVS + s[b:]

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched TennisSection.jsx")
print("   DOG_CELLS present : %s" % ("DOG_CELLS" in s))
print("   agreeAt calls left: %d" % s.count("agreeAt("))
print("   fav 4pt rule      : %s" % ("_favOK && over >= 0.04" in s))
print("RESULT: OK")
