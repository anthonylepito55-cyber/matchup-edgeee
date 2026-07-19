"""
strikeout_prediction_log.py

Same forward-test discipline as prediction_log.py (see that file's
docstring), applied to strikeout props instead of moneyline: logs each
pitcher's over/under call before their start, settles it against their
actual final strikeout total once the game goes Final, and tracks a
running hit rate. This is a genuine blind record — a call is only ever
logged before the game starts, never backfilled with hindsight.

Each row: one pitcher's strikeout call for one game, keyed by
(date, game_pk, pitcher_id) — two rows per game (one per starter).
"""

import os
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime

from data_collection import CACHE_DIR, MLB_STATS_API

LOG_PATH = os.path.join(CACHE_DIR, "strikeout_prediction_log.parquet")

LOG_COLUMNS = [
    "date", "game_pk", "pitcher_id", "pitcher_name", "team_abbr", "opp_team_abbr",
    "predicted_k", "line", "line_source", "call",  # call: "over" or "under"
    "over_prob", "under_prob",  # kept so a decided game's displayed prop card can be frozen, not just its hit-rate call
    "bookmaker", "over_price", "under_price",  # the actual sportsbook's own line/juice at prediction time — lets the
    # previous-day tab show whether a call would have beaten the book, not just whether it hit. Added after the fact,
    # so only populated for rows logged from here on; older rows read back as None via the LOG_COLUMNS backfill below.
    "logged_at",
    "settled", "actual_k", "actual_ip", "correct",  # correct: True/False/None (None = push, line_source model exact match)
]

PRE_GAME_STATUSES = {"Scheduled", "Pre-Game", "Warmup"}


def _read_log() -> pd.DataFrame:
    if not os.path.exists(LOG_PATH):
        return pd.DataFrame(columns=LOG_COLUMNS)
    df = pd.read_parquet(LOG_PATH)
    for col in LOG_COLUMNS:  # backfill gracefully if reading a file written before a column existed
        if col not in df.columns:
            df[col] = None
    return df


def _write_log(df: pd.DataFrame):
    # Atomic write (temp file + os.replace) + retry — same fix, same reasoning, and same real
    # OneDrive-sync corruption incident as prediction_log._write_log; this file lives under the
    # same synced data_cache/ and gets the same concurrent-writer exposure (logged/settled on
    # every /api/today request), so it gets the same protection.
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


def log_strikeout_predictions(date: str, games: list[dict]):
    """
    Upserts one row per starter with a real strikeout prediction, for games
    that haven't started yet. Keeps UPDATING an existing pre-game row on
    every call, right up until the game leaves a pre-game status — it does
    not freeze on the first glance. Probable pitchers are often announced
    the night before, so the first time a game is ever seen here can be
    many hours before first pitch, well before the same-day lineup/bullpen/
    rest-day picture is settled. See prediction_log.log_predictions for the
    real incident this mirrors (a moneyline pick that locked onto an
    11pm-the-night-before snapshot instead of the last, best pre-game read).
    """
    log = _read_log()
    existing_by_key = (
        {(r["date"], r["game_pk"], r["pitcher_id"]): i for i, r in log.iterrows()} if not log.empty else {}
    )

    new_rows = []
    updates = {}  # index -> row dict
    for g in games:
        sk = g.get("strikeout_predictions")
        game_pk = g.get("game_pk")
        if sk is None or game_pk is None:
            continue
        if g.get("status") not in PRE_GAME_STATUSES:
            continue

        for side, pid_key, pname_key, team_key, opp_key in (
            ("home", "home_pitcher_id", "home_pitcher_name", "home_team_abbr", "away_team_abbr"),
            ("away", "away_pitcher_id", "away_pitcher_name", "away_team_abbr", "home_team_abbr"),
        ):
            pred = sk.get(side)
            pitcher_id = g.get(pid_key)
            if pred is None or pitcher_id is None:
                continue

            row = {
                "date": date, "game_pk": game_pk, "pitcher_id": pitcher_id,
                "pitcher_name": g.get(pname_key), "team_abbr": g.get(team_key), "opp_team_abbr": g.get(opp_key),
                "predicted_k": pred.get("predicted"), "line": pred.get("line"), "line_source": pred.get("line_source"),
                "call": "over" if (pred.get("over_prob") or 0) >= 0.5 else "under",
                "over_prob": pred.get("over_prob"), "under_prob": pred.get("under_prob"),
                "bookmaker": pred.get("bookmaker"),
                "over_price": pred.get("over_price"), "under_price": pred.get("under_price"),
                "logged_at": datetime.now().isoformat(),
            }

            key = (date, game_pk, pitcher_id)
            if key in existing_by_key:
                updates[existing_by_key[key]] = row
            else:
                new_rows.append({**row, "settled": False, "actual_k": None, "actual_ip": None, "correct": None})

    if not new_rows and not updates:
        return
    if updates:
        for idx, row in updates.items():
            for col, val in row.items():
                log.at[idx, col] = val
    if new_rows:
        log = pd.concat([log, pd.DataFrame(new_rows)], ignore_index=True)
    _write_log(log)


def get_logged_strikeout_prediction(date: str, game_pk: int, pitcher_id: int) -> dict | None:
    """
    The frozen, pre-game strikeout call for one pitcher's start, if it was
    logged — same reasoning as prediction_log.get_logged_prediction: once a
    game is no longer pre-game, the K-prop card must not keep recomputing
    live, since a pitcher's own in-progress or just-finished start bleeds
    into the same recent-form/season-stat inputs that produced the call in
    the first place. Odds/pricing (bookmaker, over/under price, PrizePicks)
    aren't logged and come back None here — irrelevant for a game that's
    already decided, nothing to act on. Returns None if nothing was logged,
    so callers should fall back to live computation in that case.
    """
    log = _read_log()
    if log.empty:
        return None
    row = log[(log["date"] == date) & (log["game_pk"] == game_pk) & (log["pitcher_id"] == pitcher_id)]
    if row.empty:
        return None
    r = row.iloc[0]
    predicted = r["predicted_k"]
    if predicted is None or pd.isna(predicted):
        return None
    return {
        "predicted": float(predicted),
        "line": float(r["line"]) if pd.notna(r["line"]) else None,
        "line_source": r["line_source"] if pd.notna(r["line_source"]) else None,
        "over_prob": float(r["over_prob"]) if pd.notna(r["over_prob"]) else None,
        "under_prob": float(r["under_prob"]) if pd.notna(r["under_prob"]) else None,
        "bookmaker": None, "over_price": None, "under_price": None, "prizepicks": None,
    }


def _pitcher_boxscore_line(game_pk, pitcher_id) -> tuple:
    """(ip, k) for one pitcher in one game's final boxscore, or (None, None) if unavailable."""
    try:
        resp = requests.get(f"{MLB_STATS_API}/game/{game_pk}/boxscore", timeout=15)
        resp.raise_for_status()
        box = resp.json()
    except requests.exceptions.RequestException:
        return None, None
    for side in ("home", "away"):
        players = box.get("teams", {}).get(side, {}).get("players", {})
        p = players.get(f"ID{pitcher_id}")
        if p is None:
            continue
        stats = p.get("stats", {}).get("pitching", {})
        ip = stats.get("inningsPitched")
        k = stats.get("strikeOuts")
        if ip is None or k is None:
            return None, None
        return float(ip), int(k)
    return None, None


def settle_strikeout_predictions(max_dates: int = 14):
    """Fills in actual results for any unsettled rows whose game has gone Final —
    same lazy-settlement pattern as prediction_log.settle_predictions."""
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
        final_pks = {g["gamePk"] for g in games_today if g.get("status", {}).get("detailedState") == "Final"}

        rows_to_settle = log[(log["date"] == date) & (log["settled"] == False) & (log["game_pk"].isin(final_pks))]  # noqa: E712
        for idx in rows_to_settle.index:
            game_pk, pitcher_id = log.at[idx, "game_pk"], log.at[idx, "pitcher_id"]
            ip, k = _pitcher_boxscore_line(game_pk, pitcher_id)
            if k is None:
                continue
            line = log.at[idx, "line"]
            call = log.at[idx, "call"]
            if k == line:
                correct = None  # push — line_source "model" lines can land exactly on an integer prediction
            else:
                actual_call = "over" if k > line else "under"
                correct = (call == actual_call)
            log.at[idx, "actual_k"] = k
            log.at[idx, "actual_ip"] = ip
            log.at[idx, "correct"] = correct
            log.at[idx, "settled"] = True

    _write_log(log)


def get_strikeout_track_record() -> dict:
    """Summary + recent rows for display. Pushes (correct is None) are excluded from
    the hit-rate denominator, same as how a real sportsbook voids a pushed bet."""
    log = _read_log()
    settled = log[log["settled"] == True]  # noqa: E712
    if settled.empty:
        return {"total": 0, "correct": 0, "pushes": 0, "accuracy": None, "mae": None, "recent": []}

    decided = settled[settled["correct"].notna()]
    pushes = len(settled) - len(decided)
    correct = int(decided["correct"].sum()) if not decided.empty else 0
    total = len(decided)

    mae = float(np.mean(np.abs(settled["predicted_k"].astype(float) - settled["actual_k"].astype(float))))

    recent = settled.sort_values("date", ascending=False).head(30)
    recent_out = [
        {
            "date": r["date"], "pitcher": r["pitcher_name"], "matchup": f"{r['team_abbr']} vs {r['opp_team_abbr']}",
            "predicted_k": r["predicted_k"], "line": r["line"], "call": r["call"],
            "actual_k": r["actual_k"], "correct": None if pd.isna(r["correct"]) else bool(r["correct"]),
        }
        for _, r in recent.iterrows()
    ]

    return {
        "total": total, "correct": correct, "pushes": pushes,
        "accuracy": round(correct / total, 4) if total > 0 else None,
        "mae": round(mae, 3),
        "recent": recent_out,
    }


def get_strikeouts_for_date(date: str) -> list[dict]:
    """Every logged strikeout call for one date, keyed by game_pk — used by the
    previous-day tab to pair with prediction_log.get_games_for_date's win-prob rows."""
    log = _read_log()
    day = log[log["date"] == date]
    if day.empty:
        return []
    out = []
    for _, r in day.sort_values(["game_pk", "pitcher_name"]).iterrows():
        out.append({
            "game_pk": int(r["game_pk"]) if pd.notna(r["game_pk"]) else None,
            "pitcher_name": r["pitcher_name"], "team_abbr": r["team_abbr"], "opp_team_abbr": r["opp_team_abbr"],
            "predicted_k": float(r["predicted_k"]) if pd.notna(r["predicted_k"]) else None,
            "line": float(r["line"]) if pd.notna(r["line"]) else None,
            "call": r["call"],
            "bookmaker": r.get("bookmaker") if pd.notna(r.get("bookmaker")) else None,
            "over_price": int(r["over_price"]) if pd.notna(r.get("over_price")) else None,
            "under_price": int(r["under_price"]) if pd.notna(r.get("under_price")) else None,
            "settled": bool(r["settled"]) if pd.notna(r["settled"]) else False,
            "actual_k": float(r["actual_k"]) if pd.notna(r["actual_k"]) else None,
            "correct": None if pd.isna(r["correct"]) else bool(r["correct"]),
        })
    return out
