"""
strikeout_hyperparam_search.py

Same idea as hyperparam_search.py (the win-prob model's grid search), but
for the strikeout-prop regressor — its hyperparameters were never actually
validated against the walk-forward backtest, just copied in as reasonable-
looking defaults. Run this after any change to the strikeout training data
or feature set.

Run directly:
    python strikeout_hyperparam_search.py
"""

import pandas as pd

from props import backtest_strikeout_model, DEFAULT_XGB_PARAMS
from build_training_data import STRIKEOUT_TRAINING_CACHE

GRID = [
    {},  # current default, included as the baseline to beat
    {"max_depth": 1, "learning_rate": 0.03, "n_estimators": 300, "min_child_weight": 5, "reg_lambda": 1.5},
    {"max_depth": 1, "learning_rate": 0.03, "n_estimators": 600, "min_child_weight": 5, "reg_lambda": 1.5},
    {"max_depth": 2, "learning_rate": 0.03, "n_estimators": 300, "min_child_weight": 5, "reg_lambda": 1.5},
    {"max_depth": 2, "learning_rate": 0.02, "n_estimators": 400, "min_child_weight": 8, "reg_lambda": 2.0},
    {"max_depth": 3, "learning_rate": 0.02, "n_estimators": 300, "min_child_weight": 5, "reg_lambda": 1.5},
    {"max_depth": 3, "learning_rate": 0.015, "n_estimators": 400, "min_child_weight": 8, "reg_lambda": 2.0},
    {"max_depth": 4, "learning_rate": 0.03, "n_estimators": 300, "min_child_weight": 5, "reg_lambda": 1.5},
    {"max_depth": 5, "learning_rate": 0.02, "n_estimators": 300, "min_child_weight": 8, "reg_lambda": 2.0},
    {"max_depth": 3, "learning_rate": 0.03, "n_estimators": 300, "min_child_weight": 3, "reg_lambda": 1.0, "subsample": 0.7, "colsample_bytree": 0.7},
]


def main():
    df = pd.read_parquet(STRIKEOUT_TRAINING_CACHE)
    print(f"Loaded {len(df)} historical starts.\n")
    print(f"{'params':95s} {'mae':>8s}")
    print("-" * 110)

    results = []
    for params in GRID:
        merged = {**DEFAULT_XGB_PARAMS, **params}
        summary = backtest_strikeout_model(df, xgb_params=params)
        label = ", ".join(f"{k}={v}" for k, v in sorted(merged.items()))
        results.append((label, summary["avg_mae"]))
        print(f"{label:95s} {summary['avg_mae']:8.4f}")

    print()
    best = min(results, key=lambda r: r[1])
    print(f"Best by MAE: {best[0]}  (mae={best[1]:.4f})")


if __name__ == "__main__":
    main()
