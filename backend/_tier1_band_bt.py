# TIER-1 DOG CELLS BY PRICE BAND (2026-10-08, user "backtest the dog ones +100..+200
# over +200..+250 and see the difference"): walk-forward 2024-26, archive odds.
# Dog decimal: +100..+200 = 2.00-3.00, +200..+250 = 3.00-3.50 (and +250..+400 for context).
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
    return {k: (float(pr), float(pm), bool(w), float(m1), a, b)
            for k, pr, pm, w, m1, a, b in zip(te[KEY].itertuples(index=False, name=None),
                                              p, p_ms, te["won"].values, te["mkt"].values,
                                              te["player_odd"].values, te["rival_odd"].values)}

CELLS = ("gray_dog4", "star", "tier1", "calone_gdog", "fade_a_dog_gray")
BANDS = (("+100..+200", 2.0, 3.0), ("+200..+250", 3.0, 3.5), ("+250..+400", 3.5, 5.0))
agg = {c: {b[0]: {g: {"a": [], "y26": []} for g in ("M", "W")} for b in BANDS} for c in CELLS}
for yr in (2024, 2025, 2026):
    pa = fit_p(core_a, FC_A, yr)
    pb = fit_p(core_b, FC_B, yr)
    pc = fit_p(core_c, FC_C, yr)
    for k in set(pa) & set(pb) & set(pc):
        g = lvl.get(k, "?")
        if g == "?":
            continue
        pcr, pcg, w1, m1, a, b = pc[k]
        if m1 >= 0.5:
            continue                      # keep only rows where PLAYER is the market dog
        c1 = pcr >= 0.5                   # True = C on the dog(player)
        g1 = pcg >= 0.5
        aS = pa[k][0] >= 0.5
        bS = pb[k][0] >= 0.5
        mdog, gdog = m1, pcg
        if not (a and a > 1.0):
            continue
        fires = set()
        if g1 and gdog - mdog >= 0.04:
            fires.add("gray_dog4")
        star = c1 and g1
        alone = (not aS) and (not bS)
        if star:
            fires.add("star")
            if alone or (gdog - mdog) >= 0.04:
                fires.add("tier1")
        if alone and g1 and c1:
            fires.add("calone_gdog")
        if (not aS) and bS and c1 and g1:
            fires.add("fade_a_dog_gray")
        if not fires:
            continue
        pnl = (a - 1.0) if w1 else -1.0
        for bn, lo, hi in BANDS:
            if lo <= a < hi:
                for c in fires:
                    agg[c][bn][g]["a"].append(pnl)
                    if yr == 2026:
                        agg[c][bn][g]["y26"].append(pnl)
    print(f"{yr} done", flush=True)
for c in CELLS:
    print(f"\n{c}:", flush=True)
    for bn, lo, hi in BANDS:
        for g in ("M", "W"):
            v = agg[c][bn][g]["a"]
            if not v:
                continue
            w = sum(1 for x in v if x > 0)
            v6 = agg[c][bn][g]["y26"]
            w6 = sum(1 for x in v6 if x > 0)
            t6 = f" | 2026: {w6}-{len(v6)-w6} {100*sum(v6)/len(v6):+.1f}%" if v6 else ""
            print(f"  {bn} {g}: {w}-{len(v)-w}  win {100*w/len(v):.1f}%  ROI {100*sum(v)/len(v):+.1f}% (n={len(v)}){t6}", flush=True)
