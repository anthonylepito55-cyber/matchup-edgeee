"""THE WOMEN'S MC2 FAVOURITE LANE (2026-10-14).

User: "add the women lane on the dog tab" / "what about -150 to -200 favorites".

THE CELL: a WOMEN'S favourite priced -100..-200 that MC2 rates 4 or more points above the
de-vigged market. Forward rows only.

WHY -200 AND NOT -150. The user asked for the -100..-150 lane and asked about -150..-200 in the
same breath; the second band turned out to work as well as the first, so the lane covers both and
the band edges are constants to narrow. Measured on forward + CORRECTED recon (the recon rebuilt
with as-of states after the surface question):

    -100..-150   n=28  19-9   67.9% hit vs 55.5% needed   +22.31%   t 1.40
    -150..-200   n=23  18-5   78.3% hit vs 63.2% needed   +23.50%   t 1.73
    -100..-200   n=51  37-14  72.5% hit vs 59.0% needed   +22.85%   t 2.16

WHY THIS ONE AND NOT THE OTHER FAVOURITE CELLS. It is the only favourite cell all session that
holds up on every check:
    both windows      forward +26.72% (24)  |  corrected recon +19.40% (27)
    both price bands  +22.31% (28)          |  +23.50% (23)
    the men's half    -9.21% (74)           -- so it is not a generic favourite effect
    the baseline      every women's fav -100..-200 is -3.64% (239); men's -13.02% (355, t -2.96)
    and t 2.16 pooled, the only favourite cell to clear 2 at all.

WHAT IS STILL WEAK, and it is on the card: 51 bets. The gender split and the 4pt threshold were
both found by scanning this data, so the effect size is flattered even though the direction is
consistent. The forward half alone is 24 bets.

Every other favourite cell was refused: MC2 4pt+ pooled across both genders is +2.29% at
-100..-150, the band is blind-negative at -9.69%, and six archive favourite cells have died
forward. This is a lane, not a board mark.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tennis_log.py")
s = io.open(P, encoding="utf-8").read()
assert "mc2_fav4_w" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


# register
rep('''              # MC2 6pt+ over on the dog at ANY price -- the Dog picks tab cell
              # (2026-10-14, user "add All mc2 6 pt to dog tab")
              "mc2_dog6_all",''',
    '''              # MC2 6pt+ over on the dog at ANY price -- the Dog picks tab cell
              # (2026-10-14, user "add All mc2 6 pt to dog tab")
              "mc2_dog6_all",
              # 🟡 THE WOMEN'S FAVOURITE CELL (2026-10-14, user "add the women lane on the dog
              # tab"). A women's favourite at -100..-200 that MC2 rates 4pt+ above the de-vigged
              # market. On forward + corrected recon: +22.85% on 51 (37-14, 72.5% hit against
              # 59.0% needed, t 2.16), positive in BOTH windows (fwd +26.72%/24, recon
              # +19.40%/27) and BOTH bands (+22.31%/28 and +23.50%/23), while the men's half of
              # the same cut is -9.21% on 74 and every women's favourite in the range is -3.64%.
              # The only favourite cell in this project to clear t=2. Watch-only: 51 bets, and
              # both the gender split and the 4pt threshold were found by scanning.
              "mc2_fav4_w", "mc2_fav4_m",''')

# fire it, alongside the dog-6pt line that already lives in this forward-only block
rep('''                if _tag9 == "mc2" and _ov9 <= -0.06:
                    bet("mc2_dog6_all", dog1)''',
    '''                if _tag9 == "mc2" and _ov9 <= -0.06:
                    bet("mc2_dog6_all", dog1)
                # 🟡 MC2 4pt+ OVER THE MARKET ON A FAVOURITE at -100..-200, split by gender
                # because that is where the whole effect lives: women +22.85% on 51 (t 2.16),
                # men -9.21% on 74. Both lanes run so the split keeps being tested rather than
                # assumed. _ov9 is MC2's margin ON THE FAVOURITE, so >= +0.04 is 4pt over.
                if _tag9 == "mc2" and _ov9 >= 0.04:
                    _fdec = (d1 if not dog1 else d2)
                    if _fdec:
                        _fa9 = ((_fdec - 1) * 100 if _fdec >= 2
                                else -100.0 / max(_fdec - 1, 1e-9))
                        if -200.0 <= _fa9 <= -100.0:
                            bet("mc2_fav4_w" if _isw else "mc2_fav4_m", not dog1)''')

# record picks so the tab can list them
rep('''               "mc2_dog6_all", "mc2_take_dog_all", "mc3_take_dog_all", "mc5_take_dog_all"}''',
    '''               "mc2_dog6_all", "mc2_take_dog_all", "mc3_take_dog_all", "mc5_take_dog_all",
               # the women's favourite cell and its men's control (2026-10-14)
               "mc2_fav4_w", "mc2_fav4_m"}''')

io.open(P, "w", encoding="utf-8", newline="").write(s)
import ast

ast.parse(s)
print("patched tennis_log.py -- syntax OK")
for k in ("mc2_fav4_w", "mc2_fav4_m"):
    print("   %-14s refs %d" % (k, s.count(k)))
print("RESULT: OK")
