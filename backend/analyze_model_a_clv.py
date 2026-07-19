"""
analyze_model_a_clv.py

Does Model A (baseball-only — the model actually served as the primary prediction) show real
edge against the market's closing line, or is it just noise dressed up as a probability?

Same methodology as clv_backtest.py (walk-forward out-of-sample predictions vs. Pinnacle closing
line, Brier comparison + edge-detection at various disagreement thresholds), but with two
changes: (1) trains on BASEBALL_ONLY_FEATURE_COLUMNS instead of the full FEATURE_COLUMNS, since
that's what's actually served — clv_backtest.py never got updated after the Model A/B split
existed; (2) reads closing lines from the already-cached historical_market_probs.parquet instead
of making fresh OpticOdds calls, since a backfill is running concurrently and this shouldn't
compete with it for the shared rate limit — this means today's sample is whatever fraction of
the backfill has completed so far, not the full training set.

Run directly:
    python analyze_model_a_clv.py
"""

import os
import numpy as np
import pandas as pd

from model import train
from features import BASEBALL_ONLY_FEATURE_COLUMNS, FEATURE_COLUMNS
from build_training_data import TRAINING_CACHE
from data_collection import CACHE_DIR

ODDS_CACHE = os.path.join(CACHE_DIR, "historical_market_probs.parquet")


def walk_forward_predictions(df: pd.DataFrame, feature_columns: list, n_folds: int = 5) -> pd.DataFrame:
    df = df.sort_values("game_date").reset_index(drop=True)
    fold_size = len(df) // (n_folds + 1)
    out_rows = []
    for fold in range(1, n_folds + 1):
        train_end = fold_size * fold
        test_end = fold_size * (fold + 1)
        train_df = df.iloc[:train_end]
        test_df = df.iloc[train_end:test_end]
        if len(train_df) < 50 or len(test_df) < 10:
            continue
        model, medians, _ = train(train_df, save=False, feature_columns=feature_columns)
        X_test = test_df[feature_columns].fillna(medians)
        probs = model.predict_proba(X_test)[:, 1]
        for prob, (_, row) in zip(probs, test_df.iterrows()):
            out_rows.append({
                "game_date": row["game_date"], "game_pk": row.get("game_pk"),
                "home_win": row["home_win"], "model_home_win_prob": prob,
            })
    return pd.DataFrame(out_rows)


def report(matched: pd.DataFrame, label: str):
    print(f"\n=== {label} ({len(matched)} games with a closing line) ===")
    model_brier = float(np.mean((matched["model_home_win_prob"] - matched["home_win"]) ** 2))
    market_brier = float(np.mean((matched["market_home_win_prob"] - matched["home_win"]) ** 2))
    print(f"Model Brier vs actual outcomes:  {model_brier:.4f}")
    print(f"Market (Pinnacle closing) Brier: {market_brier:.4f}")
    print(f"{'Model beats the closing line.' if model_brier < market_brier else 'Market still beats the model.'}")

    matched = matched.copy()
    matched["edge"] = matched["model_home_win_prob"] - matched["market_home_win_prob"]
    for threshold in (0.0, 0.05, 0.10, 0.15):
        subset = matched[matched["edge"].abs() >= threshold]
        if len(subset) < 10:
            continue
        model_pick_home = subset["model_home_win_prob"] >= 0.5
        model_correct = (model_pick_home == subset["home_win"].astype(bool)).mean()
        market_pick_home = subset["market_home_win_prob"] >= 0.5
        market_correct = (market_pick_home == subset["home_win"].astype(bool)).mean()
        # Flat-stake "bet the model's favorite at the market's own closing price" ROI — the
        # actual test of whether disagreeing with the market here would have made money, not
        # just "was the pick technically correct" (favorites win more often by default).
        def payout(row):
            picked_home = row["model_home_win_prob"] >= 0.5
            won = picked_home == bool(row["home_win"])
            price_prob = row["market_home_win_prob"] if picked_home else (1 - row["market_home_win_prob"])
            if not won:
                return -1.0
            # de-vigged prob -> fair decimal odds as a stand-in for payout (no juice modeled)
            return (1 / price_prob) - 1 if price_prob > 0 else 0.0
        roi = subset.apply(payout, axis=1).mean()
        print(
            f"|edge| >= {threshold:.2f} ({len(subset)} games): "
            f"model correct {model_correct:.1%}, market's favorite correct {market_correct:.1%}, "
            f"flat-stake ROI betting model's pick at market price: {roi:+.1%}"
        )


def main():
    if not os.path.exists(ODDS_CACHE):
        print(f"No {ODDS_CACHE} found — run backfill_historical_odds.py first.")
        return
    odds_df = pd.read_parquet(ODDS_CACHE)
    market_prob_by_game = dict(zip(odds_df["game_pk"], odds_df["market_home_prob"]))
    n_with_odds = sum(1 for v in market_prob_by_game.values() if v is not None and pd.notna(v))
    print(f"Closing-line cache: {n_with_odds}/{len(odds_df)} games have a Pinnacle closing line "
          f"(backfill may still be running — this is whatever's done so far).\n")

    df = pd.read_parquet(TRAINING_CACHE)
    print(f"Loaded {len(df)} historical games for walk-forward predictions.")

    for label, feature_columns in [
        ("Model A (baseball-only, what's actually served)", BASEBALL_ONLY_FEATURE_COLUMNS),
        ("Model B (baseball + market features, for comparison)", FEATURE_COLUMNS),
    ]:
        print(f"\nGenerating walk-forward predictions using {len(feature_columns)} features...")
        preds = walk_forward_predictions(df, feature_columns)
        preds["market_home_win_prob"] = preds["game_pk"].map(market_prob_by_game)
        matched = preds.dropna(subset=["market_home_win_prob"])
        if matched.empty:
            print(f"No matches for {label} — can't compute CLV comparison.")
            continue
        report(matched, label)


if __name__ == "__main__":
    main()
