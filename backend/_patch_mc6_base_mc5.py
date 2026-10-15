"""MC6 MOVES ONTO MC5's BASE, AND THE MC2 VERSION GOES (2026-10-15).

User: "switch it to mc5 and get rid of the mc2 version", after the base comparison
(_mc6_base_choice.py) measured MC5's base as the better place to put the two terms:

    held-out                 2025              2026
    MC2 + h2h + sform    .6864 / .2236     .6898 / .2224
    MC5 + h2h + sform    .6893 / .2226     .6910 / .2220     <- better on both, both metrics

THE REDUNDANCY IS REAL AND DOES NOT CANCEL THE BETTER BASE. The surface-form term loses about a
third of its value on MC5 -- +0.0034/+0.0038 on MC2 against +0.0022/+0.0025 on MC5 -- because MC5
already carries per-surface serve/return, surface Elo, surface L5 and season-on-surface. H2H is
unchanged on every base (+0.0010/+0.0007), since no base contains H2H. But MC5's base starts
+0.0041/+0.0026 ahead, which more than covers the third given back.

The same redundancy shows in the weight grid: on MC2, wS = 1.00 was still fine (+0.0042/+0.0048);
on MC5 it is WORSE than 0.50 (+0.0023/+0.0027). The optimum shifts down, which is what redundancy
looks like. wH = 0.25 / wS = 0.50 remains the best tested pair on the new base, so the weights are
unchanged.

HOW THE REBLEND IS DONE NOW. Previously MC6 rebuilt MC2's blend by hand
(0.5*logit(elo) + 0.5*logit(markov) + asym). That is exactly logit(p1_prob), so MC6 now takes
logit of the BASE'S OWN published probability and adds the terms:

    p = sigmoid( logit(p_base) + WH*h2h + WS*sform )

Identical arithmetic, and it no longer assumes the base blends its legs 50/50 -- MC5 applies its
L5 / season / clutch terms at predict time, and this picks those up automatically instead of
silently rebuilding a blend that does not match.

ONE CAVEAT RECORDED HONESTLY: the sweep could not tell MC3 and MC5 apart. Their feature-table
legs are byte-identical, because MC5's extra terms live at predict time rather than in the
features, so what the comparison measured as "MC5" was MC3's legs. By MC5's own design those
terms are set where the cost against MC3 is zero to four decimals, so MC3 is approximately MC5 --
but the live MC6 now sits on MC5's ACTUAL output, which includes terms the sweep did not see.

THE MC2 VERSION IS GONE, not kept as a variant: the lanes were registered at n=0 with
MC6_LIVE_FROM at 22:00Z tonight and nothing had settled, so switching now costs no forward record
at all. That is precisely why it was worth doing immediately rather than later.

LANES RENAMED mc6_vs_mc2 / mc2_vs_mc6 -> mc6_vs_mc5 / mc5_vs_mc6. The MC2 pairing would now
mostly re-measure "MC5 vs MC2", which mc3_vs_mc2 already covers; the useful question is what the
two terms add on top of the base MC6 actually sits on.
"""
import io
import os

DIR = os.path.dirname(os.path.abspath(__file__))


def edit(path, pairs, guard=None):
    s = io.open(path, encoding="utf-8").read()
    if guard:
        assert guard not in s, "%s already patched" % os.path.basename(path)
    for old, new, c in pairs:
        assert s.count(old) == c, ("in %s: found %d of %r"
                                   % (os.path.basename(path), s.count(old), old[:90]))
        s = s.replace(old, new)
    io.open(path, "w", encoding="utf-8", newline="").write(s)
    return s


# ------------------------------------------------------------------ 1. the head
M6 = os.path.join(DIR, "tennis_mc6.py")
edit(M6, [
    ('"""MC v6 (2026-10-15, user: "we should make an mc6 thats exactly like mc2 but has recent h2h\nsurface form as well").\n\nEXACTLY MC2, PLUS TWO TERMS.',
     '"""MC v6 (2026-10-15). Asked for as "exactly like mc2 but has recent h2h surface form as\nwell", then moved onto MC5\'s base the same day on the user\'s call ("switch it to mc5 and get\nrid of the mc2 version") after the base comparison measured MC5 as the better place for the\nterms -- see _mc6_base_choice.py and the table below.\n\nEXACTLY MC5, PLUS TWO TERMS.', 1),
    ("MC6 does not re-implement anything: it calls tennis_mc2.predict and\nre-blends its own published legs, so the Elo leg, the Markov leg, the quadrature over day-form\nnodes and the thin-sample tilt are literally MC2's and cannot drift from it.\n\n    MC2 :  p = sigmoid( 0.5*logit(p_elo) + 0.5*logit(p_markov) + asym_tilt )\n    MC6 :  p = sigmoid( 0.5*logit(p_elo) + 0.5*logit(p_markov) + asym_tilt\n                        + MC6_WH * h2h  +  MC6_WS * sform )\n\nAt MC6_WH = MC6_WS = 0 it IS MC2, to the last decimal. That is deliberate: it makes the two\nheads' difference exactly the two new terms and nothing else.",
     "MC6 does not re-implement anything: it calls tennis_mc5.predict and\nshifts its published probability, so every layer below -- MC2's Elo and Markov legs, MC3's\nper-surface serve/return ratings, best-of-five, margin-aware Elo, MC5's surface L5, season and\nclutch terms, and the thin-sample tilt -- is literally MC5's and cannot drift from it.\n\n    MC6 :  p = sigmoid( logit(p_mc5) + MC6_WH * h2h  +  MC6_WS * sform )\n\nAt MC6_WH = MC6_WS = 0 it IS MC5, to the last decimal, which makes the two heads' difference\nexactly the two new terms and nothing else. Taking logit of the base's OWN probability rather\nthan rebuilding its blend by hand is deliberate: the arithmetic is identical for a 50/50 blend,\nand it does not assume one, so MC5's predict-time terms are picked up automatically instead of\nbeing silently dropped by a hand-rebuilt blend.", 1),
], guard="EXACTLY MC5, PLUS TWO TERMS")

s = io.open(M6, encoding="utf-8").read()
# the measured table
s = s.replace(
    """WEIGHTS WERE MEASURED FIRST, NOT AFTER (_mc6_sweep.py, 170,714 archive rows, walk-forward,
held-out years). This is the one process lesson from MC5, whose weights had to be set
retrospectively at the smallest values tested:""",
    """WHY MC5'S BASE AND NOT MC2'S (_mc6_base_choice.py, identical rows / terms / weights):

    held-out                 2025              2026
    MC2 + h2h + sform    .6864 / .2236     .6898 / .2224
    MC5 + h2h + sform    .6893 / .2226     .6910 / .2220     <- better on both, both metrics

The two terms add LESS on MC5 (+.0032/+.0031) than on MC2 (+.0044/+.0045) -- the surface-form
term loses about a third of its value, because MC5 already holds per-surface serve/return,
surface Elo, surface L5 and season-on-surface. H2H is unchanged on every base (+.0010/+.0007),
since no base contains H2H. But MC5's base starts +.0041/+.0026 ahead, which more than covers the
third given back. The same redundancy shows in the weight grid: wS = 1.00 was fine on MC2 and is
WORSE than 0.50 on MC5, so the optimum shifts down. wH .25 / wS .50 stays the best tested pair.

A caveat that belongs here rather than in a commit message: the sweep could NOT separate MC3 from
MC5 -- their feature-table legs are byte-identical, because MC5's extra terms live at predict time
rather than in the features, so "MC5" in that table is MC3's legs. By MC5's own design those terms
sit where the cost against MC3 is zero to four decimals, so MC3 is approximately MC5; the live
head now sits on MC5's ACTUAL output, which includes terms the sweep never saw.

WEIGHTS WERE MEASURED FIRST, NOT AFTER (_mc6_sweep.py, 170,714 archive rows, walk-forward,
held-out years). This is the one process lesson from MC5, whose weights had to be set
retrospectively at the smallest values tested. The table below is on MC2's base, where the sweep
was originally run:""")

# the code: base call + reblend
s = s.replace("""import tennis_mc2
from tennis_mc2 import _slug, _surf""",
              """import tennis_mc5
from tennis_mc2 import _slug, _surf""")
s = s.replace('''    base = tennis_mc2.predict(p1_name, p2_name, surface,
                              market_p1=market_p1, best_of_5=best_of_5)''',
              '''    base = tennis_mc5.predict(p1_name, p2_name, surface, best_of_5=best_of_5)''')
s = s.replace('''    # MC2's own legs, re-blended. At MC6_WH = MC6_WS = 0 this reproduces base["p1_prob"] exactly.
    z = (0.5 * _lg(base["elo_p1"]) + 0.5 * _lg(base["mkv_p1"]) + float(base.get("asym") or 0.0)
         + MC6_WH * h2h + MC6_WS * sform)''',
              '''    # MC5's own probability, shifted. At MC6_WH = MC6_WS = 0 this reproduces base["p1_prob"]
    # exactly. Using the base's published number rather than rebuilding its blend means MC5's
    # predict-time terms (surface L5, season, clutch) are carried rather than silently dropped.
    z = _lg(base["p1_prob"]) + MC6_WH * h2h + MC6_WS * sform''')
s = s.replace('''        "mc2_p1": base["p1_prob"],                 # what MC2 said, so the delta is visible
        "d_mc2": round(p - base["p1_prob"], 4),''',
              '''        "mc5_p1": base["p1_prob"],                 # what MC5 said, so the delta is visible
        "d_mc5": round(p - base["p1_prob"], 4),''')
s = s.replace('''    Returns None when MC2 returns None (either player unrated) or when MC6's own state is
    missing -- never a silent fallback to MC2, so a dead state reads as a blank column rather
    than as MC2's number under MC6's name.''',
              '''    Returns None when MC5 returns None (either player unrated) or when MC6's own state is
    missing -- never a silent fallback to MC5, so a dead state reads as a blank column rather
    than as MC5's number under MC6's name.''')
s = s.replace("""AND THE THING AUC DOES NOT TELL YOU: a better predictor is not a better bet. MC3 and MC5 both beat
MC2 on AUC and neither is bettable""",
              """AND THE THING AUC DOES NOT TELL YOU: a better predictor is not a better bet. MC3 and MC5 both beat
MC2 on AUC and neither is bettable""")
io.open(M6, "w", encoding="utf-8", newline="").write(s)
print("patched tennis_mc6.py")

# ------------------------------------------------------------------ 2. the lanes
LOG = os.path.join(DIR, "tennis_log.py")
edit(LOG, [
    ('"mc6_all", "mc6_edge2", "mc6_dog_band", "mc6_vs_mc2", "mc2_vs_mc6",',
     '"mc6_all", "mc6_edge2", "mc6_dog_band", "mc6_vs_mc5", "mc5_vs_mc6",', 1),
    ('''                # the head-to-head, only where MC6 and MC2 actually differ
                if pd.notna(_m29) and not _m2rec:
                    _m2s6 = float(_m29) >= 0.5
                    if _m2s6 != _m6b:
                        bet("mc6_vs_mc2", _m6b)
                        bet("mc2_vs_mc6", _m2s6)''',
     '''                # the head-to-head against ITS OWN BASE, only where they differ. MC6 sits on
                # MC5 (2026-10-15, user "switch it to mc5"), so pairing it against MC2 would
                # mostly re-measure MC5-vs-MC2, which mc3_vs_mc2 already covers. The useful
                # question is what the two terms add on top of the base MC6 actually uses.
                if pd.notna(_m59) and not _m5rec:
                    _m5s6 = float(_m59) >= 0.5
                    if _m5s6 != _m6b:
                        bet("mc6_vs_mc5", _m6b)
                        bet("mc5_vs_mc6", _m5s6)''', 1),
    ('''            # pair that can actually separate them -- MC6 is MC2 plus two terms, so they
              # agree on most cards and only the disagreements carry information.''',
     '''            # pair that can actually separate them -- MC6 is MC5 plus two terms, so they
              # agree on most cards and only the disagreements carry information.''', 0),
], guard="mc6_vs_mc5")
print("patched tennis_log.py")

import py_compile
for p in (M6, LOG):
    py_compile.compile(p, doraise=True)
print("compiles: OK")
print("RESULT: OK")
