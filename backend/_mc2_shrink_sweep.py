"""MC2 SERVE/RETURN SHRINKAGE SWEEP (2026-10-13, user: "Do 1 and validate it").

"1" was: empirical-Bayes shrinkage on MC2's serve/return inputs, so a 128-service-point rate
gets pulled toward the prior instead of reaching the Markov chain at face value.

IMPORTANT CORRECTION TO THE PLAN: MC2 already has that shrinkage. Stage 1b builds the ratings
online, from 0.0, with a count-decaying learning rate --

    a["S"] += (0.8 / (a["nS"] + 6)) * err

-- which is exactly the EB form, `n0` = 6. So there is nothing to add; the question is whether
n0 = 6 shrinks hard enough. It does not shrink much: the cumulative weight on observations after
8 matches is sum(0.8/(k+6), k=0..7) = 0.72, so a player with Diaz Acosta's 8-match sample already
sits 72% of the way to his raw unshrunk rate. At n0 = 20 that falls to 0.27.

So this sweeps n0 and measures. Method:

  * The REAL builder source is read off disk and exec'd with only two things changed: the four
    main S/R update constants, and the output paths. Nothing is hand-copied, so the swept logic
    cannot drift from the production pipeline. The S1/S2/R1/R2 splits are deliberately left at 6
    because they do not feed _point_probs -- changing one thing at a time keeps it readable.
  * The builder is ONE CHRONOLOGICAL PASS emitting strictly pre-match features, so every row is
    walk-forward by construction: a match's rating is built only from matches before it and its
    own result is folded in afterwards.
  * Scoring reproduces tennis_mc2.predict EXACTLY on the historical feature table -- the 3x3
    Gauss-Hermite integration over the per-player sigma 0.10/sqrt(nS), then the 50/50 log-odds
    blend with the same surface-shrunk Elo the builder already stores as p_elo. Scoring the
    Markov half alone would flatter the change, because the Elo half is untouched and dilutes it.

Reported per year AND split by sample size, because the whole point is the thin rows: a change
that lifts the thin bucket while leaving the thick one alone is the win condition, and a change
that only moves the average is not.

Run: ./venv/bin/python _mc2_shrink_sweep.py [build|score] [k0 ...]
Production files are never written -- outputs are suffixed _k<N>.
"""
import gc
import math
import os
import re
import sys

import numpy as np
import pandas as pd

SRC = "_mc2_stage1b_serve_return.py"
K0S = [6, 12, 20, 30, 45]
FEAT = "data_cache/_mc2_features_k%d.parquet"
_NODES = ((-1.7320508, 1 / 6), (0.0, 2 / 3), (1.7320508, 1 / 6))


# ----------------------------------------------------------------- build
def build(k0):
    """Exec the real builder with n0 = k0 and redirected outputs."""
    src = open(SRC, encoding="utf-8").read()
    n = 0
    for who, sign in (('a["S"]', "+="), ('b["R"]', "-="), ('b["S"]', "+="), ('a["R"]', "-=")):
        cnt = "nS" if '"S"' in who else "nR"
        side = who[0]
        old = '%s %s (0.8 / (%s["%s"] + 6)) * err' % (who, sign, side, cnt)
        new = '%s %s (0.8 / (%s["%s"] + %d)) * err' % (who, sign, side, cnt, k0)
        if old not in src:
            raise SystemExit("update line not found: %s" % old)
        src = src.replace(old, new)
        n += 1
    assert n == 4
    src = src.replace('"data_cache/_mc2_features.parquet"', '"%s"' % (FEAT % k0))
    src = src.replace('"data_cache/_mc2_state.pkl"', '"data_cache/_mc2_state_k%d.pkl"' % k0)
    # The production artifacts must not be touched by a sweep. Check the WRITE CALLS only --
    # a print() or a header comment still naming the production path is harmless, and an
    # over-broad check on the bare filename fires on exactly those.
    for _bad in ('to_parquet("data_cache/_mc2_features.parquet")',
                 'open("data_cache/_mc2_state.pkl"'):
        assert _bad not in src, "sweep would overwrite production: %s" % _bad
    print("=" * 78)
    print("BUILD n0=%d  ->  %s" % (k0, FEAT % k0))
    print("=" * 78)
    sys.stdout.flush()
    g = {"__name__": "__mc2_sweep__", "__file__": SRC}
    exec(compile(src, SRC + "(n0=%d)" % k0, "exec"), g)   # noqa: S102
    del g
    gc.collect()


# ----------------------------------------------------------------- score
# The Markov chain is IMPORTED from the engine, never re-implemented. An approximation here
# would silently change what is being compared and make the whole sweep worthless.
from tennis_mc2 import _p_match, _rnd          # noqa: E402


def _lg(p):
    p = min(max(float(p), 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def live_blend(F):
    """Reproduce tennis_mc2.predict on the feature table: sigma-integrated Markov, then the
    50/50 log-odds blend with the surface-shrunk Elo the builder already stored."""
    pa = F["pa_pt"].to_numpy(dtype=float)
    pb = F["pb_pt"].to_numpy(dtype=float)
    na = np.maximum(F["nS_a"].to_numpy(dtype=float), 4.0)
    nb = np.maximum(F["nS_b"].to_numpy(dtype=float), 4.0)
    sga, sgb = 0.10 / np.sqrt(na), 0.10 / np.sqrt(nb)
    pm = np.zeros(len(F))
    for xi, wi in _NODES:
        for xj, wj in _NODES:
            # _rnd exactly as predict() applies it, so the lru_cache keys line up too
            pm += wi * wj * np.array([_p_match(_rnd(x + xi * s_a), _rnd(y + xj * s_b))
                                      for x, y, s_a, s_b in zip(pa, pb, sga, sgb)])
    pe = F["p_elo"].to_numpy(dtype=float)
    z = 0.5 * np.array([_lg(x) for x in pe]) + 0.5 * np.array([_lg(x) for x in pm])
    return 1 / (1 + np.exp(-z)), pm


def score():
    from sklearn.metrics import roc_auc_score
    out = {}
    for k0 in K0S:
        p = FEAT % k0
        if not os.path.exists(p):
            print("   (missing %s -- build it first)" % p)
            continue
        F = pd.read_parquet(p, columns=["date", "year", "p_elo", "pa_pt", "pb_pt",
                                        "nS_a", "nS_b", "imp", "won"])
        F = F[F["imp"].notna() & F["won"].notna() & F["pa_pt"].notna()
              & F["pb_pt"].notna() & F["p_elo"].notna()].copy()
        F = F[(F["nS_a"] >= 4) & (F["nS_b"] >= 4)]
        blend, pm = live_blend(F)
        F["mc2"] = blend
        F["mkv"] = pm
        out[k0] = F
        print("   n0=%-3d scored rows %d" % (k0, len(F)))
        del blend, pm
        gc.collect()
    if not out:
        return
    yrs = [2024, 2025, 2026]
    print("\n" + "=" * 100)
    print("MC2 LIVE-EQUIVALENT BLEND -- AUC / Brier, by year.  market shown as the bar")
    print("=" * 100)
    hdr = "   %-6s" % "n0" + "".join("%22s" % ("%d (n=%d)" % (y, int((out[K0S[0]]["year"] == y).sum())))
                                     for y in yrs)
    print(hdr)
    for k0, F in out.items():
        line = "   %-6d" % k0
        for y in yrs:
            g = F[F["year"] == y]
            if len(g) < 300:
                line += "%22s" % "--"
                continue
            auc = roc_auc_score(g["won"], g["mc2"])
            br = float(((g["mc2"] - g["won"]) ** 2).mean())
            line += "%22s" % ("AUC %.4f Br %.4f" % (auc, br))
        print(line)
    F0 = out[K0S[0]]
    line = "   %-6s" % "mkt"
    for y in yrs:
        g = F0[F0["year"] == y]
        if len(g) < 300:
            line += "%22s" % "--"
            continue
        line += "%22s" % ("AUC %.4f Br %.4f"
                          % (roc_auc_score(g["won"], g["imp"]),
                             float(((g["imp"] - g["won"]) ** 2).mean())))
    print(line)

    print("\n" + "=" * 100)
    print("THE POINT OF THE EXERCISE -- by the THINNER side's serve-rated match count")
    print("=" * 100)
    buckets = ((4, 8), (8, 12), (12, 20), (20, 40), (40, 100000))
    for lo, hi in buckets:
        m0 = (np.fmin(F0["nS_a"], F0["nS_b"]) >= lo) & (np.fmin(F0["nS_a"], F0["nS_b"]) < hi)
        print("   nS %d-%d  (n=%d)" % (lo, hi, int(m0.sum())))
        if int(m0.sum()) < 150:
            print("      too few to read")
            continue
        g0 = F0[m0]
        print("      %-10s AUC %.4f  Brier %.4f   <- market"
              % ("market", roc_auc_score(g0["won"], g0["imp"]),
                 float(((g0["imp"] - g0["won"]) ** 2).mean())))
        for k0, F in out.items():
            m = (np.fmin(F["nS_a"], F["nS_b"]) >= lo) & (np.fmin(F["nS_a"], F["nS_b"]) < hi)
            g = F[m]
            if len(g) < 150:
                continue
            print("      n0=%-7d AUC %.4f  Brier %.4f   gap to mkt %+.4f"
                  % (k0, roc_auc_score(g["won"], g["mc2"]),
                     float(((g["mc2"] - g["won"]) ** 2).mean()),
                     float(((g["mc2"] - g["won"]) ** 2).mean())
                     - float(((g["imp"] - g["won"]) ** 2).mean())))

    print("\n" + "=" * 100)
    print("OVERCONFIDENCE -- mean |MC2 - market|, which is what the gate measured as the cause")
    print("=" * 100)
    for lo, hi in buckets:
        m0 = (np.fmin(F0["nS_a"], F0["nS_b"]) >= lo) & (np.fmin(F0["nS_a"], F0["nS_b"]) < hi)
        if int(m0.sum()) < 150:
            continue
        row = "   nS %-9s" % ("%d-%d" % (lo, hi))
        for k0, F in out.items():
            m = (np.fmin(F["nS_a"], F["nS_b"]) >= lo) & (np.fmin(F["nS_a"], F["nS_b"]) < hi)
            g = F[m]
            row += "  n0=%d %5.2fpt" % (k0, 100 * float((g["mc2"] - g["imp"]).abs().mean()))
        print(row)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "score"
    ks = [int(x) for x in sys.argv[2:]] or K0S
    if what == "build":
        for k in ks:
            build(k)
    else:
        score()
