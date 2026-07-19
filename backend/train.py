"""
train.py

Run after build_training_data.py has produced data_cache/training_dataset.parquet
and data_cache/strikeout_training_dataset.parquet.

    python build_training_data.py --seasons 2025 2026
    python train.py

Trains both models (win-probability + strikeout-prop), saved to
model_artifacts/, and runs a walk-forward backtest for each so you can see
realistic performance before trusting any prediction.
"""

import pandas as pd
from data_collection import CACHE_DIR
import os
import model as model_module
import props as props_module
import rating_system
from features import (
    FEATURE_COLUMNS, BASEBALL_ONLY_FEATURE_COLUMNS,
    STRIKEOUT_FEATURE_COLUMNS, STRIKEOUT_BASEBALL_ONLY_FEATURE_COLUMNS,
)

TRAINING_CACHE = os.path.join(CACHE_DIR, "training_dataset.parquet")
STRIKEOUT_TRAINING_CACHE = os.path.join(CACHE_DIR, "strikeout_training_dataset.parquet")


def main():
    if not os.path.exists(TRAINING_CACHE):
        raise FileNotFoundError(
            f"No training data at {TRAINING_CACHE}. Run build_training_data.py first:\n"
            f"  python build_training_data.py --seasons 2025 2026"
        )

    df = pd.read_parquet(TRAINING_CACHE)
    print(f"Loaded {len(df)} historical games.")

    print("\n--- Walk-forward backtest: Model B (baseball + market features, full FEATURE_COLUMNS) ---")
    backtest_results = model_module.backtest(df, feature_columns=FEATURE_COLUMNS)
    print(f"Avg Brier score: {backtest_results['avg_brier_score']:.4f}")
    print(f"Avg log loss:    {backtest_results['avg_log_loss']:.4f}")
    print(f"Avg AUC:         {backtest_results['avg_auc']:.4f}")

    print("\n--- Walk-forward backtest: Model A (baseball-only, market features excluded) ---")
    baseline_backtest_results = model_module.backtest(df, feature_columns=BASEBALL_ONLY_FEATURE_COLUMNS)
    print(f"Avg Brier score: {baseline_backtest_results['avg_brier_score']:.4f}")
    print(f"Avg log loss:    {baseline_backtest_results['avg_log_loss']:.4f}")
    print(f"Avg AUC:         {baseline_backtest_results['avg_auc']:.4f}")

    print(f"\nA vs B delta — AUC: {backtest_results['avg_auc'] - baseline_backtest_results['avg_auc']:+.4f}, "
          f"Brier: {backtest_results['avg_brier_score'] - baseline_backtest_results['avg_brier_score']:+.4f} "
          f"(negative Brier delta = B better). A large A>B gap means the market features are doing real "
          f"work beyond baseball signal alone — which also means Model B can't be trusted to find value "
          f"against that same market. See {backtest_results['note']}")

    print("\n--- Training final Model B (full feature set) ---")
    _, _, metrics = model_module.train(df, feature_columns=FEATURE_COLUMNS, model_path=model_module.MODEL_PATH)
    print(f"Validation Brier: {metrics['brier_score']:.4f}")
    print(f"Validation AUC:   {metrics['auc']:.4f}")
    print(f"Model saved to model_artifacts/xgb_model.joblib")

    print("\n--- Training final Model A (baseball-only) ---")
    _, _, baseline_metrics = model_module.train(
        df, feature_columns=BASEBALL_ONLY_FEATURE_COLUMNS, model_path=model_module.BASELINE_MODEL_PATH
    )
    print(f"Validation Brier: {baseline_metrics['brier_score']:.4f}")
    print(f"Validation AUC:   {baseline_metrics['auc']:.4f}")
    print(f"Model saved to model_artifacts/xgb_model_baseline.joblib")

    print("\n--- Rating system: walk-forward backtest (display-only, see rating_system.py) ---")
    rating_backtest = rating_system.backtest_rating_system(df)
    print(f"Avg Brier score: {rating_backtest['avg_brier_score']:.4f}")
    print(f"Avg AUC:         {rating_backtest['avg_auc']:.4f}")
    rating_system.fit_and_save_rating_system(df)
    print("Fitted rating system saved to model_artifacts/rating_system.joblib")

    if os.path.exists(STRIKEOUT_TRAINING_CACHE):
        k_df = pd.read_parquet(STRIKEOUT_TRAINING_CACHE)
        print(f"\nLoaded {len(k_df)} historical pitcher outings for strikeout model.")

        print("\n--- Strikeout walk-forward backtest: Model B (baseball + player-prop market features) ---")
        k_backtest = props_module.backtest_strikeout_model(k_df, feature_columns=STRIKEOUT_FEATURE_COLUMNS)
        print(f"Avg MAE: {k_backtest['avg_mae']:.3f} strikeouts")

        print("\n--- Strikeout walk-forward backtest: Model A (baseball-only) ---")
        k_baseline_backtest = props_module.backtest_strikeout_model(
            k_df, feature_columns=STRIKEOUT_BASEBALL_ONLY_FEATURE_COLUMNS
        )
        print(f"Avg MAE: {k_baseline_backtest['avg_mae']:.3f} strikeouts")

        print(f"\nStrikeout A vs B delta — MAE: {k_baseline_backtest['avg_mae'] - k_backtest['avg_mae']:+.4f} "
              f"(positive = B better, i.e. baseball-only is worse). A large gap means the player-prop lines "
              f"are doing real work beyond baseball signal alone — same caveat as the win-prob model above: "
              f"Model B can't be trusted to find value against the same props it's partly copying. "
              f"{k_backtest['note']}")

        print("\n--- Training final strikeout Model B (full feature set) ---")
        _, _, k_metrics = props_module.train_strikeout_model(
            k_df, feature_columns=STRIKEOUT_FEATURE_COLUMNS, model_path=props_module.STRIKEOUT_MODEL_PATH
        )
        print(f"Validation MAE: {k_metrics['mae']:.3f} strikeouts")
        print(f"Model saved to model_artifacts/strikeout_model.joblib")

        print("\n--- Training final strikeout Model A (baseball-only) ---")
        _, _, k_baseline_metrics = props_module.train_strikeout_model(
            k_df, feature_columns=STRIKEOUT_BASEBALL_ONLY_FEATURE_COLUMNS,
            model_path=props_module.STRIKEOUT_BASELINE_MODEL_PATH,
        )
        print(f"Validation MAE: {k_baseline_metrics['mae']:.3f} strikeouts")
        print(f"Model saved to model_artifacts/strikeout_model_baseline.joblib")
    else:
        print(f"\nNo strikeout training data at {STRIKEOUT_TRAINING_CACHE} — skipping strikeout model.")

    print("\nStart the API with: uvicorn main:app --reload --port 8000")


if __name__ == "__main__":
    main()
