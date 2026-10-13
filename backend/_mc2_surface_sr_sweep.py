"""PER-SURFACE SERVE/RETURN RATINGS FOR MC2 (2026-10-13, user: "make s and r per surface and
test it").

MC2's serve rating S and return rating R are single CAREER values -- `"S": 0.0, "R": 0.0` in the
state init, where elo_s and ns are per-surface dicts. Surface reaches the Markov half only
through the league-wide base(surface) baseline. So the chain cannot represent "this player is
specifically bad on hard courts", which is the read the user had on Facundo Diaz Acosta.

DESIGN. Not a raw three-way split -- that would thin every rating by a factor of three and the
thin end is already the weak end. Instead the surface rating is shrunk toward the career rating
by surface sample count, exactly the shape the Elo half already uses (w = ns/(ns+20)):

    w      = nS_surf / (nS_surf + KS)
    S_eff  = w * S_surf + (1 - w) * S_career

so KS parameterises the whole family and the CURRENT MODEL IS NESTED INSIDE IT:

    KS = 0      pure per-surface (w = 1): the literal reading of the request
    KS = 10/20/40   graded blends
    KS = 10**9  w ~ 0, i.e. today's career-only model, as a control that should reproduce
                the n0=6 baseline almost exactly -- if it does not, the harness is wrong

Both components are updated from the same error, each at its own count-decaying rate, so the
career anchor keeps its meaning and the surface component only has to carry the deviation:

    e = base(surf) + S_eff(server) - R_eff(returner)
    S_career      += 0.8/(nS+6)      * err        (unchanged from production)
    S_surf[surf]  += 0.8/(nS_surf+6) * err        (new)

The fast-form terms Sf/Rf stay all-surface: one change at a time, and at 30% weight with a
5-6 match half-life they are mostly a recency term rather than a surface term.

The real builder's source is transformed and exec'd, never hand-copied, and scoring imports the
engine's own Markov chain -- same discipline as _mc2_shrink_sweep.py. Production artifacts are
never written: outputs carry a _sk<KS> suffix.

Run: ./venv/bin/python _mc2_surface_sr_sweep.py [build|score] [KS ...]
"""
import gc
import sys

import numpy as np
import pandas as pd

from _mc2_shrink_sweep import live_blend          # the engine-faithful scorer

SRC = "_mc2_stage1b_serve_return.py"
KSS = [0, 10, 20, 40, 1000000000]
FEAT = "data_cache/_mc2_features_sk%d.parquet"


def _tag(ks):
    return "career-only control" if ks >= 1000000 else ("pure per-surface" if ks == 0
                                                        else "blend KS=%d" % ks)


def build(ks, drop_abandoned=False):
    """drop_abandoned: exclude ABANDONED matches from the serve/return rating updates.

    TennisRatio carries no "ret" or "w/o" strings -- the builder's own is_ret() matches 0 of
    616,725 rows, so retirements are entirely invisible to it and ret5 is a constant-zero
    feature. Detected instead the way the G2 work did it, by the winner never reaching the
    winning set count: 9,011 matches (1.46%), of which 4,389 still carry a serve stat line and
    therefore feed a serve rate off a handful of games into the ratings at full weight.

    The guard is deliberately NARROW. An abandoned match still has a real winner, so the Elo
    update stays -- the result is information. What gets skipped is the serve/return rating
    update and the surface-baseline update, because those read a stat line from a match nobody
    finished. The feature row is still emitted: its pre-match features are valid and `won` is
    valid, so it remains usable for scoring.
    """
    src = open(SRC, encoding="utf-8").read()

    if drop_abandoned:
        # a module-level helper, injected just before the chronological loop
        anchor = "AF = 0.12"
        assert src.count(anchor) == 1
        src = src.replace(anchor, """def _aband_sets(sc):
    if not isinstance(sc, str):
        return 0
    a = b = 0
    for tok in sc.split():
        t = tok.split(chr(40))[0]
        if "-" not in t:
            continue
        x, _, y = t.partition("-")
        try:
            x, y = int(x), int(y)
        except ValueError:
            continue
        if x > y:
            a += 1
        elif y > x:
            b += 1
    return max(a, b)


""" + anchor)
        # compute the flag once per match, inside the loop, before any update runs
        anchor = "    bs = base[s]"
        assert src.count(anchor) == 1
        # Threshold of 2 for everyone, deliberately. The builder does not read a best_of_5
        # column, and guessing one from tournament_level would need the gender logic too
        # (WTA slams are best-of-three). Using 2 universally UNDER-flags -- it misses a
        # best-of-five retirement that got as far as 2 sets -- and never over-flags, so it
        # cannot discard good data. It also matches exactly how the 9,011 were counted.
        src = src.replace(anchor, anchor + """
    _aband = _aband_sets(t.score) < 2""")
        # guard the two serve-update blocks (which also contain the base[] updates)
        for who in ("spw_a", "spw_b"):
            anchor = "    if not np.isnan(%s):" % who
            assert src.count(anchor) == 1, (anchor, src.count(anchor))
            src = src.replace(anchor, "    if not np.isnan(%s) and not _aband:" % who)

    # 1. per-surface rating fields on the state
    A = '              "S": 0.0, "R": 0.0, "nS": 0, "nR": 0,'
    assert src.count(A) == 1
    src = src.replace(A, A + """
              "S_s": {"hard": 0.0, "clay": 0.0, "grass": 0.0},
              "R_s": {"hard": 0.0, "clay": 0.0, "grass": 0.0},
              "nS_s": {"hard": 0, "clay": 0, "grass": 0},
              "nR_s": {"hard": 0, "clay": 0, "grass": 0},""")

    # 2. the pre-match expectation uses the shrunk surface blend
    A = """    Sa = 0.7 * a["S"] + 0.3 * a["Sf"]
    Ra = 0.7 * a["R"] + 0.3 * a["Rf"]
    Sb = 0.7 * b["S"] + 0.3 * b["Sf"]
    Rb = 0.7 * b["R"] + 0.3 * b["Rf"]"""
    assert src.count(A) == 1
    src = src.replace(A, """    _KS = %r
    def _bl(st, key, cnt, srf):
        w = st[cnt][srf] / (st[cnt][srf] + _KS) if _KS > 0 else 1.0
        return w * st[key + "_s"][srf] + (1 - w) * st[key]
    Sa = 0.7 * _bl(a, "S", "nS_s", s) + 0.3 * a["Sf"]
    Ra = 0.7 * _bl(a, "R", "nR_s", s) + 0.3 * a["Rf"]
    Sb = 0.7 * _bl(b, "S", "nS_s", s) + 0.3 * b["Sf"]
    Rb = 0.7 * _bl(b, "R", "nR_s", s) + 0.3 * b["Rf"]""" % float(ks))

    # 3. update the surface component alongside the career one, same error
    for who, other, sign in (("a", "b", "+"), ("b", "a", "-")):
        A = ('        %s["S"] += (0.8 / (%s["nS"] + 6)) * err\n'
             '        %s["R"] -= (0.8 / (%s["nR"] + 6)) * err'
             % (who, who, other, other))
        assert src.count(A) == 1, (A, src.count(A))
        src = src.replace(A, A + (
            '\n        %s["S_s"][s] += (0.8 / (%s["nS_s"][s] + 6)) * err'
            '\n        %s["R_s"][s] -= (0.8 / (%s["nR_s"][s] + 6)) * err'
            '\n        %s["nS_s"][s] += 1; %s["nR_s"][s] += 1'
            % (who, who, other, other, who, other)))

    # 3b. the UPDATE recomputes the expectation independently of the feature block, off the
    # raw career ratings. It must use the same blended values, or the surface components would
    # be learning against a baseline nobody predicts with -- and the two halves would drift.
    for srv, ret in (("a", "b"), ("b", "a")):
        A = 'e = bs + %s["S"] - %s["R"]' % (srv, ret)
        assert src.count(A) == 1, (A, src.count(A))
        src = src.replace(A, 'e = bs + _bl(%s, "S", "nS_s", s) - _bl(%s, "R", "nR_s", s)'
                          % (srv, ret))

    src = src.replace('"data_cache/_mc2_features.parquet"', '"%s"' % (FEAT % ks))
    src = src.replace('"data_cache/_mc2_state.pkl"',
                      '"data_cache/_mc2_state_sk%d.pkl"' % ks)
    for bad in ('to_parquet("data_cache/_mc2_features.parquet")',
                'open("data_cache/_mc2_state.pkl"'):
        assert bad not in src, "would overwrite production: %s" % bad

    print("=" * 78)
    print("BUILD KS=%d  (%s)  ->  %s" % (ks, _tag(ks), FEAT % ks))
    print("=" * 78)
    sys.stdout.flush()
    g = {"__name__": "__mc2_surf_sweep__", "__file__": SRC}
    exec(compile(src, SRC + "(KS=%d)" % ks, "exec"), g)          # noqa: S102
    del g
    gc.collect()


def score():
    from sklearn.metrics import roc_auc_score
    import os
    out = {}
    for ks in KSS:
        p = FEAT % ks
        if not os.path.exists(p):
            print("   (missing %s)" % p)
            continue
        F = pd.read_parquet(p, columns=["date", "year", "p_elo", "pa_pt", "pb_pt",
                                        "nS_a", "nS_b", "imp", "won", "surf"])
        F = F[F["imp"].notna() & F["won"].notna() & F["pa_pt"].notna()
              & F["pb_pt"].notna() & F["p_elo"].notna()]
        F = F[(F["nS_a"] >= 4) & (F["nS_b"] >= 4)].copy()
        F["mc2"], F["mkv"] = live_blend(F)
        out[ks] = F
        print("   KS=%-11d scored %d" % (ks, len(F)))
        gc.collect()
    if not out:
        return
    yrs = [2024, 2025, 2026]
    BAR = "=" * 104
    print("\n" + BAR)
    print("PER-SURFACE S/R -- MC2 live-equivalent blend, AUC / Brier by year")
    print(BAR)
    print("   %-22s" % "variant" + "".join("%24s" % str(y) for y in yrs))
    for ks, F in out.items():
        line = "   %-22s" % _tag(ks)
        for y in yrs:
            g = F[F["year"] == y]
            if len(g) < 300:
                line += "%24s" % "--"
                continue
            line += "%24s" % ("AUC %.4f Br %.4f"
                              % (roc_auc_score(g["won"], g["mc2"]),
                                 float(((g["mc2"] - g["won"]) ** 2).mean())))
        print(line)
    F0 = out[KSS[-1]] if KSS[-1] in out else list(out.values())[0]
    line = "   %-22s" % "market"
    for y in yrs:
        g = F0[F0["year"] == y]
        line += "%24s" % ("AUC %.4f Br %.4f"
                          % (roc_auc_score(g["won"], g["imp"]),
                             float(((g["imp"] - g["won"]) ** 2).mean())))
    print(line)

    print("\n" + BAR)
    print("BY SURFACE -- where a per-surface rating should help if it helps anywhere")
    print(BAR)
    for srf in ("hard", "clay", "grass"):
        m0 = F0["surf"] == srf
        if int(m0.sum()) < 400:
            continue
        g0 = F0[m0]
        print("   %s (n=%d)   market AUC %.4f Brier %.4f"
              % (srf, int(m0.sum()), roc_auc_score(g0["won"], g0["imp"]),
                 float(((g0["imp"] - g0["won"]) ** 2).mean())))
        for ks, F in out.items():
            g = F[F["surf"] == srf]
            print("      %-22s AUC %.4f  Brier %.4f"
                  % (_tag(ks), roc_auc_score(g["won"], g["mc2"]),
                     float(((g["mc2"] - g["won"]) ** 2).mean())))

    print("\n" + BAR)
    print("BY THINNER SIDE's serve-rated match count (all-surface count)")
    print(BAR)
    for lo, hi in ((4, 12), (12, 25), (25, 60), (60, 1000000)):
        m0 = (np.fmin(F0["nS_a"], F0["nS_b"]) >= lo) & (np.fmin(F0["nS_a"], F0["nS_b"]) < hi)
        if int(m0.sum()) < 300:
            continue
        g0 = F0[m0]
        print("   nS %d-%d (n=%d)   market Brier %.4f"
              % (lo, hi, int(m0.sum()), float(((g0["imp"] - g0["won"]) ** 2).mean())))
        for ks, F in out.items():
            m = (np.fmin(F["nS_a"], F["nS_b"]) >= lo) & (np.fmin(F["nS_a"], F["nS_b"]) < hi)
            g = F[m]
            print("      %-22s AUC %.4f  Brier %.4f"
                  % (_tag(ks), roc_auc_score(g["won"], g["mc2"]),
                     float(((g["mc2"] - g["won"]) ** 2).mean())))

    print("\n" + BAR)
    print("MEAN |MC2 - market|, 2026 only")
    print(BAR)
    for ks, F in out.items():
        g = F[F["year"] == 2026]
        print("   %-22s %5.2fpt" % (_tag(ks), 100 * float((g["mc2"] - g["imp"]).abs().mean())))


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "score"
    ks = [int(x) for x in sys.argv[2:]] or KSS
    if what == "build":
        for k in ks:
            build(k)
    else:
        score()
