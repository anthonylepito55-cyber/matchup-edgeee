"""BACKTEST: back the DOG when a demoted favourite signal fires (2026-10-08, user
"wouldn't I want to take the underdog on those" -> "what about backdated").
Walk-forward 2024-26 (LR+XGB, same rig as _stack_oppose_bt), true gender, one row per
match (row player = market dog), archive closing odds. Signals, all on the FAVOURITE:
  FADE-GOLD   gray (C market-blend) rates the dog 2pt+ under market
  C-EDGE5 FAV raw C rates the favourite 5pt+ over market
  D-MA2 FAV   D market-blend rates the favourite 2pt+ over market
  C-ALONE+GRAY FAV  A and B on the dog, C and gray on the favourite
"""
import numpy as np
import pandas as pd

ns = {}
src = open("_tennis_abc6_agree_bt.py", encoding="utf-8").read()
exec(compile(src.split("tot = {")[0], "_prep6", "exec"), ns)
KEY = ns["KEY"]
core_a, FC_A = ns["core_a"], ns["FC_A"]
core_b, FC_B = ns["core_b"], ns["FC_B"]
core_c, FC_C = ns["core_c"], ns["FC_C"]
nd = {}
srcd = open("_tennis_model_d_build.py", encoding="utf-8").read()
exec(compile(srcd.split("from sklearn.linear_model")[0], "_tmd_prep", "exec"), nd)
core_d, FC_D = nd["core"], nd["FC_D"]
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
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
        if m1 >= 0.5 or not oa or oa <= 1:
            continue                                   # row player = the market dog
        aS, bS = pa[k][0] >= 0.5, pb[k][0] >= 0.5
        cS, gS = pcr >= 0.5, pcg >= 0.5
        pdma = pdd[k][1]
        rows.append({
            "yr": yr, "G": g, "od": float(oa), "won": bool(w1),
            "FADE-GOLD": (m1 - pcg) >= 0.02,
            "C-EDGE5 FAV": (m1 - pcr) >= 0.05,
            "D-MA2 FAV": (m1 - pdma) >= 0.02,
            "C-ALONE+GRAY FAV": aS and bS and (not cS) and (not gS),
        })
    print(f"{yr} done  cum {len(rows)}", flush=True)
D = pd.DataFrame(rows)
D.to_parquet("data_cache/_fade_fav_signals_rows.parquet")


def rep(s):
    if len(s) < 40:
        return f"n={len(s)} (thin)"
    p = np.where(s.won, s.od - 1, -1.0)
    return f"{int(s.won.sum())}-{int((~s.won).sum())}  ROI {100*p.mean():+6.1f}%  (n={len(s)})"


SIGS = ["FADE-GOLD", "C-EDGE5 FAV", "D-MA2 FAV", "C-ALONE+GRAY FAV"]
for band, B in (("dog +100..+250", D[D.od.between(2.0, 3.5)]), ("all dog prices", D)):
    print(f"\n================ {band} ================")
    for G, gl in (("M", "MEN"), ("W", "WOMEN")):
        S = B[B.G == G]
        print(f"\n{gl}: every dog                {rep(S)}")
        for sg in SIGS:
            f = S[S[sg]]
            yrs = "  ".join(f"{y}: {rep(f[f.yr == y])}" for y in (2024, 2025, 2026))
            print(f"  fade {sg:18s} {rep(f)}")
            print(f"       by year  {yrs}")
