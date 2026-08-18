"""
_backtest_model_c_accuracy_ideas.py

Ad-hoc ablation test for two ideas to push Model C's accuracy past Model B's (they currently
tie on AUC/Brier -- see build_and_train_model_c.py). Scratch script, not wired into the
pipeline -- only promote a feature into features.py/build_training_data.py if it actually
clears the bar here.

Idea A tested: sharp-book-weighted consensus (Pinnacle/Circa/LowVig/Betcris weighted 2x vs
FanDuel 1x) as an ADDITIONAL feature alongside the existing flat-average consensus_prob,
tested via the same add-one-feature ablation methodology used for every other feature this
session (e.g. signal_agreement_score).

Idea B (movement in the final minutes before first pitch) is NOT tested here -- confirmed by
inspecting historical_market_probs.parquet's schema that it only has two snapshots per book
(_open and a single "now"/closing value), not a timeline. There's no historical data granular
enough to backtest a pre-first-pitch-freshness feature; it would need forward data collection
from the now-live poller before it could be tested at all.
"""
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, brier_score_loss

from model import train
from build_and_train_model_c import ODDS_CACHE, MONEYLINE_BOOKS, walk_forward, report
from features import MODEL_C_FEATURE_COLUMNS
from build_training_data import TRAINING_CACHE

SHARP_BOOKS = {"Pinnacle", "Circa Sports", "LowVig", "Betcris"}
BOOK_WEIGHTS = {b: (2.0 if b in SHARP_BOOKS else 1.0) for b in MONEYLINE_BOOKS}


def _sharp_weighted_consensus(odds_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in odds_df.iterrows():
        probs_effective = {}
        for book, (now_col, open_col) in MONEYLINE_BOOKS.items():
            now_val, open_val = r.get(now_col), r.get(open_col)
            val = now_val if pd.notna(now_val) else open_val
            if pd.notna(val):
                probs_effective[book] = val

        sharp_weighted = None
        if len(probs_effective) >= 2:
            total_w = sum(BOOK_WEIGHTS[b] for b in probs_effective)
            sharp_weighted = sum(BOOK_WEIGHTS[b] * p for b, p in probs_effective.items()) / total_w

        rows.append({
            "game_pk": r["game_pk"],
            "model_c_sharp_weighted_diff": (sharp_weighted - 0.5) if sharp_weighted is not None else None,
        })
    return pd.DataFrame(rows)


def walk_forward_by_fold(df: pd.DataFrame, feature_columns: list, n_folds: int = 5) -> pd.DataFrame:
    """Same walk-forward split as build_and_train_model_c.walk_forward, but reports AUC/Brier
    per fold instead of pooling all folds together -- needed to tell a real, consistent effect
    apart from one fold's noise dominating the pooled number (bit us once already this session,
    see the Model C coverage-ramp theory that only held up in fold 5)."""
    df = df.sort_values("game_date").reset_index(drop=True)
    fold_size = len(df) // (n_folds + 1)
    rows = []
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
        y_test = test_df["home_win"].astype(int)
        rows.append({
            "fold": fold,
            "n_test": len(test_df),
            "auc": roc_auc_score(y_test, probs) if y_test.nunique() > 1 else np.nan,
            "brier": brier_score_loss(y_test, probs),
        })
    return pd.DataFrame(rows)


def main():
    odds_df = pd.read_parquet(ODDS_CACHE)
    sharp_odds = _sharp_weighted_consensus(odds_df)

    # TRAINING_CACHE already has the model_c_* columns merged in (see "Train and integrate
    # Model C into the standard pipeline") -- only the new sharp-weighted feature needs merging.
    df = pd.read_parquet(TRAINING_CACHE)
    df = df.merge(sharp_odds, on="game_pk", how="left")
    n_with_signal = df["model_c_sharp_weighted_diff"].notna().sum()
    print(f"{len(df)} games in training set, {n_with_signal} with a real sharp-weighted signal.\n")

    print("Baseline: current Model C (flat 6-book average consensus)...")
    preds_baseline = walk_forward(df, MODEL_C_FEATURE_COLUMNS)
    print("Ablation: current Model C + sharp-weighted consensus feature...")
    preds_sharp = walk_forward(df, MODEL_C_FEATURE_COLUMNS + ["model_c_sharp_weighted_diff"])
    print()

    auc_b, brier_b = report("Model C (baseline)", preds_baseline)
    auc_s, brier_s = report("Model C + sharp-weighted", preds_sharp)
    print()
    print(f"Pooled AUC delta: {auc_s - auc_b:+.4f}   Pooled Brier delta: {brier_s - brier_b:+.4f} (negative Brier delta is better)")

    print("\nPer-fold breakdown (baseline vs sharp-weighted):")
    folds_b = walk_forward_by_fold(df, MODEL_C_FEATURE_COLUMNS)
    folds_s = walk_forward_by_fold(df, MODEL_C_FEATURE_COLUMNS + ["model_c_sharp_weighted_diff"])
    merged = folds_b.merge(folds_s, on="fold", suffixes=("_base", "_sharp"))
    merged["auc_delta"] = merged["auc_sharp"] - merged["auc_base"]
    merged["brier_delta"] = merged["brier_sharp"] - merged["brier_base"]
    print(merged[["fold", "n_test_base", "auc_base", "auc_sharp", "auc_delta", "brier_base", "brier_sharp", "brier_delta"]]
          .to_string(index=False))
    n_folds_improved = (merged["auc_delta"] > 0).sum()
    print(f"\n{n_folds_improved}/{len(merged)} folds improved on AUC.")


if __name__ == "__main__":
    main()
