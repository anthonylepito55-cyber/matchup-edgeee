# calone_gfav women 2025, -100..-150 (user ask 2026-10-08)
import numpy as np
ns = {}
src = open("_tennis_abc6_agree_bt.py", encoding="utf-8").read()
exec(compile(src.split("tot = {")[0], "_prep6", "exec"), ns)
KEY = ns["KEY"]
core_a, FC_A = ns["core_a"], ns["FC_A"]
core_b, FC_B = ns["core_b"], ns["FC_B"]
core_c, FC_C = ns["core_c"], ns["FC_C"]
mC = ns["mC"] if "mC" in ns else ns["m"]
lvl = {}
for k, l in zip(mC[KEY].itertuples(index=False, name=None), mC["tournament_level"].astype(str)):
    s = l.lower()
    lvl[k] = "W" if ("wom" in s or "wta" in s) else ("M" if ("atp" in s or "men" in s or "challenger" in s or "future" in s) else "?")
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
    return {k: (float(pr), float(pm), bool(w), float(m1), a)
            for k, pr, pm, w, m1, a in zip(te[KEY].itertuples(index=False, name=None),
                                           p, p_ms, te["won"].values, te["mkt"].values,
                                           te["player_odd"].values)}
for yr in (2024, 2025):
    pa = fit_p(core_a, FC_A, yr)
    pb = fit_p(core_b, FC_B, yr)
    pc = fit_p(core_c, FC_C, yr)
    res = {"M": [], "W": []}
    for k in set(pa) & set(pb) & set(pc):
        g = lvl.get(k, "?")
        if g == "?": continue
        pcr, pcg, w1, m1, a = pc[k]
        if m1 < 0.5 or not (a and 1.667 <= a <= 2.0): continue
        c1, g1 = pcr >= 0.5, pcg >= 0.5
        aS, bS = pa[k][0] >= 0.5, pb[k][0] >= 0.5
        if not (c1 and g1 and not aS and not bS): continue   # C alone on fav, gray confirms
        res[g].append((a - 1.0) if w1 else -1.0)
    for g in ("M", "W"):
        v = res[g]
        if not v: continue
        w = sum(1 for x in v if x > 0)
        print(f"{yr} {g}: {w}-{len(v)-w}  win {100*w/len(v):.1f}%  ROI {100*sum(v)/len(v):+.1f}%  (n={len(v)})", flush=True)
