"""STEP 2: ABLATE MODEL D (and check what sUTR depends on) (2026-10-10, user "yes")

Model C turned out to need none of the nine game-count features (AUC -0.01pt). D is the other
half of the pricing path -- Model P takes C, C's gray head and D's market-aware head -- so if D
also survives, the fast feed is a genuine same-day pricing path.

A CORRECTION TO MY OWN C TEST FIRST. I dropped `d_m_meff` (games-won share) as unavailable, but
it is games won / games played, and BOTH come straight off the set scores ("7-5 6-3" = 13 of 21
games). Same for tiebreaks. So the API-feasible set is LARGER than I tested and C's result only
gets stronger. What is genuinely unavailable is anything needing the SERVICE/RETURN SPLIT of
games -- hold%, break%, and per-service-game rates -- because the feed gives no service-game
count and the set scores cannot say who served first.

Classification applied here:
  AVAILABLE   serve/return point %, ace and DF counts, BP saved/converted %, anything from the
              set scores (games-won share, tiebreaks, how close losses were), and everything
              results-based (form, last-10, level shares, rank, rest, H2H, season)
  UNAVAILABLE hold%, break%, per-service-game rates, serve/return pressure points
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

import xgboost as xgb

nd = {}
src = open("_tennis_model_d_build.py", encoding="utf-8").read()
exec(compile(src.split("from sklearn.linear_model")[0], "_d_prep", "exec"), nd)
core = nd["core"]
FC_D = nd["FC_D"]
core = core.copy()
core["yr"] = pd.to_datetime(core["date"]).dt.year
print(f"D core rows: {len(core)}   features: {len(FC_D)}", flush=True)
print("FULL D FEATURE LIST:")
print("   " + ", ".join(FC_D))

# needs the SERVICE/RETURN SPLIT of games -- the one thing the feed cannot give
NEED_GAME_SPLIT = [c for c in FC_D if any(k in c for k in
                   ("hold", "break", "_pg", "_sp", "_rp", "sgw", "rgw"))]
print(f"\nfeatures needing a service-game split (UNAVAILABLE): {NEED_GAME_SPLIT}")
FEASIBLE = [c for c in FC_D if c not in NEED_GAME_SPLIT]
print(f"API-feasible D features: {len(FEASIBLE)} of {len(FC_D)}")


def fit_year(cols, yr):
    tr, te = core[core.yr < yr], core[core.yr == yr]
    Xtr, Xte = tr[cols].fillna(0), te[cols].fillna(0)
    lr = LogisticRegression(max_iter=3000, C=0.5).fit(Xtr, tr["won"])
    bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                            colsample_bytree=0.8, n_jobs=8,
                            eval_metric="logloss").fit(Xtr, tr["won"])
    p = 0.5 * (lr.predict_proba(Xte)[:, 1] + bst.predict_proba(Xte)[:, 1])
    # the market-aware head too, since that is what Model P actually consumes
    def lg(x):
        x = np.clip(np.asarray(x, float), 1e-6, 1 - 1e-6)
        return np.log(x / (1 - x))
    lrm = LogisticRegression(max_iter=3000, C=0.5).fit(
        np.column_stack([lg(tr["mkt"]), Xtr]), tr["won"])
    pm = lrm.predict_proba(np.column_stack([lg(te["mkt"]), Xte]))[:, 1]
    return p, pm


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
print("MODEL D ABLATION -- walk-forward, identical rows. Raw head and market-aware head.")
print("=" * 96)
out = {}
for lab, cols in (("full (shipped)", FC_D), ("API-feasible", FEASIBLE)):
    raw, ma = [], []
    for yr in (2024, 2025, 2026):
        te = core[core.yr == yr]
        p, pm = fit_year(cols, yr)
        raw.append(score(p, te["won"].values, te["player_odd"].values, te["mkt"].values))
        ma.append(score(pm, te["won"].values, te["player_odd"].values, te["mkt"].values))
    out[lab] = (raw, ma)
    for head, v in (("D raw", raw), ("D market-aware", ma)):
        a = np.mean([x[0] for x in v]) * 100
        l = np.mean([x[1] for x in v])
        r = np.nanmean([x[2] for x in v])
        print(f"   {lab:16s} {head:16s} feats {len(cols):2d}   AUC {a:6.2f}%   "
              f"logloss {l:.4f}   dog ROI {r:+6.1f}%   | 2026 AUC {100 * v[2][0]:.2f}%")
print("\n   change against the shipped model:")
for i, head in enumerate(("D raw", "D market-aware")):
    b, n = out["full (shipped)"][i], out["API-feasible"][i]
    print(f"      {head:16s} AUC {np.mean([x[0] for x in n]) * 100 - np.mean([x[0] for x in b]) * 100:+.2f}pt"
          f"   logloss {np.mean([x[1] for x in n]) - np.mean([x[1] for x in b]):+.4f}"
          f"   dog ROI {np.nanmean([x[2] for x in n]) - np.nanmean([x[2] for x in b]):+.1f}pt")

print("\n" + "=" * 96)
print("sUTR DEPENDENCY -- what does the court-UTR build actually read?")
print("=" * 96)
s = open("_tennis_sutr_build.py", encoding="utf-8").read()
cols_used = sorted({c for c in ("service_games_won", "return_games_won", "serve_pressure_all",
                                "serve_pressure_won", "return_pressure_all", "score",
                                "first_serve_points", "second_serve_points", "aces",
                                "breakpoints_saved_count", "return_1st_serve_points")
                    if c in s})
print(f"   archive columns referenced: {cols_used}")
split_needed = [c for c in cols_used if "games_won" in c or "pressure" in c]
print(f"   of those, needing a service-game split: {split_needed if split_needed else 'NONE'}")
print("   -> sUTR is games-share based; games come off the set scores, so it is reproducible")
print("      from the feed UNLESS it reads service/return game splits (listed above).")
