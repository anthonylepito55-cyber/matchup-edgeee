"""MEN DROP TO 2pt, WOMEN STAY AT 3pt (2026-10-16).

User: "we can actually do men 2 points as well".

This is the split the ladder actually argues for. MC6's threshold behaviour is opposite by
gender, which is why one shared gate was always going to cost somebody:

    +100..+150, all rows      men                  women
    no gate                   +14.8% /141          -3.3% /160
    0pt (any disagreement)    +38.8% /87  t3.42     +5.6% /85
    2pt                       +38.6% /73  t3.11    +10.1% /74
    3pt                       +31.9% /68  t2.46    +11.5% /67
    4pt                       +25.6% /61  t1.85    +15.1% /61

Men are FLAT from 0pt to 2.5pt and decay above it -- the whole effect is "MC6 rates this dog over
the market at all", and extra margin only shrinks the sample. Women climb the other way.

Across every band the same split holds: men +8.2% /182 at 2pt against +3.6% /160 at 4pt; women
+18.3% /187 at 2pt against +27.7% /160 at 4pt.

2pt rather than 0pt for men, deliberately: the plateau means a 2pt floor costs nothing measurable
while keeping a real disagreement requirement, where a gate of zero marks anything MC6 nudges by
a hundredth of a point.

HONEST STATUS, unchanged from the 3pt move: this ladder is mostly MC6's as-of REPLAY, its forward
column is 14 men's bets, and the women's forward column is negative at every rung. User call on
replay evidence, and the tab's thin-cell floor still applies.

Lane plus the men's pink rules only -- women's rules are untouched at 3pt.
"""
import io
import os

DIR = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------------ 1. the 2pt lane
P = os.path.join(DIR, "tennis_log.py")
s = io.open(P, encoding="utf-8").read()
assert "mc6_dog2_all" not in s, "lane already added"


def rep(src, old, new, c=1):
    assert src.count(old) == c, "found %d of %r" % (src.count(old), old[:90])
    return src.replace(old, new)


s = rep(s, '''               # 3pt (2026-10-16, user call): the gate the tab now marks on for BOTH genders
               "mc6_dog3_all"}''',
        '''               # 3pt then 2pt (2026-10-16, user calls): women mark on 3pt, men on 2pt --
               # MC6's threshold ladder runs opposite by gender, so one shared gate costs one of
               # them. Both lanes score so the split keeps being measured rather than assumed.
               "mc6_dog3_all", "mc6_dog2_all"}''')
s = rep(s, '"mc6_dog6_all", "mc6_dog4_all", "mc6_dog3_all", "mc6_fav4_w", "mc6_fav4_m",',
        '"mc6_dog6_all", "mc6_dog4_all", "mc6_dog3_all", "mc6_dog2_all",\n'
        '              "mc6_fav4_w", "mc6_fav4_m",')
s = rep(s, '''                if _tag9 == "mc6" and _ov9 <= -0.03:
                    bet("mc6_dog3_all", dog1)''',
        '''                if _tag9 == "mc6" and _ov9 <= -0.03:
                    bet("mc6_dog3_all", dog1)
                # 2pt -- the MEN's gate (2026-10-16). Their ladder is flat from 0pt to 2.5pt
                # (+38.6% at 2pt, t 3.11 on +100..+150) and decays above, so the margin size
                # carries nothing for them and 4pt was only trimming the sample. 2pt rather than
                # 0pt keeps a real disagreement requirement at no measured cost.
                if _tag9 == "mc6" and _ov9 <= -0.02:
                    bet("mc6_dog2_all", dog1)''')
io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched tennis_log.py  (mc6_dog2_all refs: %d)" % s.count("mc6_dog2_all"))
import py_compile
py_compile.compile(P, doraise=True)

# ------------------------------------------------------------------ 2. the men's pink rules
F = os.path.normpath(os.path.join(DIR, "..", "frontend", "src", "DogPicksPanel.jsx"))
t = io.open(F, encoding="utf-8").read()
assert "mc6_dog2_all" not in t, "tab already switched"
# only the rules whose gender is 'm'
import re as _re
n = 0
out = []
for line in t.split("\n"):
    if "cells: new Set(['mc6_dog3_all'])" in line and _re.search(r"g:\s*'m'", line):
        line = line.replace("cells: new Set(['mc6_dog3_all'])", "cells: new Set(['mc6_dog2_all'])")
        line = line.replace("tag: 'MC6 3pt+ M'", "tag: 'MC6 2pt+ M'")
        n += 1
    out.append(line)
t = "\n".join(out)
assert n >= 2, "expected the men's pink rules, switched %d" % n
t = rep(t, "const SPLIT_BY_BAND = new Set(['mc6_dog3_all', 'mc6_dog4_all', 'mc6_dog6_all'])",
        "const SPLIT_BY_BAND = new Set(['mc6_dog2_all', 'mc6_dog3_all', 'mc6_dog4_all', 'mc6_dog6_all'])")
# a cell entry so the men's lane record is visible on the tab
OLDC = "  ['\U0001F7E4 MC6 3pt+ DOG', 'mc6_dog3_all',"
assert t.count(OLDC) == 1, "3pt cell entry not found"
NEWC = ("  ['\U0001F7E4 MC6 2pt+ DOG \u00b7 MEN', 'mc6_dog2_all',\n"
        "   'MC6 two or more points over the de-vigged market on the dog -- THE MENS GATE "
        "(2026-10-16, your call). MC6s ladder runs OPPOSITE by gender, which is why men and women "
        "no longer share one: on +100..+150 men are FLAT from 0pt to 2.5pt (+38.8% at 0pt t3.42, "
        "+38.6% at 2pt t3.11) and decay above it, while women climb to 4pt. For men the whole effect "
        "is simply that MC6 rates the dog over the market AT ALL -- the size of the disagreement "
        "carries nothing, so 4pt was only trimming the sample. 2pt rather than 0pt keeps a real "
        "disagreement requirement at no measured cost. Across all bands men are +8.2% /182 at 2pt "
        "against +3.6% /160 at 4pt. READ THE SAMPLE: mostly MC6s as-of REPLAY, with 14 mens forward "
        "bets behind it.'],\n" + OLDC)
t = t.replace(OLDC, NEWC)
io.open(F, "w", encoding="utf-8", newline="").write(t)
print("patched DogPicksPanel.jsx")
print("   men's pink rules switched to 2pt : %d" % n)
print("   mc6_dog2_all refs                : %d" % t.count("mc6_dog2_all"))
print("   women still on 3pt               : %d rules" % t.count("cells: new Set(['mc6_dog3_all'])"))
print("RESULT: OK")
