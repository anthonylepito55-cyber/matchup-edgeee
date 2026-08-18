"""
build_and_train_model_c.py

Computes Model C's historical market features from historical_market_probs.parquet (mirroring
odds_fetcher.get_model_c_snapshot's exact live-serving formulas, including its >=2-book minimum
and the sharp-vs-public-contrast-replaced-by-avg_movement redesign), merges them onto
TRAINING_CACHE, then trains + walk-forward backtests Model C against Model A/B using the same
methodology as train.py and check_model_b_calibration.py.

Model C's 6 tracked books map onto historical_market_probs.parquet's existing per-book columns:
  Pinnacle  -> market_home_prob / market_home_prob_open       (CLOSING_BOOK, already there)
  FanDuel   -> market_home_prob_fanduel / _open                (already there, CONSENSUS_BOOKS)
  Circa     -> market_home_prob_circa / _open                  (already there, CONSENSUS_BOOKS)
  Kalshi    -> market_home_prob_kalshi (current only)           (already there, PREDICTION_MARKET_BOOKS)
  LowVig    -> market_home_prob_lowvig / _open                  (backfill_model_c_books.py, new)
  Betcris   -> market_home_prob_betcris / _open                 (backfill_model_c_books.py, new)

team_total_diff/market_total_runs reuse the existing CONSENSUS_BOOKS-averaged totals columns as an
approximation -- a separate Model-C-specific totals backfill (5 books x totals panel) wasn't built
given time cost vs. likely benefit; totals coverage doesn't vary much by book set. Disclosed here,
not silently assumed.

Run directly: python build_and_train_model_c.py
"""
import os

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, brier_score_loss, log_loss

from model import train
from features import FEATURE_COLUMNS, BASEBALL_ONLY_FEATURE_COLUMNS, MODEL_C_FEATURE_COLUMNS
from build_training_data import TRAINING_CACHE
from data_collection import CACHE_DIR

ODDS_CACHE = os.path.join(CACHE_DIR, "historical_market_probs.parquet")

MONEYLINE_BOOKS = {
    "Pinnacle": ("market_home_prob", "market_home_prob_open"),
    "FanDuel": ("market_home_prob_fanduel", "market_home_prob_fanduel_open"),
    "Circa Sports": ("market_home_prob_circa", "market_home_prob_circa_open"),
    "LowVig": ("market_home_prob_lowvig", "market_home_prob_lowvig_open"),
    "Betcris": ("market_home_prob_betcris", "market_home_prob_betcris_open"),
}


def _compute_model_c_features(odds_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in odds_df.iterrows():
        probs_now, probs_open = {}, {}
        for book, (now_col, open_col) in MONEYLINE_BOOKS.items():
            now_val, open_val = r.get(now_col), r.get(open_col)
            if pd.notna(now_val):
                probs_now[book] = now_val
            if pd.notna(open_val):
                probs_open[book] = open_val

        line_movement = None
        if "Pinnacle" in probs_now and "Pinnacle" in probs_open:
            line_movement = probs_now["Pinnacle"] - probs_open["Pinnacle"]

        all_movements = [probs_now[b] - probs_open[b] for b in MONEYLINE_BOOKS if b in probs_now and b in probs_open]
        avg_movement = (sum(all_movements) / len(all_movements)) if len(all_movements) >= 2 else None

        probs_effective = {**probs_open, **probs_now}
        consensus_prob = (sum(probs_effective.values()) / len(probs_effective)) if len(probs_effective) >= 2 else None
        book_disagreement = (max(probs_effective.values()) - min(probs_effective.values())) if len(probs_effective) >= 2 else None
        book_median_prob = float(np.median(list(probs_effective.values()))) if len(probs_effective) >= 2 else None
        book_prob_std = float(np.std(list(probs_effective.values()))) if len(probs_effective) >= 2 else None
        book_favor_diff = None
        if len(probs_effective) >= 2:
            favor_home = sum(1 for p in probs_effective.values() if p > 0.5)
            favor_away = sum(1 for p in probs_effective.values() if p < 0.5)
            book_favor_diff = (favor_home - favor_away) / len(probs_effective)

        book_movements = {b: probs_now[b] - probs_open[b] for b in probs_now if b in probs_open}
        book_movement_agreement = None
        if book_movements:
            toward_home = sum(1 for m in book_movements.values() if m > 0)
            toward_away = sum(1 for m in book_movements.values() if m < 0)
            book_movement_agreement = (toward_home - toward_away) / len(book_movements)

        kalshi = r.get("market_home_prob_kalshi")
        prediction_market_diff = None
        if pd.notna(kalshi) and "Pinnacle" in probs_effective:
            prediction_market_diff = kalshi - probs_effective["Pinnacle"]

        home_total, away_total = r.get("market_team_total_home"), r.get("market_team_total_away")
        team_total_diff = (home_total - away_total) if pd.notna(home_total) and pd.notna(away_total) else None
        market_total_runs = r.get("market_total_runs") if pd.notna(r.get("market_total_runs")) else None

        rows.append({
            "game_pk": r["game_pk"],
            "model_c_line_movement_diff": line_movement,
            "model_c_avg_movement_diff": avg_movement,
            "model_c_consensus_prob_diff": (consensus_prob - 0.5) if consensus_prob is not None else None,
            "model_c_book_disagreement": book_disagreement,
            "model_c_book_movement_agreement": book_movement_agreement,
            "model_c_consensus_median_diff": (book_median_prob - 0.5) if book_median_prob is not None else None,
            "model_c_book_prob_std": book_prob_std,
            "model_c_book_favor_diff": book_favor_diff,
            "model_c_prediction_market_diff": prediction_market_diff,
            "model_c_team_total_diff": team_total_diff,
            "model_c_market_total_runs": market_total_runs,
        })
    return pd.DataFrame(rows)


def walk_forward(df: pd.DataFrame, feature_columns: list, n_folds: int = 5) -> pd.DataFrame:
    df = df.sort_values("game_date").reset_index(drop=True)
    fold_size = len(df) // (n_folds + 1)
    out = []
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
        for p, (_, row) in zip(probs, test_df.iterrows()):
            out.append({"home_win": row["home_win"], "prob": p})
    return pd.DataFrame(out)


def report(label: str, preds: pd.DataFrame):
    auc = roc_auc_score(preds["home_win"], preds["prob"])
    brier = brier_score_loss(preds["home_win"], preds["prob"])
    ll = log_loss(preds["home_win"], preds["prob"])
    acc = ((preds["prob"] >= 0.5).astype(int) == preds["home_win"]).mean()
    print(f"{label}: n={len(preds)}  AUC={auc:.4f}  Brier={brier:.4f}  LogLoss={ll:.4f}  Accuracy={acc:.4f}")
    return auc, brier


def main():
    print("Computing Model C's historical market features from historical_market_probs.parquet...")
    odds_df = pd.read_parquet(ODDS_CACHE)
    model_c_odds = _compute_model_c_features(odds_df)
    n_with_signal = model_c_odds["model_c_consensus_prob_diff"].notna().sum()
    print(f"{len(model_c_odds)} games processed, {n_with_signal} with a real >=2-book consensus signal.\n")

    df = pd.read_parquet(TRAINING_CACHE)
    df = df.merge(model_c_odds, on="game_pk", how="left")
    print(f"{len(df)} games in training set after merge.\n")

    print("Running Model A (baseball-only) walk-forward...")
    preds_a = walk_forward(df, BASEBALL_ONLY_FEATURE_COLUMNS)
    print("Running Model B (5-book CONSENSUS_BOOKS market-aware) walk-forward...")
    preds_b = walk_forward(df, FEATURE_COLUMNS)
    print("Running Model C (6-book real-time-tracker market-aware) walk-forward...")
    preds_c = walk_forward(df, MODEL_C_FEATURE_COLUMNS)
    print()

    report("Model A", preds_a)
    report("Model B", preds_b)
    report("Model C", preds_c)


if __name__ == "__main__":
    main()
