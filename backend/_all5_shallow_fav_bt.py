# ALL-5 UNANIMOUS SHALLOW FAVORITE (2026-10-08, user "whats the backtest on this"):
# A+B+C+gray+D all on a -100..-150 favorite. Live-log replay said 12-5 +23.9% (n=17,
# post-18-condition scan = lucky-cell shape). This is the real walk-forward 2024-26
# answer on the gender-side rig (same prep/fit as _tennis_gender_side_bt).
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

BANDS = {"-100..-150": (1.667, 2.0), "-150..-200": (1.5, 1.667), "-200..-300": (1.333, 1.5)}
agg = {b: {g: {"a": [], "y": {}} for g in ("M", "W")} for b in BANDS}
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
            continue                      # orient on the favorite rows only
        heads = [pa[k][0], pb[k][0], pcr, pcg, pdd[k][0]]
        if not all(h >= 0.5 for h in heads):
            continue
        if not (a and a > 1.0):
            continue
        pnl = (a - 1.0) if w1 else -1.0
        for bn, (lo, hi) in BANDS.items():
            if lo <= a <= hi:
                agg[bn][g]["a"].append(pnl)
                agg[bn][g]["y"].setdefault(yr, []).append(pnl)
    print(f"{yr} done", flush=True)
for bn in BANDS:
    for g in ("M", "W"):
        v = agg[bn][g]["a"]
        if not v:
            continue
        w = sum(1 for x in v if x > 0)
        print(f"{bn} {g}: {w}-{len(v)-w}  win {100*w/len(v):.1f}%  ROI {100*sum(v)/len(v):+.1f}%  (n={len(v)})", flush=True)
        for yr, vv in sorted(agg[bn][g]["y"].items()):
            ww = sum(1 for x in vv if x > 0)
            print(f"    {yr}: {ww}-{len(vv)-ww}  {100*sum(vv)/len(vv):+.1f}% ({len(vv)})", flush=True)
