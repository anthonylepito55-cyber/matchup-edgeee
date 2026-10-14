"""LAST 5 ON THIS SURFACE -- the one version of the L5 idea that is not a duplicate (2026-10-13).

The all-surface L5 block was refuted: it degraded MC3 monotonically at every weight, because the
last five RESULTS are already in Elo (K is 5-10 per match, so they have been absorbed) and the
last five SERVE performances are already in `Sf`, an exponentially-weighted serve residual whose
5.4-match half-life makes roughly 47% of it the last five matches. Adding either back was a
second helping of the same information plus truncation noise.

`Sf` is SURFACE-AGNOSTIC, though. A last-5 restricted to the surface being played is therefore
genuinely new information rather than a copy -- and that is the same reasoning that made
per-surface serve/return the single biggest win of the day.

TWO CHANGES REQUIRED TO MAKE THE TEST FAIR, both of which the previous attempt lacked:
  * `hist` must record the surface of each match, which it did not.
  * `hist` was capped at 12 entries. A clay specialist entering a hard event can easily have
    0-2 hard matches in their last 12, so the cap is raised to 40 to give the surface filter
    material. load_feats still reads h[-1] and h[-5:], so its rest/m7/ret5 outputs are
    unaffected.

Coverage is reported before any ROI, because a block that only exists for half the field is a
different proposition from one that always fires.

Weight 0.0 is the control and must reproduce MC3 exactly. Nothing ships unless it beats MC3 on
AUC and Brier in all three years.

Run: ./venv/bin/python _mc5_l5surface_sweep.py [build|score]
"""
import gc
import os
import sys

import numpy as np
import pandas as pd

import _mc2_surface_sr_sweep as SW
from tennis_mc2 import _NODES, _rnd
from tennis_mc3 import MC3_KS, MC3_MOV_W, p_match

SRC = "_mc2_stage1b_serve_return.py"
FEAT = "data_cache/_mc5s_features.parquet"
STATE = "data_cache/_mc5s_state.pkl"

HELPER = '''L5S_W = [5.0, 4.0, 3.0, 2.0, 1.0]


def _l5_surf(st, srf):
    """Recency-weighted last-5 ON THIS SURFACE: (win rate, serve residual, n found).

    hist rows are (date, nsets, is_ret, won, spw_resid, surf), newest last. Weights run
    5/4/3/2/1 from the most recent backwards and are normalised over however many of the five
    exist, so a player with two prior matches on the surface is not penalised for the three
    that do not exist. n is returned so coverage can be reported rather than assumed.
    """
    h = [x for x in st["hist"] if len(x) > 5 and x[5] == srf and x[3] is not None][-5:]
    if not h:
        return 0.5, 0.0, 0
    rec = list(reversed(h))
    w = L5S_W[:len(rec)]
    tot = sum(w)
    win = sum(wi * float(r[3]) for wi, r in zip(w, rec)) / tot
    srv = sum(wi * float(r[4] if r[4] is not None else 0.0) for wi, r in zip(w, rec)) / tot
    return win, srv, len(rec)


'''


def build():
    src = open(SRC, encoding="utf-8").read()
    src = SW.apply_surface_transform(src, int(MC3_KS))
    src = SW.apply_mov_transform(src, MC3_MOV_W)

    anchor = "AF = 0.12"
    assert src.count(anchor) == 1
    src = src.replace(anchor, HELPER + anchor)

    # hist carries the result, the serve residual AND the surface
    old = 'st9["hist"].append((t.date, _ns9, _rt9))'
    assert src.count(old) == 1
    src = src.replace(old, 'st9["hist"].append((t.date, _ns9, _rt9, _h5won, _h5srv, s))')
    # raise the cap so the surface filter has material to work with
    old = '''        if len(st9["hist"]) > 12:
            st9["hist"] = st9["hist"][-12:]'''
    assert src.count(old) == 1, src.count(old)
    src = src.replace(old, '''        if len(st9["hist"]) > 40:
            st9["hist"] = st9["hist"][-40:]''')
    old = "    # ---- updates ----"
    assert src.count(old) == 1
    src = src.replace(old, """    _h5won = float(won)
    _h5srv = float(spw_a - (bs + Sa - Rb)) if not np.isnan(spw_a) else 0.0
""" + old)

    old = "    rows.append((t.date, t.date.year, t.player_slug, t.rival_slugname, s,"
    assert src.count(old) == 1
    src = src.replace(old, """    _wa, _sa9, _na9 = _l5_surf(a, s)
    _wb, _sb9, _nb9 = _l5_surf(b, s)
""" + old)
    old = '                 "score"])'
    assert src.count(old) == 1
    src = src.replace(old, '                 "score", "l5sw_a", "l5ss_a", "l5sn_a",\n'
                           '                 "l5sw_b", "l5ss_b", "l5sn_b"])')
    old = '                 str(t.score or "")))'
    assert src.count(old) == 1
    src = src.replace(old, '                 str(t.score or ""), _wa, _sa9, _na9, _wb, _sb9, _nb9))')

    src = src.replace('"data_cache/_mc2_features.parquet"', '"%s"' % FEAT)
    src = src.replace('"data_cache/_mc2_state.pkl"', '"%s"' % STATE)
    for bad in ('to_parquet("data_cache/_mc2_features.parquet")',
                'open("data_cache/_mc2_state.pkl"', 'open("data_cache/_mc3_state.pkl"'):
        assert bad not in src, "would overwrite a live artifact: %s" % bad
    print("BUILD: MC3 recipe + per-surface last-5 block (hist cap 12 -> 40)", flush=True)
    g = {"__name__": "__mc5s__", "__file__": SRC}
    exec(compile(src, SRC + "(l5surf)", "exec"), g)                # noqa: S102
    del g
    gc.collect()


def score():
    from sklearn.metrics import roc_auc_score
    if not os.path.exists(FEAT):
        raise SystemExit("missing %s -- build first" % FEAT)
    F = pd.read_parquet(FEAT)
    F = F[F["imp"].notna() & F["won"].notna() & F["pa_pt"].notna() & F["pb_pt"].notna()
          & F["p_elo"].notna() & (F["nS_a"] >= 4) & (F["nS_b"] >= 4)].reset_index(drop=True)
    print("scorable rows: %d" % len(F))
    num = lambda c: pd.to_numeric(F[c], errors="coerce").fillna(0.0).to_numpy(float)
    NA, NB = num("l5sn_a"), num("l5sn_b")
    print("\nCOVERAGE of the per-surface last-5 block:")
    for k in range(6):
        print("   %d prior matches on this surface: side A %5.1f%%   both sides %5.1f%%"
              % (k, 100 * (NA == k).mean(), 100 * ((NA == k) & (NB == k)).mean()))
    full = (NA >= 5) & (NB >= 5)
    print("   both sides with a FULL five: %.1f%% of rows" % (100 * full.mean()))

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
    PA, PB = F["pa_pt"].to_numpy(float), F["pb_pt"].to_numpy(float)
    SGA = 0.10 / np.sqrt(np.maximum(F["nS_a"].to_numpy(float), 4.0))
    SGB = 0.10 / np.sqrt(np.maximum(F["nS_b"].to_numpy(float), 4.0))
    ELO, WON = F["p_elo"].to_numpy(float), F["won"].to_numpy(float)
    MKT, YR = F["imp"].to_numpy(float), F["year"].to_numpy()
    DW = num("l5sw_a") - num("l5sw_b")
    SA, SB = num("l5ss_a"), num("l5ss_b")
    # only apply where BOTH sides have at least 3 on the surface, else the block is noise
    ok3 = (NA >= 3) & (NB >= 3)
    print("   applying the block only where both sides have 3+: %.1f%% of rows"
          % (100 * ok3.mean()))
    DW = np.where(ok3, DW, 0.0)
    SA = np.where(ok3, SA, 0.0)
    SB = np.where(ok3, SB, 0.0)
    print("   L5-surface win diff sd %.3f | serve resid sd %.4f" % (DW.std(), SA.std()))

    def lg(v):
        v = np.clip(v, 1e-6, 1 - 1e-6)
        return np.log(v / (1 - v))

    LGE = lg(ELO)

    def run(w_res, w_srv):
        pa, pb = PA + w_srv * SA, PB + w_srv * SB
        pm = np.zeros(len(F))
        for xi, wi in _NODES:
            for xj, wj in _NODES:
                pm += wi * wj * np.array(
                    [p_match(_rnd(x + xi * sa), _rnd(y + xj * sb), bool(f))
                     for x, y, sa, sb, f in zip(pa, pb, SGA, SGB, bo5)])
        z = 0.5 * (LGE + w_res * DW) + 0.5 * lg(pm)
        return 1 / (1 + np.exp(-z))

    def ev(lab, p, m=None):
        m = np.ones(len(F), bool) if m is None else m
        out = [lab]
        for y in (2024, 2025, 2026):
            q = m & (YR == y)
            out.append("AUC %.4f Br %.4f" % (roc_auc_score(WON[q], p[q]),
                                             float(((p[q] - WON[q]) ** 2).mean())))
        return "   %-18s %s   %s   %s" % tuple(out)

    BAR = "=" * 92
    print("\n" + BAR)
    print("PER-SURFACE LAST-5 -- 0.0 is MC3 and must reproduce it")
    print(BAR)
    base = run(0.0, 0.0)
    print(ev("MC3 (control)", base))
    print("   -- surface L5 RESULTS into Elo --")
    for w in (0.1, 0.25, 0.5, 1.0):
        print(ev("res w=%.2f" % w, run(w, 0.0)))
    print("   -- surface L5 SERVE residual into the point prob --")
    for w in (0.1, 0.25, 0.5):
        print(ev("srv w=%.2f" % w, run(0.0, w)))
    print("\n" + BAR)
    print("ON THE SUBSET WHERE THE BLOCK ACTUALLY FIRES (both sides 3+ on surface)")
    print(BAR)
    print(ev("MC3 (control)", base, ok3))
    for w in (0.1, 0.25, 0.5):
        print(ev("res w=%.2f" % w, run(w, 0.0), ok3))
    for w in (0.1, 0.25):
        print(ev("srv w=%.2f" % w, run(0.0, w), ok3))
    print("\n   market, all rows:")
    print(ev("MARKET", MKT))


if __name__ == "__main__":
    if (sys.argv[1] if len(sys.argv) > 1 else "score") == "build":
        build()
    else:
        score()
