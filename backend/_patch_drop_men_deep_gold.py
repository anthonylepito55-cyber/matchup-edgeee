"""REMOVE THE MEN -150..-200 GOLD MARK (2026-10-14).

User: "i only wanted man 100 to 150". Reverts _patch_gold_men_deep.py.

That cell was the only mark on either board failing the forward-positive rule (-13.95% on 13).
Gold is now: women -100..-200 (both bands), men -100..-150 only.
"""
import io
import os
import re

P = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "DogPicksPanel.jsx"))
s = io.open(P, encoding="utf-8").read()
assert "lo: -200, hi: -150, g: 'm'" in s, "already removed"

pat = re.compile(r"\n  \{ lo: -200, hi: -150, g: 'm',.*?' \},", re.S)
m = pat.search(s)
assert m, "mens deep gold entry not found"
s = s[:m.start()] + s[m.end():]

OLD_LEG = ("<b>men −100..−200</b> (⚠ both bands, added on request): −100..−150 is +18.51% forward on "
           "<b>twelve</b> bets but −30.54% on recon, and −150..−200 is <b>−13.95% forward on 13</b> — "
           "the only mark on either board that is forward-negative. What argues for the men’s side is "
           "that MC2 beats its blind band in every window (−5.16% pooled, −0.77% recon, against "
           "−11.94% blind) without clearing zero. <b>Watch marks, not takes.</b>")
NEW_LEG = ("<b>men −100..−150 only</b> (⚠ +18.51% forward on <b>twelve</b> bets, but −30.54% on recon "
           "and pooled −13.72% against a blind band of −13.60% — a watch mark). The men’s "
           "−150..−200 half is −13.95% forward and is <b>not</b> marked.")
assert s.count(OLD_LEG) == 1
s = s.replace(OLD_LEG, NEW_LEG)

s = re.sub(r"//     -150\.\.-200   women \+33\.17.*?//                  board failing the forward-positive rule, and it is one entry to remove\.\n",
           "//     -150..-200   women +33.17% /13  (+14.74% /11)   men -13.95% /13                 no\n",
           s, flags=re.S)

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("gold bands now: %d" % s.count("col: GOLD"))
for g, lo, hi in (("w", -150, -100), ("w", -200, -150), ("m", -150, -100), ("m", -200, -150)):
    k = "lo: %d, hi: %d, g: '%s'" % (lo, hi, g)
    print("   %-26s %s" % (k, "present" if k in s else "removed"))
