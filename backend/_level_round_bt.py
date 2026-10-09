"""TOURNAMENT LEVEL x ROUND, for the marked dog cells (2026-10-08).
Q1: do the dog edges live in ITF/futures (soft, low limits) or at tour level (bettable)?
Q2: do early rounds price worse than late rounds?
Rig: same walk-forward A/B/C/gray fits, true gender, one row per match.
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
meta = {}
for k, lv, rd in zip(mC[KEY].itertuples(index=False, name=None),
                     mC["tournament_level"].astype(str).str.lower(),
                     mC["round"].astype(str).str.lower()):
    if "future" in lv or "itf" in lv:
        L = "ITF"
    elif "challenger" in lv:
        L = "CH"
    elif "slam" in lv:
        L = "SLAM"
    else:
        L = "TOUR"
    late = any(t in rd for t in ("final", "semi", "quarter", "1/4", "1/2"))
    qual = "qual" in rd
    meta[k] = (L, "LATE" if late else ("QUAL" if qual else "EARLY"), GM.get(str(k[1]), "?"))
print("prep done", flush=True)
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
    pa, pb, pc = fit_p(core_a, FC_A, yr), fit_p(core_b, FC_B, yr), fit_p(core_c, FC_C, yr)
    for k in set(pa) & set(pb) & set(pc):
        L, R, G = meta.get(k, ("?", "?", "?"))
        if G == "?" or L == "?":
            continue
        pcr, pcg, w1, m1, oa = pc[k]
        if m1 >= 0.5 or not oa or oa <= 1:        # keep rows where the player IS the dog
            continue
        c1, g1 = pcr >= 0.5, pcg >= 0.5
        aS, bS = pa[k][0] >= 0.5, pb[k][0] >= 0.5
        alone = aS != c1 and bS != c1
        star = c1 and g1
        gray4 = g1 and (pcg - m1) >= 0.04
        cell = ("calone_gray" if (alone and star) else
                ("tier1" if (star and (alone or gray4)) else
                 ("star" if star else ("gray4" if gray4 else None))))
        if cell is None:
            continue
        rows.append({"cell": cell, "L": L, "R": R, "G": G, "yr": yr, "od": oa,
                     "won": w1, "band": 1 if 2.0 <= oa <= 3.0 else 0})
    print(f"{yr} done", flush=True)
D = pd.DataFrame(rows)
print(f"\ndog-cell fires: {len(D)}")


def rep(label, sub, floor=60):
    if len(sub) < floor:
        print(f"  {label:40s} n={len(sub)} (thin)")
        return
    w = sub["won"].astype(bool)
    pnl = np.where(w, sub["od"] - 1.0, -1.0)
    print(f"  {label:40s} {int(w.sum())}-{int((~w).sum())}  win {100*w.mean():.1f}%  "
          f"ROI {100*pnl.mean():+.1f}%  (n={len(sub)})")


print("\n=== BY TOURNAMENT LEVEL (any marked dog cell, +100..+200) ===")
B = D[D["band"] == 1]
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    print(f"-- {gl} --")
    for L in ("ITF", "CH", "TOUR", "SLAM"):
        rep(f"{L}", B[(B["G"] == G) & (B["L"] == L)])
        rep(f"  {L} 2026 only", B[(B["G"] == G) & (B["L"] == L) & (B["yr"] == 2026)])
print("\n=== BY ROUND STAGE ===")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    print(f"-- {gl} --")
    for R in ("EARLY", "LATE", "QUAL"):
        rep(f"{R}", B[(B["G"] == G) & (B["R"] == R)])
print("\n=== LEVEL x ROUND (both genders) ===")
for L in ("ITF", "CH", "TOUR"):
    for R in ("EARLY", "LATE"):
        rep(f"{L} {R}", B[(B["L"] == L) & (B["R"] == R)])
