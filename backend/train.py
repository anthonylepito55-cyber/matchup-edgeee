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

import json
import pandas as pd
from datetime import datetime, timezone
from data_collection import CACHE_DIR
import os
import model as model_module
import props as props_module
import rating_system
from features import (
    FEATURE_COLUMNS, BASEBALL_ONLY_FEATURE_COLUMNS, MODEL_C_FEATURE_COLUMNS,
    STRIKEOUT_FEATURE_COLUMNS, STRIKEOUT_BASEBALL_ONLY_FEATURE_COLUMNS,
    IP_FEATURE_COLUMNS, IP_BASEBALL_ONLY_FEATURE_COLUMNS,
    ER_FEATURE_COLUMNS, ER_BASEBALL_ONLY_FEATURE_COLUMNS,
)

TRAINING_CACHE = os.path.join(CACHE_DIR, "training_dataset.parquet")
STRIKEOUT_TRAINING_CACHE = os.path.join(CACHE_DIR, "strikeout_training_dataset.parquet")
# Snapshot of every backtest metric from the most recent train.py run, keyed by model name —
# lets daily_retrain.py compare a freshly-trained candidate against whatever's ACTUALLY currently
# deployed (this file only gets overwritten when a candidate is deployed, see daily_retrain.py)
# without needing to re-run a backtest against the old model files just to get a comparison point.
METRICS_PATH = os.path.join(os.path.dirname(model_module.MODEL_PATH), "metrics.json")


def main():
    if not os.path.exists(TRAINING_CACHE):
        raise FileNotFoundError(
            f"No training data at {TRAINING_CACHE}. Run build_training_data.py first:\n"
            f"  python build_training_data.py --seasons 2025 2026"
        )

    df = pd.read_parquet(TRAINING_CACHE)
    print(f"Loaded {len(df)} historical games.")
    metrics_snapshot = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "win_prob_games": len(df),
    }

    # Model B trained/backtested as a 5-seed ENSEMBLE too, same reasoning/discipline as Model A
    # and Model C -- found live 2026-08-19 that Model B has the SAME single-seed decision-stump
    # fragility: consensus_prob_diff's contribution for the identical real feature value ranged
    # +0.0021 to +0.1772 across 5 seeds (83x) on a live LAA@HOU game whose own 4 tracked books all
    # agreed within a point of each other (~59%) -- production (seed=42) landed near the high end,
    # serving 69% against a market that was really ~59-62%. This isn't cosmetic: _compute_value_bet
    # (the VALUE badge) is built specifically on Model B, so this fragility could flip/mis-flag
    # value bets on seed noise rather than real signal. Validated via backtest_ensemble before
    # switching: AUC -0.0004, Brier -0.0001 -- same wash band as Model A/C's own validations.
    print("\n--- Walk-forward backtest: Model B (baseball + market features, full FEATURE_COLUMNS, 5-seed ensemble) ---")
    backtest_results = model_module.backtest_ensemble(df, feature_columns=FEATURE_COLUMNS)
    print(f"Avg Brier score: {backtest_results['avg_brier_score']:.4f}")
    print(f"Avg log loss:    {backtest_results['avg_log_loss']:.4f}")
    print(f"Avg AUC:         {backtest_results['avg_auc']:.4f}")

    # Model A trained/backtested as a 5-seed ENSEMBLE (train_ensemble/predict_proba_ensemble),
    # not a single train() call -- found live 2026-08-18 that Model A has the SAME single-seed
    # decision-stump threshold fragility already fixed for Model C (confirmed via a 15-game SHAP
    # scan hitting identical plateau contribution values for opp_platoon_woba_diff/bullpen_fip_diff/
    # defense_oaa_diff across unrelated games). Model A is the PRIMARY served prediction, so this
    # matters more here than it did for Model C. Validated via backtest_ensemble before switching:
    # AUC -0.0021, Brier ~0.0000 vs single-seed -- within the same noise band as Model C's own
    # wash validation, so ensembling was NOT expected (or required) to improve aggregate accuracy,
    # only per-game stability.
    print("\n--- Walk-forward backtest: Model A (baseball-only, market features excluded, 5-seed ensemble) ---")
    baseline_backtest_results = model_module.backtest_ensemble(df, feature_columns=BASEBALL_ONLY_FEATURE_COLUMNS)
    print(f"Avg Brier score: {baseline_backtest_results['avg_brier_score']:.4f}")
    print(f"Avg log loss:    {baseline_backtest_results['avg_log_loss']:.4f}")
    print(f"Avg AUC:         {baseline_backtest_results['avg_auc']:.4f}")

    print(f"\nA vs B delta — AUC: {backtest_results['avg_auc'] - baseline_backtest_results['avg_auc']:+.4f}, "
          f"Brier: {backtest_results['avg_brier_score'] - baseline_backtest_results['avg_brier_score']:+.4f} "
          f"(negative Brier delta = B better). A large A>B gap means the market features are doing real "
          f"work beyond baseball signal alone — which also means Model B can't be trusted to find value "
          f"against that same market. See {backtest_results['note']}")

    # win_prob_a is the gating metric daily_retrain.py checks — Model A (baseball-only) is the
    # PRIMARY served prediction (see main.py), so it's the one that must not regress. Model B's
    # numbers are recorded too, purely for visibility/the A-vs-B delta printed above.
    metrics_snapshot["win_prob_a"] = {
        "auc": baseline_backtest_results["avg_auc"], "brier": baseline_backtest_results["avg_brier_score"],
        "log_loss": baseline_backtest_results["avg_log_loss"],
    }
    metrics_snapshot["win_prob_b"] = {
        "auc": backtest_results["avg_auc"], "brier": backtest_results["avg_brier_score"],
        "log_loss": backtest_results["avg_log_loss"],
    }

    print("\n--- Training final Model B ensemble (full feature set, 5 seeds) ---")
    _, _, metrics = model_module.train_ensemble(df, feature_columns=FEATURE_COLUMNS, model_path=model_module.MODEL_PATH)
    print(f"Validation Brier: {metrics['brier_score']:.4f}")
    print(f"Validation AUC:   {metrics['auc']:.4f}")
    print(f"Model saved to model_artifacts/xgb_model.joblib ({metrics['n_seeds']}-seed ensemble)")

    print("\n--- Training final Model A ensemble (baseball-only, 5 seeds) ---")
    _, _, baseline_metrics = model_module.train_ensemble(
        df, feature_columns=BASEBALL_ONLY_FEATURE_COLUMNS, model_path=model_module.BASELINE_MODEL_PATH
    )
    print(f"Validation Brier: {baseline_metrics['brier_score']:.4f}")
    print(f"Validation AUC:   {baseline_metrics['auc']:.4f}")
    print(f"Model saved to model_artifacts/xgb_model_baseline.joblib ({baseline_metrics['n_seeds']}-seed ensemble)")

    # Model C: same architecture, market block sourced from a continuously-polled 6-book panel
    # (FanDuel/Pinnacle/LowVig/Betcris/Circa Sports/Kalshi) instead of Model B's 5-book
    # CONSENSUS_BOOKS -- see odds_fetcher.get_model_c_snapshot and MODEL_C_FEATURE_COLUMNS.
    # Walk-forward validated (build_and_train_model_c.py) as statistically tied with Model B on
    # AUC/Brier, not a proven accuracy edge -- served for its architecture (real-time tracking,
    # the single-book-leak guards Model B doesn't have), not because it backtests better. Only
    # trained/gated here if the merged model_c_* columns actually exist on this training set (a
    # fresh build_training_data.py run always produces them now, but an older cached
    # training_dataset.parquet predating this integration wouldn't have them yet).
    #
    # Trained as a 5-seed ENSEMBLE (train_ensemble/predict_proba_ensemble), not a single train()
    # call -- found live 2026-08-18 that a single fixed seed can give one feature's learned
    # decision-stump threshold a wildly non-representative weight for a specific real matchup
    # (opp_platoon_woba_diff contributed 0.325 under seed 42 vs an average of ~0.204 across 5
    # seeds on the same real game -- nearly 3x the lowest of the 5). Validated via
    # backtest_ensemble before switching: aggregate AUC/Brier are an effective wash vs the
    # single-seed backtest (-0.0005 AUC, -0.0001 Brier -- both within noise), which is the
    # expected result -- ensembling reduces PER-GAME variance/instability, not aggregate
    # discrimination, so a wash here was the bar to clear, not an improvement.
    if "model_c_consensus_prob_diff" in df.columns:
        print("\n--- Walk-forward backtest: Model C (6-book real-time-tracked market features, 5-seed ensemble) ---")
        model_c_backtest_results = model_module.backtest_ensemble(df, feature_columns=MODEL_C_FEATURE_COLUMNS)
        print(f"Avg Brier score: {model_c_backtest_results['avg_brier_score']:.4f}")
        print(f"Avg log loss:    {model_c_backtest_results['avg_log_loss']:.4f}")
        print(f"Avg AUC:         {model_c_backtest_results['avg_auc']:.4f}")
        metrics_snapshot["win_prob_c"] = {
            "auc": model_c_backtest_results["avg_auc"], "brier": model_c_backtest_results["avg_brier_score"],
            "log_loss": model_c_backtest_results["avg_log_loss"],
        }

        print("\n--- Training final Model C ensemble (6-book real-time market features, 5 seeds) ---")
        _, _, model_c_metrics = model_module.train_ensemble(
            df, feature_columns=MODEL_C_FEATURE_COLUMNS, model_path=model_module.MODEL_C_PATH
        )
        print(f"Validation Brier: {model_c_metrics['brier_score']:.4f}")
        print(f"Validation AUC:   {model_c_metrics['auc']:.4f}")
        print(f"Model saved to model_artifacts/model_c.joblib ({model_c_metrics['n_seeds']}-seed ensemble)")
    else:
        print("\nSkipping Model C -- training_dataset.parquet predates the model_c_* columns "
              "(re-run build_training_data.py to pick them up).")

    print("\n--- Rating system: walk-forward backtest (display-only, see rating_system.py) ---")
    rating_backtest = rating_system.backtest_rating_system(df)
    print(f"Avg Brier score: {rating_backtest['avg_brier_score']:.4f}")
    print(f"Avg AUC:         {rating_backtest['avg_auc']:.4f}")
    rating_system.fit_and_save_rating_system(df)
    print("Fitted rating system saved to model_artifacts/rating_system.joblib")

    if os.path.exists(STRIKEOUT_TRAINING_CACHE):
        k_df = pd.read_parquet(STRIKEOUT_TRAINING_CACHE)
        print(f"\nLoaded {len(k_df)} historical pitcher outings for strikeout model.")
        metrics_snapshot["strikeout_games"] = len(k_df)

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

        # strikeout_a is the gating metric daily_retrain.py checks, same reasoning as win_prob_a
        # above — Model A (baseball-only) is the PRIMARY served strikeout number.
        metrics_snapshot["strikeout_a"] = {"mae": k_baseline_backtest["avg_mae"]}
        metrics_snapshot["strikeout_b"] = {"mae": k_backtest["avg_mae"]}

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

        # --- Innings pitched: same shape as strikeouts, but objective=reg:squarederror (IP is
        # continuous, not a count distribution — see props.train_strikeout_model's docstring) ---
        print("\n--- IP walk-forward backtest: Model B (baseball + market features) ---")
        ip_backtest = props_module.backtest_strikeout_model(
            k_df, label_col="innings_pitched", feature_columns=IP_FEATURE_COLUMNS, objective="reg:squarederror"
        )
        print(f"Avg MAE: {ip_backtest['avg_mae']:.3f} innings")

        print("\n--- IP walk-forward backtest: Model A (baseball-only) ---")
        ip_baseline_backtest = props_module.backtest_strikeout_model(
            k_df, label_col="innings_pitched", feature_columns=IP_BASEBALL_ONLY_FEATURE_COLUMNS,
            objective="reg:squarederror",
        )
        print(f"Avg MAE: {ip_baseline_backtest['avg_mae']:.3f} innings")

        print(f"\nIP A vs B delta — MAE: {ip_baseline_backtest['avg_mae'] - ip_backtest['avg_mae']:+.4f} "
              f"(positive = B better, i.e. baseball-only is worse).")

        # ip_a is the gating metric daily_retrain.py checks — same reasoning as strikeout_a above.
        metrics_snapshot["ip_a"] = {"mae": ip_baseline_backtest["avg_mae"]}
        metrics_snapshot["ip_b"] = {"mae": ip_backtest["avg_mae"]}

        print("\n--- Training final IP Model B (full feature set) ---")
        _, _, ip_metrics = props_module.train_strikeout_model(
            k_df, label_col="innings_pitched", feature_columns=IP_FEATURE_COLUMNS,
            model_path=props_module.IP_MODEL_PATH, objective="reg:squarederror",
        )
        print(f"Validation MAE: {ip_metrics['mae']:.3f} innings")
        print(f"Model saved to model_artifacts/ip_model.joblib")

        print("\n--- Training final IP Model A (baseball-only) ---")
        _, _, ip_baseline_metrics = props_module.train_strikeout_model(
            k_df, label_col="innings_pitched", feature_columns=IP_BASEBALL_ONLY_FEATURE_COLUMNS,
            model_path=props_module.IP_BASELINE_MODEL_PATH, objective="reg:squarederror",
        )
        print(f"Validation MAE: {ip_baseline_metrics['mae']:.3f} innings")
        print(f"Model saved to model_artifacts/ip_model_baseline.joblib")

        # --- Earned runs allowed: same shape/objective as strikeouts (count:poisson) ---
        print("\n--- ER walk-forward backtest: Model B (baseball + market features) ---")
        er_backtest = props_module.backtest_strikeout_model(
            k_df, label_col="earned_runs", feature_columns=ER_FEATURE_COLUMNS
        )
        print(f"Avg MAE: {er_backtest['avg_mae']:.3f} earned runs")

        print("\n--- ER walk-forward backtest: Model A (baseball-only) ---")
        er_baseline_backtest = props_module.backtest_strikeout_model(
            k_df, label_col="earned_runs", feature_columns=ER_BASEBALL_ONLY_FEATURE_COLUMNS
        )
        print(f"Avg MAE: {er_baseline_backtest['avg_mae']:.3f} earned runs")

        print(f"\nER A vs B delta — MAE: {er_baseline_backtest['avg_mae'] - er_backtest['avg_mae']:+.4f} "
              f"(positive = B better, i.e. baseball-only is worse).")

        metrics_snapshot["er_a"] = {"mae": er_baseline_backtest["avg_mae"]}
        metrics_snapshot["er_b"] = {"mae": er_backtest["avg_mae"]}

        print("\n--- Training final ER Model B (full feature set) ---")
        _, _, er_metrics = props_module.train_strikeout_model(
            k_df, label_col="earned_runs", feature_columns=ER_FEATURE_COLUMNS,
            model_path=props_module.ER_MODEL_PATH,
        )
        print(f"Validation MAE: {er_metrics['mae']:.3f} earned runs")
        print(f"Model saved to model_artifacts/er_model.joblib")

        print("\n--- Training final ER Model A (baseball-only) ---")
        _, _, er_baseline_metrics = props_module.train_strikeout_model(
            k_df, label_col="earned_runs", feature_columns=ER_BASEBALL_ONLY_FEATURE_COLUMNS,
            model_path=props_module.ER_BASELINE_MODEL_PATH,
        )
        print(f"Validation MAE: {er_baseline_metrics['mae']:.3f} earned runs")
        print(f"Model saved to model_artifacts/er_model_baseline.joblib")
    else:
        print(f"\nNo strikeout training data at {STRIKEOUT_TRAINING_CACHE} — skipping strikeout/IP/ER models.")

    metrics_snapshot["rating_system"] = {
        "auc": rating_backtest["avg_auc"], "brier": rating_backtest["avg_brier_score"],
    }
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics_snapshot, f, indent=2)
    print(f"\nMetrics snapshot written to {METRICS_PATH}")

    print("\nStart the API with: uvicorn main:app --reload --port 8000")
    return metrics_snapshot


if __name__ == "__main__":
    main()
