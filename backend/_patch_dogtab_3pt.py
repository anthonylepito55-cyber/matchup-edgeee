"""THE DOG TAB MARKS ON MC6 AT 3pt, BOTH GENDERS (2026-10-16).

User: "lets do men and women 3 pts for mc6 on dog tab / make sure the picks go to dog tab / it
should make kudermetova go there".

Every MC6 dog pink rule moves to the 3pt lane. Previously the tab mixed gates -- 4pt for most
bands, 6pt for men +200..+250 -- which came from MC2's ladder, where men climbed and women peaked
at 4pt. MC6's ladder has a different shape (men flat 0-2.5pt then decaying, women climbing to
4pt), so a single 3pt gate is now the better fit for both and is what the user asked for.

The card that prompted it: Polina Kudermetova at +108, MC6 +3.74pt over the de-vigged market --
clears 3pt, misses 4pt by a quarter point. MC2 (+4.12), MC3 (+4.62) and MC5 (+4.01) all had her;
MC6 is the most conservative of the four and the old gate was cutting her out.

The cell list gains a 3pt entry so the tab can show the lane's record, and the 4pt/6pt cells stay
visible for contrast rather than being deleted -- they keep scoring and the comparison stays on
screen.

HONEST STATUS: the ladder behind 3pt is mostly MC6's as-of REPLAY, and the women's forward column
is negative at every rung of it. This is a user call on replay evidence, not a forward-validated
cell, and the tab's thin-cell floor still applies so the new lane reads as thin until it fills.
"""
import io
import os

F = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "DogPicksPanel.jsx"))
s = io.open(F, encoding="utf-8").read()
assert "mc6_dog3_all" not in s, "already patched"

# ---- every MC6 dog pink rule reads the 3pt lane ----
n4 = s.count("cells: new Set(['mc6_dog4_all'])")
n6 = s.count("cells: new Set(['mc6_dog6_all'])")
assert n4 + n6 >= 4, "expected the MC6 pink rules, found %d/%d" % (n4, n6)
s = s.replace("cells: new Set(['mc6_dog4_all'])", "cells: new Set(['mc6_dog3_all'])")
s = s.replace("cells: new Set(['mc6_dog6_all'])", "cells: new Set(['mc6_dog3_all'])")
s = s.replace("tag: 'MC6 4pt+ M'", "tag: 'MC6 3pt+ M'")
s = s.replace("tag: 'MC6 4pt+ W'", "tag: 'MC6 3pt+ W'")
s = s.replace("tag: 'MC6 6pt+ M'", "tag: 'MC6 3pt+ M'")

# ---- the 3pt lane needs a cell so its record is visible, and must be markable ----
OLDC = "  ['\U0001F7E4 MC6 6pt+ DOG', 'mc6_dog6_all',"
assert s.count(OLDC) == 1, "MC6 6pt cell entry not found"
NEWC = ("  ['\U0001F7E4 MC6 3pt+ DOG', 'mc6_dog3_all',\n"
        "   'MC6 three or more points over the de-vigged market on the dog -- THE GATE THIS TAB NOW "
        "MARKS ON, both genders (2026-10-16, your call). Why 3pt rather than 4: MC6s ladder on "
        "+100..+150 is FLAT for men from 0pt to 2.5pt (+38.6% at 2pt, t 3.11) and decays above it, "
        "while women climb to 4pt (+15.1%). 3pt is where both genders sit near their own best, which "
        "is what makes one shared gate defensible instead of a compromise suiting neither. The card "
        "that prompted it: Kudermetova at +108, MC6 +3.74pt -- clears 3, misses 4 by a quarter point, "
        "while MC2 (+4.12), MC3 (+4.62) and MC5 (+4.01) all had her. READ THE SAMPLE: the ladder "
        "behind this is mostly MC6s as-of REPLAY, and the womens FORWARD column is negative at every "
        "rung of it. This is a call on replay evidence, not a forward-validated cell.'],\n"
        + OLDC)
s = s.replace(OLDC, NEWC)

# MARK_CELLS is built from PINK_RULES, so it follows automatically -- assert that it does
assert "...PINK_RULES.flatMap(r => [...r.cells])" in s, "MARK_CELLS no longer derived from PINK_RULES"
# the band-splitter must split the 3pt lane too, or its cells never appear per band
OLDS = "const SPLIT_BY_BAND = new Set(['mc6_dog4_all', 'mc6_dog6_all'])"
assert s.count(OLDS) == 1, "SPLIT_BY_BAND not found"
s = s.replace(OLDS, "const SPLIT_BY_BAND = new Set(['mc6_dog3_all', 'mc6_dog4_all', 'mc6_dog6_all'])")

io.open(F, "w", encoding="utf-8", newline="").write(s)
print("patched DogPicksPanel.jsx")
print("   mc6_dog3_all refs : %d" % s.count("mc6_dog3_all"))
print("   pink rules moved  : %d (from 4pt) + %d (from 6pt)" % (n4, n6))
print("   split-by-band     : %s" % ("mc6_dog3_all" in s.split("SPLIT_BY_BAND")[1][:120]))
print("RESULT: OK")
