"""A 3pt MC6 DOG LANE (2026-10-16).

User: "lets do men and women 3 pts for mc6 on dog tab ... it should make kudermetova go there".

Polina Kudermetova vs Sawangkaew is the card that prompted it: MC6 has her +3.74pt over the
de-vigged market at +108, so she clears 3pt and misses 4pt by a quarter of a point. Every other
head agrees she is a dog pick (MC2 +4.12, MC3 +4.62, MC5 +4.01) -- MC6 is simply the most
conservative of the four and the 4pt gate was cutting it there.

WHAT THE LADDER SAYS (log values, mostly MC6's as-of replay), +100..+150:

    gate      men                women
    no gate   +14.8% /141        -3.3% /160
    0pt       +38.8% /87  t3.42  +5.6% /85
    2pt       +38.6% /73  t3.11  +10.1% /74
    3pt       +31.9% /68  t2.46  +11.5% /67
    4pt       +25.6% /61  t1.85  +15.1% /61

Men are flat from 0pt to 2.5pt and decay after; women climb to 4pt. 3pt is the point where both
genders are still near their own best -- men give up ~7 points from their plateau, women ~4 from
theirs -- which is what makes a single shared gate defensible rather than a compromise that suits
neither.

Stated plainly: most of that evidence is MC6's backfilled replay, and the women's FORWARD column
is negative at every rung of this ladder. The shared 3pt gate is the user's call on replay
evidence, not a forward-validated cell.

Lane only -- the tab is switched separately so the two changes can be reverted independently.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tennis_log.py")
s = io.open(P, encoding="utf-8").read()
assert "mc6_dog3_all" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


# ---- record picks (the dog tab renders from pick lists) ----
rep('''               "mc6_dog6_all", "mc6_dog4_all", "mc6_take_dog_all", "mc6_fav4_w", "mc6_fav4_m"}''',
    '''               "mc6_dog6_all", "mc6_dog4_all", "mc6_take_dog_all", "mc6_fav4_w", "mc6_fav4_m",
               # 3pt (2026-10-16, user call): the gate the tab now marks on for BOTH genders
               "mc6_dog3_all"}''')

# ---- register the lane ----
rep('''              "mc6_dog6_all", "mc6_dog4_all", "mc6_fav4_w", "mc6_fav4_m",''',
    '''              "mc6_dog6_all", "mc6_dog4_all", "mc6_dog3_all", "mc6_fav4_w", "mc6_fav4_m",''')

# ---- score it beside the 4pt and 6pt gates ----
rep('''                if _tag9 in ("mc2", "mc6") and _ov9 <= -0.04:
                    bet("%s_dog4_all" % _tag9, dog1)''',
    '''                if _tag9 in ("mc2", "mc6") and _ov9 <= -0.04:
                    bet("%s_dog4_all" % _tag9, dog1)
                # 3pt, MC6 only (2026-10-16, user call). The ladder on +100..+150 is flat for men
                # from 0pt to 2.5pt (+38.6% at 2pt, t 3.11) and decays above it, while women climb
                # to 4pt (+15.1%). 3pt is where both genders sit near their own best, which is what
                # makes ONE shared gate defensible instead of a compromise suiting neither.
                # Kudermetova at +108 is the card that prompted it: MC6 +3.74pt, clears 3 not 4.
                if _tag9 == "mc6" and _ov9 <= -0.03:
                    bet("mc6_dog3_all", dog1)''')

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched tennis_log.py")
print("   mc6_dog3_all refs: %d" % s.count("mc6_dog3_all"))
import py_compile
py_compile.compile(P, doraise=True)
print("compiles: OK")
print("RESULT: OK")
