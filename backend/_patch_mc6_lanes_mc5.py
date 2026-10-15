"""MC6's PAIRED LANE NOW RUNS AGAINST MC5, ITS OWN BASE (2026-10-15).

Second half of the base switch; tennis_mc6.py was already moved onto MC5. MC6 = MC5 + two terms,
so pairing it against MC2 would mostly re-measure MC5-vs-MC2, which mc3_vs_mc2 already covers. The
question worth a lane is what the two terms add on top of the base MC6 actually sits on.

No forward record is lost: the lanes were registered at n=0 with MC6_LIVE_FROM at 22:00Z tonight
and nothing has settled, which is exactly why the switch was worth doing immediately.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tennis_log.py")
s = io.open(P, encoding="utf-8").read()
assert "mc6_vs_mc5" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


rep('"mc6_all", "mc6_edge2", "mc6_dog_band", "mc6_vs_mc2", "mc2_vs_mc6",',
    '"mc6_all", "mc6_edge2", "mc6_dog_band", "mc6_vs_mc5", "mc5_vs_mc6",')

rep("""              # pair that can actually separate them -- MC6 is MC2 plus two terms, so they
              # agree on most cards and only the disagreements carry information.""",
    """              # pair that can actually separate them -- MC6 is MC5 plus two terms, so they
              # agree on most cards and only the disagreements carry information.""")

rep("""                # the head-to-head, only where MC6 and MC2 actually differ
                if pd.notna(_m29) and not _m2rec:
                    _m2s6 = float(_m29) >= 0.5
                    if _m2s6 != _m6b:
                        bet("mc6_vs_mc2", _m6b)
                        bet("mc2_vs_mc6", _m2s6)""",
    """                # the head-to-head against ITS OWN BASE, only where they differ. MC6 sits on
                # MC5 (2026-10-15, user "switch it to mc5 and get rid of the mc2 version"), so
                # pairing it against MC2 would mostly re-measure MC5-vs-MC2, which mc3_vs_mc2
                # already covers. What deserves a lane is what the two terms add on top of the
                # base MC6 actually uses.
                if pd.notna(_m59) and not _m5rec:
                    _m5s6 = float(_m59) >= 0.5
                    if _m5s6 != _m6b:
                        bet("mc6_vs_mc5", _m6b)
                        bet("mc5_vs_mc6", _m5s6)""")

# the MC6 scoring block sits beside MC5's, so _m59/_m5rec are already in scope -- assert it
i6 = s.find('_m69 = r.get("mc6_p1")')
i5 = s.find('_m59 = r.get("mc5_p1")')
assert 0 < i5 < i6, "MC5's vars must be assigned before MC6's block uses them"

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched tennis_log.py")
for k in ("mc6_vs_mc5", "mc5_vs_mc6", "mc6_vs_mc2", "mc2_vs_mc6"):
    print("   %-14s %d" % (k, s.count(k)))
import py_compile
py_compile.compile(P, doraise=True)
print("compiles: OK")
print("RESULT: OK")
