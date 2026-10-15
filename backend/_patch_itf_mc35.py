"""MC3 AND MC5 ON THE ITF CARDS, AND IN THE ITF BROWN GATE (2026-10-15).

User: "i want mc3 and mc5 added to the itf brown picks".

The frontend gate could not have been the whole job: MC3 and MC5 were not on the ITF endpoint at
all. Measured before touching anything --

    /api/tennis/itf : 211 cards
        mc2 p1_prob present  54 / 211   (itf_men 16/107, itf_women 38/104)
        mc3 p1_prob present   0 / 211
        mc5 p1_prob present   0 / 211

so adding them to mc2DogMarked() would have marked exactly nothing. The ITF endpoint attaches
MC2 (added 2026-10-08) but was never extended when MC3 and MC5 shipped on 2026-10-13. That is
also the real answer to the earlier question "do some itf games not have m3 and mc5?" -- none of
them did.

TWO CHANGES.

1. BACKEND: attach MC3 and MC5 to every ITF card with the same calls the board uses, with
   best_of_5=False (ITF is best-of-three). Placed beside the MC2 attach and therefore BEFORE
   log_predictions, so ITF rows start carrying mc3_p1 / mc5_p1 in the ledger too -- which is
   what lets these heads ever build an ITF forward record instead of staying untestable.

2. FRONTEND (separate patch): the ITF board gate accepts a mark from MC2, MC3 or MC5 on the same
   gender x band cells, and the card says which heads marked it.

An unrated pair returns None from any head, so coverage will stay partial on ITF -- that is the
TennisRatio pool, not a bug, and a None head simply does not mark.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
s = io.open(P, encoding="utf-8").read()
assert s.count('import tennis_mc2 as _tm2') == 2, "expected board + ITF mc2 attach"
assert '"mc3": mc3' not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


rep("""        try:
            import tennis_mc2 as _tm2
            mc2 = _tm2.predict(p1, p2, surf, market_p1=_mk1)
        except Exception:  # noqa: BLE001
            mc2 = None""",
    """        try:
            import tennis_mc2 as _tm2
            mc2 = _tm2.predict(p1, p2, surf, market_p1=_mk1)
        except Exception:  # noqa: BLE001
            mc2 = None
        # MC v3 AND MC v5 ON ITF TOO (2026-10-15, user "i want mc3 and mc5 added to the itf brown
        # picks"). They shipped on 2026-10-13 and this endpoint was never extended, so MC3 and MC5
        # were present on 0 of 211 ITF cards while MC2 was on 54 -- a frontend gate reading them
        # would have marked nothing. best_of_5 is False: ITF is best-of-three, and MC3/MC5 price
        # best-of-five differently (see the slam BO5 fix, 2026-10-13).
        #
        # Attached HERE, above log_predictions, so ITF rows carry mc3_p1 / mc5_p1 into the ledger.
        # That is the point: these heads have almost no forward record (MC3 ~92 rows, MC5 ~31), and
        # they cannot build one on a slate they are never scored on.
        try:
            import tennis_mc3 as _tm3i
            mc3 = _tm3i.predict(p1, p2, surf, best_of_5=False)
        except Exception:  # noqa: BLE001
            mc3 = None
        try:
            import tennis_mc5 as _tm5i
            mc5 = _tm5i.predict(p1, p2, surf, best_of_5=False)
        except Exception:  # noqa: BLE001
            mc5 = None""")

rep("""                      "mc2": mc2,
                      "tr_context": {"p1": ctx1, "p2": ctx2},""",
    """                      "mc2": mc2, "mc3": mc3, "mc5": mc5,
                      "tr_context": {"p1": ctx1, "p2": ctx2},""")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched main.py")
print('   "mc3": mc3 refs   %d' % s.count('"mc3": mc3'))
print("   _tm3i / _tm5i     %d / %d" % (s.count("_tm3i"), s.count("_tm5i")))
import py_compile
py_compile.compile(P, doraise=True)
print("compiles: OK")
print("RESULT: OK")
