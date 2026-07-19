"""
tennis_hyperparam_search.py

The MLB model's max_depth=1 default (see model.py) was tuned for a ~3,800-
row dataset, where maximal regularization won every search. Tennis has
~68k (ATP) / ~45k (WTA) rows — copying that default without re-testing
would be a real mistake, since more data generally supports more model
capacity. This runs a grid search over the same walk-forward backtest used
in build_tennis_training_data.py, picking whichever config wins on
average Brier score across folds (not a single lucky split).

Run directly: python tennis_hyperparam_search.py
"""

import itertools
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

from tennis_data import get_atp_match_history, get_wta_match_history
from tennis_features import compute_walk_forward_state, FEATURE_COLUMNS
import tennis_model

GRID = {
    "max_depth": [1, 3, 5, 7],
    "n_estimators": [300, 600],
    "learning_rate": [0.03, 0.1],
}


def walk_forward_grid_search(feat_df: pd.DataFrame, n_folds: int = 5) -> pd.DataFrame:
    df = feat_df.sort_values("Date").reset_index(drop=True)
    fold_size = len(df) // (n_folds + 1)

    keys = list(GRID.keys())
    combos = list(itertools.product(*GRID.values()))
    results = []

    for combo in combos:
        params = dict(zip(keys, combo))
        fold_briers, fold_aucs = [], []

        for fold in range(1, n_folds + 1):
            train_end = fold_size * fold
            test_end = fold_size * (fold + 1)
            train_df, test_df = df.iloc[:train_end], df.iloc[train_end:test_end]
            if len(train_df) < 200 or len(test_df) < 50:
                continue

            model, medians, _ = tennis_model.train(train_df, league="_search", save=False, xgb_params=params)
            X_test = test_df[FEATURE_COLUMNS].fillna(medians)
            y_test = test_df["player_1_won"].astype(int)
            probs = model.predict_proba(X_test)[:, 1]

            fold_briers.append(brier_score_loss(y_test, probs))
            if y_test.nunique() > 1:
                fold_aucs.append(roc_auc_score(y_test, probs))

        results.append({
            **params,
            "avg_brier": np.mean(fold_briers),
            "avg_auc": np.mean(fold_aucs) if fold_aucs else np.nan,
            "n_folds": len(fold_briers),
        })
        print(f"  {params} -> Brier={results[-1]['avg_brier']:.4f}, AUC={results[-1]['avg_auc']:.4f}")

    return pd.DataFrame(results).sort_values("avg_brier")


if __name__ == "__main__":
    for league, history_fn in (("atp", get_atp_match_history), ("wta", get_wta_match_history)):
        print(f"\n=== {league.upper()} hyperparameter search ({len(list(itertools.product(*GRID.values())))} configs) ===")
        history = history_fn()
        feat_df, _, _ = compute_walk_forward_state(history)
        results = walk_forward_grid_search(feat_df)
        print(f"\nTop 5 configs for {league.upper()} by avg Brier:")
        print(results.head(5).to_string(index=False))
        results.to_csv(f"tennis_{league}_hyperparam_results.csv", index=False)
