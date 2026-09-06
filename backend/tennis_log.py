"""Tennis forward record (2026-09-06): freeze -> settle -> track record.

Tennis predictions were served for two months with NO ledger -- computed daily, displayed,
never frozen, never graded. This module gives tennis the same discipline as the MLB log:
each match's prediction and odds are UPSERTED until first serve and frozen after it,
settled from OpticOdds completed-fixture results (set totals), and served as a real
forward track record. Started 2026-09-06 -- the record begins now, empty, honestly.
"""
import json
import os
from datetime import datetime, timezone

import pandas as pd
import requests

from tennis_data import OPTICODDS_API_KEY, OPTICODDS_BASE_URL, TENNIS_LEAGUES, CACHE_DIR

LOG_PATH = os.path.join(CACHE_DIR, "tennis_prediction_log.parquet")

COLUMNS = ["date", "fixture_id", "league", "tournament", "round", "player_1", "player_2",
           "start_time_utc", "surface", "best_of_5", "p1_win_prob", "p1_odds", "p2_odds",
           "bookmaker", "logged_at", "settled", "p1_won"]


def _read_log() -> pd.DataFrame:
    if os.path.exists(LOG_PATH):
        df = pd.read_parquet(LOG_PATH)
        for c in COLUMNS:
            if c not in df.columns:
                df[c] = None
        return df
    return pd.DataFrame(columns=COLUMNS)


def _write_log(df: pd.DataFrame):
    tmp = LOG_PATH + ".tmp"
    df.to_parquet(tmp)
    os.replace(tmp, LOG_PATH)


def _started(start_time_utc) -> bool:
    try:
        st = pd.Timestamp(start_time_utc)
        if st.tzinfo is None:
            st = st.tz_localize("UTC")
        return datetime.now(timezone.utc) >= st
    except Exception:
        return False


def log_predictions(matches: list, date: str):
    """Upsert today's predicted matches. A row updates freely until first serve and is
    FROZEN afterward (same freeze rule as the MLB log). Only matches carrying both a
    prediction and live odds are logged -- a record row must be gradeable and priced."""
    rows = []
    now = datetime.now(timezone.utc).isoformat()
    for m in matches:
        pred = m.get("prediction") or {}
        odds = m.get("live_odds") or {}
        if pred.get("player_1_win_prob") is None or odds.get("player_1") is None or odds.get("player_2") is None:
            continue
        if not m.get("fixture_id"):
            continue
        rows.append({
            "date": date, "fixture_id": m["fixture_id"], "league": m.get("league"),
            "tournament": m.get("tournament"), "round": m.get("round"),
            "player_1": m.get("player_1"), "player_2": m.get("player_2"),
            "start_time_utc": m.get("start_time_utc"), "surface": m.get("surface"),
            "best_of_5": bool(m.get("best_of_5")), "p1_win_prob": float(pred["player_1_win_prob"]),
            "p1_odds": odds.get("player_1"), "p2_odds": odds.get("player_2"),
            "bookmaker": odds.get("bookmaker"), "logged_at": now, "settled": False, "p1_won": None,
        })
    if not rows:
        return
    log = _read_log()
    new = pd.DataFrame(rows)
    if log.empty:
        _write_log(new)
        return
    frozen_ids = set(log[(log["settled"] == True) | log["start_time_utc"].apply(_started)]["fixture_id"])  # noqa: E712
    new = new[~new["fixture_id"].isin(frozen_ids)]
    if new.empty:
        return
    keep = log[~log["fixture_id"].isin(set(new["fixture_id"]))]
    _write_log(pd.concat([keep, new], ignore_index=True))


def settle(max_dates: int = 10):
    """Fill winners for unsettled rows whose match has started, from OpticOdds completed
    fixtures (result.scores.*.total = sets won; player_1 is the home competitor)."""
    if not OPTICODDS_API_KEY:
        return
    log = _read_log()
    if log.empty:
        return
    todo = log[(log["settled"] != True) & log["start_time_utc"].apply(_started)]  # noqa: E712
    if todo.empty:
        return
    changed = False
    for date in sorted(todo["date"].unique())[-max_dates:]:
        try:
            end = (datetime.strptime(date, "%Y-%m-%d") + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures", params={
                "league": TENNIS_LEAGUES, "start_date_after": date, "start_date_before": end,
            }, headers={"X-Api-Key": OPTICODDS_API_KEY}, timeout=20)
            resp.raise_for_status()
            fixtures = resp.json().get("data", [])
        except requests.exceptions.RequestException:
            continue
        for f in fixtures:
            if f.get("status") != "completed":
                continue
            scores = ((f.get("result") or {}).get("scores") or {})
            h = ((scores.get("home") or {}).get("total"))
            a = ((scores.get("away") or {}).get("total"))
            if h is None or a is None or h == a:
                continue
            m = log["fixture_id"] == f.get("id")
            if m.any() and not bool(log.loc[m, "settled"].iloc[0]):
                log.loc[m, "p1_won"] = bool(h > a)
                log.loc[m, "settled"] = True
                changed = True
    if changed:
        _write_log(log)


def _decimal(am) -> float | None:
    try:
        am = float(am)
    except (TypeError, ValueError):
        return None
    return 1 + am / 100 if am > 0 else 1 + 100 / abs(am)


def get_tennis_track_record() -> dict:
    """Forward record of the frozen tennis log: model accuracy vs the market's own favorite
    on the same matches, plus flat-1u ROI at the logged odds for (a) every model pick and
    (b) only the matches where model and market disagree -- the only bets that could ever
    carry an edge. Empty until matches settle; grows one slate at a time."""
    log = _read_log()
    settled = log[(log["settled"] == True) & log["p1_won"].notna() & log["p1_win_prob"].notna()]  # noqa: E712
    out = {"total_logged": int(len(log)), "settled": int(len(settled)), "since": str(log["date"].min()) if len(log) else None}
    if settled.empty:
        return out
    rows = []
    for _, r in settled.iterrows():
        d1, d2 = _decimal(r["p1_odds"]), _decimal(r["p2_odds"])
        if d1 is None or d2 is None:
            continue
        i1, i2 = 1 / d1, 1 / d2
        mkt_p1 = i1 / (i1 + i2)
        model_p1_pick = r["p1_win_prob"] >= 0.5
        mkt_p1_pick = mkt_p1 >= 0.5
        won = bool(r["p1_won"])
        model_right = (model_p1_pick == won)
        dec_pick = d1 if model_p1_pick else d2
        rows.append({"model_right": model_right, "mkt_right": (mkt_p1_pick == won),
                     "disagree": model_p1_pick != mkt_p1_pick,
                     "flat": (dec_pick - 1.0) if model_right else -1.0})
    d = pd.DataFrame(rows)
    if d.empty:
        return out
    out.update({
        "n": int(len(d)),
        "model_accuracy": round(float(d["model_right"].mean()), 4),
        "market_accuracy": round(float(d["mkt_right"].mean()), 4),
        "flat_roi_pct": round(100 * float(d["flat"].mean()), 2),
        "n_disagree": int(d["disagree"].sum()),
        "disagree_model_accuracy": round(float(d[d["disagree"]]["model_right"].mean()), 4) if d["disagree"].any() else None,
        "disagree_flat_roi_pct": round(100 * float(d[d["disagree"]]["flat"].mean()), 2) if d["disagree"].any() else None,
    })
    return out
