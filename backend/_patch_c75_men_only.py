"""c75 DOG FLIP: MEN +100..+150 ONLY, STAYS PINK (2026-10-14).

User: "i want only c75 dog flip men 100 150 highlighted" then "oh shit i meant pink thne".
So the colour is unchanged; the WOMENS +150..+200 rule is removed.

    men   +100..+150   +22.88% on 65 (37-28, 56.9% hit, t 1.73)   KEEPS PINK
    women +150..+200   +10.68% on 22 (t 0.38)                     REMOVED
"""
import io
import os
import re

P = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "DogPicksPanel.jsx"))
s = io.open(P, encoding="utf-8").read()
assert "c75 FLIP W" in s, "already removed"

pat = re.compile(r"\n  \{ lo: 150, hi: 200, g: 'w', tag: 'c75 FLIP W[^']*', cells: new Set\(\['mc_c75_dog'\]\), tip: '.*?' \},", re.S)
m = pat.search(s)
assert m, "womens c75 rule not found"
s = s[:m.start()] + s[m.end():]

OLD = ("<b>men at +100..+150</b> (+22.88% on 65, t 1.73) and <b>women at "
       "+150..+200</b> (⚠ +10.68% on 22, thin). The genders run opposite ways here: men are "
       "−26.27% at +150..+200 and women are −23.53% at +100..+150, so each is marked only in "
       "its own band.")
NEW = ("<b>men at +100..+150 only</b> (+22.88% on 65, t 1.73). The men’s record collapses outside "
       "that band (−26.27% at +150..+200) and the women’s half is −23.53% at +100..+150, so "
       "neither is marked.")
assert s.count(OLD) == 1
s = s.replace(OLD, NEW)

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("c75 pink rules left: %d" % s.count("cells: new Set(['mc_c75_dog'])"))
print("womens c75 rule gone:", "c75 FLIP W" not in s)
