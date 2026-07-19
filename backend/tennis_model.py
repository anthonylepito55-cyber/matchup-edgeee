"""
tennis_model.py

Trains a gradient-boosted classifier (XGBoost) on the walk-forward tennis
features (tennis_features.py) to predict player_1's win probability.
Mirrors model.py's structure/conventions exactly (same calibration
approach, same walk-forward backtest shape) — see that file's comments
for the reasoning behind sigmoid calibration and why max_depth=1 tends to
win on datasets this size; started from the same defaults here rather than
re-deriving from scratch, to be re-validated for tennis specifically via
this module's own backtest() before trusting the starting point.
"""

import os
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.calibration import CalibratedClassifierCV
import xgboost as xgb

from tennis_features import FEATURE_COLUMNS

MODEL_DIR = os.path.join(os.path.dirname(__file__), "model_artifacts")
os.makedirs(MODEL_DIR, exist_ok=True)


def _model_path(league: str) -> str:
    return os.path.join(MODEL_DIR, f"tennis_{league}_xgb_model.joblib")


DEFAULT_XGB_PARAMS = {
    # Grid-searched (tennis_hyperparam_search.py) over max_depth in
    # {1,3,5,7} x n_estimators in {300,600} x learning_rate in {0.03,0.1},
    # against the same walk-forward backtest used to validate the model
    # (build_tennis_training_data.py). Despite having ~15-18x more training
    # rows than the MLB model this was originally copied from, max_depth=1
    # still won for BOTH tours — deeper trees (5, 7) got consistently
    # *worse* on both ATP and WTA (e.g. ATP: depth=1 Brier 0.2086 vs
    # depth=7 Brier 0.2117-0.2173 depending on other params). With only 7
    # diff-features, depth-1 stumps plus boosting are already expressive
    # enough; deeper trees start fitting feature-interaction noise instead.
    # n_estimators=600 (vs the MLB default's 300) was the one real gain —
    # small but consistent across both tours.
    "n_estimators": 600,
    "max_depth": 1,
    "learning_rate": 0.03,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "reg_lambda": 1.5,
}


def train(training_df: pd.DataFrame, league: str, label_col: str = "player_1_won",
          save: bool = True, xgb_params: dict = None):
    """training_df must contain FEATURE_COLUMNS + label_col. league is 'atp' or 'wta' —
    kept as fully separate models/files since men's and women's tour dynamics
    (best-of-5 at majors for men only, different serve/physicality baselines)
    are different enough that a shared model would blur both."""
    X = training_df[FEATURE_COLUMNS].copy()
    y = training_df[label_col].astype(int)

    medians = X.median(numeric_only=True)
    X = X.fillna(medians)

    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42, shuffle=True)

    params = {**DEFAULT_XGB_PARAMS, **(xgb_params or {})}
    base_model = xgb.XGBClassifier(
        **params, objective="binary:logistic", eval_metric="logloss", random_state=42,
    )
    calibrated = CalibratedClassifierCV(base_model, method="sigmoid", cv=5)
    calibrated.fit(X_train, y_train)

    val_probs = calibrated.predict_proba(X_val)[:, 1]
    metrics = {
        "brier_score": brier_score_loss(y_val, val_probs),
        "log_loss": log_loss(y_val, val_probs),
        "auc": roc_auc_score(y_val, val_probs),
        "n_train": len(X_train),
        "n_val": len(X_val),
    }

    if save:
        joblib.dump({"model": calibrated, "medians": medians, "metrics": metrics}, _model_path(league))

    return calibrated, medians, metrics


def load_model(league: str):
    path = _model_path(league)
    if not os.path.exists(path):
        return None, None, None
    obj = joblib.load(path)
    return obj["model"], obj["medians"], obj["metrics"]


def predict_proba(feature_row: pd.DataFrame, league: str) -> dict:
    model, medians, _ = load_model(league)
    if model is None:
        raise RuntimeError(f"No trained {league} tennis model found. Run build_tennis_training_data.py first.")
    X = feature_row[FEATURE_COLUMNS].fillna(medians)
    p1_prob = float(model.predict_proba(X)[:, 1][0])
    return {"player_1_win_prob": round(p1_prob, 4), "player_2_win_prob": round(1 - p1_prob, 4)}


def backtest(historical_df: pd.DataFrame, label_col: str = "player_1_won", n_folds: int = 5,
             xgb_params: dict = None) -> dict:
    """Walk-forward backtest — same shape as model.py's, see that file for the reasoning."""
    df = historical_df.sort_values("Date").reset_index(drop=True)
    fold_size = len(df) // (n_folds + 1)
    results = []

    for fold in range(1, n_folds + 1):
        train_end = fold_size * fold
        test_end = fold_size * (fold + 1)
        train_df = df.iloc[:train_end]
        test_df = df.iloc[train_end:test_end]
        if len(train_df) < 200 or len(test_df) < 50:
            continue

        model, medians, _ = train(train_df, league="_backtest", save=False, xgb_params=xgb_params)

        X_test = test_df[FEATURE_COLUMNS].fillna(medians)
        y_test = test_df[label_col].astype(int)
        probs = model.predict_proba(X_test)[:, 1]

        results.append({
            "fold": fold,
            "n_test": len(test_df),
            "brier_score": brier_score_loss(y_test, probs),
            "log_loss": log_loss(y_test, probs),
            "auc": roc_auc_score(y_test, probs) if y_test.nunique() > 1 else np.nan,
            "predicted_mean": probs.mean(),
            "actual_mean": y_test.mean(),
        })

    results_df = pd.DataFrame(results)
    return {
        "avg_brier_score": results_df["brier_score"].mean(),
        "avg_log_loss": results_df["log_loss"].mean(),
        "avg_auc": results_df["auc"].mean(),
        "folds": results_df.to_dict(orient="records"),
    }
