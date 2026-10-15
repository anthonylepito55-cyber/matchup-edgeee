"""WIRE MC6 INTO THE SLATE AND THE LEDGER (2026-10-15).

MC6 (tennis_mc6.py) exists and its state is built; this attaches it so it actually appears and,
more importantly, so it starts ACCUMULATING A FORWARD RECORD. A head that is never logged can
never be judged -- MC3 and MC5 both spent days effectively untestable for exactly this reason,
and MC3/MC5 were on 0 of 211 ITF cards until this morning.

THREE PLACES, deliberately all of them:
  1. the board slate (tennis_today) -- beside the MC2/MC3/MC5 attach
  2. the ITF slate -- beside the same, with best_of_5=False
  3. the ledger (tennis_log) -- a mc6_p1 column and a mc6_recon flag, in the same shape as
     mc5_p1/mc5_recon, written by log_predictions before first serve

NO BOARD MARK. MC6 is watch-only: a column and a lane. Every MC head measured -8.7% to -9.7% at
every edge gate, so a +0.004 AUC gain is not a reason to colour a card, and colour changes need a
live lane record plus explicit sign-off regardless.
"""
import io
import os

DIR = os.path.dirname(os.path.abspath(__file__))


def patch(path, pairs, check):
    s = io.open(path, encoding="utf-8").read()
    assert check not in s, "%s already patched" % os.path.basename(path)
    for old, new, cnt in pairs:
        assert s.count(old) == cnt, ("in %s: found %d of %r"
                                     % (os.path.basename(path), s.count(old), old[:80]))
        s = s.replace(old, new)
    io.open(path, "w", encoding="utf-8", newline="").write(s)
    return s


# ---------------------------------------------------------------- 1 + 2. main.py
MAIN = os.path.join(DIR, "main.py")
board_old = """            try:
                import tennis_mc5 as _tm5
                r["mc5"] = _tm5.predict(r["player_1"], r["player_2"], r.get("surface"),
                                        best_of_5=bool(r.get("best_of_5")))
            except Exception:  # noqa: BLE001
                r["mc5"] = None"""
board_new = board_old + """
            # MC v6 (2026-10-15, user "we should make an mc6 thats exactly like mc2 but has
            # recent h2h surface form as well"). MC2's blend plus a recency-weighted H2H term
            # and a surface-form RESIDUAL, weights measured walk-forward before the module was
            # written (_mc6_sweep.py): held-out AUC +0.0043 / +0.0045 over MC2 on 2025 / 2026,
            # and the gain is the SURFACE-FORM half -- H2H alone is worth +0.0007 to +0.0011 and
            # is negative if turned up. WATCH ONLY: no board mark, display + ledger only.
            try:
                import tennis_mc6 as _tm6
                r["mc6"] = _tm6.predict(r["player_1"], r["player_2"], r.get("surface"),
                                        best_of_5=bool(r.get("best_of_5")))
            except Exception:  # noqa: BLE001
                r["mc6"] = None"""

itf_old = """        try:
            import tennis_mc5 as _tm5i
            mc5 = _tm5i.predict(p1, p2, surf, best_of_5=False)
        except Exception:  # noqa: BLE001
            mc5 = None"""
itf_new = itf_old + """
        # MC6 on ITF too, from the start -- MC3 and MC5 were on 0 of 211 ITF cards for two days
        # because this endpoint was not extended when they shipped (fixed 2026-10-15).
        try:
            import tennis_mc6 as _tm6i
            mc6 = _tm6i.predict(p1, p2, surf, best_of_5=False)
        except Exception:  # noqa: BLE001
            mc6 = None"""

patch(MAIN, [
    (board_old, board_new, 1),
    (itf_old, itf_new, 1),
    ('"mc2": mc2, "mc3": mc3, "mc5": mc5,', '"mc2": mc2, "mc3": mc3, "mc5": mc5, "mc6": mc6,', 1),
], check='r["mc6"]')
print("patched main.py")

# ---------------------------------------------------------------- 3. tennis_log.py
LOG = os.path.join(DIR, "tennis_log.py")
patch(LOG, [
    ('           "mc5_p1", "mc5_recon",',
     '           "mc5_p1", "mc5_recon",\n'
     '           # MC6 (2026-10-15): MC2 + recency-weighted H2H + surface-form residual.\n'
     '           # Logged from day one so it builds a forward record instead of being\n'
     '           # untestable the way MC3 and MC5 were for their first days.\n'
     '           "mc6_p1", "mc6_recon",', 1),
    ('            "mc5_p1": (m.get("mc5") or {}).get("p1_prob"),\n'
     '            "mc5_recon": False,',
     '            "mc5_p1": (m.get("mc5") or {}).get("p1_prob"),\n'
     '            "mc5_recon": False,\n'
     '            "mc6_p1": (m.get("mc6") or {}).get("p1_prob"),\n'
     '            "mc6_recon": False,', 1),
], check='"mc6_p1"')
print("patched tennis_log.py")

import py_compile
for p in (MAIN, LOG, os.path.join(DIR, "tennis_mc6.py")):
    py_compile.compile(p, doraise=True)
print("compiles: OK")
print("RESULT: OK")
