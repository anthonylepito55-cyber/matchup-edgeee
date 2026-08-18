"""
model.py

Trains a gradient-boosted classifier (XGBoost) on historical pitcher
matchups, using the features from features.py (season/recent-form
pitching stats, bullpen, opponent lineup, park factor, rest days).

Includes:
  - train(): fit on historical data
  - predict_proba(): single-matchup prediction
  - backtest(): walk-forward evaluation with calibration (Brier score,
    log loss, reliability bins) so you can see if this is actually any good
    before trusting it with real money.
"""

import os
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.calibration import CalibratedClassifierCV
import xgboost as xgb

from features import FEATURE_COLUMNS

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model_artifacts", "xgb_model.joblib")
os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)

# "Model A" — same architecture, trained on BASEBALL_ONLY_FEATURE_COLUMNS (no market-derived
# features) — see train.py and features.BASEBALL_ONLY_FEATURE_COLUMNS. MODEL_PATH above
# ("Model B", full feature set) keeps its original name/behavior; this is purely additive.
BASELINE_MODEL_PATH = os.path.join(os.path.dirname(__file__), "model_artifacts", "xgb_model_baseline.joblib")

# "Model C" — same architecture again, trained on features.MODEL_C_FEATURE_COLUMNS (baseball
# features + the 6-book real-time-tracked market block instead of Model B's 5-book
# CONSENSUS_BOOKS one). See build_and_train_model_c.py for the walk-forward backtest that
# validated this before serving -- statistically tied with Model B on AUC/Brier, not a proven
# accuracy edge; served for its architecture (continuous polling, single-book-leak guards Model B
# doesn't have), not because it backtests better.
MODEL_C_PATH = os.path.join(os.path.dirname(__file__), "model_artifacts", "model_c.joblib")


DEFAULT_XGB_PARAMS = {
    # Grid-searched (hyperparam_search.py) against the walk-forward backtest
    # on the current feature set (post leakage-fix, post platoon-split):
    # max_depth=1 (decision stumps) beat every deeper config tried — Brier
    # 0.2486 vs 0.2492 for the previous max_depth=2 default, AUC 0.555 vs
    # 0.548, consistently across all 5 folds, not a single lucky split.
    # Makes sense given the data size (~3,800 rows): depth-1 trees are
    # maximally regularized, letting boosting build up complexity slowly
    # across many weak learners rather than each tree overfitting to a
    # feature interaction it only saw a handful of times.
    "n_estimators": 300,
    "max_depth": 1,
    "learning_rate": 0.03,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "reg_lambda": 1.5,
}


def train(training_df: pd.DataFrame, label_col: str = "home_win", save: bool = True, xgb_params: dict = None,
          feature_columns: list = None, model_path: str = None, random_state: int = 42):
    """
    training_df must contain feature_columns (defaults to FEATURE_COLUMNS) + label_col (1 if
    home team won). Missing feature values are median-imputed.

    xgb_params overrides DEFAULT_XGB_PARAMS — used by the hyperparameter
    grid search (see hyperparam_search.py) to try alternate configs against
    the same walk-forward backtest without duplicating this function.

    feature_columns/model_path let train.py fit "Model A" (baseball-only) alongside the default
    full feature set without duplicating this function — see BASELINE_MODEL_PATH above.

    random_state controls BOTH the train/val split AND XGBoost's own row/column subsampling
    (subsample=0.8/colsample_bytree=0.8 in DEFAULT_XGB_PARAMS make this a real source of
    model-to-model variance, not just split variance) — the two places this pipeline is
    stochastic. Defaults to 42 (this file's long-standing fixed seed) so every existing caller
    is unaffected; only multi-seed stability studies (see analyze_feature_stability.py) pass
    something else.
    """
    feature_columns = feature_columns or FEATURE_COLUMNS
    model_path = model_path or MODEL_PATH
    X = training_df[feature_columns].copy()
    y = training_df[label_col].astype(int)

    medians = X.median(numeric_only=True)
    X = X.fillna(medians)

    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=random_state, shuffle=True)

    params = {**DEFAULT_XGB_PARAMS, **(xgb_params or {})}
    base_model = xgb.XGBClassifier(
        **params,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=random_state,
    )

    # Calibrate probabilities — raw XGBoost probs tend to be overconfident,
    # and for betting purposes calibration matters more than raw accuracy.
    # Sigmoid (Platt scaling) rather than isotonic: isotonic fits an
    # arbitrary step function per CV fold, which overfits badly on the
    # few-hundred-example folds this dataset size produces; sigmoid is a
    # constrained 2-parameter curve that generalizes much better here.
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
        joblib.dump({"model": calibrated, "medians": medians, "metrics": metrics}, model_path)

    return calibrated, medians, metrics


def load_model(model_path: str = None):
    model_path = model_path or MODEL_PATH
    if not os.path.exists(model_path):
        return None, None, None
    obj = joblib.load(model_path)
    return obj["model"], obj["medians"], obj["metrics"]


def predict_proba(feature_row: pd.DataFrame, model_path: str = None, feature_columns: list = None) -> dict:
    """
    feature_row: 1-row DataFrame with FEATURE_COLUMNS (from features_to_row) — a superset of
    whatever feature_columns this model actually uses is fine, the extra columns are ignored.
    Returns home/away win probabilities.
    """
    feature_columns = feature_columns or FEATURE_COLUMNS
    model, medians, metrics = load_model(model_path)
    if model is None:
        raise RuntimeError("No trained model found. Run train() first (see train.py).")

    X = feature_row[feature_columns].fillna(medians)
    model_prob_home = float(model.predict_proba(X)[:, 1][0])

    return {
        "home_win_prob": round(model_prob_home, 4),
        "away_win_prob": round(1 - model_prob_home, 4),
    }


# Fixed seed set for ensemble training -- reproducible (not re-drawn per run), and the exact 5
# seeds already used to diagnose Model C's opp_platoon_woba_diff threshold sensitivity
# (2026-08-18: seed 42 alone gave that feature a 0.325 contribution on a real matchup where the
# other 4 seeds ranged 0.111-0.252, avg ~0.204 -- a single fixed seed can land on an unusually
# steep part of a decision-stump ensemble's learned step function for one feature, purely from
# where that seed's row/column subsampling happened to place split thresholds. Averaging several
# independently-trained seeds smooths this out without needing to identify every fragile feature
# by hand.)
ENSEMBLE_SEEDS = [1, 7, 42, 100, 777]


def train_ensemble(training_df: pd.DataFrame, label_col: str = "home_win", save: bool = True, xgb_params: dict = None,
                    feature_columns: list = None, model_path: str = None, seeds: list = None):
    """
    Trains len(seeds) independent models on the SAME data (only random_state differs -- both the
    train/val split and XGBoost's own row/column subsampling, see train()'s docstring), then
    predict_proba_ensemble averages their probabilities at inference time. See ENSEMBLE_SEEDS'
    comment above for why this exists: a single fixed seed can give one feature's learned
    threshold an outsized, non-representative weight for a specific real matchup, purely from
    where that seed happened to place split points -- not distinguishable from a "real" signal
    without comparing multiple independent fits.

    Saved artifact shape is {"models": [...], "medians": ..., "metrics": ..., "seeds": [...]} --
    deliberately different from train()'s {"model": ..., ...} single-model shape, so
    load_model()/predict_proba() (used by every other model in this app) fail loudly rather than
    silently mis-reading an ensemble file. Use load_model_ensemble()/predict_proba_ensemble() for
    anything trained here.
    """
    seeds = seeds or ENSEMBLE_SEEDS
    feature_columns = feature_columns or FEATURE_COLUMNS
    model_path = model_path or MODEL_PATH

    models = []
    medians = None
    val_metrics_list = []
    for seed in seeds:
        m, med, metrics = train(
            training_df, label_col, save=False, xgb_params=xgb_params,
            feature_columns=feature_columns, random_state=seed,
        )
        models.append(m)
        medians = med  # medians are computed from training_df alone, identical across seeds
        val_metrics_list.append(metrics)

    ensemble_metrics = {
        "brier_score": float(np.mean([mm["brier_score"] for mm in val_metrics_list])),
        "log_loss": float(np.mean([mm["log_loss"] for mm in val_metrics_list])),
        "auc": float(np.mean([mm["auc"] for mm in val_metrics_list])),
        "n_train": val_metrics_list[0]["n_train"],
        "n_val": val_metrics_list[0]["n_val"],
        "n_seeds": len(seeds),
    }

    if save:
        joblib.dump({"models": models, "medians": medians, "metrics": ensemble_metrics, "seeds": seeds}, model_path)

    return models, medians, ensemble_metrics


def load_model_ensemble(model_path: str = None):
    model_path = model_path or MODEL_PATH
    if not os.path.exists(model_path):
        return None, None, None
    obj = joblib.load(model_path)
    return obj["models"], obj["medians"], obj["metrics"]


def predict_proba_ensemble(feature_row: pd.DataFrame, model_path: str = None, feature_columns: list = None) -> dict:
    """Same contract as predict_proba(), but averages every seed's own probability rather than
    reading a single model -- see train_ensemble()'s docstring for why. seed_probs is included
    for transparency/debugging (e.g. a wide spread across seeds for one game is itself a useful
    "how much should I trust this number" signal), not used by any caller today."""
    feature_columns = feature_columns or FEATURE_COLUMNS
    models, medians, metrics = load_model_ensemble(model_path)
    if models is None:
        raise RuntimeError("No trained ensemble model found. Run train_ensemble() first.")

    X = feature_row[feature_columns].fillna(medians)
    seed_probs = [float(m.predict_proba(X)[:, 1][0]) for m in models]
    avg_prob = float(np.mean(seed_probs))

    return {
        "home_win_prob": round(avg_prob, 4),
        "away_win_prob": round(1 - avg_prob, 4),
        "seed_probs": [round(p, 4) for p in seed_probs],
    }


def backtest_ensemble(historical_df: pd.DataFrame, label_col: str = "home_win", n_folds: int = 5,
                       xgb_params: dict = None, feature_columns: list = None, seeds: list = None) -> dict:
    """Same walk-forward methodology as backtest(), but each fold trains len(seeds) models and
    averages their held-out predictions before scoring -- lets you validate the ensemble actually
    improves (or at least doesn't hurt) AUC/Brier before trusting it in production, same
    "validate before claiming improvement" standard as every other change to this pipeline."""
    seeds = seeds or ENSEMBLE_SEEDS
    feature_columns = feature_columns or FEATURE_COLUMNS
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

        seed_probs = []
        medians = None
        for seed in seeds:
            m, med, _ = train(
                train_df, label_col, save=False, xgb_params=xgb_params,
                feature_columns=feature_columns, random_state=seed,
            )
            medians = med
            X_test = test_df[feature_columns].fillna(med)
            seed_probs.append(m.predict_proba(X_test)[:, 1])
        probs = np.mean(seed_probs, axis=0)

        y_test = test_df[label_col].astype(int)
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
    summary = {
        "avg_brier_score": results_df["brier_score"].mean(),
        "avg_log_loss": results_df["log_loss"].mean(),
        "avg_auc": results_df["auc"].mean(),
        "folds": results_df.to_dict(orient="records"),
        "n_seeds": len(seeds),
    }
    return summary


def backtest(historical_df: pd.DataFrame, label_col: str = "home_win", n_folds: int = 5, xgb_params: dict = None,
             feature_columns: list = None) -> dict:
    """
    Walk-forward backtest: trains on earlier data, tests on later data,
    repeated across folds ordered by date. Reports calibration so you
    can sanity check the model isn't just overconfident noise.

    historical_df must be sorted by game_date ascending and contain
    feature_columns (defaults to FEATURE_COLUMNS) + label_col + game_date.
    """
    feature_columns = feature_columns or FEATURE_COLUMNS
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

        model, medians, _ = train(train_df, label_col, save=False, xgb_params=xgb_params, feature_columns=feature_columns)

        X_test = test_df[feature_columns].fillna(medians)
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
    summary = {
        "avg_brier_score": results_df["brier_score"].mean(),
        "avg_log_loss": results_df["log_loss"].mean(),
        "avg_auc": results_df["auc"].mean(),
        "folds": results_df.to_dict(orient="records"),
        "note": (
            "Brier score < 0.25 beats a coin flip; MLB game outcomes are "
            "inherently noisy, so even a well-calibrated model typically "
            "lands around 0.23-0.24 Brier and 55-58% AUC. If your numbers "
            "look dramatically better than that, be suspicious of leakage."
        ),
    }
    return summary
