"""CARRY MC6's EV ON EVERY LANE PICK (2026-10-16).

User: "make sure to show it on the dogs tab" -- the MC6 verdict added beside the board's gold
favourite marks has to appear on the Dog picks tab too.

The board could compute it inline because it holds the live card with every head on it. The tab
cannot: it renders from lane PICK RECORDS, and those carry date, players, price, result and P/L
but no model probability at all. So the number has to travel with the pick.

Added as mc6_ev: MC6's expected value at the OFFERED price, on THE SIDE THE LANE BET. Taking the
offered price rather than the de-vigged one is the point of the whole exercise -- on Grant vs Ito
MC2 looked right precisely because it was measured against a de-vigged number, and the bet still
lost money at -128.

Computed for the bet side rather than the favourite side specifically, so it is meaningful on dog
cells as well as the gold favourite ones, even though only the gold marks render it today.

None when MC6 has no read on that match. That must never be displayed as agreement.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tennis_log.py")
s = io.open(P, encoding="utf-8").read()
assert '"mc6_ev"' not in s, "already patched"

OLD = '''                        "score": r.get("score"), "settled": bool(settled),
                        "won": (None if not settled else bool(won1 == side1)),'''
assert s.count(OLD) == 1, "pick record not found (%d)" % s.count(OLD)
NEW = '''                        "score": r.get("score"), "settled": bool(settled),
                        # MC6's EV AT THE OFFERED PRICE on the side this lane bet (2026-10-16).
                        # The tab renders from these records and has no access to the heads, so
                        # the second opinion has to travel with the pick. Offered price, not
                        # de-vigged: a de-vigged margin is what made MC2 look right on the card
                        # that prompted this. None means MC6 had no read -- never agreement.
                        "mc6_ev": (lambda _p: (None if _p is None or pd.isna(_p) else round(
                            float((_p if side1 else 1.0 - _p)) * float(d1 if side1 else d2) - 1.0,
                            4)))(r.get("mc6_p1")),
                        "won": (None if not settled else bool(won1 == side1)),'''
s = s.replace(OLD, NEW)
io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched tennis_log.py")
print("   mc6_ev refs: %d" % s.count('"mc6_ev"'))
import py_compile
py_compile.compile(P, doraise=True)
print("compiles: OK")
print("RESULT: OK")
