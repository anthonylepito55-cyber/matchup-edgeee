"""
compute_clv_backtest_cache.py

Precomputes the historical walk-forward CLV backtest (Model A vs Pinnacle closing lines) into a
small JSON cache the live app can read instantly -- the actual backtest retrains the model 5
times over ~6,600 games and takes a couple minutes, far too slow to run inside a request. Same
methodology/bucket thresholds as analyze_model_a_clv.py and prediction_log.get_clv_track_record's
CLV_EDGE_BUCKETS, so the two are directly comparable in the UI.

Not wired into daily_retrain.py (yet) -- the model and the odds-backfill cache both change slowly
enough that this only needs an occasional manual re-run, not a nightly one. Run directly:
    python compute_clv_backtest_cache.py
"""
import json
import os

import numpy as np
import pandas as pd

from model import train
from features import BASEBALL_ONLY_FEATURE_COLUMNS
from build_training_data import TRAINING_CACHE
from data_collection import CACHE_DIR
from prediction_log import CLV_EDGE_BUCKETS

ODDS_CACHE = os.path.join(CACHE_DIR, "historical_market_probs.parquet")
# model_artifacts/, not data_cache/ -- data_cache/ is gitignored (Railway never sees it), while
# model_artifacts/ is deliberately committed (see prediction_log.CLV_BACKTEST_CACHE_PATH).
OUT_PATH = os.path.join(os.path.dirname(__file__), "model_artifacts", "clv_backtest_summary.json")


def walk_forward_predictions(df: pd.DataFrame, n_folds: int = 5) -> pd.DataFrame:
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
        model, medians, _ = train(train_df, save=False, feature_columns=BASEBALL_ONLY_FEATURE_COLUMNS)
        X_test = test_df[BASEBALL_ONLY_FEATURE_COLUMNS].fillna(medians)
        probs = model.predict_proba(X_test)[:, 1]
        for prob, (_, row) in zip(probs, test_df.iterrows()):
            out_rows.append({"game_pk": row["game_pk"], "home_win": row["home_win"], "model_home_win_prob": prob})
    return pd.DataFrame(out_rows)


def main():
    if not os.path.exists(ODDS_CACHE):
        print(f"No {ODDS_CACHE} -- run backfill_historical_odds.py first.")
        return
    odds_df = pd.read_parquet(ODDS_CACHE)
    market_prob_by_game = dict(zip(odds_df["game_pk"], odds_df["market_home_prob"]))

    df = pd.read_parquet(TRAINING_CACHE)
    print(f"Generating walk-forward predictions for {len(df)} games...")
    preds = walk_forward_predictions(df)
    preds["market_home_prob"] = preds["game_pk"].map(market_prob_by_game)
    matched = preds.dropna(subset=["market_home_prob"]).copy()
    print(f"Matched {len(matched)} games to a Pinnacle closing line.")

    matched["edge"] = matched["model_home_win_prob"] - matched["market_home_prob"]
    buckets = []
    for threshold in CLV_EDGE_BUCKETS:
        sub = matched[matched["edge"].abs() >= threshold]
        n = len(sub)
        if n == 0:
            buckets.append({"threshold": threshold, "games": 0, "correct": 0, "accuracy": None})
            continue
        model_pick_home = sub["model_home_win_prob"] >= 0.5
        correct = int((model_pick_home == sub["home_win"].astype(bool)).sum())
        buckets.append({"threshold": threshold, "games": n, "correct": correct, "accuracy": round(correct / n, 4)})
        print(f"  |edge|>={threshold:.2f}: {n} games, {correct}/{n} = {correct/n*100:.1f}%")

    game_dates = pd.read_parquet(TRAINING_CACHE)[["game_pk", "game_date"]].drop_duplicates("game_pk")
    matched_dates = matched.merge(game_dates, on="game_pk", how="left")
    summary = {
        "total": len(matched),
        "buckets": buckets,
        "date_range": [str(matched_dates["game_date"].min())[:10], str(matched_dates["game_date"].max())[:10]],
        "computed_at": pd.Timestamp.now().isoformat(),
    }
    with open(OUT_PATH, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
