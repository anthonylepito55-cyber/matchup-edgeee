# EVERY FAVORITE SIGNAL AT -100..-150 (2026-10-08): walk-forward 2024-26, archive odds.
# Fav decimal 1.667-2.0. All rig-compatible favorite cells, M/W, all-years + 2026.
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

CELLS = ("c_fav", "gray_fav", "fade_gold", "cedge5_fav", "calone_gfav", "tier3",
         "dma_edge2_fav", "abc_agree_fav", "abcd_agree_fav", "all5_fav", "ab_agree_fav",
         "d_fav", "form_proxy_none")
agg = {c: {g: {"a": [], "y26": []} for g in ("M", "W")} for c in CELLS}
for yr in (2024, 2025, 2026):
    pa = fit_p(core_a, FC_A, yr)
    pb = fit_p(core_b, FC_B, yr)
    pc = fit_p(core_c, FC_C, yr)
    pdd = fit_p(core_d, FC_D, yr)
    for k in set(pa) & set(pb) & set(pc) & set(pdd):
        g = lvl.get(k, "?")
        if g == "?":
            continue
        pcr, pcg, w1, m1, a, b = pc[k]
        if m1 < 0.5:
            continue                      # player must be the FAVORITE
        if not (a and 1.4 <= a <= 1.5):
            continue                      # -100..-150
        aS = pa[k][0] >= 0.5
        bS = pb[k][0] >= 0.5
        dS = pdd[k][0] >= 0.5
        dgS = pdd[k][1] >= 0.5
        c1 = pcr >= 0.5
        g1 = pcg >= 0.5
        mdog, gdog = 1 - m1, 1 - pcg
        hate = (mdog - gdog) >= 0.02
        alone = (not aS) and (not bS) if c1 else (aS and bS)
        fires = set()
        if c1: fires.add("c_fav")
        if g1: fires.add("gray_fav")
        if hate: fires.add("fade_gold")
        if pcr - m1 >= 0.05: fires.add("cedge5_fav")
        if c1 and g1 and not aS and not bS: fires.add("calone_gfav")
        star = c1 and g1 and False        # star is dog-side; tier3 = not star & hate
        if hate and not (c1 and g1 and m1 < 0.5): fires.add("tier3")
        if dgS and pdd[k][1] - m1 >= 0.02: fires.add("dma_edge2_fav")
        if aS and bS and c1: fires.add("abc_agree_fav")
        if aS and bS and c1 and dS: fires.add("abcd_agree_fav")
        if aS and bS and c1 and g1 and dS: fires.add("all5_fav")
        if aS and bS: fires.add("ab_agree_fav")
        if dS: fires.add("d_fav")
        if not fires:
            continue
        pnl = (a - 1.0) if w1 else -1.0
        for c in fires:
            agg[c][g]["a"].append(pnl)
            if yr == 2026:
                agg[c][g]["y26"].append(pnl)
    print(f"{yr} done", flush=True)
for c in CELLS:
    out = []
    for g in ("M", "W"):
        v = agg[c][g]["a"]
        if not v:
            continue
        w = sum(1 for x in v if x > 0)
        v6 = agg[c][g]["y26"]
        w6 = sum(1 for x in v6 if x > 0)
        t6 = f" | 26: {w6}-{len(v6)-w6} {100*sum(v6)/len(v6):+.1f}%" if v6 else ""
        out.append(f"  {g}: {w}-{len(v)-w} {100*w/len(v):.0f}% ROI {100*sum(v)/len(v):+.1f}% (n={len(v)}){t6}")
    if out:
        print(c)
        for o in out:
            print(o, flush=True)
