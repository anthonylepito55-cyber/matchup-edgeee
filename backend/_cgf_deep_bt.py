"""PURPLE CGF DISSECTION (2026-10-08): C ALONE against A and B, gray confirms C, and
C's side is the market FAVOURITE. Walk-forward 2024-26, true gender, one row per match.
Splits: year, price sub-band, tournament level, round, surface, gray-confirmation
strength, C-over-market magnitude, and the looser variants (C+gray without "alone").
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
for k, lv, rd, sf in zip(mC[KEY].itertuples(index=False, name=None),
                         mC["tournament_level"].astype(str).str.lower(),
                         mC["round"].astype(str).str.lower(),
                         mC["surface"].astype(str).str.lower()):
    L = ("ITF" if ("future" in lv or "itf" in lv) else
         "CH" if "challenger" in lv else "SLAM" if "slam" in lv else "TOUR")
    late = any(t in rd for t in ("final", "semi", "quarter", "1/4", "1/2"))
    S = "clay" if "clay" in sf else ("grass" if "grass" in sf else "hard")
    meta[k] = (L, "LATE" if late else "EARLY", S, GM.get(str(k[1]), "?"))
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
    bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05,
                            subsample=0.9, colsample_bytree=0.8, n_jobs=8,
                            eval_metric="logloss").fit(Xtr, tr["won"])
    p = 0.5 * (lr.predict_proba(Xte)[:, 1] + bst.predict_proba(Xte)[:, 1])
    lrm = LogisticRegression(max_iter=3000, C=0.5).fit(
        np.column_stack([lg(tr["mkt"]), Xtr]), tr["won"])
    pm = lrm.predict_proba(np.column_stack([lg(te["mkt"]), Xte]))[:, 1]
    return {k: (float(a), float(b), bool(w), float(m), o)
            for k, a, b, w, m, o in zip(te[KEY].itertuples(index=False, name=None), p, pm,
                                        te["won"].values, te["mkt"].values,
                                        te["player_odd"].values)}


rows = []
for yr in (2024, 2025, 2026):
    pa, pb, pc = fit_p(core_a, FC_A, yr), fit_p(core_b, FC_B, yr), fit_p(core_c, FC_C, yr)
    for k in set(pa) & set(pb) & set(pc):
        L, R, S, G = meta.get(k, ("?", "?", "?", "?"))
        if G == "?":
            continue
        pcr, pcg, w1, m1, oa = pc[k]
        if m1 < 0.5 or not oa or oa <= 1:        # the row's player must BE the favourite
            continue
        c1, g1 = pcr >= 0.5, pcg >= 0.5
        aS, bS = pa[k][0] >= 0.5, pb[k][0] >= 0.5
        if not c1 or not g1:                     # C and gray both on this favourite
            continue
        n_opp = int(aS != c1) + int(bS != c1)    # how many of A/B oppose C
        rows.append({"yr": yr, "L": L, "R": R, "S": S, "G": G, "od": oa, "won": w1,
                     "n_opp": n_opp, "gray_edge": pcg - m1, "c_edge": pcr - m1, "mkt": m1})
    print(f"{yr} done", flush=True)
D = pd.DataFrame(rows)
D.to_parquet("data_cache/_cgf_rows.parquet")  # dump so any later slice is instant
D["band"] = np.where((D["od"] >= 1.667) & (D["od"] <= 2.0), "-100..-150",
                     np.where((D["od"] >= 1.5) & (D["od"] < 1.667), "-150..-200", "other"))
print(f"\nC+gray favourite rows: {len(D)}  (alone, i.e. BOTH A and B oppose: "
      f"{int((D['n_opp'] == 2).sum())})")
CGF = D[(D["n_opp"] == 2) & (D["band"] == "-100..-150")]
print(f"THE MARK (alone + -100..-150): {len(CGF)}")


def rep(label, sub, floor=30):
    if len(sub) < floor:
        print(f"  {label:36s} n={len(sub)} (thin)")
        return
    w = sub["won"].astype(bool)
    pnl = np.where(w, sub["od"] - 1.0, -1.0)
    print(f"  {label:36s} {int(w.sum())}-{int((~w).sum())}  win {100*w.mean():.1f}%  "
          f"ROI {100*pnl.mean():+.1f}%  (n={len(sub)})")


print("\n=== THE MARK, BY YEAR ===")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    for y in (2024, 2025, 2026):
        rep(f"{gl} {y}", CGF[(CGF["G"] == G) & (CGF["yr"] == y)], floor=25)
    rep(f"{gl} all years", CGF[CGF["G"] == G])
print("\n=== PRICE SUB-BAND (within the mark) ===")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    sub = CGF[CGF["G"] == G]
    rep(f"{gl} -100..-125", sub[sub["od"] >= 1.8])
    rep(f"{gl} -125..-150", sub[sub["od"] < 1.8])
print("\n=== TOURNAMENT LEVEL ===")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    for L in ("TOUR", "CH", "ITF", "SLAM"):
        rep(f"{gl} {L}", CGF[(CGF["G"] == G) & (CGF["L"] == L)])
print("\n=== ROUND / SURFACE ===")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    for R in ("EARLY", "LATE"):
        rep(f"{gl} {R}", CGF[(CGF["G"] == G) & (CGF["R"] == R)])
    for S in ("hard", "clay", "grass"):
        rep(f"{gl} {S}", CGF[(CGF["G"] == G) & (CGF["S"] == S)])
print("\n=== CONFIRMATION STRENGTH (gray above market) ===")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    sub = CGF[CGF["G"] == G]
    rep(f"{gl} gray <2pt over mkt", sub[sub["gray_edge"] < 0.02])
    rep(f"{gl} gray 2-5pt", sub[(sub["gray_edge"] >= 0.02) & (sub["gray_edge"] < 0.05)])
    rep(f"{gl} gray 5pt+", sub[sub["gray_edge"] >= 0.05])
print("\n=== C-OVER-MARKET MAGNITUDE ===")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    sub = CGF[CGF["G"] == G]
    rep(f"{gl} C <5pt over mkt", sub[sub["c_edge"] < 0.05])
    rep(f"{gl} C 5pt+ over mkt", sub[sub["c_edge"] >= 0.05])
print("\n=== LOOSER VARIANTS (same -100..-150 band) ===")
B = D[D["band"] == "-100..-150"]
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    rep(f"{gl} C+gray, BOTH oppose (the mark)", B[(B["G"] == G) & (B["n_opp"] == 2)])
    rep(f"{gl} C+gray, ONE opposes", B[(B["G"] == G) & (B["n_opp"] == 1)])
    rep(f"{gl} C+gray, NEITHER opposes", B[(B["G"] == G) & (B["n_opp"] == 0)])
print("\n=== THE MARK AT -150..-200 (for contrast) ===")
D2 = D[(D["n_opp"] == 2) & (D["band"] == "-150..-200")]
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    rep(f"{gl} -150..-200", D2[D2["G"] == G])
