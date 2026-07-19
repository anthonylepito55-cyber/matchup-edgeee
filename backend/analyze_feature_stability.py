"""
analyze_feature_stability.py

Multi-seed stability study for a single candidate-for-pruning feature (default: game_wind_mph),
per your framework: don't act on one training run's feature importance — repeat across several
random seeds, record rank/gain/permutation/SHAP importance each time, AND run a paired
with-vs-without comparison (same seed, same fold, same everything else) so the with/without
Brier/AUC/ECE/ROI delta isn't confounded by run-to-run noise.

Methodology per seed:
  - Same 5-fold chronological walk-forward split as everywhere else in this app (model.py,
    clv_backtest.py, analyze_*.py) — train on earlier folds, predict on the next held-out slice.
  - Two variants trained on the EXACT same folds/seed: "with" (full BASEBALL_ONLY_FEATURE_COLUMNS)
    and "without" (same list minus TARGET_FEATURE) — isolates the target feature's effect from
    everything else that also varies seed to seed.
  - model.train()'s new random_state param (added for this script) seeds both the train/val split
    AND XGBoost's own row/column subsampling (subsample=0.8/colsample_bytree=0.8 in
    DEFAULT_XGB_PARAMS), so different seeds really do produce different models, not just different
    splits of the same model.

Per (seed, fold), for the "with" variant only: gain-based rank (avg across the internal
CalibratedClassifierCV boosters), permutation importance (shuffle TARGET_FEATURE within that
fold's held-out set, Brier degradation), and mean |SHAP value| (TreeExplainer on the same
boosters). Aggregated into mean/std across all seed*fold runs, plus "% of runs in the bottom N
features" as the effectively-unused check.

Run directly:
    python analyze_feature_stability.py [--feature game_wind_mph] [--seeds 8]
"""

import argparse
import numpy as np
import pandas as pd
import shap
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

import model as model_module
from features import BASEBALL_ONLY_FEATURE_COLUMNS
from build_training_data import TRAINING_CACHE
from data_collection import CACHE_DIR
import os

ODDS_CACHE = os.path.join(CACHE_DIR, "historical_market_probs.parquet")
N_FOLDS = 5
PERM_SHUFFLES = 20
BOTTOM_N = 5  # "effectively unused" threshold: rank in the bottom BOTTOM_N features


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


def walk_forward_run(df: pd.DataFrame, feature_columns: list, seed: int, target_feature: str = None):
    """Runs one seeded walk-forward backtest. If target_feature is given (must be in
    feature_columns), also returns per-fold (rank, gain, perm_importance, mean_abs_shap) for it."""
    fold_size = len(df) // (N_FOLDS + 1)
    all_probs, all_outcomes, all_game_pk = [], [], []
    target_stats = []

    for fold in range(1, N_FOLDS + 1):
        train_end = fold_size * fold
        test_end = fold_size * (fold + 1)
        train_df = df.iloc[:train_end]
        test_df = df.iloc[train_end:test_end]
        if len(train_df) < 50 or len(test_df) < 10:
            continue

        model_obj, medians, _ = model_module.train(
            train_df, save=False, feature_columns=feature_columns, random_state=seed
        )
        X_test = test_df[feature_columns].fillna(medians)
        probs = model_obj.predict_proba(X_test)[:, 1]
        all_probs.extend(probs)
        all_outcomes.extend(test_df["home_win"].astype(int).tolist())
        all_game_pk.extend(test_df["game_pk"].tolist())

        if target_feature is not None:
            boosters = [cc.estimator for cc in model_obj.calibrated_classifiers_]
            gain_matrix = np.array([b.feature_importances_ for b in boosters])
            avg_gain = gain_matrix.mean(axis=0)
            order = np.argsort(-avg_gain)
            target_idx = feature_columns.index(target_feature)
            rank = int(np.where(order == target_idx)[0][0]) + 1
            gain = float(avg_gain[target_idx])

            # Permutation importance: shuffle target_feature within this fold's held-out set.
            base_brier = brier_score_loss(test_df["home_win"].astype(int), probs)
            degradations = []
            rng = np.random.default_rng(seed * 1000 + fold)
            for _ in range(PERM_SHUFFLES):
                X_perm = X_test.copy()
                X_perm[target_feature] = rng.permutation(X_perm[target_feature].values)
                perm_probs = model_obj.predict_proba(X_perm)[:, 1]
                degradations.append(brier_score_loss(test_df["home_win"].astype(int), perm_probs) - base_brier)
            perm_importance = float(np.mean(degradations))

            # SHAP: mean |value| across the same internal boosters.
            shap_vals = []
            for b in boosters:
                explainer = shap.TreeExplainer(b)
                shap_vals.append(explainer.shap_values(X_test))
            avg_shap = np.mean(shap_vals, axis=0)
            mean_abs_shap = float(np.mean(np.abs(avg_shap[:, target_idx])))

            target_stats.append({
                "seed": seed, "fold": fold, "rank": rank, "gain": gain,
                "perm_importance": perm_importance, "mean_abs_shap": mean_abs_shap,
                "n_features": len(feature_columns),
            })

    return pd.DataFrame({"prob": all_probs, "home_win": all_outcomes, "game_pk": all_game_pk}), target_stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature", default="game_wind_mph")
    parser.add_argument("--seeds", type=int, default=8)
    args = parser.parse_args()

    target_feature = args.feature
    n_seeds = args.seeds
    seeds = list(range(1, n_seeds + 1))  # 1..n_seeds, distinct from the default 42 used everywhere else

    df = pd.read_parquet(TRAINING_CACHE).sort_values("game_date").reset_index(drop=True)
    with_cols = list(BASEBALL_ONLY_FEATURE_COLUMNS)
    without_cols = [c for c in BASEBALL_ONLY_FEATURE_COLUMNS if c != target_feature]
    print(f"Target feature: {target_feature}")
    print(f"Loaded {len(df)} historical games. Running {n_seeds} seeds x 5 folds x 2 variants "
          f"(with/without {target_feature}).\n")

    odds_df = pd.read_parquet(ODDS_CACHE) if os.path.exists(ODDS_CACHE) else None
    market_prob_by_game = dict(zip(odds_df["game_pk"], odds_df["market_home_prob"])) if odds_df is not None else {}

    all_target_stats = []
    paired_rows = []

    for seed in seeds:
        with_preds, target_stats = walk_forward_run(df, with_cols, seed, target_feature=target_feature)
        without_preds, _ = walk_forward_run(df, without_cols, seed, target_feature=None)
        all_target_stats.extend(target_stats)

        def summarize(preds):
            probs = preds["prob"].values
            outcomes = preds["home_win"].values
            row = {
                "brier": brier_score_loss(outcomes, probs),
                "log_loss": log_loss(outcomes, probs),
                "auc": roc_auc_score(outcomes, probs),
                "ece": expected_calibration_error(probs, outcomes),
            }
            mkt = preds.copy()
            mkt["market_prob"] = mkt["game_pk"].map(market_prob_by_game)
            matched = mkt.dropna(subset=["market_prob"])
            matched = matched[(matched["prob"] - matched["market_prob"]).abs() >= 0.10]
            if len(matched) >= 10:
                picked_home = matched["prob"] >= 0.5
                won = picked_home == matched["home_win"].astype(bool)
                price = np.where(picked_home, matched["market_prob"], 1 - matched["market_prob"])
                payout = np.where(won, np.where(price > 0, (1 / price) - 1, 0.0), -1.0)
                row["roi_edge10"] = float(np.mean(payout))
                row["roi_edge10_n"] = len(matched)
            else:
                row["roi_edge10"] = np.nan
                row["roi_edge10_n"] = len(matched)
            return row

        with_summary = summarize(with_preds)
        without_summary = summarize(without_preds)
        paired_rows.append({"seed": seed, **{f"with_{k}": v for k, v in with_summary.items()},
                             **{f"without_{k}": v for k, v in without_summary.items()}})
        print(f"Seed {seed}: with Brier {with_summary['brier']:.4f} AUC {with_summary['auc']:.4f} | "
              f"without Brier {without_summary['brier']:.4f} AUC {without_summary['auc']:.4f}")

    stats_df = pd.DataFrame(all_target_stats)
    print(f"\n=== {target_feature}: importance across {len(stats_df)} (seed x fold) runs ===")
    print(f"Rank:               mean {stats_df['rank'].mean():.1f} / {stats_df['n_features'].iloc[0]}, "
          f"std {stats_df['rank'].std():.1f}, min {stats_df['rank'].min()}, max {stats_df['rank'].max()}")
    print(f"Gain importance:    mean {stats_df['gain'].mean():.5f}, std {stats_df['gain'].std():.5f}")
    print(f"Perm importance:    mean {stats_df['perm_importance'].mean():.6f}, "
          f"std {stats_df['perm_importance'].std():.6f}, "
          f"% negative (shuffling helped): {(stats_df['perm_importance'] < 0).mean():.0%}")
    print(f"Mean |SHAP|:        mean {stats_df['mean_abs_shap'].mean():.5f}, std {stats_df['mean_abs_shap'].std():.5f}")
    n_features = stats_df['n_features'].iloc[0]
    pct_bottom = (stats_df['rank'] > n_features - BOTTOM_N).mean()
    print(f"% of runs in bottom {BOTTOM_N}/{n_features} features: {pct_bottom:.0%}")

    paired_df = pd.DataFrame(paired_rows)
    print(f"\n=== Paired with-vs-without comparison ({n_seeds} seeds, same seed/fold both sides) ===")
    for metric in ("brier", "log_loss", "auc", "ece"):
        deltas = paired_df[f"with_{metric}"] - paired_df[f"without_{metric}"]
        favors_with = (deltas < 0).sum() if metric != "auc" else (deltas > 0).sum()
        print(f"{metric:10s}: with {paired_df[f'with_{metric}'].mean():.4f} vs without "
              f"{paired_df[f'without_{metric}'].mean():.4f} | mean delta (with-without) "
              f"{deltas.mean():+.5f}, seeds favoring 'with': {favors_with}/{n_seeds}")
    roi_with = paired_df["with_roi_edge10"].dropna()
    roi_without = paired_df["without_roi_edge10"].dropna()
    print(f"roi_edge10: with mean {roi_with.mean():+.1%} (n_seeds={len(roi_with)}) vs "
          f"without mean {roi_without.mean():+.1%} (n_seeds={len(roi_without)})")

    print(f"\n=== Verdict ===")
    print(f"{target_feature} sits at rank {stats_df['rank'].mean():.0f}/{n_features} on average "
          f"({pct_bottom:.0%} of runs in the bottom {BOTTOM_N}), "
          f"perm importance mean {stats_df['perm_importance'].mean():.6f} "
          f"({(stats_df['perm_importance'] < 0).mean():.0%} of runs negative). "
          f"Removing it changes Brier by {(paired_df['with_brier'] - paired_df['without_brier']).mean():+.5f} "
          f"and AUC by {(paired_df['with_auc'] - paired_df['without_auc']).mean():+.5f} on average.")


if __name__ == "__main__":
    main()
