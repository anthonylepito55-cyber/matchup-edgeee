"""
analyze_xfip_siera_fix.py

One-off validation: did fixing xfip_diff/siera_diff's training wiring (see
build_training_data._season_to_date_stats_from_history's batted_ball_mix param, and
data_collection.compute_xfip_siera) actually help Model A (baseball-only, what's actually
served), or just add noise with a fancier justification?

Reports the full requested metric suite against the walk-forward out-of-fold predictions:
Brier score, log loss, AUC, ECE, CLV/ROI vs. Pinnacle's closing line, and feature importance
(XGBoost gain-based, off the final trained model) — specifically where xera_diff/xfip_diff/
siera_diff rank among BASEBALL_ONLY_FEATURE_COLUMNS, since that's the direct evidence of whether
the fix gave the model anything to work with.

Run directly:
    python analyze_xfip_siera_fix.py
"""

import os
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

import model as model_module
from features import BASEBALL_ONLY_FEATURE_COLUMNS
from build_training_data import TRAINING_CACHE
from data_collection import CACHE_DIR

ODDS_CACHE = os.path.join(CACHE_DIR, "historical_market_probs.parquet")
N_FOLDS = 5


def expected_calibration_error(probs: np.ndarray, outcomes: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0, 1, n_bins + 1)
    bin_idx = np.clip(np.digitize(probs, bins) - 1, 0, n_bins - 1)
    total = 0.0
    for b in range(n_bins):
        mask = bin_idx == b
        if mask.sum() == 0:
            continue
        total += (mask.sum() / len(probs)) * abs(probs[mask].mean() - outcomes[mask].mean())
    return total


def walk_forward_predictions(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("game_date").reset_index(drop=True)
    fold_size = len(df) // (N_FOLDS + 1)
    out_rows = []
    for fold in range(1, N_FOLDS + 1):
        train_end = fold_size * fold
        test_end = fold_size * (fold + 1)
        train_df = df.iloc[:train_end]
        test_df = df.iloc[train_end:test_end]
        if len(train_df) < 50 or len(test_df) < 10:
            continue
        model, medians, _ = model_module.train(train_df, save=False, feature_columns=BASEBALL_ONLY_FEATURE_COLUMNS)
        X_test = test_df[BASEBALL_ONLY_FEATURE_COLUMNS].fillna(medians)
        probs = model.predict_proba(X_test)[:, 1]
        for prob, (_, row) in zip(probs, test_df.iterrows()):
            out_rows.append({"game_pk": row.get("game_pk"), "home_win": row["home_win"], "prob": prob})
    return pd.DataFrame(out_rows)


def main():
    df = pd.read_parquet(TRAINING_CACHE)
    print(f"Loaded {len(df)} historical games.\n")

    preds = walk_forward_predictions(df)
    probs = preds["prob"].values
    outcomes = preds["home_win"].astype(int).values

    print(f"=== Model A (baseball-only, what's actually served) — {len(preds)} walk-forward predictions ===")
    print(f"Brier score: {brier_score_loss(outcomes, probs):.4f}")
    print(f"Log loss:    {log_loss(outcomes, probs):.4f}")
    print(f"AUC:         {roc_auc_score(outcomes, probs):.4f}")
    print(f"ECE:         {expected_calibration_error(probs, outcomes):.4f}")

    if os.path.exists(ODDS_CACHE):
        odds_df = pd.read_parquet(ODDS_CACHE)
        market_prob_by_game = dict(zip(odds_df["game_pk"], odds_df["market_home_prob"]))
        preds = preds.copy()
        preds["market_prob"] = preds["game_pk"].map(market_prob_by_game)
        matched = preds.dropna(subset=["market_prob"])
        print(f"\n=== CLV / ROI vs. Pinnacle closing line ({len(matched)}/{len(preds)} games matched) ===")
        market_brier = brier_score_loss(matched["home_win"].astype(int), matched["market_prob"])
        model_brier = brier_score_loss(matched["home_win"].astype(int), matched["prob"])
        print(f"Model Brier:  {model_brier:.4f}")
        print(f"Market Brier: {market_brier:.4f}")
        matched = matched.copy()
        matched["edge"] = matched["prob"] - matched["market_prob"]
        for threshold in (0.0, 0.05, 0.10, 0.15):
            subset = matched[matched["edge"].abs() >= threshold]
            if len(subset) < 10:
                continue
            picked_home = subset["prob"] >= 0.5
            model_correct = (picked_home == subset["home_win"].astype(bool)).mean()
            market_pick_home = subset["market_prob"] >= 0.5
            market_correct = (market_pick_home == subset["home_win"].astype(bool)).mean()

            def payout(row):
                picked = row["prob"] >= 0.5
                won = picked == bool(row["home_win"])
                price = row["market_prob"] if picked else (1 - row["market_prob"])
                if not won:
                    return -1.0
                return (1 / price) - 1 if price > 0 else 0.0

            roi = subset.apply(payout, axis=1).mean()
            print(f"|edge| >= {threshold:.2f} ({len(subset)} games): model correct {model_correct:.1%}, "
                  f"market favorite correct {market_correct:.1%}, flat-stake ROI {roi:+.1%}")
    else:
        print(f"\nNo {ODDS_CACHE} found — skipping CLV/ROI.")

    # Feature importance off the actual final trained (full-data) model, not a fold model —
    # this is what's really being served.
    print("\n=== Feature importance (XGBoost gain, final trained Model A) ===")
    m, medians, metrics = model_module.load_model(model_module.BASELINE_MODEL_PATH)
    booster = m.calibrated_classifiers_[0].estimator
    importances = booster.feature_importances_
    imp_df = pd.DataFrame({"feature": BASEBALL_ONLY_FEATURE_COLUMNS, "importance": importances})
    imp_df = imp_df.sort_values("importance", ascending=False).reset_index(drop=True)
    imp_df["rank"] = imp_df.index + 1
    print(imp_df.head(20).to_string(index=False))

    print("\n--- Specifically: xera_diff / xfip_diff / siera_diff ---")
    for feat in ("xera_diff", "xfip_diff", "siera_diff"):
        row = imp_df[imp_df["feature"] == feat]
        if not row.empty:
            print(f"{feat}: rank {row.iloc[0]['rank']}/{len(imp_df)}, importance {row.iloc[0]['importance']:.4f}")


if __name__ == "__main__":
    main()
