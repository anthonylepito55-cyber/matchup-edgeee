"""
model_e.py -- "Model E": the betting model. Fully separate from Models A/B/C (its own
artifacts, its own serving fields, its own log columns, its own track record) so nothing
here can change what A/B/C predict or display.

Why it exists (2026-08-20): the clean A/B/C backtest showed that no model beats the market
on Brier across ALL games (B +0.0016, noise), but Model B's DISAGREEMENTS with the market do
carry real edge -- underdog flag 53.1% vs 46.5% market-implied (n=607), favorite flag 62.1% vs
57.2% (n=1,474) on the 2026-08-20 clean revalidation. Beating the market means +CLV/+ROI on
the bets you actually place, not a better Brier on every game. Model E is built around that:

  1. Base: Model B's recipe (DEFAULT_XGB_PARAMS depth-1 stumps + sigmoid CalibratedClassifierCV,
     5-seed ensemble via model.train_ensemble) on MODEL_E_FEATURE_COLUMNS below -- Model B's 14
     market features plus the 13 baseball features that still add information once the market is
     known (feature study 2026-08-20, see the comment on MODEL_E_FEATURE_COLUMNS). Started as
     exactly Model B's 69 columns; pruning to 27 was the one change that beat it on walk-forward
     betting outcomes AND calibration, so that's the base now.
  2. A post-hoc calibration layer (isotonic / Platt / identity, chosen by leakage-free
     walk-forward validation in build_and_train_model_e.py) fitted on OUT-OF-FOLD ensemble
     predictions. Model B's known pathology is over-shooting at the extremes on ~14 mutually
     correlated market features -- exactly where value flags fire -- and a flag keyed off a
     miscalibrated probability is a mis-sized bet. This layer cannot hurt AUC (monotone) and
     is only kept if it measurably improves OOF Brier/log-loss; otherwise "identity" is saved
     and Model E == Model B numerically.
  3. A betting layer (compute_bet): the two value types that survived the clean large-sample
     revalidation (underdog / favorite -- dog_value came out NEGATIVE and is not here),
     priced against the BEST available book price for that side, with a fractional-Kelly
     stake and expected value, plus first-seen price/probability carried forward so CLV
     (did the line move toward us after we flagged it?) is measurable per bet.

Everything that touches the live app is additive: new keys in /api/today, new columns in
prediction_log (model_e_prob, model_e_bet_json), a new /api/model-e-track-record.
"""
import json
import math
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

import model as model_module
from features import FEATURE_COLUMNS, MARKET_FEATURE_COLUMNS

# The 13 baseball features Model E actually uses, + Model B's 14 market features = 27 columns.
# Chosen by the 2026-08-20 feature study (_model_e_feature_study.py, _model_e_nested_confirm.py,
# _model_e_final_set.py; results in model_artifacts/model_e_feature_study.json etc.): ranked by
# permutation importance IN THE PRESENCE OF the market features ("what baseball signal still adds
# information once the market price is known"), union of the full-data top-10 and the
# folds-1-3-only top-10 (so the tail isn't one noisy ranking). vs Model B's full 55+14 recipe on
# the same walk-forward folds/seeds/prices: AUC 0.6142 vs 0.6048, Brier 0.2379 vs 0.2393, betting
# ROI@fair +11.7% vs +11.4% @0.02 (on MORE bets), +15.4% vs +12.9% @0.04, +19.6% vs +18.9% @0.06,
# worst fold -1.1% vs -5.8%; the gain also survived a nested (no-selection-leakage) check.
# The 42 dropped baseball columns are mostly the redundant starter-FIP family -- the market
# already prices starters; bullpen, lineups, defense and opponent power are where the edge is.
# Every candidate that ADDED signal (LR weight-score feature, blends, fip-gap sample weights,
# retired extras) tested worse. Prune, don't add.
MODEL_E_BASEBALL_COLUMNS = [
    "bullpen_fip_diff", "opp_platoon_woba_diff", "defense_oaa_diff", "opp_power_diff",
    "opp_lineup_woba_diff", "recent_bb9_diff", "season_ip_per_start_diff", "recent_hr9_diff",
    "travel_fatigue_diff", "lineup_chase_percentile_diff", "fip_trend_diff", "lineup_xwoba_diff",
    "pitches_per_start_diff",
]
MODEL_E_FEATURE_COLUMNS = MODEL_E_BASEBALL_COLUMNS + MARKET_FEATURE_COLUMNS
assert all(c in FEATURE_COLUMNS for c in MODEL_E_FEATURE_COLUMNS)  # every column is one Model B's row already carries

ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "model_artifacts")
MODEL_E_PATH = os.path.join(ARTIFACT_DIR, "model_e.joblib")
MODEL_E_CALIBRATOR_PATH = os.path.join(ARTIFACT_DIR, "model_e_calibrator.joblib")
MODEL_E_VALIDATION_PATH = os.path.join(ARTIFACT_DIR, "model_e_validation.json")
# Baseball-only leg: MODEL_E_BASEBALL_COLUMNS with NO market features -- the same 13 factors
# as a market-blind model. Comparison-only (never bets): it exists to be measured against
# Model A on the same frozen games. Validated 2026-08-20: vs Model A (55 baseball cols),
# full 5-fold AUC 0.5874 vs 0.5774 / Brier 0.2431 vs 0.2442; nested (rank folds 1-3,
# score 4-5) AUC 0.5889 vs 0.5824 and disagreement-with-market ROI@fair +16.8% vs +10.8%.
MODEL_E_BASEBALL_PATH = os.path.join(ARTIFACT_DIR, "model_e_baseball.joblib")

# --- betting layer constants -----------------------------------------------------------------
# Same 0.02 thresholds the existing VALUE badge validated (main.UNDERDOG/FAVORITE_VALUE_THRESHOLD)
# and that the 2026-08-20 clean revalidation confirmed on n=607 / n=1,474. dog_value deliberately
# absent: -1.7 pts vs market-implied on n=1,133 in that same clean run.
UNDERDOG_THRESHOLD = 0.02
FAVORITE_THRESHOLD = 0.02
KELLY_FRACTION = 0.25       # quarter-Kelly: backtest edges routinely halve live; full Kelly on a halved edge over-bets ~2x
BANKROLL_UNITS = 100.0      # stakes are expressed in units of a 100-unit bankroll
MAX_STAKE_UNITS = 5.0       # hard cap regardless of what Kelly says -- a single MLB game is never worth more
MIN_EV_PCT = 0.0            # don't flag a bet whose EV at the best available price is negative after the book's vig
STRONG_EDGE = 0.06          # gap at which backtest ROI@fair roughly doubled vs the 0.02 floor -- see compute_bet
# Underdog flips with only 2-4 pts of edge are near-pick'em games (market dog 48-50%, model 52-54%):
# 2026-08-20 underdog profile on 932 held-out flips -- that bucket was -18.5% ROI, negative in 3 of
# 4 folds, while 4-6 pts was +11%, 8+ pts +20%. Model E's underdog bets therefore need >= 4 pts.
# F5 passes min_underdog_edge=0.02 explicitly (its own validation used 0.02; not re-tested).
UNDERDOG_MIN_EDGE = 0.04
# Dog grade by how strongly the model flips (same profile): A = model has the dog >= 55%
# (+21% ROI 55-60%, +35% 60%+, fold-stable), B = 52-55% (+6%). Display/ranking only.
DOG_GRADE_A = 0.55


# ============================================================================================
# Calibration layer
# ============================================================================================

def _clip(p):
    return np.clip(np.asarray(p, dtype=float), 1e-4, 1 - 1e-4)


class Calibrator:
    """Monotone map raw ensemble prob -> calibrated prob. kind in {"identity", "platt", "isotonic"}.
    Picklable (joblib) and tiny; fitted ONLY on out-of-fold predictions (see
    build_and_train_model_e.py) so it never sees a prediction the base model made on its own
    training rows -- fitting a calibrator on in-sample predictions would just learn the base
    model's in-sample overconfidence and "correct" for something that doesn't exist live."""

    def __init__(self, kind: str = "identity"):
        self.kind = kind
        self._iso = None
        self._lr = None
        self.n_fit = 0

    def fit(self, raw_probs, y):
        raw_probs = _clip(raw_probs)
        y = np.asarray(y, dtype=int)
        self.n_fit = int(len(y))
        if self.kind == "isotonic":
            self._iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(raw_probs, y)
        elif self.kind == "platt":
            logit = np.log(raw_probs / (1 - raw_probs)).reshape(-1, 1)
            self._lr = LogisticRegression(C=1e6, solver="lbfgs").fit(logit, y)
        return self

    def transform(self, raw_probs):
        raw_probs = _clip(raw_probs)
        if self.kind == "isotonic" and self._iso is not None:
            return _clip(self._iso.predict(raw_probs))
        if self.kind == "platt" and self._lr is not None:
            logit = np.log(raw_probs / (1 - raw_probs)).reshape(-1, 1)
            return _clip(self._lr.predict_proba(logit)[:, 1])
        return raw_probs


def expected_calibration_error(probs, y, n_bins: int = 10) -> float:
    """Standard ECE: bucket by predicted prob, |mean predicted - mean actual| weighted by bucket size."""
    probs = np.asarray(probs, dtype=float)
    y = np.asarray(y, dtype=float)
    edges = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (probs > lo) & (probs <= hi)
        if m.any():
            ece += m.mean() * abs(probs[m].mean() - y[m].mean())
    return float(ece)


def save_calibrator(cal: Calibrator, path: str = MODEL_E_CALIBRATOR_PATH):
    joblib.dump({"kind": cal.kind, "calibrator": cal}, path)


def load_calibrator(path: str = MODEL_E_CALIBRATOR_PATH) -> Calibrator:
    if not os.path.exists(path):
        return Calibrator("identity")
    return joblib.load(path)["calibrator"]


# ============================================================================================
# Prediction
# ============================================================================================

def is_trained() -> bool:
    return model_module.load_model_ensemble(MODEL_E_PATH)[0] is not None


def is_baseball_trained() -> bool:
    return model_module.load_model_ensemble(MODEL_E_BASEBALL_PATH)[0] is not None


def predict_baseball(feature_row: pd.DataFrame) -> dict:
    """Market-blind leg: same 13 baseball factors, no market columns. {"home_win_prob", ...}."""
    return model_module.predict_proba_ensemble(feature_row, model_path=MODEL_E_BASEBALL_PATH,
                                               feature_columns=MODEL_E_BASEBALL_COLUMNS)


def predict(feature_row: pd.DataFrame) -> dict:
    """{"home_win_prob", "raw_home_win_prob", "calibration"} -- raw is the 5-seed ensemble
    average over MODEL_E_FEATURE_COLUMNS, home_win_prob is after the calibration layer.
    feature_row must carry those columns (Model B's FEATURE_COLUMNS row is a superset, it works)."""
    raw = model_module.predict_proba_ensemble(feature_row, model_path=MODEL_E_PATH, feature_columns=MODEL_E_FEATURE_COLUMNS)
    cal = load_calibrator()
    p = float(cal.transform([raw["home_win_prob"]])[0])
    return {"home_win_prob": round(p, 4), "raw_home_win_prob": raw["home_win_prob"], "calibration": cal.kind}


# ============================================================================================
# Betting layer
# ============================================================================================

def american_to_decimal(price) -> float | None:
    if price is None:
        return None
    price = float(price)
    return 1 + price / 100.0 if price > 0 else 1 + 100.0 / abs(price)


def decimal_to_american(dec: float) -> int:
    return int(round((dec - 1) * 100)) if dec >= 2 else int(round(-100 / (dec - 1)))


def _best_price(book_prices: dict | None, side: str):
    """(best_american_price, book) for `side` ("home"/"away") across {book: {"home":.., "away":..}}.
    Best for the bettor = highest decimal payout. None if no book prices available."""
    best = None
    for book, pr in (book_prices or {}).items():
        dec = american_to_decimal((pr or {}).get(side))
        if dec is None:
            continue
        if best is None or dec > best[0]:
            best = (dec, pr[side], book)
    return (best[1], best[2], best[0]) if best else (None, None, None)


def compute_bet(model_e_home_prob: float, market_home_prob: float, home_abbr: str, away_abbr: str,
                book_prices: dict | None = None, live_odds: dict | None = None,
                previous_bet: dict | None = None, min_underdog_edge: float = None) -> dict | None:
    """
    Returns the Model E bet for this game, or None when there's no qualifying edge.

    Side selection mirrors main._compute_value_bet's validated logic (underdog flip / favorite
    reinforcement at 0.02), but then PRICES the bet: best available american price for that
    side across `book_prices` (falls back to `live_odds`' single book), fair price implied by
    Model E's own probability, EV% at the best price, quarter-Kelly stake in units. A bet with
    negative EV at the best real price (the book's vig eats the edge) is NOT returned even if
    the probability gap clears the threshold -- the gap is measured against a de-vigged
    consensus, the stake is placed against a vigged line, and only the latter pays.

    previous_bet: the bet dict already frozen for this game on an earlier call today, if any.
    first_seen_* fields are carried forward from it unchanged so the row always remembers the
    price/probability at the moment the bet FIRST qualified (the earliest moment the user could
    have placed it), while everything else keeps updating until first pitch. CLV per bet =
    close (final pre-game market prob on our side) minus first_seen market prob on our side.
    """
    if model_e_home_prob is None or market_home_prob is None:
        return None
    market_favors_home = market_home_prob >= 0.5
    fav_side = "home" if market_favors_home else "away"
    dog_side = "away" if market_favors_home else "home"
    p_model_fav = model_e_home_prob if market_favors_home else 1 - model_e_home_prob
    p_mkt_fav = market_home_prob if market_favors_home else 1 - market_home_prob

    min_dog_edge = UNDERDOG_MIN_EDGE if min_underdog_edge is None else min_underdog_edge
    if p_model_fav < 0.5 - UNDERDOG_THRESHOLD and (1 - p_model_fav) - (1 - p_mkt_fav) >= min_dog_edge:
        side, bet_type = dog_side, "underdog"
        p_model, p_mkt = 1 - p_model_fav, 1 - p_mkt_fav
    elif p_model_fav - p_mkt_fav >= FAVORITE_THRESHOLD:
        side, bet_type = fav_side, "favorite"
        p_model, p_mkt = p_model_fav, p_mkt_fav
    else:
        return None

    price, book, dec = _best_price(book_prices, side)
    if price is None and live_odds and live_odds.get(side) is not None:
        price, book, dec = live_odds[side], live_odds.get("bookmaker"), american_to_decimal(live_odds[side])
    if dec is None:
        # no real price to bet into -- still report the probability edge, but no stake
        ev_pct = kelly_full = stake = None
    else:
        b = dec - 1.0
        ev_pct = round((p_model * dec - 1.0) * 100, 2)
        kelly_full = max(0.0, (b * p_model - (1 - p_model)) / b)
        stake = round(min(MAX_STAKE_UNITS, KELLY_FRACTION * kelly_full * BANKROLL_UNITS), 2)
        if ev_pct < MIN_EV_PCT:
            return None

    side_abbr = home_abbr if side == "home" else away_abbr
    bet = {
        "side": side_abbr, "side_is_home": side == "home", "type": bet_type,
        "model_prob": round(p_model, 4), "market_prob": round(p_mkt, 4),
        "edge": round(p_model - p_mkt, 4),
        # ROI@fair rose monotonically with the disagreement gap in the 2026-08-20 base comparison
        # (+11% at 0.02 -> +19% at 0.06 -> +26% at 0.08 for Model B's recipe); Kelly already sizes
        # these up, "strong" just makes them visible at a glance.
        "strength": "strong" if (p_model - p_mkt) >= STRONG_EDGE else "normal",
        "dog_grade": ("A" if p_model >= DOG_GRADE_A else "B") if bet_type == "underdog" else None,
        "best_price": price, "best_book": book,
        "fair_price": decimal_to_american(1 / p_model),
        "ev_pct": ev_pct, "kelly_full": round(kelly_full, 4) if kelly_full is not None else None,
        "stake_units": stake,
    }
    prev = previous_bet or {}
    if prev.get("first_seen_at") and prev.get("side") == side_abbr:
        for k in ("first_seen_at", "first_seen_market_prob", "first_seen_price", "first_seen_book"):
            bet[k] = prev.get(k)
    else:
        from datetime import datetime, timezone
        bet["first_seen_at"] = datetime.now(timezone.utc).isoformat()
        bet["first_seen_market_prob"] = round(p_mkt, 4)
        bet["first_seen_price"] = price
        bet["first_seen_book"] = book
    return bet


SHADE_MIN_EDGE = 0.02   # model must like the dog at least this much more than the market


def compute_shade_bet(model_e_home_prob: float, market_home_prob: float, home_abbr: str, away_abbr: str,
                      book_prices: dict | None = None, live_odds: dict | None = None,
                      previous_bet: dict | None = None) -> dict | None:
    """
    UNPROVEN signal, deliberately kept out of compute_bet: the model likes the market's UNDERDOG
    more than the price does, but does NOT flip to it (it still has the favorite winning). The old
    `dog_value` flag was this pattern and was removed after it backtested negative.

    Re-tested 2026-08-21 on two windows and they CONTRADICT each other:
        full sample (3,586 games): n=934, dog wins 39.8%, ROI -3.2%
        last 1,000 games:          n=207, dog wins 43.5%, ROI +2.5%
      (and with F5 also shading to the dog: -8.8% full vs +5.8% recent)
    Sub-buckets flip sign between windows too, so this is most likely noise around break-even, not
    a discovered edge. For comparison, real FLIPS (compute_bet's underdog branch) returned +13.6%
    and +24.5% on the same two windows -- 3-5x better and positive in both.

    Served and logged separately (model_e_shade / model_e_shade_json) so the live forward record
    can settle it, and excluded from the validated slip's risk total. Do not merge into
    compute_bet without a window that actually validates it.
    """
    if model_e_home_prob is None or market_home_prob is None:
        return None
    # never shadow a real bet
    if compute_bet(model_e_home_prob, market_home_prob, home_abbr, away_abbr,
                   book_prices=book_prices, live_odds=live_odds) is not None:
        return None
    market_favors_home = market_home_prob >= 0.5
    dog_side = "away" if market_favors_home else "home"
    p_model = (1 - model_e_home_prob) if market_favors_home else model_e_home_prob
    p_mkt = (1 - market_home_prob) if market_favors_home else market_home_prob
    shade = p_model - p_mkt
    # No upper bound on p_model: compute_bet above already claimed every bet it will take, so
    # anything reaching here is by definition not a validated bet. Without this, dogs the model
    # rates 50-52% (its STRONGEST dog reads that still miss the flip rule) fell through both
    # functions and produced nothing at all -- a blind spot, not a decision. Found 2026-08-21
    # when CLE@COL sat at 51.2% and vanished from the board entirely.
    if shade < SHADE_MIN_EDGE:
        return None
    price, book, dec = _best_price(book_prices, dog_side)
    if price is None and live_odds and live_odds.get(dog_side) is not None:
        price, book, dec = live_odds[dog_side], live_odds.get("bookmaker"), american_to_decimal(live_odds[dog_side])
    if dec is None:
        return None
    b = dec - 1.0
    ev_pct = round((p_model * dec - 1.0) * 100, 2)
    if ev_pct < MIN_EV_PCT:
        return None
    kelly_full = max(0.0, (b * p_model - (1 - p_model)) / b)
    bet = {
        "side": away_abbr if dog_side == "away" else home_abbr, "side_is_home": dog_side == "home",
        "type": "shade", "unproven": True,
        "model_prob": round(p_model, 4), "market_prob": round(p_mkt, 4), "edge": round(shade, 4),
        "best_price": price, "best_book": book, "fair_price": decimal_to_american(1 / p_model),
        "ev_pct": ev_pct, "kelly_full": round(kelly_full, 4),
        "stake_units": round(min(MAX_STAKE_UNITS, KELLY_FRACTION * kelly_full * BANKROLL_UNITS), 2),
    }
    prev = previous_bet or {}
    if prev.get("first_seen_at") and prev.get("side") == bet["side"]:
        for k in ("first_seen_at", "first_seen_market_prob", "first_seen_price", "first_seen_book"):
            bet[k] = prev.get(k)
    else:
        from datetime import datetime, timezone
        bet["first_seen_at"] = datetime.now(timezone.utc).isoformat()
        bet["first_seen_market_prob"] = round(p_mkt, 4)
        bet["first_seen_price"] = price
        bet["first_seen_book"] = book
    return bet


def grade_bet(bet: dict, home_won: bool) -> dict:
    """Profit in units for a settled bet at its logged best price, plus CLV in probability points
    (positive = the market moved toward our side between first flag and close)."""
    won = bool(home_won) if bet.get("side_is_home") else not bool(home_won)
    stake = bet.get("stake_units") or 0.0
    dec = american_to_decimal(bet.get("best_price"))
    profit = (stake * (dec - 1.0) if won else -stake) if dec is not None else None
    clv = None
    if bet.get("first_seen_market_prob") is not None and bet.get("market_prob") is not None:
        clv = round(bet["market_prob"] - bet["first_seen_market_prob"], 4)
    return {"won": won, "profit_units": round(profit, 3) if profit is not None else None, "clv": clv}


def load_validation() -> dict | None:
    if not os.path.exists(MODEL_E_VALIDATION_PATH):
        return None
    with open(MODEL_E_VALIDATION_PATH) as f:
        return json.load(f)


# ============================================================================================
# Per-feature explanation -- "which features are actually pushing this bet"
# ============================================================================================

def explain(feature_row: pd.DataFrame, top_n: int = None) -> list[dict] | None:
    """Per-feature contribution to Model E's prediction for one game, in log-odds (margin) space.

    Uses XGBoost's own pred_contribs on every booster behind the ensemble -- 5 seeds x the
    CalibratedClassifierCV folds inside each -- and averages them, so the numbers correspond to
    the probability actually served rather than to one arbitrary seed. Same technique as
    _model_a_shap_scan.py, just averaged over the ensemble instead of reading seed 42.

    Returns [{feature, value, contribution, favors}] sorted by |contribution| descending, where
    positive contribution pushes toward the HOME team. None if the model isn't trained.

    Exists because feature_breakdown only carries rating_system's category rollups, not the 13
    raw columns Model E runs on -- so a bet could not be traced to the features driving it
    (found 2026-08-22 on TOR@NYY, where the F5/E reads looked wrong against Cease and there was
    no way to see which inputs were responsible).
    """
    models, medians, _ = model_module.load_model_ensemble(MODEL_E_PATH)
    if models is None:
        return None
    import xgboost as xgb

    X = feature_row[MODEL_E_FEATURE_COLUMNS].fillna(medians)
    dm = xgb.DMatrix(X, feature_names=list(MODEL_E_FEATURE_COLUMNS))
    totals = np.zeros(len(MODEL_E_FEATURE_COLUMNS), dtype=float)
    n = 0
    for m in models:
        for cc in getattr(m, "calibrated_classifiers_", []):
            est = getattr(cc, "estimator", None)
            if est is None:
                continue
            try:
                contribs = est.get_booster().predict(dm, pred_contribs=True)
            except Exception:
                continue
            totals += np.asarray(contribs)[0][:-1]   # last column is the bias term
            n += 1
    if not n:
        return None
    totals /= n
    out = []
    for col, contrib in zip(MODEL_E_FEATURE_COLUMNS, totals):
        raw = feature_row[col].iloc[0] if col in feature_row else None
        try:
            raw = None if raw is None or (isinstance(raw, float) and math.isnan(raw)) else round(float(raw), 4)
        except (TypeError, ValueError):
            raw = None
        out.append({"feature": col, "value": raw, "contribution": round(float(contrib), 5),
                    "favors": "home" if contrib > 0 else "away" if contrib < 0 else "neutral"})
    out.sort(key=lambda r: -abs(r["contribution"]))
    return out[:top_n] if top_n else out


# The market columns Model E genuinely depends on. Its 13 baseball features were selected for
# what they add ON TOP OF a market price -- starter quality (FIP, K-BB%, recent FIP, HR/9) was
# pruned precisely because the market already prices it. With these absent, E is a market-aware
# model with the market removed: it kept the complements and dropped the load-bearing baseball
# stats, so it will happily produce a confident number built on bullpen/lineup/defense alone.
#
# Real failure 2026-08-22, NYM@CWS: Castillo (4.99 ERA, 5.74 recent FIP, 2.28 recent HR/9) vs
# Scott (3.51 / 2.42 / 0.36). E had the White Sox at 68% and staked 5u on a market-feature-less
# row; the White Sox lost. 19 of 80 tracked game-days (23.8%) had all five of these missing at the
# final pre-game snapshot, so this is common, not a freak event.
#
# NOTE this cannot be measured in the backtest: the training data only yields a bet when
# consensus_prob_diff exists, so every backtested bet has a full market block by construction
# (2,219 of 2,221). It is a live-only failure mode -- see _missing_market_study.py.
CORE_MARKET_COLUMNS = ["consensus_prob_diff", "consensus_median_diff", "book_disagreement",
                       "book_prob_std", "book_favor_diff"]


def core_market_present(feature_row) -> bool:
    """True when Model E has the market features it was built to complement."""
    try:
        for c in CORE_MARKET_COLUMNS:
            if c not in feature_row:
                return False
            v = feature_row[c].iloc[0]
            if v is None or (isinstance(v, float) and math.isnan(v)) or pd.isna(v):
                return False
        return True
    except Exception:
        return False
