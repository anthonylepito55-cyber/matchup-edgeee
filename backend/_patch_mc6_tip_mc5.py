"""THE MC6 CARD TOOLTIP CATCHES UP WITH THE BASE SWITCH (2026-10-15).

Pointing the card's number at d_mc5 left the tooltip still saying the legs are "literally MC2's",
that MC6 "IS MC2" at weight zero, and that the lane is mc6_vs_mc2. All three are now wrong, and a
tooltip whose job is to say exactly what a head does cannot be half-updated -- that is how a card
ends up quietly lying about the model behind it.

Rewritten against the real thing, and with the base-comparison numbers added, since "why MC5 and
not MC2" is the first question the line now invites.
"""
import io
import os

F = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "TennisSection.jsx"))
s = io.open(F, encoding="utf-8").read()
assert "literally MC2's and cannot drift" in s, "tooltip already updated?"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


rep("""EXACTLY MC5 PLUS TWO TERMS -- it calls MC5 and shifts MC5's own probability, so the Elo leg, the Markov engine, the day-form quadrature and the thin-sample tilt are literally MC2's and cannot drift. At weight zero MC6 IS MC2 to the last decimal, which makes the difference on this card exactly the two terms below and nothing else.""",
    """EXACTLY MC5 PLUS TWO TERMS -- it calls MC5 and shifts MC5's own probability, so everything below it (MC2's Elo and Markov legs, MC3's per-surface serve/return ratings, best-of-five, margin-aware Elo, MC5's surface L5, season and clutch terms, and the thin-sample tilt) is literally MC5's and cannot drift. At weight zero MC6 IS MC5 to the last decimal, which makes the difference on this card exactly the two terms below and nothing else. It is built by taking the logit of MC5's own published probability rather than rebuilding its blend by hand -- identical arithmetic, and it cannot silently drop MC5's predict-time terms.""")

rep("""WEIGHTS WERE MEASURED BEFORE THE MODULE WAS WRITTEN (170,714 archive rows, walk-forward, held-out years) -- the process lesson from MC5, whose weights had to be set afterwards:""",
    """WHY MC5'S BASE AND NOT MC2'S. Built on MC2 first, then moved on the same day after measuring both on identical rows, terms and weights:\\n    held-out                 2025              2026\\n    MC2 + h2h + sform    .6864 / .2236     .6898 / .2224\\n    MC5 + h2h + sform    .6893 / .2226     .6910 / .2220   <- better on both, both metrics\\nThe terms add LESS on MC5 (+.0032/+.0031) than on MC2 (+.0044/+.0045) -- surface form loses about a third of its value, because MC5 already holds per-surface serve/return, surface Elo, surface L5 and season-on-surface. H2H is unchanged on every base, since no base contains H2H. But MC5 starts +.0041/+.0026 ahead, which more than covers the third given back. Caveat worth knowing: the sweep could NOT separate MC3 from MC5 (their feature legs are byte-identical, MC5's extras live at predict time), so "MC5" in that table is MC3's legs; the live head sits on MC5's actual output.\\n\\nWEIGHTS WERE MEASURED BEFORE THE MODULE WAS WRITTEN (170,714 archive rows, walk-forward, held-out years) -- the process lesson from MC5, whose weights had to be set afterwards. This table is on MC2's base, where the sweep was first run:""")

rep("""The mc6_vs_mc2 lane opened at n=0 on 2026-10-15 22:00Z and is what will decide it.""",
    """The mc6_vs_mc5 lane -- MC6 against its own base, so it measures what the two terms add rather than re-measuring MC5 against MC2 -- opened at n=0 on 2026-10-15 22:00Z and is what will decide it.""")

io.open(F, "w", encoding="utf-8", newline="").write(s)
print("patched TennisSection.jsx")
for k in ("IS MC5 to the last decimal", "mc6_vs_mc5 lane", "WHY MC5'S BASE"):
    print("   %-30s %d" % (k, s.count(k)))
print("   stale 'literally MC2' refs: %d" % s.count("literally MC2's"))
print("RESULT: OK")
