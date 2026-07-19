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
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime

from data_collection import CACHE_DIR, MLB_STATS_API
from odds_fetcher import devig_home_prob as _devig_home_prob

LOG_PATH = os.path.join(CACHE_DIR, "prediction_log.parquet")

# Shared with main.py: a game only gets a fresh live-computed prediction while
# it's in one of these states — once it's started, main.py serves the frozen
# logged prediction instead (see get_logged_prediction below for why).
PRE_GAME_STATUSES = {"Scheduled", "Pre-Game", "Warmup"}

LOG_COLUMNS = [
    "date", "game_pk", "home_team_abbr", "away_team_abbr",
    "home_pitcher_name", "away_pitcher_name",
    # NOTE the naming trap here: despite its name, "model_home_win_prob" has always held the
    # FINAL/displayed probability (after _apply_confidence_override), not the raw pre-override
    # model output — log_predictions below reads pred.get("home_win_prob"), not
    # pred.get("model_home_win_prob"), into this column. Every existing reader (settle_predictions,
    # get_track_record, get_logged_prediction, get_games_for_date) depends on that FINAL-value
    # behavior, so the column is kept as-is rather than renamed. raw_model_home_win_prob below is
    # the actual pre-override value, added after discovering it was being silently dropped —
    # every overridden row logged before this fix has no recoverable raw counterfactual.
    "model_home_win_prob", "raw_model_home_win_prob", "overridden", "reason",
    "recent_form_json", "season_stats_json", "team_stats_json", "lineup_breakdown_json",  # pre-game snapshot of the display breakdown, see get_logged_prediction
    "market_home_prob",       # de-vigged implied home win prob from live_odds at prediction time, if available
    "logged_at",
    "settled", "home_score", "away_score", "home_won", "correct",
]


def _read_log() -> pd.DataFrame:
    if not os.path.exists(LOG_PATH):
        return pd.DataFrame(columns=LOG_COLUMNS)
    try:
        df = pd.read_parquet(LOG_PATH)
    except Exception as e:
        # A genuinely corrupted log is a much bigger deal than a corrupted re-fetchable cache
        # (see data_collection._load_or_fetch's same fix) — this is irreplaceable forward-test
        # history, not something a live re-fetch can regenerate. So this does NOT silently fall
        # back to an empty log the way a cache miss would; it fails loudly so the corruption gets
        # noticed and investigated rather than quietly starting the track record over from zero.
        raise RuntimeError(
            f"prediction_log.parquet exists but failed to read ({e!r}) — this is the real "
            "forward-test history, not a re-fetchable cache. Investigate before doing anything "
            "that might overwrite it; do not delete/recreate without recovering the data first."
        ) from e
    for col in LOG_COLUMNS:  # backfill gracefully if reading a file written before a column existed
        if col not in df.columns:
            df[col] = None
    return df


def _write_log(df: pd.DataFrame):
    # Atomic write (temp file + os.replace) — same fix and same reasoning as
    # data_collection._load_or_fetch: a direct df.to_parquet(LOG_PATH) truncates the destination
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
    tmp_path = f"{LOG_PATH}.{os.getpid()}.{time.time_ns()}.tmp"
    for attempt in range(5):
        try:
            df.to_parquet(tmp_path)
            os.replace(tmp_path, LOG_PATH)
            return
        except OSError:
            if attempt == 4:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                df.to_parquet(LOG_PATH)
                return
            time.sleep(0.2 * (attempt + 1))


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

        row = {
            "date": date, "game_pk": game_pk,
            "home_team_abbr": g.get("home_team_abbr"), "away_team_abbr": g.get("away_team_abbr"),
            "home_pitcher_name": g.get("home_pitcher_name"), "away_pitcher_name": g.get("away_pitcher_name"),
            "model_home_win_prob": pred.get("home_win_prob"),
            "raw_model_home_win_prob": pred.get("model_home_win_prob"),
            "overridden": pred.get("overridden", False),
            "reason": g.get("reason"),
            "recent_form_json": json.dumps(g.get("recent_form")) if g.get("recent_form") else None,
            "season_stats_json": json.dumps(g.get("season_stats")) if g.get("season_stats") else None,
            "team_stats_json": json.dumps(g.get("team_stats")) if g.get("team_stats") else None,
            "lineup_breakdown_json": json.dumps(g.get("lineup_breakdown")) if g.get("lineup_breakdown") else None,
            "market_home_prob": market_home_prob,
            "logged_at": datetime.now().isoformat(),
        }

        key = (date, game_pk)
        if key in existing_by_key:
            updates[existing_by_key[key]] = row
        else:
            new_rows.append({
                **row,
                "settled": False, "home_score": None, "away_score": None, "home_won": None, "correct": None,
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
        "season_stats": _load_json("season_stats_json"),
        "team_stats": _load_json("team_stats_json"),
        "lineup_breakdown": _load_json("lineup_breakdown_json"),
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

    out = []
    for _, r in day.sort_values("game_pk").iterrows():
        out.append({
            "game_pk": int(r["game_pk"]) if pd.notna(r["game_pk"]) else None,
            "home_team_abbr": r["home_team_abbr"], "away_team_abbr": r["away_team_abbr"],
            "home_pitcher_name": r["home_pitcher_name"], "away_pitcher_name": r["away_pitcher_name"],
            "model_home_win_prob": float(r["model_home_win_prob"]) if pd.notna(r["model_home_win_prob"]) else None,
            "raw_model_home_win_prob": (
                float(r["raw_model_home_win_prob"]) if pd.notna(r["raw_model_home_win_prob"]) else None
            ),
            "overridden": bool(r["overridden"]) if pd.notna(r["overridden"]) else False,
            "market_home_prob": float(r["market_home_prob"]) if pd.notna(r["market_home_prob"]) else None,
            "reason": r.get("reason"),
            # Pre-game snapshot of each pitcher's recent-form/season stat line, frozen at
            # prediction time — same fields the live "pitcher stats" toggle shows, just
            # read back from the log instead of recomputed (recomputing here would risk
            # the exact leakage get_logged_prediction's docstring warns about: a decided
            # game's own outcome bleeding into its own "recent form").
            "recent_form": _load_json(r, "recent_form_json"),
            "season_stats": _load_json(r, "season_stats_json"),
            "team_stats": _load_json(r, "team_stats_json"),
            "lineup_breakdown": _load_json(r, "lineup_breakdown_json"),
            "settled": bool(r["settled"]) if pd.notna(r["settled"]) else False,
            "home_score": int(r["home_score"]) if pd.notna(r["home_score"]) else None,
            "away_score": int(r["away_score"]) if pd.notna(r["away_score"]) else None,
            "home_won": bool(r["home_won"]) if pd.notna(r["home_won"]) else None,
            "correct": bool(r["correct"]) if pd.notna(r["correct"]) else None,
        })
    return out
