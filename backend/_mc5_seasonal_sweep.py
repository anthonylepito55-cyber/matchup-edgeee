"""IS THE SEASONAL TERM WORTH ITS WEIGHT, AND SHOULD IT SCALE WITH SEASON LENGTH? (2026-10-13)

User: "what if it had seasonal stats weighted to how many games they had that season".

Two gaps this closes:
  1. MC5_SEAS = 0.10 was SHIPPED WITHOUT BEING SWEPT. It is the only one of MC5's terms that
     never got a number, which is not good enough.
  2. The user's refinement is genuinely distinct from what is already there. EB shrinkage pulls
     the seasonal RATE toward 0.5 when a season is short -- a 2-0 January reads 0.64, not 1.00 --
     but the WEIGHT on the resulting differential is a flat 0.10 whether a player has 4 matches
     on the surface or 40.

So three families are compared against MC3 on identical rows:

    FIXED       z_elo += W * (sw_a - sw_b)
    SCALED      z_elo += W * nmin/(nmin + K2) * (sw_a - sw_b)
    NO SHRINK   the same but with the rate unshrunk, to isolate what EB shrinkage is doing

SCALED uses the THINNER side's match count, because a comparison is only as strong as its weaker
half: a 40-match season against a 4-match one is still a 4-match comparison. Diaz Acosta on hard
is the case in point -- 4 matches against Mochizuki's 36 -- and under FIXED his 0.278 counts as
heavily as Mochizuki's 0.354.

Weight 0 is MC3 and must reproduce it. Nothing changes unless a variant beats MC3 on AUC and
Brier in all three years.
"""
import gc
import os
import sys

import numpy as np
import pandas as pd

import _mc2_surface_sr_sweep as SW
from tennis_mc2 import _NODES, _rnd
from tennis_mc3 import p_match
from tennis_mc5 import MC5_KS, MC5_MOV_W, MC5_SEAS_K

SRC = "_mc2_stage1b_serve_return.py"
FEAT = "data_cache/_mc5seas_features.parquet"
STATE = "data_cache/_mc5seas_state.pkl"


def build():
    src = open(SRC, encoding="utf-8").read()
    src = SW.apply_surface_transform(src, int(MC5_KS))
    src = SW.apply_mov_transform(src, MC5_MOV_W)

    # the per-(year, surface) tally on the state, updated AFTER the row is emitted
    old = '              "pw": 0.0, "pa": 0.0,'
    assert src.count(old) == 1
    src = src.replace(old, old + '\n              "seas": {},')
    old = '    a["n"] += 1; b["n"] += 1; a["ns"][s] += 1; b["ns"][s] += 1'
    assert src.count(old) == 1
    src = src.replace(old, old + """
    _yk = (int(t.date.year), s)
    for _st9, _w9 in ((a, won), (b, 1.0 - won)):
        _t9 = _st9["seas"].setdefault(_yk, [0.0, 0])
        _t9[0] += float(_w9)
        _t9[1] += 1""")

    # emit the season-to-date rate and count for both sides, strictly prior
    old = "    rows.append((t.date, t.date.year, t.player_slug, t.rival_slugname, s,"
    assert src.count(old) == 1
    src = src.replace(old, """    _sk9 = (int(t.date.year), s)
    _ta9 = a["seas"].get(_sk9) or [0.0, 0]
    _tb9 = b["seas"].get(_sk9) or [0.0, 0]
    _swa, _sna = (_ta9[0] / _ta9[1] if _ta9[1] else 0.5), _ta9[1]
    _swb, _snb = (_tb9[0] / _tb9[1] if _tb9[1] else 0.5), _tb9[1]
""" + old)
    old = '                 "score"])'
    assert src.count(old) == 1
    src = src.replace(old, '                 "score", "sw_a", "sn_a", "sw_b", "sn_b"])')
    old = '                 str(t.score or "")))'
    assert src.count(old) == 1
    src = src.replace(old, '                 str(t.score or ""), _swa, _sna, _swb, _snb))')

    src = src.replace('"data_cache/_mc2_features.parquet"', '"%s"' % FEAT)
    src = src.replace('"data_cache/_mc2_state.pkl"', '"%s"' % STATE)
    for bad in ('to_parquet("data_cache/_mc2_features.parquet")',
                'open("data_cache/_mc2_state.pkl"', 'open("data_cache/_mc3_state.pkl"',
                'open("data_cache/_mc5_state.pkl"'):
        assert bad not in src, "would overwrite a live artifact: %s" % bad
    print("BUILD: MC3 recipe + season-to-date-on-surface columns", flush=True)
    g = {"__name__": "__mc5seas__", "__file__": SRC}
    exec(compile(src, SRC + "(seas)", "exec"), g)                  # noqa: S102
    del g
    gc.collect()


def score():
    from sklearn.metrics import roc_auc_score
    if not os.path.exists(FEAT):
        raise SystemExit("missing %s -- build first" % FEAT)
    F = pd.read_parquet(FEAT)
    F = F[F["imp"].notna() & F["won"].notna() & F["pa_pt"].notna() & F["pb_pt"].notna()
          & F["p_elo"].notna() & (F["nS_a"] >= 4) & (F["nS_b"] >= 4)].reset_index(drop=True)
    num = lambda c: pd.to_numeric(F[c], errors="coerce").fillna(0.0).to_numpy(float)
    RAW_A, NA = num("sw_a"), num("sn_a")
    RAW_B, NB = num("sw_b"), num("sn_b")
    NMIN = np.minimum(NA, NB)
    print("scorable rows: %d" % len(F))
    print("season matches on this surface, thinner side: median %.0f  p25 %.0f  p75 %.0f"
          % (np.median(NMIN), np.percentile(NMIN, 25), np.percentile(NMIN, 75)))
    for t in (0, 2, 4, 8, 16):
        print("   thinner side has <= %2d: %5.1f%% of rows" % (t, 100 * (NMIN <= t).mean()))

    # EB-shrunk rate, as MC5 ships it, and the unshrunk one for contrast
    SH_A = (RAW_A * NA + MC5_SEAS_K * 0.5) / (NA + MC5_SEAS_K)
    SH_B = (RAW_B * NB + MC5_SEAS_K * 0.5) / (NB + MC5_SEAS_K)
    D_SH = np.where((NA > 0) & (NB > 0), SH_A - SH_B, 0.0)
    D_RAW = np.where((NA > 0) & (NB > 0), RAW_A - RAW_B, 0.0)
    print("   shrunk differential sd %.4f | unshrunk sd %.4f" % (D_SH.std(), D_RAW.std()))

    def sets_won(s):
        if not isinstance(s, str) or not s.strip():
            return 0
        x = y = 0
        for tok in s.split():
            t2 = tok.split("(")[0]
            if "-" not in t2:
                continue
            u, _, v = t2.partition("-")
            try:
                u, v = int(u), int(v)
            except ValueError:
                continue
            if u > v:
                x += 1
            elif v > u:
                y += 1
        return max(x, y)

    bo5 = np.array([sets_won(s) >= 3 for s in F["score"]])
    PA, PB = F["pa_pt"].to_numpy(float), F["pb_pt"].to_numpy(float)
    SGA = 0.10 / np.sqrt(np.maximum(F["nS_a"].to_numpy(float), 4.0))
    SGB = 0.10 / np.sqrt(np.maximum(F["nS_b"].to_numpy(float), 4.0))
    WON, MKT, YR = F["won"].to_numpy(float), F["imp"].to_numpy(float), F["year"].to_numpy()

    def lg(v):
        v = np.clip(v, 1e-6, 1 - 1e-6)
        return np.log(v / (1 - v))

    LGE = lg(F["p_elo"].to_numpy(float))
    pm = np.zeros(len(F))
    for xi, wi in _NODES:
        for xj, wj in _NODES:
            pm += wi * wj * np.array([p_match(_rnd(x + xi * sa), _rnd(y + xj * sb), bool(f))
                                      for x, y, sa, sb, f in zip(PA, PB, SGA, SGB, bo5)])
    LGM = lg(pm)

    def run(add):
        return 1 / (1 + np.exp(-(0.5 * (LGE + add) + 0.5 * LGM)))

    def ev(lab, p):
        out = [lab]
        for y in (2024, 2025, 2026):
            m = YR == y
            out.append("AUC %.4f Br %.4f" % (roc_auc_score(WON[m], p[m]),
                                             float(((p[m] - WON[m]) ** 2).mean())))
        return "   %-24s %s   %s   %s" % tuple(out)

    BAR = "=" * 98
    print("\n" + BAR)
    print("SEASONAL TERM -- 0 is MC3 and must reproduce it. SHIPPED is fixed W=0.10")
    print(BAR)
    print(ev("MC3 (control)", run(0.0)))
    print("   -- FIXED weight, as shipped --")
    # extended past 0.50 because the first pass was still improving at the edge of its range,
    # and a parameter chosen at a boundary is an artifact waiting to happen
    for w in (0.05, 0.10, 0.25, 0.50, 0.75, 1.00, 1.50, 2.00, 3.00):
        print(ev("fixed W=%.2f%s" % (w, "  <-- SHIPPED" if w == 0.10 else ""), run(w * D_SH)))
    print("   -- SCALED by the thinner side's season length (the user's idea) --")
    for k2 in (5.0, 10.0, 20.0):
        sc = NMIN / (NMIN + k2)
        for w in (0.10, 0.25, 0.50):
            print(ev("scaled W=%.2f K2=%g" % (w, k2), run(w * sc * D_SH)))
    print("   -- SCALED but with the rate UNSHRUNK, to isolate the EB step --")
    for w in (0.10, 0.25):
        print(ev("scaled-noshrink W=%.2f" % w, run(w * (NMIN / (NMIN + 10.0)) * D_RAW)))
    print("\n   market:")
    print(ev("MARKET", MKT))


if __name__ == "__main__":
    if (sys.argv[1] if len(sys.argv) > 1 else "score") == "build":
        build()
    else:
        score()
