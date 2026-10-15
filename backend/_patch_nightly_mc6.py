"""THE NIGHTLY REBUILD ALSO REBUILDS MC6's STATE (2026-10-15).

MC6's H2H and surface-form state is built from the match archive, so it goes stale exactly the way
the MC2/MC3 rating states did before 2026-10-13 -- and that staleness had moved 42% of cards past
a mark gate before anyone noticed. MC6's terms are more sensitive to it than the ratings are: the
whole point of the H2H term is recency, and surface form has a 5-match half-life, so a state a
week old is materially wrong rather than merely dated.

Added as a NON-FATAL step, after the rating states are already swapped in. The ordering matters:
_mc6_build_state.py reads the same archive the rating rebuild refreshes, so it must run after, and
a failure here must not roll back a good rating rebuild. MC6 is a watch-only display column; the
ratings feed the whole board.

Run: ./venv/bin/python _patch_nightly_mc6.py   (then the systemd unit needs no change)
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nightly_tennis_ratings.py")
s = io.open(P, encoding="utf-8").read()
assert "_mc6_build_state" not in s, "already patched"

ANCHOR = """# --------------------------------------------------------- duplicate watch"""
assert s.count(ANCHOR) == 1, "anchor not found"

NEW = '''# --------------------------------------------------------- MC6 state
# MC6 (2026-10-15) = MC2 + recency-weighted H2H + surface-form residual. Its state is built from
# the archive the rating rebuild just refreshed, so it runs AFTER the states are swapped in.
#
# NON-FATAL on purpose: MC6 is a watch-only display column, the rating states feed the whole
# board, and a failure here must not roll back a good rating rebuild. _mc6_build_state.py writes
# temp -> validate -> atomic replace with a .bak, so an interrupted run leaves the live state
# untouched and MC6 simply serves yesterday's numbers.
#
# This matters more for MC6 than for the ratings: the H2H term is explicitly about recency and
# surface form has a 5-match half-life, so a week-old state is wrong rather than merely dated.
say("=" * 70)
say("MC6 state (H2H + surface form)")
say("=" * 70)
try:
    if DRY:
        say("dry run: skipping")
    else:
        rc = os.system("%s _mc6_build_state.py" % sys.executable)      # noqa: S605
        if rc != 0:
            say("MC6 state build exited %d -- NOT fatal, MC6 keeps the previous state" % rc)
            FAILED.append("mc6_state: exit %d" % rc)
        else:
            say("MC6 state rebuilt")
except Exception as e:                                                 # noqa: BLE001
    say("MC6 state build failed (not fatal): %s" % e)
    FAILED.append("mc6_state: %s" % e)

''' + ANCHOR
s = s.replace(ANCHOR, NEW)

# MC6's failure must not fail the whole unit -- it is reported, not fatal
OLD_V = """if FAILED:
    print("RESULT: FAIL -- %s" % " | ".join(FAILED))
    raise SystemExit(1)"""
assert s.count(OLD_V) == 1, "verdict block not found"
s = s.replace(OLD_V, """# MC6's state is watch-only: report it, but do not fail the unit over it, or a flaky MC6
# build would mark a perfectly good rating rebuild as failed and page for nothing.
_hard = [f for f in FAILED if not f.startswith("mc6_state")]
if _hard:
    print("RESULT: FAIL -- %s" % " | ".join(FAILED))
    raise SystemExit(1)
if FAILED:
    say("non-fatal: %s" % " | ".join(FAILED))""")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched nightly_tennis_ratings.py")
print("   _mc6_build_state refs: %d" % s.count("_mc6_build_state"))
import py_compile
py_compile.compile(P, doraise=True)
print("compiles: OK")
print("RESULT: OK")
