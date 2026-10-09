"""EVERY HIGHLIGHTED MARK, RE-BACKTESTED WITH CORRECT GENDER (2026-10-08).

Why: tournament_level only says "futures" for ITF, so the old rule ("future" -> M) filed
every women's ITF match as MEN (17,210 of 2026's rows = 31% of its men's bucket) while its
"W" bucket was WTA-tour only. True gender = data_cache/_slug_gender.parquet (built from
unambiguous events + per-player propagation, 100% coverage, 1,759 players).

Each cell is evaluated with the EXACT predicate the board mark uses, including its price
band, split by true gender, all-years and 2026. Sim-based marks (green bait, orange MC2,
c75) are in _mc_asof_bt.py / _mc_dogfav_bt.py -- this file is the stats-model family.
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
mC = ns["mC"] if "mC" in ns else ns["m"]
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
gender = {k: GM.get(str(k[1]), "?") for k in mC[KEY].itertuples(index=False, name=None)}
nd = {}
srcd = open("_tennis_model_d_build.py", encoding="utf-8").read()
exec(compile(srcd.split("from sklearn.linear_model")[0], "_tmd_prep", "exec"), nd)
core_d, FC_D = nd["core"], nd["FC_D"]
print("cores ready", flush=True)
from sklearn.linear_model import LogisticRegression
import xgboost as xgb


def lg(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def fit_p(core, FC, yr):
    tr = core[core["date"].dt.year < yr]
    te = core[core["date"].dt.year == yr]
    Xtr, Xte = tr[FC].fillna(0), te[FC].fillna(0)
    ytr = tr["won"]
    lr = LogisticRegression(max_iter=3000, C=0.5).fit(Xtr, ytr)
    bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                            colsample_bytree=0.8, n_jobs=8, eval_metric="logloss").fit(Xtr, ytr)
    p = 0.5 * (lr.predict_proba(Xte)[:, 1] + bst.predict_proba(Xte)[:, 1])
    lr_ms = LogisticRegression(max_iter=3000, C=0.5).fit(np.column_stack([lg(tr["mkt"]), Xtr]), ytr)
    p_ms = lr_ms.predict_proba(np.column_stack([lg(te["mkt"]), Xte]))[:, 1]
    return {k: (float(pr), float(pm), bool(w), float(m1), a, b)
            for k, pr, pm, w, m1, a, b in zip(te[KEY].itertuples(index=False, name=None),
                                              p, p_ms, te["won"].values, te["mkt"].values,
                                              te["player_odd"].values, te["rival_odd"].values)}


# mark -> list of (label, side_is_dog, price_band_decimal_or_None)
MARKS = ("BLUE gray4-dog", "BLUE tier1-dog", "BLUE calone-gray-dog", "BLUE fadeA-dog-gray",
         "BLUE cedge5-fav-W", "PURPLE CGF calone-gfav -100/-150",
         "PURPLE CE5 cedge5-fav -150/-200", "PURPLE FGW fadegold-fav -200/-300",
         "x-ref cedge5-fav -200/-250", "x-ref fadegold-fav -150/-200",
         "x-ref calone-gfav -150/-200", "x-ref gray4-dog +100/+200",
         "x-ref tier1-dog +100/+200", "x-ref calone-gray-dog +100/+200")
agg = {m: {g: {"all": [], "y26": []} for g in ("M", "W")} for m in MARKS}


def add(mark, g, yr, won, od):
    if od is None or od <= 1:
        return
    pnl = (od - 1.0) if won else -1.0
    agg[mark][g]["all"].append(pnl)
    if yr == 2026:
        agg[mark][g]["y26"].append(pnl)


for yr in (2024, 2025, 2026):
    pa, pb, pc, pdd = (fit_p(core_a, FC_A, yr), fit_p(core_b, FC_B, yr),
                       fit_p(core_c, FC_C, yr), fit_p(core_d, FC_D, yr))
    for k in set(pa) & set(pb) & set(pc):
        g = gender.get(k, "?")
        if g == "?":
            continue
        pcr, pcg, w1, m1, oa, ob = pc[k]
        if not oa or not ob or oa <= 1 or ob <= 1:
            continue
        aS, bS = pa[k][0] >= 0.5, pb[k][0] >= 0.5
        c1, g1 = pcr >= 0.5, pcg >= 0.5
        dogp = m1 < 0.5                     # this row's player is the market dog
        mdog, gdog = (m1, pcg) if dogp else (1 - m1, 1 - pcg)
        hate = (mdog - gdog) >= 0.02
        alone = aS != c1 and bS != c1
        star = c1 == g1 and g1 == dogp
        # --- dog-side marks: the row's player must BE the dog and the cell must fire
        if dogp:
            won, od = w1, oa
            if g1 and (pcg - m1) >= 0.04:
                add("BLUE gray4-dog", g, yr, won, od)
                if 2.0 <= od <= 3.0:
                    add("x-ref gray4-dog +100/+200", g, yr, won, od)
            if star and (alone or (pcg - m1) >= 0.04):
                add("BLUE tier1-dog", g, yr, won, od)
                if 2.0 <= od <= 3.0:
                    add("x-ref tier1-dog +100/+200", g, yr, won, od)
            if alone and g1 and c1:
                add("BLUE calone-gray-dog", g, yr, won, od)
                if 2.0 <= od <= 3.0:
                    add("x-ref calone-gray-dog +100/+200", g, yr, won, od)
            if (not aS) and bS and c1 and g1:
                add("BLUE fadeA-dog-gray", g, yr, won, od)
        # --- favorite-side marks: the row's player must BE the favorite
        else:
            won, od = w1, oa
            if (pcr - m1) >= 0.05:
                if g == "W":
                    add("BLUE cedge5-fav-W", g, yr, won, od)
                if 1.5 <= od <= 1.667:
                    add("PURPLE CE5 cedge5-fav -150/-200", g, yr, won, od)
                if 1.4 <= od <= 1.5:
                    add("x-ref cedge5-fav -200/-250", g, yr, won, od)
            if alone and g1 and c1:
                if 1.667 <= od <= 2.0:
                    add("PURPLE CGF calone-gfav -100/-150", g, yr, won, od)
                if 1.5 <= od <= 1.667:
                    add("x-ref calone-gfav -150/-200", g, yr, won, od)
            if hate:
                if 1.333 <= od <= 1.5:
                    add("PURPLE FGW fadegold-fav -200/-300", g, yr, won, od)
                if 1.5 <= od <= 1.667:
                    add("x-ref fadegold-fav -150/-200", g, yr, won, od)
    print(f"{yr} done", flush=True)

print("\n=== HIGHLIGHTED MARKS, TRUE GENDER (all-years | 2026) ===")
for mk in MARKS:
    out = []
    for g in ("M", "W"):
        v, v6 = agg[mk][g]["all"], agg[mk][g]["y26"]
        if len(v) < 20:
            continue
        w = sum(1 for x in v if x > 0)
        t = f"{g}: {w}-{len(v)-w} {100*sum(v)/len(v):+.1f}% (n={len(v)})"
        if len(v6) >= 20:
            w6 = sum(1 for x in v6 if x > 0)
            t += f" | 26 {w6}-{len(v6)-w6} {100*sum(v6)/len(v6):+.1f}% (n={len(v6)})"
        out.append(t)
    if out:
        print(f"{mk}\n   " + "\n   ".join(out), flush=True)
