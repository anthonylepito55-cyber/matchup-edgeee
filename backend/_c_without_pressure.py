"""CAN MODEL C WORK WITHOUT PRESSURE POINTS? (2026-10-10, user "Run it")

This decides whether buying a faster feed is worth anything. The fast feed that the user's
RapidAPI key unlocks carries serve-side stats same-day but has NO serve/return pressure points,
and `c_rp_diff_p1` is Model C's single biggest driver. So:
  * if C survives losing c_sp/c_rp, the fast feed becomes a genuine same-day pricing path and a
    paid tier is justified
  * if it does not, TennisRatio is structurally irreplaceable and speed is a dead end

Two tests, because they answer it from different directions:

  A. ABLATION -- refit C with d_c_sp and d_c_rp removed, same walk-forward recipe as shipped
     (LR + XGB 50/50, base fit on years < Y), scored on IDENTICAL rows. Discrimination (AUC),
     calibration (logloss, Brier) and the practical cell (C's dog picks against the market).

  B. NATURAL EXPERIMENT -- the pressure columns are only ~30% populated overall and 71.6% in
     2026, so C ALREADY prices plenty of matches without them (missing features are filled with
     0 at fit time). Compare C's real performance on rows that HAVE pressure against rows that
     do not. If C is no worse without, that is the strongest evidence available.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

import xgboost as xgb

PRESSURE = ["d_c_sp", "d_c_rp"]

# the shipped C prep, exactly as _tennis_abc6_agree_bt.py loads it
ns = {}
src = open("_tennis_model_c_build.py", encoding="utf-8").read()
exec(compile(src.split("from sklearn.linear_model")[0], "_c_prep", "exec"), ns)
m, feats, FC = ns["m"], ns["feats"], ns["FC"]
X = pd.DataFrame({k: pd.to_numeric(v, errors="coerce") for k, v in feats.items()})
KEY = ["date", "player_slug", "rival_slugname"]
core = m[KEY + ["won", "mkt", "player_odd", "rival_odd"]].join(X)
core = core[core["mkt"].notna() & X.notna().sum(axis=1).ge(18)].reset_index(drop=True)
core["yr"] = core["date"].dt.year
print(f"C core rows: {len(core)}   features: {len(FC)}", flush=True)
have = [c for c in PRESSURE if c in FC]
print(f"pressure features present in FC: {have}")
print(f"pressure coverage in the core: "
      f"{100 * core[have].notna().all(axis=1).mean():.1f}%  "
      f"(2026: {100 * core.loc[core.yr == 2026, have].notna().all(axis=1).mean():.1f}%)",
      flush=True)
FC_NO = [c for c in FC if c not in PRESSURE]


def lg(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def fit_year(cols, yr):
    tr, te = core[core.yr < yr], core[core.yr == yr]
    Xtr, Xte = tr[cols].fillna(0), te[cols].fillna(0)
    lr = LogisticRegression(max_iter=3000, C=0.5).fit(Xtr, tr["won"])
    bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                            colsample_bytree=0.8, n_jobs=8,
                            eval_metric="logloss").fit(Xtr, tr["won"])
    return 0.5 * (lr.predict_proba(Xte)[:, 1] + bst.predict_proba(Xte)[:, 1])


def metrics(p, y, odd, mkt):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    r = pd.Series(p).rank().values
    n1 = int(y.sum())
    auc = (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * (len(y) - n1))
    ll = -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
    br = np.mean((p - y) ** 2)
    # the practical cell: C picks the DOG (C > 50% while the market has them under 50%)
    sel = (p > 0.5) & (mkt < 0.5) & (odd > 1.005)
    roi = (100 * np.where(y[sel] > 0.5, odd[sel] - 1, -1).mean()) if sel.sum() > 50 else np.nan
    return auc, ll, br, roi, int(sel.sum())


print("\n" + "=" * 92)
print("A. ABLATION -- refit C without d_c_sp / d_c_rp, identical rows")
print("=" * 92)
print(f"   {'year':6s} {'variant':14s} {'AUC':>7s} {'logloss':>9s} {'Brier':>8s} "
      f"{'C dog ROI':>10s} {'n dogs':>7s}")
agg = {"full": [], "no_pressure": [], "market": []}
for yr in (2024, 2025, 2026):
    te = core[core.yr == yr]
    y, odd, mkt = te["won"].values, te["player_odd"].values, te["mkt"].values
    pf = fit_year(FC, yr)
    pn = fit_year(FC_NO, yr)
    for lab, p in (("full", pf), ("no_pressure", pn)):
        a, l, b, r, n = metrics(p, y, odd, mkt)
        agg[lab].append((a, l, b, r, n))
        print(f"   {yr:<6d} {lab:14s} {100 * a:6.2f}% {l:9.4f} {b:8.4f} "
              f"{r:9.1f}% {n:7d}")
    a, l, b, r, n = metrics(mkt, y, odd, mkt)
    agg["market"].append((a, l, b, r, n))
    print(f"   {yr:<6d} {'market':14s} {100 * a:6.2f}% {l:9.4f} {b:8.4f}")
    print()
print("   POOLED 2024-26:")
for lab in ("full", "no_pressure", "market"):
    v = np.array([[x[0], x[1], x[2]] for x in agg[lab]]).mean(0)
    roi = np.nanmean([x[3] for x in agg[lab]])
    print(f"      {lab:14s} AUC {100 * v[0]:6.2f}%   logloss {v[1]:.4f}   Brier {v[2]:.4f}"
          + (f"   C dog ROI {roi:+.1f}%" if lab != "market" else ""))
d_auc = (np.mean([x[0] for x in agg["no_pressure"]])
         - np.mean([x[0] for x in agg["full"]])) * 100
d_ll = np.mean([x[1] for x in agg["no_pressure"]]) - np.mean([x[1] for x in agg["full"]])
print(f"\n   >>> dropping pressure changes AUC by {d_auc:+.2f}pt and logloss by {d_ll:+.4f}")

print("\n" + "=" * 92)
print("B. NATURAL EXPERIMENT -- C's real performance where pressure EXISTS vs where it does not")
print("=" * 92)
print("   (C already prices both; missing features are filled with 0 at fit time)")
print(f"   {'year':6s} {'rows':16s} {'n':>7s} {'AUC':>7s} {'logloss':>9s} {'mkt logloss':>12s}")
for yr in (2024, 2025, 2026):
    te = core[core.yr == yr].reset_index(drop=True)
    p = fit_year(FC, yr)
    hasp = te[have].notna().all(axis=1).values
    for lab, msk in (("HAS pressure", hasp), ("no pressure", ~hasp)):
        if msk.sum() < 300:
            continue
        a, l, b, r, n = metrics(p[msk], te["won"].values[msk], te["player_odd"].values[msk],
                                te["mkt"].values[msk])
        am, lm, _, _, _ = metrics(te["mkt"].values[msk], te["won"].values[msk],
                                  te["player_odd"].values[msk], te["mkt"].values[msk])
        print(f"   {yr:<6d} {lab:16s} {int(msk.sum()):7d} {100 * a:6.2f}% {l:9.4f} {lm:12.4f}")
print("\n   If C is no worse on the no-pressure rows, the pressure family is not load-bearing")
print("   and a feed without it can price matches. If it is clearly worse, speed is a dead end.")
