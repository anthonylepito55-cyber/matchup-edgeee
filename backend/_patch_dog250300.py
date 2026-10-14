"""THE +250..+300 LONG-DOG LANE (2026-10-13).

User: "if its over +250 but models move the underdog over 8 points then thats still a good dog
bet aka iva jovic vs dayan yastremska" -> "lets cap it at 300".

A dog priced +250..+300 that ALL THREE heads (MC2, MC3, MC5) rate 8 or more points above its
de-vigged market price. The board marks it; this registers the lane that judges it, requiring the
same three-head agreement so the mark and the record score one rule rather than two.

THE EVIDENCE, stated plainly because this mark runs AGAINST its own backtest:
    archive, both heads 8pt+ on a +250..+300 dog   -10.66% on 4,124, negative every year
                                                   (-20.3 / -8.6 / -12.3), and worse than
                                                   backing every dog in the band (-8.93%)
    the same at TOUR level                         -5.33% on 1,133 vs -1.78% for the band
    tour + WTA only                                -7.63% on 1,564 vs -4.69%
    the margin ladder above +250                   FLAT: 8pt -15.5%, 12pt -14.5%, 15pt -14.8%,
                                                   20pt -14.1% -- a bigger gap buys nothing
    frozen live log, all THREE heads 8pt+          +100.09% on 22 (54.5% hit) vs -7.28% for the
                                                   band; n=22 has a standard error near 30
                                                   points, so ~1.6se from zero

So the archive says no on ~14,000 bets across four levels and three years, and the forward log
says yes on 22. The cap at +300 is the user's call and sits on the right side of the one real
boundary in the data: +300 and up runs -17% to -18% at this margin.

Like the Ⓖ G marks, this is a user-called VISIBILITY mark, deliberately exempt from the
"backtest-positive AND live-positive" gate. The lane is what settles it. Auto-unmark still
applies through mc2Alive.

Also fixes an omission while in here: this block skipped surface_bad and inplay_suspect rows but
not resolve_bad, the flag added earlier today for the 15 rows priced off the wrong player.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tennis_log.py")
s = io.open(P, encoding="utf-8").read()
assert "mc2_dog_250_300" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


# 1. register the key
rep('''                     "mc2_dog3", "mc2_dog_dead", "mc2_dog_long",
                     "mc2_fav_on_ev", "mc2_fav_band_ev", "mc2_fav_deep_ev")}''',
    '''                     "mc2_dog3", "mc2_dog_dead", "mc2_dog_long", "mc2_dog_250_300",
                     "mc2_fav_on_ev", "mc2_fav_band_ev", "mc2_fav_deep_ev")}''')

# 2. also honour resolve_bad here (added today, this block predates it)
# all THREE scoring blocks use this skip list, and the 15 wrong-player rows should not count
# in any of them, so it is fixed everywhere rather than just in the MC2 pass.
rep('''            for _bad in ("surface_bad", "inplay_suspect"):''',
    '''            for _bad in ("surface_bad", "inplay_suspect", "resolve_bad"):''', 3)

# 3. the branch, checked FIRST because its price range sits outside MC2_DOG_AM entirely
rep('''            if (MC2_DOG_LONG_AM[0] <= _dogam <= MC2_DOG_LONG_AM[1]
                    and overm <= -MC2_DOG_LONG_T):''',
    '''            # +250..+300 with ALL THREE heads 8pt+ over on the dog (2026-10-13, user
            # "lets cap it at 300"). Three-head agreement is part of the rule, so the lane
            # reads mc3_p1 and mc5_p1 too -- a mark the board shows on three heads must not be
            # scored here on one. A row missing either head cannot satisfy the rule.
            _ag8 = None
            if 250 < _dogam <= 300 and overm <= -0.08:
                _ag8 = True
                for _c8 in ("mc3_p1", "mc5_p1"):
                    _v8 = rr.get(_c8) if _c8 in _q3.columns else None
                    if _v8 is None or pd.isna(_v8):
                        _ag8 = False
                        break
                    _pf8 = float(_v8) if fav1m else 1.0 - float(_v8)
                    if (_pf8 - mkfavm) > -0.08:      # that head is not 8pt+ on the dog
                        _ag8 = False
                        break
            if _ag8:
                key, takes1 = "mc2_dog_250_300", (not fav1m)
            elif (MC2_DOG_LONG_AM[0] <= _dogam <= MC2_DOG_LONG_AM[1]
                    and overm <= -MC2_DOG_LONG_T):''')

# 4. the dog-side aggregation must treat it as a dog cell
rep('''            _isdog3 = k.endswith("_dog_flip")''',
    '''            _isdog3 = k.endswith("_dog_flip") or k in ("mc2_dog3", "mc2_dog_long",
                                                          "mc2_dog_250_300", "mc2_dog_dead")''')

io.open(P, "w", encoding="utf-8", newline="").write(s)
import ast

ast.parse(s)
print("patched tennis_log.py -- syntax OK")
print("   mc2_dog_250_300 refs: %d" % s.count("mc2_dog_250_300"))
print("   resolve_bad skip lists updated: %d"
      % s.count('for _bad in ("surface_bad", "inplay_suspect", "resolve_bad")'))
print("RESULT: OK")
