"""
_tb_shap_diagnostic_c.py (one-off, safe to delete after running)

Same technique as _tb_shap_diagnostic.py (which answered this for Model B on 2026-08-17), applied
to Model C for tonight's TOR@TB game: monkeypatches build_matchup_features to capture the EXACT
raw feature dict main.py builds during a real _compute_today_response() run, then computes
XGBoost's pred_contribs (SHAP-equivalent additive per-feature contribution) for that exact vector
on the underlying (pre-calibration) Model C estimator -- real per-feature attribution instead of
raw magnitude sorting (which is misleading across features on different scales).

Run directly: python _tb_shap_diagnostic_c.py
"""
import datetime
import pandas as pd
import numpy as np
import xgboost as xgb

import features as features_module
import main as main_module
import model as model_module
import odds_fetcher
from features import MODEL_C_FEATURE_COLUMNS, MODEL_C_MARKET_FEATURE_COLUMNS, features_to_row

_real_build_matchup_features = features_module.build_matchup_features
captured = {}


def _spy(**kwargs):
    feats = _real_build_matchup_features(**kwargs)
    if kwargs.get("home_team_abbr") == "TB":
        captured["feats"] = feats
    return feats


main_module.build_matchup_features = _spy

today = datetime.date.today().strftime("%Y-%m-%d")
print(f"Force-refreshing Model C's snapshot for {today}...")
snap = odds_fetcher.get_model_c_snapshot(today, True)
main_module._model_c_snapshot_cache[today] = snap

print(f"Running a real _compute_today_response('{today}') to capture TB's exact live feature vector...")
result = main_module._compute_today_response(today)

feats = captured.get("feats")
if feats is None:
    print("Never captured TB's feats -- game may not be in today's slate anymore. Aborting.")
    raise SystemExit(1)

for g in result["games"]:
    if g.get("home_team_abbr") == "TB":
        print(f"\nLive prediction right now: model_a={g['prediction']['model_home_win_prob']:.4f}  "
              f"model_b={g.get('market_model_prob')}  model_c={g.get('model_c_prob')}")
        print(f"data_quality: {g.get('data_quality')}")

row = features_to_row(feats, feature_columns=MODEL_C_FEATURE_COLUMNS)
model_c, medians_c, _ = model_module.load_model(model_module.MODEL_C_PATH)
booster = model_c.calibrated_classifiers_[0].estimator.get_booster()

X = row[MODEL_C_FEATURE_COLUMNS].fillna(medians_c)
dmat = xgb.DMatrix(X, feature_names=MODEL_C_FEATURE_COLUMNS)
contribs = booster.predict(dmat, pred_contribs=True)[0]
contrib_series = pd.Series(contribs[:-1], index=MODEL_C_FEATURE_COLUMNS).sort_values(key=abs, ascending=False)
bias = contribs[-1]

print(f"\nRaw-score bias (base rate): {bias:.4f}")
print("\nTop 20 features by |raw-score contribution| for TONIGHT'S actual TB game (Model C):")
for feat, val in contrib_series.head(20).items():
    tag = "[MARKET_C]" if feat in MODEL_C_MARKET_FEATURE_COLUMNS else ""
    raw_val = X[feat].iloc[0]
    print(f"  {feat:35s} contrib={val:+.4f}  raw_value={raw_val:.4f}  {tag}")

market_sum = contrib_series[[c for c in MODEL_C_MARKET_FEATURE_COLUMNS if c in contrib_series.index]].sum()
baseball_sum = contrib_series[[c for c in contrib_series.index if c not in MODEL_C_MARKET_FEATURE_COLUMNS]].sum()
print(f"\nSum of signed contributions -- market_c features: {market_sum:+.4f}")
print(f"Sum of signed contributions -- baseball features: {baseball_sum:+.4f}")
print(f"(positive = pushes toward home/TB winning, since TB is home tonight)")
