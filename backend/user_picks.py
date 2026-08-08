"""
user_picks.py

Lets the user lock in their own pick for a game before it starts, then settles it against the
real outcome once the game is Final -- a genuine forward test of "does the user's own read beat
the model," not a retrospective reconstruction (see the extensive backtest discussion this session
that led here: every retrospective approximation of the user's process tested consistently below
the model's real accuracy, but a retrospective approximation isn't the same as the user's actual
live judgment, which can use context -- injuries, lineup news, gut feel -- no backtest can capture).

Settlement reuses prediction_log's already-settled home_score/away_score/home_won for the same
(date, game_pk) rather than re-deriving it -- one source of truth for "what actually happened."
"""
import os
import json
import time
import pandas as pd

from data_collection import CACHE_DIR
from prediction_log import _read_log as _read_prediction_log, PRE_GAME_STATUSES

LOG_PATH = os.path.join(CACHE_DIR, "user_picks.parquet")

LOG_COLUMNS = [
    "date", "game_pk", "home_team_abbr", "away_team_abbr", "picked_team", "picked_at",
]


def _read_log() -> pd.DataFrame:
    if not os.path.exists(LOG_PATH):
        return pd.DataFrame(columns=LOG_COLUMNS)
    try:
        df = pd.read_parquet(LOG_PATH)
    except Exception as e:
        raise RuntimeError(
            f"user_picks.parquet exists but failed to read ({e!r}) -- this is the user's own "
            "forward-test record, not a re-fetchable cache. Investigate before overwriting."
        ) from e
    for col in LOG_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df


def _write_log(df: pd.DataFrame):
    # Same atomic-write + retry pattern as prediction_log._write_log -- same OneDrive-sync
    # interference risk, same reasoning for why a direct to_parquet() isn't safe here.
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


def set_user_pick(date: str, game_pk: int, home_team_abbr: str, away_team_abbr: str,
                   picked_team: str, game_status: str) -> dict:
    """
    Locks in (or updates) the user's pick for one game -- only while the game is still in a
    pre-game state, same freeze point prediction_log.py uses for the model's own predictions.
    Once a game has started, the pick can no longer be set/changed: allowing a post-start change
    would let hindsight leak into what's supposed to be a blind forward test, the exact failure
    mode this feature exists to avoid repeating from the retrospective backtests earlier tonight.
    """
    if game_status not in PRE_GAME_STATUSES:
        return {"status": "locked", "reason": f"game is already {game_status}, pick can no longer be set"}
    if picked_team not in (home_team_abbr, away_team_abbr):
        return {"status": "error", "reason": "picked_team must be the home or away team abbreviation"}

    log = _read_log()
    existing = log[(log["date"] == date) & (log["game_pk"] == game_pk)]
    row = {
        "date": date, "game_pk": game_pk,
        "home_team_abbr": home_team_abbr, "away_team_abbr": away_team_abbr,
        "picked_team": picked_team, "picked_at": pd.Timestamp.now().isoformat(),
    }
    if not existing.empty:
        idx = existing.index[0]
        for col, val in row.items():
            log.at[idx, col] = val
    else:
        log = pd.concat([log, pd.DataFrame([row])], ignore_index=True)
    _write_log(log)
    return {"status": "ok", "picked_team": picked_team}


def get_user_pick(date: str, game_pk: int) -> dict | None:
    log = _read_log()
    if log.empty:
        return None
    row = log[(log["date"] == date) & (log["game_pk"] == game_pk)]
    if row.empty:
        return None
    r = row.iloc[0]
    return {"picked_team": r["picked_team"], "picked_at": r["picked_at"]}


def get_user_picks_for_date(date: str) -> list[dict]:
    log = _read_log()
    day = log[log["date"] == date]
    return [
        {"game_pk": int(r["game_pk"]), "picked_team": r["picked_team"], "picked_at": r["picked_at"]}
        for _, r in day.iterrows()
    ]


def get_user_track_record() -> dict:
    """
    User accuracy vs the model's OWN accuracy, computed on the SAME subset of games the user
    actually picked -- not the model's overall record, which spans a different (larger) set of
    games and wouldn't be a fair comparison. Settlement (home_score/away_score/home_won) is read
    straight from prediction_log's already-settled rows for the same (date, game_pk).
    """
    picks = _read_log()
    if picks.empty:
        return {"total": 0, "user_correct": 0, "user_accuracy": None,
                "model_correct": 0, "model_accuracy": None, "recent": []}

    pred_log = _read_prediction_log()
    pred_log = pred_log[pred_log["settled"] == True]  # noqa: E712
    merged = picks.merge(pred_log, on=["date", "game_pk"], how="inner", suffixes=("", "_pred"))
    merged = merged[merged["home_score"].notna() & merged["away_score"].notna()]
    if merged.empty:
        return {"total": 0, "user_correct": 0, "user_accuracy": None,
                "model_correct": 0, "model_accuracy": None, "recent": []}

    merged["actual_winner"] = merged.apply(
        lambda r: r["home_team_abbr"] if r["home_won"] else r["away_team_abbr"], axis=1)
    merged["user_correct"] = merged["picked_team"] == merged["actual_winner"]

    model_favored_home = merged["model_home_win_prob"] >= 0.5
    merged["model_pick"] = [
        (h_abbr if fav_home else a_abbr)
        for fav_home, h_abbr, a_abbr in zip(model_favored_home, merged["home_team_abbr"], merged["away_team_abbr"])
    ]
    merged["model_correct"] = merged["model_pick"] == merged["actual_winner"]

    total = len(merged)
    user_correct = int(merged["user_correct"].sum())
    model_correct = int(merged["model_correct"].sum())

    recent = merged.sort_values("date", ascending=False).head(30)
    recent_out = [
        {
            "date": r["date"], "matchup": f"{r['away_team_abbr']}@{r['home_team_abbr']}",
            "picked_team": r["picked_team"], "model_pick": r["model_pick"],
            "actual_winner": r["actual_winner"],
            "user_correct": bool(r["user_correct"]), "model_correct": bool(r["model_correct"]),
        }
        for _, r in recent.iterrows()
    ]

    return {
        "total": total,
        "user_correct": user_correct, "user_accuracy": round(user_correct / total, 4),
        "model_correct": model_correct, "model_accuracy": round(model_correct / total, 4),
        "recent": recent_out,
    }
