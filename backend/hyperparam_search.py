"""
hyperparam_search.py

Grid search over XGBoost hyperparameters, validated the same way the app's
own accuracy claims are validated: walk-forward backtest (model.backtest),
not a single train/test split. Run this after any change to the training
data or feature set — the best config for one feature set isn't
necessarily best for another.

Run directly:
    python hyperparam_search.py
"""

import pandas as pd

from model import backtest, DEFAULT_XGB_PARAMS
from build_training_data import TRAINING_CACHE

GRID = [
    {},  # current default, included as the baseline to beat
    {"max_depth": 2, "learning_rate": 0.03, "n_estimators": 250, "min_child_weight": 5, "reg_lambda": 1.5},
    {"max_depth": 2, "learning_rate": 0.02, "n_estimators": 400, "min_child_weight": 8, "reg_lambda": 2.0},
    {"max_depth": 2, "learning_rate": 0.015, "n_estimators": 400, "min_child_weight": 5, "reg_lambda": 1.0},
    {"max_depth": 3, "learning_rate": 0.02, "n_estimators": 300, "min_child_weight": 5, "reg_lambda": 1.5},
    {"max_depth": 3, "learning_rate": 0.015, "n_estimators": 300, "min_child_weight": 8, "reg_lambda": 2.0},
    {"max_depth": 2, "learning_rate": 0.02, "n_estimators": 300, "min_child_weight": 3, "reg_lambda": 1.0},
    {"max_depth": 2, "learning_rate": 0.02, "n_estimators": 300, "min_child_weight": 10, "reg_lambda": 2.5},
    {"max_depth": 2, "learning_rate": 0.025, "n_estimators": 350, "min_child_weight": 6, "reg_lambda": 1.5, "subsample": 0.7, "colsample_bytree": 0.7},
    {"max_depth": 1, "learning_rate": 0.03, "n_estimators": 300, "min_child_weight": 5, "reg_lambda": 1.5},
]


def main():
    df = pd.read_parquet(TRAINING_CACHE)
    print(f"Loaded {len(df)} historical games.\n")
    print(f"{'params':70s} {'brier':>8s} {'auc':>8s}")
    print("-" * 90)

    results = []
    for params in GRID:
        merged = {**DEFAULT_XGB_PARAMS, **params}
        summary = backtest(df, xgb_params=params)
        label = ", ".join(f"{k}={v}" for k, v in sorted(merged.items()))
        results.append((label, summary["avg_brier_score"], summary["avg_auc"]))
        print(f"{label:70s} {summary['avg_brier_score']:8.4f} {summary['avg_auc']:8.4f}")

    print()
    best = min(results, key=lambda r: r[1])
    print(f"Best by Brier: {best[0]}  (brier={best[1]:.4f}, auc={best[2]:.4f})")


if __name__ == "__main__":
    main()
