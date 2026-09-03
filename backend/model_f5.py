"""
model_f5.py -- the FIRST-5-INNINGS winner model. Separate artifacts, separate serving fields,
never touches Models A/B/C/E.

Why: this app's features are fundamentally a starting-pitcher read, and the full-game moneyline
dilutes that with bullpens and late innings. OpticOdds' "1st Half Moneyline" (= first 5 innings
in MLB) prices almost exactly what the features measure, in a thinner, less efficient market.
Verified 2026-08-20: live F5 prices on today's fixtures across books, and historical F5 prices
(open + close) on settled 2026 games, so it can be trained AND backtested against its own market.

Recipe: Model B's exactly (FEATURE_COLUMNS, DEFAULT_XGB_PARAMS, 5-seed ensemble) -- the full-game
market features stay in as inputs because they're still informative about F5 -- trained on
f5_home_win from build_f5_labels.py (ties after 5 are dropped from training; a 2-way F5 line
pushes on a tie). Bets go through model_e.compute_bet with the F5 market price, so the same
underdog/favorite rule, best-price shopping, quarter-Kelly sizing and CLV bookkeeping apply.
"""
import os

import pandas as pd

import model as model_module
from data_collection import CACHE_DIR
from features import FEATURE_COLUMNS

ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "model_artifacts")
MODEL_F5_PATH = os.path.join(ARTIFACT_DIR, "model_f5.joblib")
MODEL_F5_VALIDATION_PATH = os.path.join(ARTIFACT_DIR, "model_f5_validation.json")
F5_LABELS_PATH = os.path.join(CACHE_DIR, "f5_labels.parquet")
F5_MARKET_PATH = os.path.join(CACHE_DIR, "f5_market_probs.parquet")
LABEL_COL = "f5_home_win"


def is_trained() -> bool:
    return model_module.load_model_ensemble(MODEL_F5_PATH)[0] is not None


def predict(feature_row: pd.DataFrame) -> dict:
    """{"home_win_prob": P(home leads after 5 | not tied), ...} -- same row Model B uses."""
    return model_module.predict_proba_ensemble(feature_row, model_path=MODEL_F5_PATH, feature_columns=FEATURE_COLUMNS)


def training_frame(training_df: pd.DataFrame) -> pd.DataFrame:
    """training_dataset rows joined to their F5 label (decided-after-5 games only) and, where the
    backfill has reached them, the F5 market close/open probs."""
    if not os.path.exists(F5_LABELS_PATH):
        raise FileNotFoundError("run build_f5_labels.py first")
    lab = pd.read_parquet(F5_LABELS_PATH)[["game_pk", LABEL_COL, "f5_home_runs", "f5_away_runs"]]
    df = training_df.merge(lab, on="game_pk", how="inner")
    df = df[df[LABEL_COL].notna()].copy()
    df[LABEL_COL] = df[LABEL_COL].astype(int)
    if os.path.exists(F5_MARKET_PATH):
        mk = pd.read_parquet(F5_MARKET_PATH)[["game_pk", "f5_market_home_prob", "f5_market_home_prob_open", "f5_books"]]
        df = df.merge(mk, on="game_pk", how="left")
    else:
        df["f5_market_home_prob"] = float("nan")
        df["f5_market_home_prob_open"] = float("nan")
        df["f5_books"] = 0
    return df.sort_values("game_date").reset_index(drop=True)


def load_validation() -> dict | None:
    import json
    if not os.path.exists(MODEL_F5_VALIDATION_PATH):
        return None
    with open(MODEL_F5_VALIDATION_PATH) as f:
        return json.load(f)


# Bets against the F5 market are only produced once the walk-forward validation (written by
# build_and_train_model_f5.py, with the F5 odds backfill in place) shows positive ROI at fair
# odds on a real sample -- the F5 PREDICTION can be shown regardless, the BET cannot. Same
# validate-before-shipping rule as every other betting signal in this app.
MIN_VALIDATION_BETS = 200


def bets_enabled() -> bool:
    v = load_validation() or {}
    allb = (v.get("betting_fair_odds") or {}).get("all") or {}
    return bool(allb) and allb.get("n", 0) >= MIN_VALIDATION_BETS and (allb.get("roi_fair_odds_pct") or 0) > 0
