"""TRAIN THE MODEL C VARIANTS FOR FORWARD TRACKING (2026-10-10, user "Yes").

The ablation showed Model C loses nothing when the game-count features go, and that dropping
pressure + hold/break actually lifted the backtest dog ROI from +14.2% to +15.5%. That is
within noise on a backtest, and the standing rule is that the frozen live log decides -- so
these ship as TRACKED VARIANTS, not as a replacement. Nothing about the board changes.

Two variants, each a strict subset of the shipped feature list, so `predict_c` can score them
through its existing code path (it builds every feature and then selects `mdl["features"]`):

  C-NOHB  drops serve/return pressure and hold%/break% -- the best backtest cell (+15.5%)
  C-API   also drops the per-service-game rates, leaving only what the fast RapidAPI feed can
          supply. NOTE: `d_m_meff` (games-won share) is KEPT, unlike in the first ablation --
          games won and played both come off the set scores, so it IS available. That makes
          this 27 features rather than the 26 I first tested.

Same recipe as the shipped artifact: LR(C=0.5) + XGB(300, depth 4, lr 0.05) averaged 50/50,
plus the market-aware head, fitted on ALL rows, saved beside tennis_model_c.joblib.
"""
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score

import xgboost as xgb

#: needs the service/return split of games -- unavailable from the fast feed
PRESSURE = ["d_c_sp", "d_c_rp"]
HOLDBRK = ["d_c_sgw", "d_c_rgw"]
PERGAME = ["d_c_bpcre_pg", "d_c_bpdef_pg", "d_c_aces_pg", "d_c_dfs_pg"]

ns = {}
src = open("_tennis_model_c_build.py", encoding="utf-8").read()
exec(compile(src.split("from sklearn.linear_model")[0], "_c_prep", "exec"), ns)
m, feats, FC = ns["m"], ns["feats"], ns["FC"]
X = pd.DataFrame({k: pd.to_numeric(v, errors="coerce") for k, v in feats.items()})
KEY = ["date", "player_slug", "rival_slugname"]
core = m[KEY + ["won", "mkt", "player_odd", "rival_odd"]].join(X)
core = core[core["mkt"].notna() & X.notna().sum(axis=1).ge(18)].reset_index(drop=True)
core["yr"] = core["date"].dt.year
print(f"C core rows: {len(core)}   shipped features: {len(FC)}", flush=True)


def lg(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


VARIANTS = {
    "nohb": [c for c in FC if c not in PRESSURE + HOLDBRK],
    "api": [c for c in FC if c not in PRESSURE + HOLDBRK + PERGAME],
}
for tag, cols in VARIANTS.items():
    print(f"\n=== variant {tag}: {len(cols)} features "
          f"(dropped {sorted(set(FC) - set(cols))}) ===", flush=True)
    # a walk-forward sanity line, so a bad variant cannot ship silently
    for yr in (2025, 2026):
        tr, te = core[core.yr < yr], core[core.yr == yr]
        Xtr, Xte = tr[cols].fillna(0), te[cols].fillna(0)
        lr_ = LogisticRegression(max_iter=3000, C=0.5).fit(Xtr, tr["won"])
        bs_ = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05,
                                subsample=0.9, colsample_bytree=0.8, n_jobs=8,
                                eval_metric="logloss").fit(Xtr, tr["won"])
        p = 0.5 * (lr_.predict_proba(Xte)[:, 1] + bs_.predict_proba(Xte)[:, 1])
        print(f"   {yr}: logloss {log_loss(te['won'], p):.4f}  "
              f"auc {roc_auc_score(te['won'], p):.4f}  (n={len(te)})", flush=True)
    Xall, yall = core[cols].fillna(0), core["won"]
    lr = LogisticRegression(max_iter=3000, C=0.5).fit(Xall, yall)
    bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                            colsample_bytree=0.8, n_jobs=8,
                            eval_metric="logloss").fit(Xall, yall)
    lr_ms = LogisticRegression(max_iter=3000, C=0.5).fit(
        np.column_stack([lg(core["mkt"]), Xall]), yall)
    out = f"model_artifacts/tennis_model_c_{tag}.joblib"
    joblib.dump({"lr": lr, "xgb": bst, "lr_ms": lr_ms, "features": cols,
                 "trained_at": time.strftime("%Y-%m-%d"), "n_train": int(len(core)),
                 "variant": tag, "dropped": sorted(set(FC) - set(cols))}, out)
    print(f"   saved {out}", flush=True)
print("\ndone -- these are TRACKED variants; the shipped tennis_model_c.joblib is untouched")
