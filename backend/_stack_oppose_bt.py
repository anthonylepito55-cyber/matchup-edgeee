"""STACKING + OPPOSITION-COUNT BACKTEST (2026-10-08, user "backtest this").

The live 3-week read (235 deduped marked games) said:
  * stacking: 1 mark -8.8% (n=129), 2 marks +13.6%, 3 marks +55.1% (n=31), 5+ -9.9% (n=18)
  * opposition: 0-2 signals against our pick -6.6% (n=107), 3-4 against +14.8%,
    5+ against +11.8% (n=38) -- i.e. heavy opposition looked like a POSITIVE sign
Both are small. This replays them on the archive, walk-forward 2024-26, true gender,
one row per match, at archive closing odds.

What is replayable (and therefore what this tests):
  MARKS (the dog cells the board stacks): C-alone+gray, tier-1, gray 4pt+, fade-A
  OPPOSITION SIGNALS: Model A, Model B, Model D, MC2 (as-of ratings), pure form
    (tennis_pure_form.form with asof=). Model X and UTR are live-only and excluded.
"""
import math

import numpy as np
import pandas as pd

import tennis_mc2 as m2
import tennis_pure_form as pf

ns = {}
src = open("_tennis_abc6_agree_bt.py", encoding="utf-8").read()
exec(compile(src.split("tot = {")[0], "_prep6", "exec"), ns)
KEY = ns["KEY"]
core_a, FC_A = ns["core_a"], ns["FC_A"]
core_b, FC_B = ns["core_b"], ns["FC_B"]
core_c, FC_C = ns["core_c"], ns["FC_C"]
mC = ns["mC"] if "mC" in ns else ns["m"]
nd = {}
srcd = open("_tennis_model_d_build.py", encoding="utf-8").read()
exec(compile(srcd.split("from sklearn.linear_model")[0], "_tmd_prep", "exec"), nd)
core_d, FC_D = nd["core"], nd["FC_D"]
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
surf = {k: str(sf).title() for k, sf in zip(mC[KEY].itertuples(index=False, name=None),
                                            mC["surface"].astype(str))}

# --- MC2 as-of probability per (date, a, b), from the walk-forward feature table
F = pd.read_parquet("data_cache/_mc2_features.parquet")
F = F[F["pa_pt"].notna() & F["p_elo"].notna() & (F["nS_a"] >= 4) & (F["nS_b"] >= 4)]
lgt = lambda p: math.log(max(min(p, 1 - 1e-6), 1e-6) / (1 - max(min(p, 1 - 1e-6), 1e-6)))
_c = {}


def mc2p(pa, pb, na, nb, pe):
    k = (round(pa, 2), round(pb, 2), min(int(na), 60), min(int(nb), 60))
    pm = _c.get(k)
    if pm is None:
        sa, sb = 0.10 / max(k[2], 4) ** 0.5, 0.10 / max(k[3], 4) ** 0.5
        pm = sum(wi * wj * m2._p_match(m2._rnd(k[0] + xi * sa), m2._rnd(k[1] + xj * sb))
                 for xi, wi in m2._NODES for xj, wj in m2._NODES)
        _c[k] = pm
    return 1 / (1 + math.exp(-(0.5 * lgt(pe) + 0.5 * lgt(pm))))


MC2 = {}
for r in F.itertuples():
    d0 = pd.Timestamp(r.date).normalize()
    p = mc2p(float(r.pa_pt), float(r.pb_pt), r.nS_a, r.nS_b, float(r.p_elo))
    MC2[(d0, str(r.a), str(r.b))] = p
    MC2[(d0, str(r.b), str(r.a))] = 1 - p
print(f"prep done; MC2 keys {len(MC2)}", flush=True)
from sklearn.linear_model import LogisticRegression
import xgboost as xgb


def lg(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def fit_p(core, FC, yr):
    tr = core[core["date"].dt.year < yr]
    te = core[core["date"].dt.year == yr]
    Xtr, Xte = tr[FC].fillna(0), te[FC].fillna(0)
    lr = LogisticRegression(max_iter=3000, C=0.5).fit(Xtr, tr["won"])
    bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                            colsample_bytree=0.8, n_jobs=8, eval_metric="logloss").fit(Xtr, tr["won"])
    p = 0.5 * (lr.predict_proba(Xte)[:, 1] + bst.predict_proba(Xte)[:, 1])
    lrm = LogisticRegression(max_iter=3000, C=0.5).fit(np.column_stack([lg(tr["mkt"]), Xtr]), tr["won"])
    pm = lrm.predict_proba(np.column_stack([lg(te["mkt"]), Xte]))[:, 1]
    return {k: (float(a), float(b), bool(w), float(m), o)
            for k, a, b, w, m, o in zip(te[KEY].itertuples(index=False, name=None), p, pm,
                                        te["won"].values, te["mkt"].values, te["player_odd"].values)}


rows = []
for yr in (2024, 2025, 2026):
    pa, pb, pc, pdd = (fit_p(core_a, FC_A, yr), fit_p(core_b, FC_B, yr),
                       fit_p(core_c, FC_C, yr), fit_p(core_d, FC_D, yr))
    for k in set(pa) & set(pb) & set(pc) & set(pdd):
        g = GM.get(str(k[1]), "?")
        if g == "?":
            continue
        pcr, pcg, w1, m1, oa = pc[k]
        if m1 >= 0.5 or not oa or oa <= 1:          # the row's player IS the market dog
            continue
        c1, g1 = pcr >= 0.5, pcg >= 0.5               # True = on this dog
        aS, bS, dS = pa[k][0] >= 0.5, pb[k][0] >= 0.5, pdd[k][0] >= 0.5
        alone = (not aS) and (not bS)
        gray4 = g1 and (pcg - m1) >= 0.04
        star = c1 and g1
        cells = []
        if alone and c1 and g1:
            cells.append("calone")
        if star and (alone or gray4):
            cells.append("tier1")
        if gray4:
            cells.append("gray4")
        if (not aS) and bS and c1 and g1:
            cells.append("fadeA")
        if not cells:
            continue
        d0 = pd.Timestamp(k[0]).normalize()
        mc2 = MC2.get((d0, str(k[1]), str(k[2])))
        sf = surf.get(k, "Hard")
        f1, _n1 = pf.form(str(k[1]), sf, asof=k[0])
        f2, _n2 = pf.form(str(k[2]), sf, asof=k[0])
        against = {
            "A": not aS, "B": not bS, "D": not dS,
            "MC2": (None if mc2 is None else mc2 < 0.5),
            "form": (None if (f1 is None or f2 is None) else (f1 - f2) < 0),
        }
        rows.append({"yr": yr, "G": g, "od": float(oa), "won": bool(w1),
                     "n_marks": len(cells), "cells": "+".join(cells), **{f"x_{a}": v for a, v in against.items()}})
    print(f"{yr} done  cum {len(rows)}", flush=True)

D = pd.DataFrame(rows)
D.to_parquet("data_cache/_stack_oppose_rows.parquet")
sig = ["x_A", "x_B", "x_D", "x_MC2", "x_form"]
D["n_known"] = sum(D[c].notna().astype(int) for c in sig)
D["n_against"] = sum(D[c].fillna(False).astype(bool).astype(int) for c in sig)
print(f"\nmarked dog matches: {len(D)}  ({int((D.G == 'W').sum())} women)")
print(f"all 5 opposition signals known on {int((D.n_known == 5).sum())} of them\n")


def rep(label, sub, floor=40):
    if len(sub) < floor:
        print(f"  {label:42s} n={len(sub)} (thin)")
        return
    w = sub["won"].astype(bool)
    pnl = np.where(w, sub["od"] - 1.0, -1.0)
    print(f"  {label:42s} {int(w.sum())}-{int((~w).sum())}  win {100*w.mean():.1f}%  "
          f"ROI {100*pnl.mean():+7.1f}%  (n={len(sub)})")


for band_lbl, B in (("ALL DOG PRICES", D), ("DOG +100..+200", D[(D.od >= 2.0) & (D.od <= 3.0)])):
    print(f"=================== {band_lbl} ===================")
    print("=== 1. STACKING: how many of the 4 dog marks fire ===")
    for G, gl in (("M", "MEN"), ("W", "WOMEN")):
        for k in (1, 2, 3, 4):
            rep(f"{gl}: {k} mark(s)", B[(B.G == G) & (B.n_marks == k)])
    print("=== 2. OPPOSITION: of A, B, D, MC2, form -- how many oppose (all 5 known) ===")
    K = B[B.n_known == 5]
    for G, gl in (("M", "MEN"), ("W", "WOMEN")):
        for lo, hi, lab in ((0, 1, "0-1 against"), (2, 2, "2 against"), (3, 3, "3 against"),
                            (4, 5, "4-5 against")):
            rep(f"{gl}: {lab}", K[(K.G == G) & K.n_against.between(lo, hi)])
    print("=== 3. 2026 only (both genders) ===")
    B6 = B[B.yr == 2026]
    for k in (1, 2, 3, 4):
        rep(f"2026: {k} mark(s)", B6[B6.n_marks == k])
    K6 = B6[B6.n_known == 5]
    for lo, hi, lab in ((0, 1, "0-1 against"), (2, 3, "2-3 against"), (4, 5, "4-5 against")):
        rep(f"2026: {lab}", K6[K6.n_against.between(lo, hi)])
    print()
