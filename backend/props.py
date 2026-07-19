"""
props.py

Predicts a starting pitcher's strikeout total for one game, using an
XGBoost regressor with a Poisson objective — strikeouts are a
non-negative count (0, 1, 2, ...), which Poisson loss fits much better
than plain squared-error regression assumes for a symmetric, unbounded
target.

Features (see features.py's STRIKEOUT_FEATURE_COLUMNS): the pitcher's own
season and recent-form K/9, their recent average innings per start (a
high K/9 over 3 innings still means fewer total K's than a lower K/9 over
7), and the opposing team's season strikeout rate — a lineup that
whiffs more than average boosts every pitcher's expected K total against
them, independent of that pitcher's own skill.

Includes:
  - train_strikeout_model(): fit on historical per-outing data
  - predict_strikeouts(): single-pitcher-outing point prediction (the mean)
  - over_under_prob(): turns that point prediction into an actual over/under
    probability for a given line, treating it as a Poisson mean — this is
    what lets the app say "62% chance of going over 5.5", not just "6.4
    predicted strikeouts"
  - backtest_strikeout_model(): walk-forward MAE, same spirit as model.py's
    backtest() — so you can see how far off this typically runs before
    trusting it.
"""

import os
import joblib
import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import xgboost as xgb

from features import STRIKEOUT_FEATURE_COLUMNS

STRIKEOUT_MODEL_PATH = os.path.join(os.path.dirname(__file__), "model_artifacts", "strikeout_model.joblib")
os.makedirs(os.path.dirname(STRIKEOUT_MODEL_PATH), exist_ok=True)

# "Model A" — same architecture, trained on STRIKEOUT_BASEBALL_ONLY_FEATURE_COLUMNS (no
# player-prop market features) — see train.py and features.STRIKEOUT_BASEBALL_ONLY_FEATURE_COLUMNS.
# STRIKEOUT_MODEL_PATH above ("Model B", full feature set) keeps its original name/behavior;
# this is purely additive, same pattern as model.py's BASELINE_MODEL_PATH.
STRIKEOUT_BASELINE_MODEL_PATH = os.path.join(os.path.dirname(__file__), "model_artifacts", "strikeout_model_baseline.joblib")

DEFAULT_XGB_PARAMS = {
    # Grid-searched (strikeout_hyperparam_search.py) against the walk-
    # forward MAE backtest. Result: the original copied-in defaults were
    # already close to optimal — best config found (this one) beat them by
    # 1.7989 vs 1.8004 MAE, a 0.0015-strikeout difference that's noise-
    # level, not a real win. Applied anyway since it doesn't hurt, but
    # unlike the tennis model, tuning this one wasn't actually the lever —
    # the ~1.8 K average error is close to the honest ceiling for this
    # feature set (see features.py's STRIKEOUT_FEATURE_COLUMNS scope).
    "n_estimators": 300,
    "max_depth": 3,
    "learning_rate": 0.03,
    "subsample": 0.7,
    "colsample_bytree": 0.7,
    "min_child_weight": 3,
    "reg_lambda": 1.0,
}


def train_strikeout_model(training_df: pd.DataFrame, label_col: str = "strikeouts", save: bool = True,
                           xgb_params: dict = None, feature_columns: list = None, model_path: str = None):
    """
    training_df must contain feature_columns (defaults to STRIKEOUT_FEATURE_COLUMNS) + label_col
    (actual strikeouts recorded in that start). Missing feature values are median-imputed.

    xgb_params overrides DEFAULT_XGB_PARAMS — used by
    strikeout_hyperparam_search.py to try alternate configs against the
    same walk-forward backtest without duplicating this function.

    feature_columns/model_path let train.py fit "Model A" (baseball-only) alongside the default
    full feature set without duplicating this function — see STRIKEOUT_BASELINE_MODEL_PATH above.
    """
    feature_columns = feature_columns or STRIKEOUT_FEATURE_COLUMNS
    model_path = model_path or STRIKEOUT_MODEL_PATH
    X = training_df[feature_columns].copy()
    y = training_df[label_col].astype(float)

    medians = X.median(numeric_only=True)
    X = X.fillna(medians)

    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42, shuffle=True)

    params = {**DEFAULT_XGB_PARAMS, **(xgb_params or {})}
    model = xgb.XGBRegressor(
        **params,
        objective="count:poisson",
        random_state=42,
    )
    model.fit(X_train, y_train)

    val_preds = model.predict(X_val)
    metrics = {
        "mae": mean_absolute_error(y_val, val_preds),
        "predicted_mean": float(val_preds.mean()),
        "actual_mean": float(y_val.mean()),
        "n_train": len(X_train),
        "n_val": len(X_val),
    }

    if save:
        joblib.dump({"model": model, "medians": medians, "metrics": metrics}, model_path)

    return model, medians, metrics


def load_strikeout_model(model_path: str = None):
    model_path = model_path or STRIKEOUT_MODEL_PATH
    if not os.path.exists(model_path):
        return None, None, None
    obj = joblib.load(model_path)
    return obj["model"], obj["medians"], obj["metrics"]


def predict_strikeouts(feature_row: pd.DataFrame, model_path: str = None, feature_columns: list = None) -> float:
    """feature_row: 1-row DataFrame with STRIKEOUT_FEATURE_COLUMNS (from strikeout_features_to_row)
    — a superset of whatever feature_columns this model actually uses is fine, extras are ignored."""
    feature_columns = feature_columns or STRIKEOUT_FEATURE_COLUMNS
    model, medians, metrics = load_strikeout_model(model_path)
    if model is None:
        raise RuntimeError("No trained strikeout model found. Run train.py first.")
    X = feature_row[feature_columns].fillna(medians)
    return float(model.predict(X)[0])


def over_under_prob(mean_k: float, line: float) -> dict:
    """
    P(actual strikeouts > line) and P(< line), treating the model's point
    prediction as the mean (lambda) of a Poisson distribution — a natural
    fit since the model itself was trained with a Poisson objective on
    exactly this target. `line` is a half-integer (e.g. 5.5) so there's no
    push to handle; P(over) + P(under) = 1 by construction.
    """
    threshold = int(np.floor(line))  # over 5.5 means 6+, i.e. more than floor(5.5)
    p_under = float(poisson.cdf(threshold, mean_k))
    return {"over": round(1 - p_under, 4), "under": round(p_under, 4)}


def backtest_strikeout_model(historical_df: pd.DataFrame, label_col: str = "strikeouts", n_folds: int = 5,
                              xgb_params: dict = None, feature_columns: list = None) -> dict:
    """Walk-forward backtest: trains on earlier outings, tests on later ones."""
    feature_columns = feature_columns or STRIKEOUT_FEATURE_COLUMNS
    df = historical_df.sort_values("game_date").reset_index(drop=True)
    fold_size = len(df) // (n_folds + 1)
    results = []

    for fold in range(1, n_folds + 1):
        train_end = fold_size * fold
        test_end = fold_size * (fold + 1)
        train_df = df.iloc[:train_end]
        test_df = df.iloc[train_end:test_end]
        if len(train_df) < 50 or len(test_df) < 10:
            continue

        model, medians, _ = train_strikeout_model(train_df, label_col, save=False, xgb_params=xgb_params, feature_columns=feature_columns)

        X_test = test_df[feature_columns].fillna(medians)
        y_test = test_df[label_col].astype(float)
        preds = model.predict(X_test)

        results.append({
            "fold": fold,
            "n_test": len(test_df),
            "mae": mean_absolute_error(y_test, preds),
            "predicted_mean": float(preds.mean()),
            "actual_mean": float(y_test.mean()),
        })

    results_df = pd.DataFrame(results)
    return {
        "avg_mae": results_df["mae"].mean(),
        "folds": results_df.to_dict(orient="records"),
        "note": (
            "MAE is the average number of strikeouts the prediction is off "
            "by. A pitcher's actual strikeout total in any single start is "
            "genuinely noisy (early hook, big lead, rain delay), so don't "
            "expect this to be dead-on every time — treat it as a center "
            "estimate, not a guarantee."
        ),
    }
