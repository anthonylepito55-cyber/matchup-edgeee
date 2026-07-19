"""
build_tennis_training_data.py

Builds walk-forward features for ATP and WTA, trains each league's model,
and — critically — validates against the market: the same free dataset
already carries each historical match's own pre-match decimal odds
(Odd_1/Odd_2), so this can check whether the model's predictions actually
add anything over what the market already priced in, on the exact same
held-out rows the model itself is scored on. Same discipline as the MLB
side's clv_backtest.py: a Brier/AUC number in isolation can look good while
the model still has no real edge over the market — the market comparison
is the real test.

Run directly: python build_tennis_training_data.py
"""

import numpy as np
import pandas as pd

from tennis_data import get_atp_match_history, get_wta_match_history
from tennis_features import compute_walk_forward_state, FEATURE_COLUMNS
import tennis_model


def _devig_player_1_prob(odd_1, odd_2):
    """Decimal odds -> de-vigged (no-juice) implied win probability for player_1."""
    if pd.isna(odd_1) or pd.isna(odd_2) or odd_1 <= 1 or odd_2 <= 1:
        return np.nan
    p1_raw, p2_raw = 1.0 / odd_1, 1.0 / odd_2
    total = p1_raw + p2_raw
    return p1_raw / total if total > 0 else np.nan


def _market_brier(test_df: pd.DataFrame) -> dict:
    market_prob = test_df.apply(lambda r: _devig_player_1_prob(r["Odd_1"], r["Odd_2"]), axis=1)
    valid = market_prob.notna()
    if valid.sum() == 0:
        return {"n": 0, "brier": None}
    y = test_df.loc[valid, "player_1_won"].astype(int)
    p = market_prob[valid]
    return {"n": int(valid.sum()), "brier": float(np.mean((p - y) ** 2))}


def build_and_validate(league: str, history: pd.DataFrame, n_folds: int = 5):
    print(f"\n=== {league.upper()} ===")
    print(f"raw matches: {len(history)}")

    feat_df, player_states, h2h = compute_walk_forward_state(history)
    print(f"features built. NaN rates:\n{feat_df[FEATURE_COLUMNS].isna().mean().round(3)}")

    # Walk-forward comparison: model vs. market, same held-out rows each fold.
    df = feat_df.sort_values("Date").reset_index(drop=True)
    fold_size = len(df) // (n_folds + 1)
    model_results, market_results = [], []

    for fold in range(1, n_folds + 1):
        train_end = fold_size * fold
        test_end = fold_size * (fold + 1)
        train_df, test_df = df.iloc[:train_end], df.iloc[train_end:test_end]
        if len(train_df) < 200 or len(test_df) < 50:
            continue

        model, medians, _ = tennis_model.train(train_df, league="_fold_check", save=False)
        X_test = test_df[FEATURE_COLUMNS].fillna(medians)
        y_test = test_df["player_1_won"].astype(int)
        probs = model.predict_proba(X_test)[:, 1]

        from sklearn.metrics import brier_score_loss, roc_auc_score
        model_results.append({
            "fold": fold, "n": len(test_df),
            "brier": brier_score_loss(y_test, probs),
            "auc": roc_auc_score(y_test, probs) if y_test.nunique() > 1 else np.nan,
        })
        market_results.append({"fold": fold, **_market_brier(test_df)})

    model_df = pd.DataFrame(model_results)
    market_df = pd.DataFrame(market_results)
    print(f"\nmodel walk-forward: avg Brier={model_df['brier'].mean():.4f}, avg AUC={model_df['auc'].mean():.4f}")
    valid_market = market_df.dropna(subset=["brier"])
    if not valid_market.empty:
        print(f"market baseline (same folds, rows with posted odds only): avg Brier={valid_market['brier'].mean():.4f}, n={valid_market['n'].sum()}")
    else:
        print("market baseline: no rows with valid odds in test folds")

    # Final model trained on ALL history, saved for live serving.
    final_model, medians, metrics = tennis_model.train(feat_df, league=league, save=True)
    print(f"\nfinal {league} model trained on full history: {metrics}")

    return feat_df, player_states, h2h, metrics


if __name__ == "__main__":
    atp_history = get_atp_match_history(force_refresh=True)
    build_and_validate("atp", atp_history)

    wta_history = get_wta_match_history(force_refresh=True)
    build_and_validate("wta", wta_history)
