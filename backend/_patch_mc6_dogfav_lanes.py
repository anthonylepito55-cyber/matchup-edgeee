"""MC6 VERSIONS OF THE DOG-TAB AND GOLD-FAV LANES (2026-10-16).

User: "i want u to use all mc6 instead of mc2, same rules as mc2 but all dogs tab using mc6".

Step one of that: the lanes have to exist and start scoring before the tab can read them. This
adds MC6 alongside MC2 rather than replacing it, so the two run on identical rows under identical
rules and the swap can be judged instead of assumed.

    mc6_dog6_all   MC6 >= 6pt over the de-vigged market on the dog, any price
    mc6_dog4_all   the 4pt version
    mc6_fav4_w     MC6 >= 4pt over on a WOMEN'S favourite priced -100..-200
    mc6_fav4_m     the men's control, same cut

Identical thresholds, bands and gender split to the MC2 originals -- the point of the swap is to
change the HEAD, not the rule, so anything that moves is attributable to MC6.

THE CONSTRAINT THE USER NEEDS TO SEE BEFORE THE TAB FLIPS. The lane loop refuses recon rows (a
backfill is not a pick that was ever shown), and MC6 has only ~105 forward rows against MC2's
~800. So these lanes start near empty and the dog tab's gender x band gates -- which need 25
settles per cell -- would hide almost everything. That is a real cost of the swap and it is
measured rather than discovered after shipping.

MC6 is also added to the unstamped take lanes (mc6_take_dog_all / mc6_take_fav_all) so it sits
beside MC2/MC3/MC5 in every comparison the $25 tab already makes.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tennis_log.py")
s = io.open(P, encoding="utf-8").read()
assert "mc6_dog4_all" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


# ---- 1. record picks for the new cells (the dog tab reads pick lists) ----
rep('''               "mc2_dog6_all", "mc2_dog4_all",
               "mc2_take_dog_all", "mc3_take_dog_all", "mc5_take_dog_all",
               # the women's favourite cell and its men's control (2026-10-14)
               "mc2_fav4_w", "mc2_fav4_m"}''',
    '''               "mc2_dog6_all", "mc2_dog4_all",
               "mc2_take_dog_all", "mc3_take_dog_all", "mc5_take_dog_all",
               # the women's favourite cell and its men's control (2026-10-14)
               "mc2_fav4_w", "mc2_fav4_m",
               # the MC6 twins (2026-10-16, user "all dogs tab using mc6 instead"): identical
               # rules, different head, so the swap is measurable rather than assumed
               "mc6_dog6_all", "mc6_dog4_all", "mc6_take_dog_all", "mc6_fav4_w", "mc6_fav4_m"}''')

# ---- 2. register the lane names ----
rep('''              # the women-s pink mark reads (see the bet() site for the two ladders)
              "mc2_dog6_all", "mc2_dog4_all",''',
    '''              # the women-s pink mark reads (see the bet() site for the two ladders)
              "mc2_dog6_all", "mc2_dog4_all",
              # MC6 twins of the dog-tab and gold-fav cells (2026-10-16)
              "mc6_dog6_all", "mc6_dog4_all", "mc6_fav4_w", "mc6_fav4_m",
              "mc6_take_dog_all", "mc6_take_fav_all",''')

# ---- 3. MC6 joins the unstamped take loop, and the cell rules fire for it too ----
rep('''            for _tag9, _pv9, _rc0 in (("mc2", r.get("mc2_p1"), r.get("mc2_recon")),
                                      ("mc3", r.get("mc3_p1"), r.get("mc3_recon")),
                                      ("mc5", r.get("mc5_p1"), r.get("mc5_recon"))):''',
    '''            for _tag9, _pv9, _rc0 in (("mc2", r.get("mc2_p1"), r.get("mc2_recon")),
                                      ("mc3", r.get("mc3_p1"), r.get("mc3_recon")),
                                      ("mc5", r.get("mc5_p1"), r.get("mc5_recon")),
                                      # MC6 (2026-10-16): same loop so it is scored on identical
                                      # rows under identical rules as the heads it may replace
                                      ("mc6", r.get("mc6_p1"), r.get("mc6_recon"))):''')

rep('''                if _tag9 == "mc2" and _ov9 <= -0.06:
                    bet("mc2_dog6_all", dog1)''',
    '''                if _tag9 in ("mc2", "mc6") and _ov9 <= -0.06:
                    bet("%s_dog6_all" % _tag9, dog1)''')

rep('''                if _tag9 == "mc2" and _ov9 <= -0.04:
                    bet("mc2_dog4_all", dog1)''',
    '''                if _tag9 in ("mc2", "mc6") and _ov9 <= -0.04:
                    bet("%s_dog4_all" % _tag9, dog1)''')

rep('''                if _tag9 == "mc2" and _ov9 >= 0.04:
                    _fdec = (d1 if not dog1 else d2)
                    if _fdec:
                        _fa9 = ((_fdec - 1) * 100 if _fdec >= 2
                                else -100.0 / max(_fdec - 1, 1e-9))
                        if -200.0 <= _fa9 <= -100.0:
                            bet("mc2_fav4_w" if _isw else "mc2_fav4_m", not dog1)''',
    '''                if _tag9 in ("mc2", "mc6") and _ov9 >= 0.04:
                    _fdec = (d1 if not dog1 else d2)
                    if _fdec:
                        _fa9 = ((_fdec - 1) * 100 if _fdec >= 2
                                else -100.0 / max(_fdec - 1, 1e-9))
                        if -200.0 <= _fa9 <= -100.0:
                            bet("%s_fav4_%s" % (_tag9, "w" if _isw else "m"), not dog1)''')

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched tennis_log.py")
for k in ("mc6_dog4_all", "mc6_dog6_all", "mc6_fav4_w", "mc6_fav4_m"):
    print("   %-16s %d" % (k, s.count(k)))
import py_compile
py_compile.compile(P, doraise=True)
print("compiles: OK")
print("RESULT: OK")
