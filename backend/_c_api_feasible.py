"""CAN MODEL C RUN ON ONLY WHAT THE FAST FEED CAN SUPPLY? (2026-10-10)

The first ablation settled the narrow question: dropping d_c_sp / d_c_rp costs Model C nothing
(AUC +0.03pt, logloss -0.0002, dog ROI +14.2% -> +14.6%). So the pressure family is NOT
load-bearing, and my earlier claim that `c_rp_diff_p1` is "Model C's biggest driver" was wrong --
that was an inference from one large feature value on the Brengle match, never a measurement.

But pressure was not the only gap. The RapidAPI feed gives no SERVICE-GAME COUNT, so every
per-game feature is unavailable too, and the hold%/break% derivation from set scores failed
(25% within tolerance). The real question is therefore the whole API-feasible feature set.

UNAVAILABLE from the feed (needs a service/return game count we cannot get):
    d_c_sgw, d_c_rgw            hold% and break%
    d_c_sp, d_c_rp              pressure points
    d_c_bpcre_pg, d_c_bpdef_pg  BPs created/faced per game
    d_c_aces_pg, d_c_dfs_pg     aces/DFs per service game
    d_m_meff                    games-won share
AVAILABLE or derivable: serve/return point percentages, aces and DF counts, BP saved and
converted percentages, tiebreaks (from the score), dominance ratio (from point percentages),
plus everything non-stat -- rank, odds, surface, round, level, H2H, form, season.

Staged so the cost of each loss is visible, rather than one all-or-nothing number.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

import xgboost as xgb

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
print("FULL FEATURE LIST:")
print("   " + ", ".join(FC))

PRESS = ["d_c_sp", "d_c_rp"]
HOLDBRK = ["d_c_sgw", "d_c_rgw"]
PERGAME = ["d_c_bpcre_pg", "d_c_bpdef_pg", "d_c_aces_pg", "d_c_dfs_pg", "d_m_meff"]
STAGES = [
    ("full (shipped)", []),
    ("- pressure", PRESS),
    ("- pressure, hold/break", PRESS + HOLDBRK),
    ("API-FEASIBLE (- all game-count)", PRESS + HOLDBRK + PERGAME),
]
for lab, drop in STAGES:
    miss = [c for c in drop if c not in FC]
    if miss:
        print(f"   NOTE: {lab}: not in FC, ignored -> {miss}")


def fit_year(cols, yr):
    tr, te = core[core.yr < yr], core[core.yr == yr]
    Xtr, Xte = tr[cols].fillna(0), te[cols].fillna(0)
    lr = LogisticRegression(max_iter=3000, C=0.5).fit(Xtr, tr["won"])
    bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                            colsample_bytree=0.8, n_jobs=8,
                            eval_metric="logloss").fit(Xtr, tr["won"])
    return 0.5 * (lr.predict_proba(Xte)[:, 1] + bst.predict_proba(Xte)[:, 1])


def score(p, y, odd, mkt):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    r = pd.Series(p).rank().values
    n1 = int(y.sum())
    auc = (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * (len(y) - n1))
    ll = -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
    sel = (p > 0.5) & (mkt < 0.5) & (odd > 1.005)
    roi = (100 * np.where(y[sel] > 0.5, odd[sel] - 1, -1).mean()) if sel.sum() > 50 else np.nan
    return auc, ll, roi, int(sel.sum())


print("\n" + "=" * 96)
print("STAGED ABLATION -- what each lost family costs Model C (walk-forward, identical rows)")
print("=" * 96)
res = {}
for lab, drop in STAGES:
    cols = [c for c in FC if c not in drop]
    per = []
    for yr in (2024, 2025, 2026):
        te = core[core.yr == yr]
        per.append(score(fit_year(cols, yr), te["won"].values, te["player_odd"].values,
                         te["mkt"].values))
    res[lab] = per
    a = np.mean([x[0] for x in per]) * 100
    l = np.mean([x[1] for x in per])
    r = np.nanmean([x[2] for x in per])
    y26 = per[2]
    print(f"   {lab:34s} feats {len(cols):2d}   AUC {a:6.2f}%   logloss {l:.4f}   "
          f"dog ROI {r:+6.1f}%   | 2026 AUC {100 * y26[0]:.2f}% ROI {y26[2]:+.1f}%")
base = res["full (shipped)"]
ba, bl = np.mean([x[0] for x in base]) * 100, np.mean([x[1] for x in base])
print("\n   change against the shipped model:")
for lab in [s[0] for s in STAGES][1:]:
    p = res[lab]
    print(f"      {lab:34s} AUC {np.mean([x[0] for x in p]) * 100 - ba:+.2f}pt   "
          f"logloss {np.mean([x[1] for x in p]) - bl:+.4f}   "
          f"dog ROI {np.nanmean([x[2] for x in p]) - np.nanmean([x[2] for x in base]):+.1f}pt")
te26 = core[core.yr == 2026]
am, lm, _, _ = score(te26["mkt"].values, te26["won"].values, te26["player_odd"].values,
                     te26["mkt"].values)
print(f"\n   for scale, the 2026 market: AUC {100 * am:.2f}%  logloss {lm:.4f}")
