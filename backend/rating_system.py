"""
rating_system.py

A hand-built, transparent power-rating ALTERNATIVE to the trained XGBoost model (model.py) — not
a replacement for it. Computes a win probability as a rank-weighted sum of z-scored category
signals, with weights fixed by the user's own stated priority order (2026-07-12), rather than
letting gradient boosting discover its own weights. Every category's contribution to a given
game is inspectable (score_matchup returns it directly), which is the actual point of building
this as its own thing: not a black box, and directly checkable against "does this make sense"
the way the trained model's raw feature importances don't invite you to.

Reuses the exact same underlying feature diffs already computed for the XGBoost model
(features.build_matchup_features / FEATURE_COLUMNS) — this is a different WEIGHTING of the same
signals already in this app, not a new data pipeline.

Category priority order and what maps to what (some of the user's 12 signals collapse to the
same underlying number in this codebase, and two aren't available as a standalone diff feature
here — see the inline notes):
  1. starting_pitcher_quality  — FIP/K-BB%/HR9/H9/whiff/chase/hard-hit/GB/barrel, season+recent+prior, rest days
  2. bullpen_availability      — bullpen FIP, high-leverage-arm FIP, fatigue, bullpen-edge-when-close
  3. batter_pitch_type_matchup — arsenal-weighted matchup wOBA
  4. weather_and_park          — park_factor_home is ALREADY wind/temp-adjusted (see features.py) —
                                  weather (rank 4) and park factors (rank 6) are the same number here,
                                  not two independent signals; counted once at rank 4's weight.
  5. official_lineups          — real/predicted-lineup wOBA and platoon wOBA
  (rank 6 — see weather_and_park above)
  7. team_offense_30d          — 7-game and 30-day team batting average
  (rank 8, umpire tendencies — excluded: confirmed no free data source, see the session's plan doc)
  9. defensive_metrics         — team BABIP allowed
  10. market_movement          — opening-to-current moneyline shift
  11. travel_fatigue           — distance since each team's last game
  (rank 12, injuries — not a standalone diff feature here; already reflected INSIDE
   official_lineups (a missing player is simply absent from the real lineup) and in how thin/
   unreliable recent-form samples get discounted — no separate category to avoid double-counting)

Backtested independently, walk-forward, against both actual outcomes and the trained model's own
predictions (see backtest_rating_system) — deliberately NOT kept "regardless of backtest" the way
several individual features were this session. A system whose whole value proposition is being
demonstrably sharp needs to actually prove out, or the comparison itself is the useful thing to
report honestly.
"""

import os
import joblib
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

RATING_SYSTEM_PATH = os.path.join(os.path.dirname(__file__), "model_artifacts", "rating_system.joblib")
os.makedirs(os.path.dirname(RATING_SYSTEM_PATH), exist_ok=True)

CATEGORY_MAP = {
    "starting_pitcher_quality": (1, [
        "fip_diff", "k_bb_pct_diff", "prior_season_fip_diff", "prior_season_k_bb_pct_diff",
        "season_ip_per_start_diff", "hr9_diff", "h9_diff",
        "recent_fip_diff", "recent_k9_diff", "recent_bb9_diff", "recent_hr9_diff", "recent_h9_diff",
        "recent_ip_per_start_diff", "whiff_pct_diff", "chase_pct_diff", "hard_hit_pct_diff",
        "gb_pct_diff", "barrel_pct_diff", "rest_days_diff",
    ]),
    "bullpen_availability": (2, [
        "bullpen_fip_diff", "bullpen_fatigue_diff", "high_leverage_bullpen_fip_diff",
        "bullpen_edge_when_close_diff",
    ]),
    "batter_pitch_type_matchup": (3, ["arsenal_matchup_woba_diff"]),
    "weather_and_park": (4, ["park_factor_home"]),
    "official_lineups": (5, ["opp_lineup_woba_diff", "opp_platoon_woba_diff"]),
    "team_offense_30d": (7, ["recent_team_batting_diff", "recent_team_batting_30d_diff"]),
    "defensive_metrics": (9, ["defense_babip_diff"]),
    "market_movement": (10, ["line_movement_diff"]),
    "travel_fatigue": (11, ["travel_fatigue_diff"]),
}

# Rank-based weight: 1/rank, directly derived from the user's stated priority order — not fit to
# data. Only one free parameter is calibrated against outcomes (the global `scale` below); the
# RELATIVE importance of each category is fixed by this schedule alone.
CATEGORY_WEIGHTS = {cat: 1.0 / rank for cat, (rank, _cols) in CATEGORY_MAP.items()}


def _category_raw_score(feats: dict, cols: list) -> float:
    """Sum of available (non-missing) feature values in this category, or NaN if every one of
    them is missing for this game — distinct from 0, which would wrongly mean "average" instead
    of "no data." Handled at combine time in score_matchup (imputed to that category's own mean,
    i.e. z=0, "no signal" rather than "bad for either side")."""
    vals = [feats.get(c) for c in cols]
    vals = [v for v in vals if v is not None and pd.notna(v)]
    return float(sum(vals)) if vals else np.nan


def _category_raw_scores_df(df: pd.DataFrame) -> pd.DataFrame:
    """{category: raw_score} for every row in df — vectorized version of _category_raw_score,
    used to fit z-score parameters and calibrate `scale` against a whole training set at once."""
    out = {}
    for cat, (_rank, cols) in CATEGORY_MAP.items():
        present = [c for c in cols if c in df.columns]
        out[cat] = df[present].sum(axis=1, skipna=True, min_count=1) if present else pd.Series(np.nan, index=df.index)
    return pd.DataFrame(out)


def fit_rating_system(train_df: pd.DataFrame, label_col: str = "home_win") -> dict:
    """
    Fits the ONLY two things this system learns from data: each category's z-score mean/std
    (so a FIP-unit category and a probability-unit category are on the same comparable scale
    before weighting), and a single global `scale` calibrated to minimize Brier score against
    actual outcomes (Platt-scaling-style — one multiplier, not per-category tuning). Everything
    else (which categories exist, their relative weight) is fixed by CATEGORY_WEIGHTS above.
    """
    raw = _category_raw_scores_df(train_df)
    zscore_params = {}
    for cat in CATEGORY_MAP:
        col = raw[cat]
        mean = col.mean()
        std = col.std()
        zscore_params[cat] = (float(mean) if pd.notna(mean) else 0.0, float(std) if pd.notna(std) and std > 0 else 1.0)

    z = pd.DataFrame({
        cat: ((raw[cat] - zscore_params[cat][0]) / zscore_params[cat][1]).fillna(0.0)
        for cat in CATEGORY_MAP
    })
    weighted_sum = sum(z[cat] * CATEGORY_WEIGHTS[cat] for cat in CATEGORY_MAP)

    y = train_df[label_col].astype(int).values
    home_win_rate = float(np.clip(y.mean(), 0.01, 0.99))
    base_rate = float(np.log(home_win_rate / (1 - home_win_rate)))  # logit of the base rate — home-field advantage, calibrated from data, not assumed

    def brier_for_scale(scale):
        logit = base_rate + scale * weighted_sum.values
        prob = 1 / (1 + np.exp(-logit))
        return brier_score_loss(y, prob)

    result = minimize_scalar(brier_for_scale, bounds=(0.01, 5.0), method="bounded")
    scale = float(result.x)

    return {"zscore_params": zscore_params, "scale": scale, "base_rate": base_rate}


def fit_and_save_rating_system(train_df: pd.DataFrame, label_col: str = "home_win") -> dict:
    """fit_rating_system on the full dataset, persisted the same way model.py saves the trained
    XGBoost model — so live serving (main.py) doesn't refit on every request. Call this alongside
    train.py's main model training so the two stay in sync with the same training data."""
    fitted = fit_rating_system(train_df, label_col)
    joblib.dump(fitted, RATING_SYSTEM_PATH)
    return fitted


def load_rating_system() -> dict | None:
    if not os.path.exists(RATING_SYSTEM_PATH):
        return None
    return joblib.load(RATING_SYSTEM_PATH)


def score_matchup(fitted: dict, feats: dict) -> dict:
    """Returns {"home_win_prob":, "away_win_prob":, "category_contributions": {cat: weighted_z}}
    for one game — the contributions dict is the actual reason this exists: "pitcher quality:
    +0.31, bullpen: +0.08, matchup: -0.05, ..." instead of just a probability with no visible
    reasoning."""
    zscore_params, scale, base_rate = fitted["zscore_params"], fitted["scale"], fitted["base_rate"]
    contributions = {}
    total = 0.0
    for cat, (_rank, cols) in CATEGORY_MAP.items():
        raw = _category_raw_score(feats, cols)
        mean, std = zscore_params[cat]
        z = (raw - mean) / std if pd.notna(raw) else 0.0
        weighted = CATEGORY_WEIGHTS[cat] * z
        contributions[cat] = round(float(weighted), 4)
        total += weighted
    logit = base_rate + scale * total
    prob = float(1 / (1 + np.exp(-logit)))
    return {
        "home_win_prob": round(prob, 4),
        "away_win_prob": round(1 - prob, 4),
        "category_contributions": contributions,
    }


def backtest_rating_system(historical_df: pd.DataFrame, label_col: str = "home_win", n_folds: int = 5) -> dict:
    """
    Same walk-forward fold structure as model.backtest() — trains (fits z-score params + scale)
    on earlier data, scores later data, repeated across date-ordered folds — so the two systems'
    numbers are directly, fairly comparable, not apples-to-oranges from different validation
    setups. historical_df must be sorted by game_date and contain every CATEGORY_MAP feature
    column + label_col + game_date.
    """
    df = historical_df.sort_values("game_date").reset_index(drop=True)
    fold_size = len(df) // (n_folds + 1)
    results = []

    for fold in range(1, n_folds + 1):
        train_end = fold_size * fold
        test_end = fold_size * (fold + 1)
        train_df = df.iloc[:train_end]
        test_df = df.iloc[train_end:test_end]
        if len(train_df) < 50 or len(test_df) < 10:
            continue

        fitted = fit_rating_system(train_df, label_col)
        probs = np.array([score_matchup(fitted, row.to_dict())["home_win_prob"] for _, row in test_df.iterrows()])
        y_test = test_df[label_col].astype(int).values

        results.append({
            "fold": fold,
            "n_test": len(test_df),
            "brier_score": brier_score_loss(y_test, probs),
            "log_loss": log_loss(y_test, probs),
            "auc": roc_auc_score(y_test, probs) if len(np.unique(y_test)) > 1 else np.nan,
            "predicted_mean": float(probs.mean()),
            "actual_mean": float(y_test.mean()),
        })

    results_df = pd.DataFrame(results)
    return {
        "avg_brier_score": float(results_df["brier_score"].mean()),
        "avg_log_loss": float(results_df["log_loss"].mean()),
        "avg_auc": float(results_df["auc"].mean()),
        "folds": results_df.to_dict(orient="records"),
    }
