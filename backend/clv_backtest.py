"""
clv_backtest.py

Compares this model's out-of-sample (walk-forward) predictions against
OpticOdds closing lines — the standard sports-betting validation: if a
model can't beat de-vigged closing lines from a sharp book (Pinnacle),
it doesn't have real market edge, however good its Brier score looks in
isolation against actual outcomes alone.

Two separate questions, easy to conflate:
  - Backtest Brier/AUC: is the model calibrated and better than a coin flip?
  - CLV here: does the model know something the market's closing price
    doesn't already know? A model can pass the first and fail the second
    (most public models do — the market is hard to beat).

Rate-limited: OpticOdds historical odds endpoint allows ~10 req/15s, so
this takes a while for a meaningful sample. Scoped to the most recent
--limit games by default to keep runtime bounded; the full training set
would take over an hour.

Run directly:
    python clv_backtest.py --limit 500
"""

import argparse
import os
import time
import requests
import pandas as pd
import numpy as np
from dotenv import load_dotenv

from model import train
from features import FEATURE_COLUMNS
from build_training_data import TRAINING_CACHE
from odds_fetcher import (
    _fetch_fixture_map, _fetch_closing_line, CLOSING_BOOK, HISTORICAL_RATE_LIMIT_SLEEP, OPTICODDS_API_KEY,
)

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def walk_forward_predictions(df: pd.DataFrame, n_folds: int = 5) -> pd.DataFrame:
    """
    Same walk-forward fold structure as model.backtest(), but returns a
    per-game prediction for every row in each fold's held-out test slice
    (not just aggregate fold metrics) — needed to join a specific
    prediction to a specific game's closing line.
    """
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
        model, medians, _ = train(train_df, save=False)
        X_test = test_df[FEATURE_COLUMNS].fillna(medians)
        probs = model.predict_proba(X_test)[:, 1]
        for prob, (_, row) in zip(probs, test_df.iterrows()):
            out_rows.append({
                "game_date": row["game_date"], "home_team": row["home_team"], "away_team": row["away_team"],
                "game_pk": row.get("game_pk"), "home_win": row["home_win"], "model_home_win_prob": prob,
            })
    return pd.DataFrame(out_rows)


def _devig(home_odds, away_odds):
    def implied(odds):
        return 100 / (odds + 100) if odds > 0 else -odds / (-odds + 100)
    ph, pa = implied(home_odds), implied(away_odds)
    return ph / (ph + pa)


def main(limit: int):
    if not OPTICODDS_API_KEY:
        print("No OPTICODDS_API_KEY configured — set it in backend/.env")
        return

    df = pd.read_parquet(TRAINING_CACHE)
    if "home_team" not in df.columns:
        print("training_dataset.parquet is missing home_team/away_team/game_pk — "
              "rebuild it first (python build_training_data.py) with the current code.")
        return

    print(f"Generating walk-forward out-of-sample predictions for {len(df)} games...")
    preds = walk_forward_predictions(df)
    preds = preds.sort_values("game_date", ascending=False).head(limit).reset_index(drop=True)
    print(f"Using the most recent {len(preds)} out-of-sample predictions.\n")

    start_date = preds["game_date"].min()
    end_date = (pd.Timestamp(preds["game_date"].max()) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"Fetching OpticOdds fixture list for {start_date}..{end_date}...")
    fixture_map = _fetch_fixture_map(start_date, end_date)
    print(f"Found {len(fixture_map)} indexed fixtures.\n")

    print(f"Pulling {CLOSING_BOOK} closing lines (rate-limited, ~{HISTORICAL_RATE_LIMIT_SLEEP}s/game)...")
    rows = []
    for i, row in preds.iterrows():
        if i % 25 == 0:
            print(f"  ...{i}/{len(preds)}")
        fixture_id = fixture_map.get((row["game_date"], row["home_team"], row["away_team"]))
        if fixture_id is None:
            continue
        closing = _fetch_closing_line(fixture_id)
        time.sleep(HISTORICAL_RATE_LIMIT_SLEEP)
        if not closing:
            continue
        market_home_prob = _devig(closing["home"], closing["away"])
        rows.append({
            **row.to_dict(),
            "market_home_win_prob": market_home_prob,
        })

    matched = pd.DataFrame(rows)
    print(f"\nMatched {len(matched)}/{len(preds)} predictions to a {CLOSING_BOOK} closing line.\n")
    if matched.empty:
        print("No matches — can't compute CLV comparison.")
        return

    model_brier = float(np.mean((matched["model_home_win_prob"] - matched["home_win"]) ** 2))
    market_brier = float(np.mean((matched["market_home_win_prob"] - matched["home_win"]) ** 2))
    print(f"Model Brier vs actual outcomes:  {model_brier:.4f}")
    print(f"Market (closing line) Brier:     {market_brier:.4f}")
    print(f"{'Model beats the closing line.' if model_brier < market_brier else 'Market still beats the model.'}\n")

    # Edge-detection: when the model disagrees with the market by a wide
    # margin, does it call the outcome better than the market did?
    matched["edge"] = matched["model_home_win_prob"] - matched["market_home_win_prob"]
    for threshold in (0.05, 0.10, 0.15):
        subset = matched[matched["edge"].abs() >= threshold]
        if len(subset) < 10:
            continue
        model_pick_home = subset["model_home_win_prob"] >= 0.5
        model_correct = (model_pick_home == subset["home_win"].astype(bool)).mean()
        market_pick_home = subset["market_home_win_prob"] >= 0.5
        market_correct = (market_pick_home == subset["home_win"].astype(bool)).mean()
        print(
            f"|edge| >= {threshold:.2f} ({len(subset)} games): "
            f"model correct {model_correct:.1%}, market's favorite correct {market_correct:.1%}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=500, help="Number of most recent games to check (rate-limited pull)")
    args = parser.parse_args()
    main(args.limit)
