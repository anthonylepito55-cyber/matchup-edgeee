"""
prediction_log.py

Logs every prediction the app actually serves and settles it against the
real final score once the game is over — a genuine forward-test record,
distinct from the historical walk-forward backtest. Backtesting can be
subtly optimistic (data-prep quirks, hindsight in how features were built);
this can't be, since predictions are logged before the outcome is known.

Each row: one game's prediction, keyed by (date, game_pk). Settled lazily —
call settle_predictions() any time to backfill actual results for games
that have gone Final since they were logged.
"""

import os
import json
import math
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime

from data_collection import CACHE_DIR, MLB_STATS_API
from odds_fetcher import devig_home_prob as _devig_home_prob

LOG_PATH = os.path.join(CACHE_DIR, "prediction_log.parquet")
# Precomputed by compute_clv_backtest_cache.py — a full walk-forward retrain is far too slow to
# run inside a request, so this is a static snapshot, occasionally refreshed manually, not a
# per-request computation like the rest of this file. Lives in model_artifacts/, NOT data_cache/
# (data_cache/ is gitignored -- Railway never sees it -- while model_artifacts/ is deliberately
# committed, same reason the trained model files themselves are: no retrain-on-deploy step).
CLV_BACKTEST_CACHE_PATH = os.path.join(os.path.dirname(__file__), "model_artifacts", "clv_backtest_summary.json")

# Shared with main.py: a game only gets a fresh live-computed prediction while
# it's in one of these states — once it's started, main.py serves the frozen
# logged prediction instead (see get_logged_prediction below for why).
PRE_GAME_STATUSES = {"Scheduled", "Pre-Game", "Warmup"}

LOG_COLUMNS = [
    "date", "game_pk", "home_team_abbr", "away_team_abbr",
    "home_pitcher_name", "away_pitcher_name",
    "home_pitcher_id", "away_pitcher_id",  # needed to look up this game's frozen strikeout/IP/ER
    # prop predictions (see strikeout_prediction_log.get_logged_*, keyed by (date, game_pk, pitcher_id))
    # from get_games_for_date -- those props were already being frozen in their own log, just never
    # joined back in for the previous-day tab.
    "venue", "game_time_utc",  # display-only metadata, cheap to keep
    # NOTE the naming trap here: despite its name, "model_home_win_prob" has always held the
    # FINAL/displayed probability (after _apply_confidence_override), not the raw pre-override
    # model output — log_predictions below reads pred.get("home_win_prob"), not
    # pred.get("model_home_win_prob"), into this column. Every existing reader (settle_predictions,
    # get_track_record, get_logged_prediction, get_games_for_date) depends on that FINAL-value
    # behavior, so the column is kept as-is rather than renamed. raw_model_home_win_prob below is
    # the actual pre-override value, added after discovering it was being silently dropped —
    # every overridden row logged before this fix has no recoverable raw counterfactual.
    "model_home_win_prob", "raw_model_home_win_prob", "overridden", "reason",
    "recent_form_json", "last3_form_json", "season_stats_json", "team_stats_json", "lineup_breakdown_json",  # pre-game snapshot of the display breakdown, see get_logged_prediction
    "rating_breakdown_json",  # pre-game snapshot of the display-only composite rating system's category breakdown — see rating_system.py; NOT used as a model input, purely for the previous-day tab to show alongside the actual prediction
    "feature_breakdown_json",  # pre-game snapshot of every individual raw diff feature behind rating_breakdown_json's category rollups — see rating_system.feature_level_breakdown; same non-model, display-only status
    "market_home_prob",       # de-vigged implied home win prob from live_odds at prediction time, if available
    "market_model_prob",      # Model B's own (market-inclusive) probability, distinct from market_home_prob above (which is the raw devigged odds line, not a model output)
    "model_c_prob",           # Model C's own probability (baseball + the 6-book real-time-tracked market block) -- comparison-only like market_model_prob, never drives the primary prediction; see main.py
    "value_bet_json",         # {side, type, model_prob, market_prob} from main._compute_value_bet, or None -- frozen for the same reason market_model_prob is (recomputing live for a decided game would use the live_odds line at request time, not the price actually offered pre-game)
    "model_e_prob",           # Model E's calibrated probability (see model_e.py) -- comparison/betting only, never drives the primary prediction
    "model_e_bet_json",       # model_e.compute_bet output (side/type/best price/stake/first-seen price), frozen like value_bet_json; graded by get_model_e_track_record
    "model_e_baseball_prob",  # Model E's market-blind leg (same 13 factors, no market) -- comparison vs Model A only, never bets
    "model_e_shade_json",     # model_e.compute_shade_bet -- UNPROVEN dog-shade signal, logged separately so the forward record can settle it; never part of the validated slip
    "model_omega_bet_json",   # Omega SHADOW bettor (model_e.compute_omega_prob + compute_bet) -- Jacob's market-anchored model graded through the identical pipeline as Model E, logged/settled separately so E-vs-Omega has one shared scoreboard; never on the slip
    "model_omega_prob",       # Omega's own probability at freeze time -- displayed under Model E on the game card, frozen like every other model prob
    "jacob_book_bet_json",    # Jacob's live BOOK pick for this game (proxied from the clone on :8080, kept picks only), frozen pre-game and settled through Model E's grading so his card's certification claims finally face neutral grading
    "model_f5_prob",          # F5 model's P(home leads after 5 innings) -- see model_f5.py; comparison/betting only
    "f5_market_home_prob",    # de-vigged consensus F5 ("1st Half Moneyline") home prob at freeze time -- see odds_fetcher.get_f5_odds
    "model_f5_bet_json",      # model_e.compute_bet output against the F5 market price, or None; graded by get_model_f5_track_record
    "f5_settled", "f5_home_runs", "f5_away_runs", "f5_home_won",  # first-5-innings result (f5_home_won None = tied after 5 = push), via settle_f5
    "live_odds_json", "book_odds_json",  # the moneyline pair and the full multi-book consensus panel, frozen at prediction time -- these are point-in-time market snapshots, showing "current" odds for a past game would be actively misleading
    "prediction_market_odds_json",  # {book: devigged_home_prob} for Kalshi/Polymarket -- same point-in-time-snapshot reasoning as book_odds_json above, just for prediction-market exchanges instead of sportsbooks
    "h2h_json",                # this pitcher-vs-opponent head-to-head history -- previously nulled for decided games (see main.py's old h2h_out leakage comment) since there was nowhere to freeze it; now captured like everything else here
    "simulation_json",         # the Monte Carlo run-distribution output (win_prob_home/projected_total/projected_spread/etc.) -- same previously-nulled-for-decided-games gap as h2h above
    "injuries_json", "pitcher_warnings_json", "data_quality_json",
    "opener_affected", "note",
    "logged_at",
    "settled", "home_score", "away_score", "home_won", "correct",
]


def _read_parquet_log(path: str, columns: list[str]) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_parquet(path)
    except Exception as e:
        # A genuinely corrupted log is a much bigger deal than a corrupted re-fetchable cache
        # (see data_collection._load_or_fetch's same fix) — this is irreplaceable forward-test
        # history, not something a live re-fetch can regenerate. So this does NOT silently fall
        # back to an empty log the way a cache miss would; it fails loudly so the corruption gets
        # noticed and investigated rather than quietly starting the track record over from zero.
        raise RuntimeError(
            f"{path} exists but failed to read ({e!r}) — this is the real "
            "forward-test history, not a re-fetchable cache. Investigate before doing anything "
            "that might overwrite it; do not delete/recreate without recovering the data first."
        ) from e
    for col in columns:  # backfill gracefully if reading a file written before a column existed
        if col not in df.columns:
            df[col] = None
    return df


def _write_parquet_atomic(df: pd.DataFrame, path: str):
    # Atomic write (temp file + os.replace) — same fix and same reasoning as
    # data_collection._load_or_fetch: a direct df.to_parquet(path) truncates the destination
    # before writing, so two concurrent writers (this app logs/settles on every /api/today
    # request, and FastAPI runs requests in parallel threads) can interleave and corrupt the
    # file. Confirmed as the actual cause of a real corruption incident this session — see
    # recover_prediction_log.py for how that got recovered from cached API responses.
    #
    # Retry + fallback for the SAME reason data_collection._load_or_fetch has one: data_cache
    # lives under OneDrive, whose sync engine transiently interferes with just-created temp files
    # (PermissionError/WinError 5 if locked mid-sync, FileNotFoundError/WinError 2 if OneDrive
    # grabbed the tmp file before os.replace could run) — confirmed live. This file is the
    # irreplaceable one, so on repeated failure it falls back to a direct write rather than losing
    # today's predictions to a crash — accepting the original rare read-race back as a much
    # smaller risk than silently never logging a slate.
    tmp_path = f"{path}.{os.getpid()}.{time.time_ns()}.tmp"
    for attempt in range(5):
        try:
            df.to_parquet(tmp_path)
            os.replace(tmp_path, path)
            return
        except OSError:
            if attempt == 4:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                df.to_parquet(path)
                return
            time.sleep(0.2 * (attempt + 1))


def _read_log() -> pd.DataFrame:
    return _read_parquet_log(LOG_PATH, LOG_COLUMNS)


def _write_log(df: pd.DataFrame):
    _write_parquet_atomic(df, LOG_PATH)


def log_predictions(date: str, games: list[dict]):
    """
    Upserts one row per game that has a real prediction (skips TBD/
    unpredicted games). Only logs/updates games that haven't started yet
    (status is a pre-game state) — this is what makes the log a genuine
    forward test: a prediction is only ever recorded/updated before the
    outcome is knowable, never after (logging a decided game would
    silently mix hindsight into what's supposed to be a blind record).

    Keeps UPDATING an existing pre-game row on every call, right up until
    the game leaves a pre-game status — it does not freeze on the first
    glance. A game's probable pitchers are often announced the night
    before, so the first time this ever sees a given game can be many
    hours before first pitch, well before the confirmed lineup, same-day
    bullpen usage, or updated rest days are known. Locking onto that first,
    least-informed snapshot and never updating it meant the "official"
    prediction could be materially staler than what the model actually
    believed by game time — caught directly from a real case: a
    prediction logged at 11:21pm the night before a game stayed frozen at
    that stale value even though the live number visibly moved during the
    game-day as better information came in, and once the game started, the
    display reverted to that stale original instead of the last, best
    pre-game read. Once a game leaves a pre-game status, the guard below
    (`status not in PRE_GAME_STATUSES`) naturally stops any further
    updates — that's the real, correct freeze point, not "first request
    ever."
    """
    log = _read_log()
    existing_by_key = (
        {(r["date"], r["game_pk"]): i for i, r in log.iterrows()} if not log.empty else {}
    )

    new_rows = []
    updates = {}  # index -> row dict
    for g in games:
        pred = g.get("prediction")
        game_pk = g.get("game_pk")
        if pred is None or game_pk is None:
            continue
        if g.get("status") not in PRE_GAME_STATUSES:
            continue

        live_odds = g.get("live_odds")
        market_home_prob = (
            _devig_home_prob(live_odds["home"], live_odds["away"]) if live_odds else None
        )

        def _j(key):
            val = g.get(key)
            return json.dumps(val) if val else None

        row = {
            "date": date, "game_pk": game_pk,
            "home_team_abbr": g.get("home_team_abbr"), "away_team_abbr": g.get("away_team_abbr"),
            "home_pitcher_name": g.get("home_pitcher_name"), "away_pitcher_name": g.get("away_pitcher_name"),
            "home_pitcher_id": g.get("home_pitcher_id"), "away_pitcher_id": g.get("away_pitcher_id"),
            "venue": g.get("venue"), "game_time_utc": g.get("game_time_utc"),
            "model_home_win_prob": pred.get("home_win_prob"),
            "raw_model_home_win_prob": pred.get("model_home_win_prob"),
            "overridden": pred.get("overridden", False),
            "reason": g.get("reason"),
            "recent_form_json": _j("recent_form"),
            "last3_form_json": _j("last3_form"),
            "season_stats_json": _j("season_stats"),
            "team_stats_json": _j("team_stats"),
            "lineup_breakdown_json": _j("lineup_breakdown"),
            "rating_breakdown_json": _j("rating_breakdown"),
            "feature_breakdown_json": _j("feature_breakdown"),
            "market_home_prob": market_home_prob,
            "market_model_prob": g.get("market_model_prob"),
            "model_c_prob": g.get("model_c_prob"),
            "value_bet_json": _j("value_bet"),
            "model_e_prob": g.get("model_e_prob"),
            "model_e_bet_json": _j("model_e_bet"),
            "model_e_baseball_prob": g.get("model_e_baseball_prob"),
            "model_e_shade_json": _j("model_e_shade"),
            "model_omega_bet_json": _j("model_omega_bet"),
            "model_omega_prob": g.get("model_omega_prob"),
            "jacob_book_bet_json": _j("jacob_book_bet"),
            "model_f5_prob": g.get("model_f5_prob"),
            "f5_market_home_prob": (g.get("f5_odds") or {}).get("home_prob"),
            "model_f5_bet_json": _j("model_f5_bet"),
            "live_odds_json": _j("live_odds"),
            "book_odds_json": _j("book_odds"),
            "prediction_market_odds_json": _j("prediction_market_odds"),
            "h2h_json": _j("h2h"),
            "simulation_json": _j("simulation"),
            "injuries_json": _j("injuries"),
            "pitcher_warnings_json": _j("pitcher_warnings"),
            "data_quality_json": _j("data_quality"),
            "opener_affected": g.get("opener_affected", False),
            "note": g.get("note"),
            "logged_at": datetime.now().isoformat(),
        }

        key = (date, game_pk)
        if key in existing_by_key:
            updates[existing_by_key[key]] = row
        else:
            new_rows.append({
                **row,
                "settled": False, "home_score": None, "away_score": None, "home_won": None, "correct": None,
                "f5_settled": False, "f5_home_runs": None, "f5_away_runs": None, "f5_home_won": None,
            })

    if not new_rows and not updates:
        return
    if updates:
        for idx, row in updates.items():
            for col, val in row.items():
                log.at[idx, col] = val
    if new_rows:
        log = pd.concat([log, pd.DataFrame(new_rows)], ignore_index=True)
    _write_log(log)


HISTORY_PATH = os.path.join(CACHE_DIR, "prediction_history.parquet")

HISTORY_COLUMNS = [
    "logged_at", "date", "game_pk", "home_team_abbr", "away_team_abbr",
    "status", "model_home_win_prob", "market_model_prob", "market_home_prob",
    "live_odds_json", "completeness_pct", "missing_features_json",
]

# Fields compared to decide whether a new snapshot is actually worth appending — see
# log_prediction_history's docstring on why this is diff-triggered rather than one row per call.
_HISTORY_DIFF_FIELDS = ["model_home_win_prob", "market_model_prob", "market_home_prob", "completeness_pct"]


def log_prediction_history(date: str, games: list[dict]):
    """
    Append-only companion to log_predictions above — exists specifically to answer "what was
    this number an hour/a night ago, and what changed" after the fact, which the upserting main
    log can't: it only ever keeps the single latest pre-game snapshot, so once a value is
    overwritten there's no way to recover what it used to be. Real, repeated need this session
    (a user-reported number from "last night" with no way to confirm what actually changed vs.
    what I could only infer from timing).

    Diff-triggered, not one row per call: this fires alongside log_predictions on every /api/today
    request (which can be every ~1 minute via the frontend's auto-refresh, for hours pregame,
    across ~15 games/day) — logging unconditionally would mean thousands of near-duplicate rows
    per game for a value that usually hasn't actually moved. A new row is only appended when
    model_home_win_prob, market_model_prob, market_home_prob, or data-completeness differs from
    the last recorded snapshot for that (date, game_pk) — so the table stays proportional to how
    often things actually changed, while still capturing every real movement with a timestamp.

    Same pre-game-only scope as log_predictions (skips TBD games and anything already decided) —
    this is a history of the forward-test log's own values, not a separate tracking mechanism.
    """
    hist = _read_parquet_log(HISTORY_PATH, HISTORY_COLUMNS)
    last_by_key = {}
    if not hist.empty:
        for (d, pk), sub in hist.groupby(["date", "game_pk"]):
            last_by_key[(d, pk)] = sub.iloc[sub["logged_at"].values.argmax()]

    new_rows = []
    for g in games:
        pred = g.get("prediction")
        game_pk = g.get("game_pk")
        if pred is None or game_pk is None:
            continue
        if g.get("status") not in PRE_GAME_STATUSES:
            continue

        live_odds = g.get("live_odds")
        market_home_prob = (
            _devig_home_prob(live_odds["home"], live_odds["away"]) if live_odds else None
        )
        data_quality = g.get("data_quality") or {}

        row = {
            "logged_at": datetime.now().isoformat(),
            "date": date, "game_pk": game_pk,
            "home_team_abbr": g.get("home_team_abbr"), "away_team_abbr": g.get("away_team_abbr"),
            "status": g.get("status"),
            "model_home_win_prob": pred.get("home_win_prob"),
            "market_model_prob": g.get("market_model_prob"),
            "market_home_prob": market_home_prob,
            "live_odds_json": json.dumps(live_odds) if live_odds else None,
            "completeness_pct": data_quality.get("completeness_pct"),
            "missing_features_json": json.dumps(data_quality.get("missing_features")) if data_quality.get("missing_features") else None,
        }

        key = (date, game_pk)
        last = last_by_key.get(key)
        changed = last is None or any(
            not _values_equal(last.get(f), row.get(f)) for f in _HISTORY_DIFF_FIELDS
        )
        if changed:
            new_rows.append(row)

    if not new_rows:
        return
    hist = pd.concat([hist, pd.DataFrame(new_rows)], ignore_index=True)
    _write_parquet_atomic(hist, HISTORY_PATH)


def _values_equal(a, b) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        if isinstance(a, float) or isinstance(b, float):
            return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        pass
    return a == b


def get_prediction_history(game_pk: int, date: str = None) -> list[dict]:
    """Every recorded snapshot for one game, oldest first — the actual answer to "what was this
    at some point in the past and when did it change," instead of reconstructing it after the
    fact. Empty list if nothing was ever logged (e.g. the game was never in a pre-game state
    while the app was polling, or logging only started after this feature shipped)."""
    hist = _read_parquet_log(HISTORY_PATH, HISTORY_COLUMNS)
    if hist.empty:
        return []
    sub = hist[hist["game_pk"] == game_pk]
    if date:
        sub = sub[sub["date"] == date]
    sub = sub.sort_values("logged_at")

    def _num(val):
        """NaN -> None. A snapshot taken before the moneyline posted stores market_home_prob as
        NaN, and NaN is not valid JSON -- FastAPI's encoder raised
        "Out of range float values are not JSON compliant", 500-ing this endpoint for every game
        that was first seen before its odds went up (i.e. most of them). Found 2026-08-21."""
        if val is None:
            return None
        try:
            f = float(val)
        except (TypeError, ValueError):
            return None
        return None if (math.isnan(f) or math.isinf(f)) else f

    out = []
    for _, r in sub.iterrows():
        out.append({
            "logged_at": r["logged_at"], "status": r["status"],
            "model_home_win_prob": _num(r["model_home_win_prob"]),
            "market_model_prob": _num(r["market_model_prob"]),
            "market_home_prob": _num(r["market_home_prob"]),
            "live_odds": json.loads(r["live_odds_json"]) if r.get("live_odds_json") else None,
            "completeness_pct": _num(r["completeness_pct"]),
            "missing_features": json.loads(r["missing_features_json"]) if r.get("missing_features_json") else None,
        })
    return out


def get_logged_prediction(date: str, game_pk: int) -> dict | None:
    """
    The frozen, pre-game snapshot for one game, if it was logged — for
    redisplaying an already-started/decided game without silently
    recomputing anything live. Recomputing live for a game that's already
    underway or Final is a real leakage bug, not just a display quirk: a
    starter's "recent form" naturally comes to include their OWN start in
    the very game being redisplayed once enough time passes, so a fresh
    computation can end up using that game's own outcome as an input to
    "predict" it — caught directly from a case where a pitcher's
    last_start_date had already rolled forward to today's date on a replay
    of today's own game.

    This covers more than the raw win probability: `reason`, `recent_form`,
    and `season_stats` are also frozen from the same pre-game snapshot.
    Freezing only the probability while still live-recomputing the reason
    text and stat breakdown caused a real, confirmed bug — the reason could
    end up citing whichever team a *later*, contaminated live recompute
    favored, flatly contradicting the frozen probability shown right next
    to it (e.g. "54% home favored" next to a reason praising the away
    pitcher's recent form). Returns None if nothing was logged (e.g. the
    logging call failed, or predictions haven't accumulated for this date
    yet), so callers should fall back to live computation in that case.
    """
    log = _read_log()
    if log.empty:
        return None
    row = log[(log["date"] == date) & (log["game_pk"] == game_pk)]
    if row.empty:
        return None
    r = row.iloc[0]
    home_prob = r["model_home_win_prob"]  # despite the name, this is the FINAL/displayed prob — see LOG_COLUMNS
    if home_prob is None or pd.isna(home_prob):
        return None

    def _load_json(col):
        val = r.get(col) if hasattr(r, "get") else r[col]
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        try:
            return json.loads(val)
        except (TypeError, ValueError):
            return None

    raw_prob = r.get("raw_model_home_win_prob") if hasattr(r, "get") else r["raw_model_home_win_prob"]
    # Rows logged before raw_model_home_win_prob existed have no recoverable true raw value —
    # showing the final value in its place (as this used to do) silently mislabels an overridden
    # number as "what the model said before adjustment," which is wrong for exactly the rows
    # where it matters. Honest missing data beats a plausible-looking wrong number.
    raw_prob_out = float(raw_prob) if raw_prob is not None and pd.notna(raw_prob) else None

    return {
        "home_win_prob": float(home_prob),
        "away_win_prob": round(1 - float(home_prob), 4),
        "model_home_win_prob": raw_prob_out,
        "overridden": bool(r["overridden"]) if pd.notna(r["overridden"]) else False,
        "reason": r["reason"] if pd.notna(r["reason"]) else None,
        "recent_form": _load_json("recent_form_json"),
        "last3_form": _load_json("last3_form_json"),
        "season_stats": _load_json("season_stats_json"),
        "team_stats": _load_json("team_stats_json"),
        "lineup_breakdown": _load_json("lineup_breakdown_json"),
        "rating_breakdown": _load_json("rating_breakdown_json"),
        "feature_breakdown": _load_json("feature_breakdown_json"),
        "market_model_prob": r.get("market_model_prob") if pd.notna(r.get("market_model_prob")) else None,
        "model_c_prob": r.get("model_c_prob") if pd.notna(r.get("model_c_prob")) else None,
        "value_bet": _load_json("value_bet_json"),
        "model_e_prob": r.get("model_e_prob") if pd.notna(r.get("model_e_prob")) else None,
        "model_e_bet": _load_json("model_e_bet_json"),
        "model_e_baseball_prob": r.get("model_e_baseball_prob") if pd.notna(r.get("model_e_baseball_prob")) else None,
        "model_e_shade": _load_json("model_e_shade_json"),
        "model_omega_bet": _load_json("model_omega_bet_json"),
        "model_omega_prob": r.get("model_omega_prob") if pd.notna(r.get("model_omega_prob")) else None,
        "jacob_book_bet": _load_json("jacob_book_bet_json"),
        "model_f5_prob": r.get("model_f5_prob") if pd.notna(r.get("model_f5_prob")) else None,
        "f5_market_home_prob": r.get("f5_market_home_prob") if pd.notna(r.get("f5_market_home_prob")) else None,
        "model_f5_bet": _load_json("model_f5_bet_json"),
        "live_odds": _load_json("live_odds_json"),
        "book_odds": _load_json("book_odds_json"),
        "prediction_market_odds": _load_json("prediction_market_odds_json"),
        "h2h": _load_json("h2h_json"),
        "simulation": _load_json("simulation_json"),
        "injuries": _load_json("injuries_json"),
        "pitcher_warnings": _load_json("pitcher_warnings_json"),
        "data_quality": _load_json("data_quality_json"),
    }


def settle_predictions(max_dates: int = 14):
    """
    Fills in actual results for any unsettled log rows. Looks at the most
    recent `max_dates` distinct dates with unsettled rows (no point
    re-checking a game from months ago that's clearly done and clearly
    already settled) and pulls final scores from the MLB schedule API.
    """
    log = _read_log()
    if log.empty:
        return
    unsettled = log[log["settled"] == False]  # noqa: E712
    if unsettled.empty:
        return

    dates = sorted(unsettled["date"].unique())[-max_dates:]
    for date in dates:
        try:
            resp = requests.get(f"{MLB_STATS_API}/schedule", params={"sportId": 1, "date": date}, timeout=15)
            resp.raise_for_status()
            games_today = resp.json().get("dates", [{}])[0].get("games", [])
        except (requests.exceptions.RequestException, IndexError):
            continue

        results_by_pk = {}
        for g in games_today:
            if g.get("status", {}).get("detailedState") != "Final":
                continue
            home_score = g.get("teams", {}).get("home", {}).get("score")
            away_score = g.get("teams", {}).get("away", {}).get("score")
            if home_score is None or away_score is None:
                continue
            results_by_pk[g["gamePk"]] = (home_score, away_score)

        for idx in log[(log["date"] == date) & (log["settled"] == False)].index:  # noqa: E712
            game_pk = log.at[idx, "game_pk"]
            if game_pk not in results_by_pk:
                continue
            home_score, away_score = results_by_pk[game_pk]
            home_won = home_score > away_score
            model_prob = log.at[idx, "model_home_win_prob"]
            predicted_home = model_prob is not None and model_prob >= 0.5
            log.at[idx, "home_score"] = home_score
            log.at[idx, "away_score"] = away_score
            log.at[idx, "home_won"] = home_won
            log.at[idx, "correct"] = (predicted_home == home_won)
            log.at[idx, "settled"] = True

    _write_log(log)


def get_track_record() -> dict:
    """
    Summary + recent rows for display. `brier` here is computed on the FINAL/displayed
    model_home_win_prob (post-override, if one fired — see LOG_COLUMNS' note on that column's
    name) against the actual outcome. That's the right number for "how did the app's real,
    served predictions do" — this is genuine forward accuracy, not a backtest number, so it's
    the number to trust most once enough games have accumulated (a handful of games is still
    mostly noise; treat this as a slow-growing signal, not a verdict after day one). It is NOT a
    clean read on the raw model in isolation — see raw_model_home_win_prob for that.
    """
    log = _read_log()
    settled = log[log["settled"] == True]  # noqa: E712
    if settled.empty:
        return {"total": 0, "correct": 0, "accuracy": None, "brier": None, "recent": []}

    correct = int(settled["correct"].sum())
    total = len(settled)
    probs = settled["model_home_win_prob"].astype(float)
    outcomes = settled["home_won"].astype(float)
    brier = float(np.mean((probs - outcomes) ** 2))

    recent = settled.sort_values("date", ascending=False).head(30)
    recent_out = [
        {
            "date": r["date"], "matchup": f"{r['away_team_abbr']}@{r['home_team_abbr']}",
            "home_win_prob": r["model_home_win_prob"], "home_score": r["home_score"], "away_score": r["away_score"],
            "correct": bool(r["correct"]),
        }
        for _, r in recent.iterrows()
    ]

    return {"total": total, "correct": correct, "accuracy": round(correct / total, 4), "brier": round(brier, 4), "recent": recent_out}


# Same bucket boundaries used in the backtest analysis (analyze_model_a_clv.py) this is the real
# forward-test counterpart to -- kept identical so the two numbers are directly comparable as the
# live sample grows.
CLV_EDGE_BUCKETS = (0.0, 0.05, 0.10, 0.15)


def get_clv_track_record() -> dict:
    """
    Real forward test of "does betting the model against the market actually work" -- not a
    backtest. Every settled row already has model_home_win_prob (the served prediction) and
    market_home_prob (de-vigged live odds, frozen at prediction time, same field the previous-day
    tab already shows) -- both captured before the outcome was known, so this is a genuine blind
    record, same discipline as get_track_record/get_user_track_record.

    Buckets by |model - market| edge (see CLV_EDGE_BUCKETS): for each threshold, "does the
    model's pick actually land more often than a coin flip when it disagrees with the market by
    at least this much." This directly mirrors analyze_model_a_clv.py's backtest methodology, so
    the two can be compared honestly over time -- the backtest says what the edge USED to look
    like across historical data; this says what it's actually doing since it started being
    tracked. Grows slowly (one slate a day), so early reads are mostly noise -- same caveat as
    every other track record in this app.

    Also returns "historical_backtest" (from compute_clv_backtest_cache.py's static JSON cache,
    None if that hasn't been run) -- the two are DIFFERENT methodologies (fold-retrained model on
    old data vs. the literal model that was live that day) and are kept as separate labeled
    fields rather than merged into one number, specifically so a real divergence between them
    (which is exactly what showed up the first time this was built -- 62% backtest vs 50% live on
    a small early sample) stays visible instead of getting averaged away.
    """
    historical_backtest = None
    if os.path.exists(CLV_BACKTEST_CACHE_PATH):
        try:
            with open(CLV_BACKTEST_CACHE_PATH) as f:
                historical_backtest = json.load(f)
        except (OSError, ValueError):
            historical_backtest = None

    log = _read_log()
    settled = log[log["settled"] == True]  # noqa: E712
    matched = settled[settled["market_home_prob"].notna() & settled["model_home_win_prob"].notna()].copy()
    if matched.empty:
        return {"total": 0, "buckets": [], "recent": [], "since": None, "historical_backtest": historical_backtest}

    matched["model_home_win_prob"] = matched["model_home_win_prob"].astype(float)
    matched["market_home_prob"] = matched["market_home_prob"].astype(float)
    matched["home_won"] = matched["home_won"].astype(bool)
    matched["edge"] = matched["model_home_win_prob"] - matched["market_home_prob"]

    buckets = []
    for threshold in CLV_EDGE_BUCKETS:
        sub = matched[matched["edge"].abs() >= threshold]
        n = len(sub)
        if n == 0:
            buckets.append({"threshold": threshold, "games": 0, "correct": 0, "accuracy": None})
            continue
        model_pick_home = sub["model_home_win_prob"] >= 0.5
        correct = int((model_pick_home == sub["home_won"]).sum())
        buckets.append({
            "threshold": threshold, "games": n, "correct": correct,
            "accuracy": round(correct / n, 4),
        })

    recent = matched.sort_values("date", ascending=False).head(30)
    recent_out = [
        {
            "date": r["date"], "matchup": f"{r['away_team_abbr']}@{r['home_team_abbr']}",
            "model_home_win_prob": round(float(r["model_home_win_prob"]), 4),
            "market_home_prob": round(float(r["market_home_prob"]), 4),
            "edge": round(float(r["edge"]), 4),
            "home_won": bool(r["home_won"]),
            "correct": bool((r["model_home_win_prob"] >= 0.5) == r["home_won"]),
        }
        for _, r in recent.iterrows()
    ]

    return {
        "total": len(matched), "buckets": buckets, "recent": recent_out,
        "since": str(matched["date"].min()),
        "historical_backtest": historical_backtest,
    }


def get_available_dates() -> list[str]:
    """Every date with at least one logged prediction, most recent first — powers the
    frontend's previous-day tab so it only offers dates that actually have data."""
    log = _read_log()
    if log.empty:
        return []
    return sorted(log["date"].dropna().unique().tolist(), reverse=True)


def get_games_for_date(date: str) -> list[dict]:
    """
    Every logged prediction for one date, whatever its settlement state —
    read straight from the frozen log (never recomputed), same discipline
    as get_logged_prediction. Used by the previous-day tab so a user can
    see exactly what was predicted (and, once settled, what happened)
    without re-deriving anything live.
    """
    log = _read_log()
    day = log[log["date"] == date]
    if day.empty:
        return []

    def _load_json(row, col):
        val = row.get(col) if hasattr(row, "get") else row[col]
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        try:
            return json.loads(val)
        except (TypeError, ValueError):
            return None

    def _int_or_none(val):
        return int(val) if pd.notna(val) else None

    out = []
    for _, r in day.sort_values("game_pk").iterrows():
        out.append({
            "game_pk": int(r["game_pk"]) if pd.notna(r["game_pk"]) else None,
            "home_team_abbr": r["home_team_abbr"], "away_team_abbr": r["away_team_abbr"],
            "home_pitcher_name": r["home_pitcher_name"], "away_pitcher_name": r["away_pitcher_name"],
            "home_pitcher_id": _int_or_none(r.get("home_pitcher_id")),
            "away_pitcher_id": _int_or_none(r.get("away_pitcher_id")),
            "venue": r.get("venue") if pd.notna(r.get("venue")) else None,
            "game_time_utc": r.get("game_time_utc") if pd.notna(r.get("game_time_utc")) else None,
            "model_home_win_prob": float(r["model_home_win_prob"]) if pd.notna(r["model_home_win_prob"]) else None,
            "raw_model_home_win_prob": (
                float(r["raw_model_home_win_prob"]) if pd.notna(r["raw_model_home_win_prob"]) else None
            ),
            "overridden": bool(r["overridden"]) if pd.notna(r["overridden"]) else False,
            "market_home_prob": float(r["market_home_prob"]) if pd.notna(r["market_home_prob"]) else None,
            "market_model_prob": float(r["market_model_prob"]) if pd.notna(r.get("market_model_prob")) else None,
            "value_bet": _load_json(r, "value_bet_json"),
            "model_e_prob": float(r["model_e_prob"]) if pd.notna(r.get("model_e_prob")) else None,
            "model_e_bet": _load_json(r, "model_e_bet_json"),
            "model_e_baseball_prob": float(r["model_e_baseball_prob"]) if pd.notna(r.get("model_e_baseball_prob")) else None,
            "model_e_shade": _load_json(r, "model_e_shade_json"),
            "model_omega_bet": _load_json(r, "model_omega_bet_json"),
            "model_f5_prob": float(r["model_f5_prob"]) if pd.notna(r.get("model_f5_prob")) else None,
            "f5_market_home_prob": float(r["f5_market_home_prob"]) if pd.notna(r.get("f5_market_home_prob")) else None,
            "model_f5_bet": _load_json(r, "model_f5_bet_json"),
            "f5_home_won": (bool(r["f5_home_won"]) if pd.notna(r.get("f5_home_won")) else None),
            "reason": r.get("reason"),
            # Pre-game snapshot of each pitcher's recent-form/season stat line, frozen at
            # prediction time — same fields the live "pitcher stats" toggle shows, just
            # read back from the log instead of recomputed (recomputing here would risk
            # the exact leakage get_logged_prediction's docstring warns about: a decided
            # game's own outcome bleeding into its own "recent form").
            "recent_form": _load_json(r, "recent_form_json"),
            "last3_form": _load_json(r, "last3_form_json"),
            "season_stats": _load_json(r, "season_stats_json"),
            "team_stats": _load_json(r, "team_stats_json"),
            "lineup_breakdown": _load_json(r, "lineup_breakdown_json"),
            "rating_breakdown": _load_json(r, "rating_breakdown_json"),
            "feature_breakdown": _load_json(r, "feature_breakdown_json"),
            "live_odds": _load_json(r, "live_odds_json"),
            "book_odds": _load_json(r, "book_odds_json"),
            "prediction_market_odds": _load_json(r, "prediction_market_odds_json"),
            "h2h": _load_json(r, "h2h_json"),
            "simulation": _load_json(r, "simulation_json"),
            "injuries": _load_json(r, "injuries_json"),
            "pitcher_warnings": _load_json(r, "pitcher_warnings_json"),
            "data_quality": _load_json(r, "data_quality_json"),
            "opener_affected": bool(r.get("opener_affected")) if pd.notna(r.get("opener_affected")) else False,
            "note": r.get("note") if pd.notna(r.get("note")) else None,
            "settled": bool(r["settled"]) if pd.notna(r["settled"]) else False,
            "home_score": int(r["home_score"]) if pd.notna(r["home_score"]) else None,
            "away_score": int(r["away_score"]) if pd.notna(r["away_score"]) else None,
            "home_won": bool(r["home_won"]) if pd.notna(r["home_won"]) else None,
            "correct": bool(r["correct"]) if pd.notna(r["correct"]) else None,
        })
    return out


# ============================================================================================
# Model E (see model_e.py) -- read-side helpers. Kept here rather than in model_e.py so the
# parquet log has exactly one owner module; model_e.py never touches the file directly.
# ============================================================================================

def _records_json_safe(df: pd.DataFrame) -> list[dict]:
    """to_dict(orient="records") with NaN -> None. A column mixing None with floats (e.g. an F5
    push's clv=None next to real CLVs) gets its Nones silently coerced to NaN by pandas, and NaN
    is not valid JSON -- FastAPI's encoder raises "Out of range float values are not JSON
    compliant", 500-ing the whole endpoint (confirmed live on /api/model-f5-track-record
    2026-09-01; the Model E record carried the identical hazard in flat_profit/clv)."""
    return df.astype(object).where(pd.notna(df), None).to_dict(orient="records")


def get_logged_model_e_bet(date: str, game_pk: int) -> dict | None:
    """The model_e_bet dict currently frozen for this game (pre-game rows keep updating, so
    this is 'the latest', not 'the first') -- main.py passes it back into model_e.compute_bet as
    previous_bet so the first-seen price/probability survive each refresh."""
    log = _read_log()
    if log.empty:
        return None
    row = log[(log["date"] == date) & (log["game_pk"] == game_pk)]
    if row.empty:
        return None
    val = row.iloc[0].get("model_e_bet_json")
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return json.loads(val)
    except (TypeError, ValueError):
        return None


def get_model_e_track_record() -> dict:
    """
    Real forward record of Model E's BETS (not its predictions): every settled row that carried
    a model_e_bet at freeze time, graded at the best book price that was logged, with CLV
    (close minus first-seen market prob on our side; positive = the line moved toward us after
    we flagged it). Same blind-forward-test discipline as get_track_record: the bet, its price
    and its stake were all frozen before first pitch; nothing is recomputed here.

    ROI is on the quarter-Kelly stakes actually logged (units of a 100-unit bankroll), and also
    flat 1u per bet so stake sizing can't flatter or hide the pick quality. Grows one slate a
    day -- early reads are noise, same caveat as every other track record in this app.
    """
    import model_e  # local import: model_e imports model/features only, no cycle back here
    log = _read_log()
    settled = log[(log["settled"] == True) & log["model_e_bet_json"].notna()]  # noqa: E712
    bets = []
    for _, r in settled.iterrows():
        try:
            bet = json.loads(r["model_e_bet_json"])
        except (TypeError, ValueError):
            continue
        if not bet or r["home_won"] is None or pd.isna(r["home_won"]):
            continue
        g = model_e.grade_bet(bet, bool(r["home_won"]))
        dec = model_e.american_to_decimal(bet.get("best_price"))
        bets.append({
            "date": r["date"], "matchup": f"{r['away_team_abbr']}@{r['home_team_abbr']}",
            "side": bet.get("side"), "type": bet.get("type"),
            "model_prob": bet.get("model_prob"), "market_prob": bet.get("market_prob"),
            "best_price": bet.get("best_price"), "best_book": bet.get("best_book"),
            "stake_units": bet.get("stake_units"), "won": g["won"],
            "profit_units": g["profit_units"],
            "flat_profit": ((dec - 1.0) if g["won"] else -1.0) if dec is not None else None,
            "clv": g["clv"],
            # class inputs, frozen on the bet at bet time: dog_grade since the beginning,
            # f5_value since 2026-09-03 (it CANNOT be reconstructed at settle time -- the F5
            # model/market read that defined it is gone once the game starts). Older bets
            # without the field read None and land in fav_nof5 below, same as the frontend's
            # no-F5-read class.
            "dog_grade": bet.get("dog_grade"), "f5_value": bet.get("f5_value"),
        })
    if not bets:
        return {"total": 0, "by_type": {}, "by_class": {}, "recent": [], "since": None, "validation": model_e.load_validation()}
    df = pd.DataFrame(bets)

    def _agg(sub):
        staked = sub["stake_units"].fillna(0).sum()
        profit = sub["profit_units"].fillna(0).sum()
        flat = sub["flat_profit"].dropna()
        clv = sub["clv"].dropna()
        return {
            "n": int(len(sub)), "wins": int(sub["won"].sum()), "hit_rate": round(sub["won"].mean(), 4),
            "market_implied": round(sub["market_prob"].mean(), 4),
            "edge_pts": round(sub["won"].mean() - sub["market_prob"].mean(), 4),
            "units_staked": round(staked, 2), "units_profit": round(profit, 2),
            "roi_pct": round(100 * profit / staked, 2) if staked else None,
            "flat_roi_pct": round(100 * flat.mean(), 2) if len(flat) else None,
            "avg_clv_pts": round(100 * clv.mean(), 2) if len(clv) else None,
            "clv_positive_share": round((clv > 0).mean(), 3) if len(clv) else None,
        }

    by_type = {t: _agg(sub) for t, sub in df.groupby("type")}
    by_type["all"] = _agg(df)

    # Per-class live forward record -- the exact five classes ProfitView's class-ROI chips key
    # on (frontend commit 4715249): a chip swaps its backtest constant for this live number,
    # tagged LIVE, once the class reaches n >= 150 graded bets. Class assignment mirrors the
    # frontend's own rule verbatim: underdogs split by dog_grade (anything but "A" -> dog_b),
    # favorites split by the f5_value frozen at bet time (True/False/None -> yes/no/no-read).
    def _bet_class(r):
        if r.get("type") == "underdog":
            return "dog_a" if r.get("dog_grade") == "A" else "dog_b"
        if r.get("f5_value") is True:
            return "fav_f5yes"
        if r.get("f5_value") is False:
            return "fav_f5no"
        return "fav_nof5"

    df["bet_class"] = [_bet_class(r) for r in bets]
    by_class = {}
    for cls, sub in df.groupby("bet_class"):
        flat = sub["flat_profit"].dropna()
        by_class[cls] = {
            "n": int(len(sub)),
            "hit_rate": round(float(sub["won"].mean()), 4),
            "units_profit": round(float(sub["profit_units"].fillna(0).sum()), 2),
            "flat_roi_pct": round(100 * float(flat.mean()), 2) if len(flat) else None,
        }
    # market-blind leg vs Model A: pick accuracy on the same settled games (both frozen pre-game)
    leg = log[(log["settled"] == True) & log["model_e_baseball_prob"].notna() & log["model_home_win_prob"].notna() & log["home_won"].notna()]  # noqa: E712
    baseball_leg = None
    if len(leg):
        hw = leg["home_won"].astype(bool)
        baseball_leg = {"n": int(len(leg)),
                        "e_baseball_hit": round(float(((leg["model_e_baseball_prob"].astype(float) >= 0.5) == hw).mean()), 4),
                        "model_a_hit": round(float(((leg["model_home_win_prob"].astype(float) >= 0.5) == hw).mean()), 4),
                        "since": str(leg["date"].min())}
    recent = _records_json_safe(df.sort_values("date", ascending=False).head(40))
    # UNPROVEN dog-shade signal, graded separately (never mixed into by_type) -- see
    # model_e.compute_shade_bet for why it is tracked rather than bet.
    shade_rows = []
    for _, r in log[(log["settled"] == True) & log["model_e_shade_json"].notna()].iterrows():  # noqa: E712
        try:
            sb = json.loads(r["model_e_shade_json"])
        except (TypeError, ValueError):
            continue
        if not sb or r["home_won"] is None or pd.isna(r["home_won"]):
            continue
        g = model_e.grade_bet(sb, bool(r["home_won"]))
        dec = model_e.american_to_decimal(sb.get("best_price"))
        shade_rows.append({"won": g["won"], "profit_units": g["profit_units"], "stake_units": sb.get("stake_units"),
                           "flat": ((dec - 1.0) if g["won"] else -1.0) if dec is not None else None,
                           "market_prob": sb.get("market_prob")})
    shade = None
    if shade_rows:
        sdf = pd.DataFrame(shade_rows)
        staked = float(sdf["stake_units"].fillna(0).sum())
        shade = {"n": int(len(sdf)), "hit_rate": round(float(sdf["won"].mean()), 4),
                 "market_implied": round(float(sdf["market_prob"].mean()), 4),
                 "units_staked": round(staked, 2), "units_profit": round(float(sdf["profit_units"].fillna(0).sum()), 2),
                 "roi_pct": round(100 * float(sdf["profit_units"].fillna(0).sum()) / staked, 2) if staked else None,
                 "flat_roi_pct": round(100 * float(sdf["flat"].dropna().mean()), 2) if sdf["flat"].notna().any() else None}
    # Omega SHADOW record -- Jacob's market-anchored model graded through the identical
    # best-price/quarter-Kelly pipeline as Model E (see model_e.OMEGA_B0). Same grading code
    # path as the shade stream above; kept fully separate from by_type/by_class.
    omega_rows = []
    if "model_omega_bet_json" in log.columns:
        for _, r in log[(log["settled"] == True) & log["model_omega_bet_json"].notna()].iterrows():  # noqa: E712
            try:
                ob = json.loads(r["model_omega_bet_json"])
            except (TypeError, ValueError):
                continue
            if not ob or r["home_won"] is None or pd.isna(r["home_won"]):
                continue
            g = model_e.grade_bet(ob, bool(r["home_won"]))
            dec = model_e.american_to_decimal(ob.get("best_price"))
            omega_rows.append({"won": g["won"], "profit_units": g["profit_units"], "stake_units": ob.get("stake_units"),
                               "flat": ((dec - 1.0) if g["won"] else -1.0) if dec is not None else None,
                               "market_prob": ob.get("market_prob"), "clv": g.get("clv")})
    omega = None
    if omega_rows:
        odf = pd.DataFrame(omega_rows)
        staked = float(odf["stake_units"].fillna(0).sum())
        omega = {"n": int(len(odf)), "hit_rate": round(float(odf["won"].mean()), 4),
                 "market_implied": round(float(odf["market_prob"].mean()), 4),
                 "units_staked": round(staked, 2), "units_profit": round(float(odf["profit_units"].fillna(0).sum()), 2),
                 "roi_pct": round(100 * float(odf["profit_units"].fillna(0).sum()) / staked, 2) if staked else None,
                 "flat_roi_pct": round(100 * float(odf["flat"].dropna().mean()), 2) if odf["flat"].notna().any() else None,
                 "avg_clv_pts": round(100 * float(odf["clv"].dropna().mean()), 2) if odf["clv"].notna().any() else None}
    # Jacob's BOOK record -- his kept picks (proxied live from the clone) graded through the
    # same code path as everything else here. His stakes, our neutral settlement.
    book_rows = []
    if "jacob_book_bet_json" in log.columns:
        for _, r in log[(log["settled"] == True) & log["jacob_book_bet_json"].notna()].iterrows():  # noqa: E712
            try:
                jb = json.loads(r["jacob_book_bet_json"])
            except (TypeError, ValueError):
                continue
            if not jb or r["home_won"] is None or pd.isna(r["home_won"]):
                continue
            g = model_e.grade_bet(jb, bool(r["home_won"]))
            dec = model_e.american_to_decimal(jb.get("best_price"))
            book_rows.append({"won": g["won"], "profit_units": g["profit_units"], "stake_units": jb.get("stake_units"),
                              "flat": ((dec - 1.0) if g["won"] else -1.0) if dec is not None else None,
                              "market_prob": jb.get("market_prob"), "clv": g.get("clv")})
    jacob_book = None
    if book_rows:
        jdf = pd.DataFrame(book_rows)
        staked = float(jdf["stake_units"].fillna(0).sum())
        jacob_book = {"n": int(len(jdf)), "hit_rate": round(float(jdf["won"].mean()), 4),
                      "market_implied": round(float(jdf["market_prob"].dropna().mean()), 4) if jdf["market_prob"].notna().any() else None,
                      "units_staked": round(staked, 2), "units_profit": round(float(jdf["profit_units"].fillna(0).sum()), 2),
                      "roi_pct": round(100 * float(jdf["profit_units"].fillna(0).sum()) / staked, 2) if staked else None,
                      "flat_roi_pct": round(100 * float(jdf["flat"].dropna().mean()), 2) if jdf["flat"].notna().any() else None,
                      "avg_clv_pts": round(100 * float(jdf["clv"].dropna().mean()), 2) if jdf["clv"].notna().any() else None}
    # LIVE per-signal splits over the real settled E bets -- feeds the Profit tab's confluence
    # panel so it ranks by what has ACTUALLY happened, not backtest numbers. Flat 1u grading at
    # each bet's logged best price. Signals: line movement since first flag (toward/flat/against)
    # and whether the Omega formula would fire the same bet (e_alone vs omega_same -- the
    # 7/7-fold backtest split, now measured live).
    sig_rows = []
    for _, r in log[(log["settled"] == True) & log["model_e_bet_json"].notna()].iterrows():  # noqa: E712
        try:
            eb = json.loads(r["model_e_bet_json"])
        except (TypeError, ValueError):
            continue
        if not eb or r["home_won"] is None or pd.isna(r["home_won"]):
            continue
        g = model_e.grade_bet(eb, bool(r["home_won"]))
        dec = model_e.american_to_decimal(eb.get("best_price"))
        flat = ((dec - 1.0) if g["won"] else -1.0) if dec is not None else None
        fs, mp = eb.get("first_seen_market_prob"), eb.get("market_prob")
        move = (mp - fs) if (fs is not None and mp is not None) else None
        o_same = False
        if pd.notna(r.get("model_e_baseball_prob")) and pd.notna(r.get("market_home_prob")):
            op = model_e.compute_omega_prob(float(r["model_e_baseball_prob"]), float(r["market_home_prob"]))
            if op is not None:
                ob = model_e.compute_bet(op, float(r["market_home_prob"]),
                                         str(r["home_team_abbr"]), str(r["away_team_abbr"]))
                o_same = bool(ob and ob.get("side_is_home") == eb.get("side_is_home"))
        sig_rows.append({"flat": flat, "won": g["won"], "move": move, "o_same": o_same})

    def _agg_sig(rows):
        v = [x["flat"] for x in rows if x["flat"] is not None]
        if not v:
            return None
        return {"n": len(rows), "flat_roi_pct": round(100 * sum(v) / len(v), 2),
                "hit_rate": round(sum(1 for x in rows if x["won"]) / len(rows), 4)}

    by_signal = {
        "line_toward": _agg_sig([x for x in sig_rows if x["move"] is not None and x["move"] > 0.005]),
        "line_flat": _agg_sig([x for x in sig_rows if x["move"] is not None and abs(x["move"]) <= 0.005]),
        "line_against": _agg_sig([x for x in sig_rows if x["move"] is not None and x["move"] < -0.005]),
        "e_alone": _agg_sig([x for x in sig_rows if not x["o_same"]]),
        "omega_same": _agg_sig([x for x in sig_rows if x["o_same"]]),
    }
    return {"total": int(len(df)), "by_type": by_type, "by_class": by_class, "recent": recent,
            "since": str(df["date"].min()),
            "validation": model_e.load_validation(), "baseball_leg": baseball_leg, "shade": shade, "omega": omega,
            "jacob_book": jacob_book, "by_signal": by_signal}


# ============================================================================================
# F5 model (see model_f5.py) -- read-side helpers, settlement by linescore, track record
# ============================================================================================

def get_logged_model_f5_bet(date: str, game_pk: int) -> dict | None:
    log = _read_log()
    if log.empty:
        return None
    row = log[(log["date"] == date) & (log["game_pk"] == game_pk)]
    if row.empty:
        return None
    val = row.iloc[0].get("model_f5_bet_json")
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return json.loads(val)
    except (TypeError, ValueError):
        return None


def settle_f5(max_dates: int = 14):
    """Fills first-5-innings results for rows whose game is already settled (full-game final) but
    whose F5 outcome hasn't been recorded -- only rows the F5 model actually predicted on, from
    the MLB linescore (per-inning runs). Tied after 5 -> f5_home_won None (a push on a 2-way F5
    line). Same lazy, most-recent-dates-first pattern as settle_predictions."""
    log = _read_log()
    if log.empty:
        return
    todo = log[(log["settled"] == True) & (log["f5_settled"] != True) & log["model_f5_prob"].notna()]  # noqa: E712
    if todo.empty:
        return
    dates = sorted(todo["date"].unique())[-max_dates:]
    for idx in todo[todo["date"].isin(dates)].index:
        pk = log.at[idx, "game_pk"]
        try:
            resp = requests.get(f"{MLB_STATS_API}/game/{int(pk)}/linescore", timeout=15)
            resp.raise_for_status()
            innings = resp.json().get("innings", [])
        except (requests.exceptions.RequestException, ValueError):
            continue
        if len(innings) < 5:
            continue
        h = sum(int((i.get("home") or {}).get("runs") or 0) for i in innings[:5])
        a = sum(int((i.get("away") or {}).get("runs") or 0) for i in innings[:5])
        log.at[idx, "f5_home_runs"] = h
        log.at[idx, "f5_away_runs"] = a
        log.at[idx, "f5_home_won"] = (h > a) if h != a else None
        log.at[idx, "f5_settled"] = True
    _write_log(log)


def get_model_f5_track_record() -> dict:
    """Forward record of the F5 model: pick accuracy vs the F5 market's own pick on the same
    frozen rows, plus the graded F5 bets (ties = push, stake returned). Same blind-forward
    discipline as every other track record here; bets only exist if model_f5.bets_enabled()."""
    import model_e
    import model_f5
    log = _read_log()
    done = log[(log["f5_settled"] == True) & log["model_f5_prob"].notna()].copy()  # noqa: E712
    out = {"total": 0, "decided": 0, "model_hit_rate": None, "market_hit_rate": None, "bets": {}, "recent": [],
           "since": None, "validation": model_f5.load_validation(), "bets_enabled": model_f5.bets_enabled()}
    if done.empty:
        return out
    dec = done[done["f5_home_won"].notna()].copy()
    out["total"] = int(len(done))
    out["decided"] = int(len(dec))
    out["since"] = str(done["date"].min())
    if len(dec):
        dec["f5_home_won"] = dec["f5_home_won"].astype(bool)
        out["model_hit_rate"] = round(float(((dec["model_f5_prob"].astype(float) >= 0.5) == dec["f5_home_won"]).mean()), 4)
        mk = dec[dec["f5_market_home_prob"].notna()]
        if len(mk):
            out["market_hit_rate"] = round(float(((mk["f5_market_home_prob"].astype(float) >= 0.5) == mk["f5_home_won"]).mean()), 4)
            out["market_n"] = int(len(mk))
    bets = []
    for _, r in done[done["model_f5_bet_json"].notna()].iterrows():
        try:
            bet = json.loads(r["model_f5_bet_json"])
        except (TypeError, ValueError):
            continue
        if not bet:
            continue
        base = {"date": r["date"], "matchup": f"{r['away_team_abbr']}@{r['home_team_abbr']}", "side": bet.get("side"),
                "type": bet.get("type"), "best_price": bet.get("best_price"), "stake_units": bet.get("stake_units")}
        if r["f5_home_won"] is None or pd.isna(r["f5_home_won"]):
            bets.append({**base, "won": None, "profit_units": 0.0, "push": True, "clv": None})
            continue
        g = model_e.grade_bet(bet, bool(r["f5_home_won"]))
        bets.append({**base, "won": g["won"], "profit_units": g["profit_units"], "push": False, "clv": g["clv"]})
    if bets:
        b = pd.DataFrame(bets)
        live = b[~b["push"]]
        staked = float(live["stake_units"].fillna(0).sum())
        profit = float(live["profit_units"].fillna(0).sum())
        out["bets"] = {"n": int(len(b)), "pushes": int(b["push"].sum()), "wins": int(live["won"].fillna(False).sum()),
                       "hit_rate": round(float(live["won"].mean()), 4) if len(live) else None,
                       "units_staked": round(staked, 2), "units_profit": round(profit, 2),
                       "roi_pct": round(100 * profit / staked, 2) if staked else None}
        out["recent"] = _records_json_safe(b.sort_values("date", ascending=False).head(40))
    return out


def get_opening_market_prob(date: str, game_pk: int):
    """The earliest de-vigged market price we ever recorded for this game today -- our "opening"
    reference for line movement. Read from prediction_history (logged on every refresh), not from
    the bet's own first_seen_market_prob, because that one only starts when the BET first
    qualified; a game we watched for hours before it became a bet would otherwise report no
    movement. None if we never saw a price.

    Used to flag bets where the market has moved hard against our side. Validated 2026-08-22:
    pooled, bets with the line 4+ pts against returned -44% (n=103), and on all games the side a
    4+ pt move goes toward wins 77.6% vs a 56.3% implied price. On disjoint windows the direction
    holds but the magnitude does not (-56% early on n=75, -12% late on n=28, CI straddling zero),
    so this WARNS and never gates -- four other sub-rules have already failed that same test.
    """
    hist = _read_parquet_log(HISTORY_PATH, HISTORY_COLUMNS)
    if hist.empty:
        return None
    sub = hist[(hist["game_pk"] == game_pk) & (hist["date"] == date)]
    sub = sub[sub["market_home_prob"].notna()]
    if sub.empty:
        return None
    row = sub.sort_values("logged_at").iloc[0]
    try:
        val = float(row["market_home_prob"])
    except (TypeError, ValueError):
        return None
    return None if math.isnan(val) else val
