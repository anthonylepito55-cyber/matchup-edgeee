"""MC5 CANDIDATE: MC3 + a recency-weighted LAST-5 block + PRESSURE/CLUTCH (2026-10-13).

User asked for a head that adds "the last 5 games weighted by soonest wins or losses to latest
as well as pressure/clutch points". Named MC5, not MC4, because mc4_* already exists in the lane
namespace meaning "4 MC models agree" (the 4-MC DOG chip) and reusing it would collide.

WHAT IS ADDED, and how each enters:

  L5 RESULTS -> the Elo half.  "wins or losses weighted soonest to latest" is a result signal,
      and results are what Elo is. Weights 5/4/3/2/1 over the last five matches, normalised, so
      the most recent carries 33% and the fifth 7%.
          logit(p_elo) += L5W * (l5win_a - l5win_b)

  L5 SERVE FORM -> the Markov half, on the point probability. Stored as the RESIDUAL
      (actual serve points won minus what was expected against that opponent), so it is already
      opponent-adjusted and a big number means "served above their own level against that
      specific returner", not "played someone weak".
          pa_pt += L5S * l5srv_a      pb_pt += L5S * l5srv_b

  CLUTCH -> the Markov half, in log-odds. The builder already keeps an EB-shrunk pressure-point
      rate, (pw + 12.5)/(pa + 25) - 0.5, as-of and centred on zero.
          logit(p_markov) += CLW * (clutch_a - clutch_b)

MC3 ALREADY HAS A RECENCY TERM, and the distinction matters: its `Sf` is exponential with a
~5.4-match half-life and never truncates, so the last five matches are about 47% of that term
and roughly 14% of the serve rating overall. What is NEW here is a HARD five-match window with
explicit linear weights -- a different object, and the one C/G2/D have and MC2/MC3 lack.

EXPECTATIONS, stated before the numbers so they cannot be rationalised afterwards: clutch has
already been refuted twice on this family -- as tiebreak skill in Tier 2 (no gain, worse on the
subset where the rates differ) and as a stacker feature in Tier 3 (no OOS gain, coefficient
flipped sign between windows). The L5 block is the genuinely untested half.

Each term is swept ALONE first so it is attributable, then the best combination. Nothing ships
unless it beats MC3 on AUC and Brier in all three years, which is the bar the three shipped
MC3 changes cleared.

Run: ./venv/bin/python _mc5_l5_clutch_sweep.py [build|score]
"""
import gc
import math
import os
import sys

import numpy as np
import pandas as pd

import _mc2_surface_sr_sweep as SW
from tennis_mc2 import _NODES, _rnd
from tennis_mc3 import MC3_KS, MC3_MOV_W, p_match

SRC = "_mc2_stage1b_serve_return.py"
FEAT = "data_cache/_mc5_features.parquet"
STATE = "data_cache/_mc5_state.pkl"

# the L5 recency weights: most recent first, 5/4/3/2/1 normalised
L5_HELPER = '''L5_W = [5.0, 4.0, 3.0, 2.0, 1.0]


def _l5_block(st):
    """Recency-weighted last-5 win rate and serve residual, from strictly prior matches.

    hist rows are (date, nsets, is_ret, won, spw_resid), newest last. Weights run 5/4/3/2/1 from
    the MOST RECENT backwards, normalised over however many of the five exist, so a player with
    three prior matches is not penalised for the two that do not exist.
    """
    h = [x for x in st["hist"] if x[3] is not None][-5:]
    if not h:
        return 0.5, 0.0
    rec = list(reversed(h))                      # newest first
    w = L5_W[:len(rec)]
    tot = sum(w)
    win = sum(wi * float(r[3]) for wi, r in zip(w, rec)) / tot
    srv = sum(wi * float(r[4] if r[4] is not None else 0.0)
              for wi, r in zip(w, rec)) / tot
    return win, srv


'''


def build():
    src = open(SRC, encoding="utf-8").read()
    src = SW.apply_surface_transform(src, int(MC3_KS))
    src = SW.apply_mov_transform(src, MC3_MOV_W)

    # 1. the helper
    anchor = "AF = 0.12"
    assert src.count(anchor) == 1
    src = src.replace(anchor, L5_HELPER + anchor)

    # 2. hist must carry the result and the serve residual, not just (date, nsets, ret)
    old = 'st9["hist"].append((t.date, _ns9, _rt9))'
    assert src.count(old) == 1
    src = src.replace(old, 'st9["hist"].append((t.date, _ns9, _rt9, _h5won, _h5srv))')
    # the two values, computed where both the result and the serve residual are known
    old = "    # ---- updates ----"
    assert src.count(old) == 1
    src = src.replace(old, """    # L5 inputs for the NEXT match: the result, and how far this player's serve beat what
    # was expected of it against THIS opponent (so the residual is opponent-adjusted).
    _h5won = float(won)
    _h5srv = float(spw_a - (bs + Sa - Rb)) if not np.isnan(spw_a) else 0.0
""" + old)
    # load_feats reads x[1]/x[2], which still line up; nothing else indexes hist

    # 3. emit the four L5 columns per row, alongside the clutch the builder already computes
    old = "    rows.append((t.date, t.date.year, t.player_slug, t.rival_slugname, s,"
    assert src.count(old) == 1
    src = src.replace(old, """    _l5wa, _l5sa = _l5_block(a)
    _l5wb, _l5sb = _l5_block(b)
""" + old)
    old = '                 "score"])'
    assert src.count(old) == 1
    src = src.replace(old, '                 "score", "l5win_a", "l5srv_a", "l5win_b", "l5srv_b"])')
    old = '                 str(t.score or "")))'
    assert src.count(old) == 1, src.count(old)
    src = src.replace(old, '                 str(t.score or ""), _l5wa, _l5sa, _l5wb, _l5sb))')

    src = src.replace('"data_cache/_mc2_features.parquet"', '"%s"' % FEAT)
    src = src.replace('"data_cache/_mc2_state.pkl"', '"%s"' % STATE)
    for bad in ('to_parquet("data_cache/_mc2_features.parquet")',
                'open("data_cache/_mc2_state.pkl"',
                'open("data_cache/_mc3_state.pkl"'):
        assert bad not in src, "would overwrite a live artifact: %s" % bad
    print("BUILD MC5 features (MC3 recipe + L5 block + clutch already present)", flush=True)
    g = {"__name__": "__mc5_build__", "__file__": SRC}
    exec(compile(src, SRC + "(mc5)", "exec"), g)                   # noqa: S102
    del g
    gc.collect()


def score():
    from sklearn.metrics import roc_auc_score
    if not os.path.exists(FEAT):
        raise SystemExit("missing %s -- run build first" % FEAT)
    F = pd.read_parquet(FEAT)
    need = ["p_elo", "pa_pt", "pb_pt", "nS_a", "nS_b", "imp", "won", "year", "score",
            "clutch_a", "clutch_b", "l5win_a", "l5srv_a", "l5win_b", "l5srv_b"]
    miss = [c for c in need if c not in F.columns]
    if miss:
        raise SystemExit("feature table lacks %s" % miss)
    F = F[F["imp"].notna() & F["won"].notna() & F["pa_pt"].notna() & F["pb_pt"].notna()
          & F["p_elo"].notna() & (F["nS_a"] >= 4) & (F["nS_b"] >= 4)].reset_index(drop=True)
    print("scorable rows: %d" % len(F))

    def sets_won(s):
        if not isinstance(s, str) or not s.strip():
            return 0
        x = y = 0
        for tok in s.split():
            t = tok.split("(")[0]
            if "-" not in t:
                continue
            u, _, v = t.partition("-")
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
    PA = F["pa_pt"].to_numpy(float)
    PB = F["pb_pt"].to_numpy(float)
    SGA = 0.10 / np.sqrt(np.maximum(F["nS_a"].to_numpy(float), 4.0))
    SGB = 0.10 / np.sqrt(np.maximum(F["nS_b"].to_numpy(float), 4.0))
    ELO = F["p_elo"].to_numpy(float)
    WON = F["won"].to_numpy(float)
    MKT = F["imp"].to_numpy(float)
    YR = F["year"].to_numpy()
    num = lambda c: pd.to_numeric(F[c], errors="coerce").fillna(0.0).to_numpy(float)
    DW = num("l5win_a") - num("l5win_b")
    DS_A, DS_B = num("l5srv_a"), num("l5srv_b")
    DC = num("clutch_a") - num("clutch_b")
    print("L5 win diff: sd %.3f | L5 serve resid: sd %.4f | clutch diff: sd %.4f"
          % (DW.std(), DS_A.std(), DC.std()))

    def lg(v):
        v = np.clip(v, 1e-6, 1 - 1e-6)
        return np.log(v / (1 - v))

    LGE = lg(ELO)

    def run(l5w, l5s, clw):
        pa = PA + l5s * DS_A
        pb = PB + l5s * DS_B
        pm = np.zeros(len(F))
        for xi, wi in _NODES:
            for xj, wj in _NODES:
                pm += wi * wj * np.array(
                    [p_match(_rnd(x + xi * sa), _rnd(y + xj * sb), bool(f))
                     for x, y, sa, sb, f in zip(pa, pb, SGA, SGB, bo5)])
        z = 0.5 * (LGE + l5w * DW) + 0.5 * (lg(pm) + clw * DC)
        return 1 / (1 + np.exp(-z))

    def ev(lab, p):
        out = [lab]
        for y in (2024, 2025, 2026):
            m = YR == y
            out.append("AUC %.4f Br %.4f" % (roc_auc_score(WON[m], p[m]),
                                             float(((p[m] - WON[m]) ** 2).mean())))
        out.append("gap %5.2fpt" % (100 * float(np.abs(p - MKT).mean())))
        return "   %-18s %s   %s   %s   %s" % tuple(out)

    BAR = "=" * 104
    print("\n" + BAR)
    print("ONE TERM AT A TIME -- 0.0 is MC3 and must reproduce it")
    print(BAR)
    print("   %-18s %-21s %-21s %-21s %s" % ("variant", "2024", "2025", "2026", ""))
    base = run(0.0, 0.0, 0.0)
    print(ev("MC3 (control)", base))
    print("   -- L5 RESULTS into Elo --")
    for w in (0.25, 0.5, 1.0, 2.0):
        print(ev("L5W=%.2f" % w, run(w, 0.0, 0.0)))
    print("   -- L5 SERVE residual into the point prob --")
    for w in (0.25, 0.5, 1.0):
        print(ev("L5S=%.2f" % w, run(0.0, w, 0.0)))
    print("   -- CLUTCH into the Markov log-odds --")
    for w in (1.0, 3.0, 6.0):
        print(ev("CLW=%.1f" % w, run(0.0, 0.0, w)))
    print("\n   market, same rows:")
    print(ev("MARKET", MKT))


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "score"
    if what == "build":
        build()
    else:
        score()
