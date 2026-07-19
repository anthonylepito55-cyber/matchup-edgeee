"""
build_training_data.py

Constructs the historical training set the model needs:
  1. Pull team schedules & results for past seasons (pybaseball)
  2. Pull probable/actual starting pitchers per game (MLB Stats API, historical dates)
  3. Build feature rows for every historical game, walking forward through
     time so recent-form/rest-days features only see prior starts (features.py)
  4. Label each row with whether the home team won

This is the slowest part of the pipeline (lots of API calls), so it
caches aggressively. Expect a first run over 2-3 seasons to take a
while — that's normal, MLB Stats API and pybaseball rate-limit you.

Run directly:
    python build_training_data.py --seasons 2025 2026
"""

import argparse
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from data_collection import (
    get_team_batting_splits,
    get_team_bullpen_stats,
    get_team_high_leverage_bullpen_stats,
    get_team_defense_oaa,
    get_park_factor,
    get_team_batting_vs_hand,
    get_pitcher_hand,
    get_pitcher_statcast_daily,
    statcast_cumulative_as_of,
    statcast_recent_as_of,
    get_pitcher_velocity_daily,
    statcast_velocity_trend,
    get_pitcher_pitch_types_daily,
    statcast_pitch_diversity,
    statcast_pitch_mix_as_of,
    get_batter_pitch_arsenal,
    get_batter_expected_stats,
    get_batter_exitvelo_barrels,
    get_batter_percentile_ranks,
    get_batted_ball_profile,
    get_batter_team_map,
    get_season_pitching_stats,
    season_stat_row_lookup,
    compute_xfip_siera,
    get_recent_il_activations,
    days_since_il_return,
    MLB_STATS_API,
    CACHE_DIR,
)
from features import (
    build_matchup_features, features_to_row, FEATURE_COLUMNS, build_strikeout_features,
    blend_with_prior_season,
)
from weather import get_team_weather_range, TEAM_HOME_VENUE, venue_distance_miles

import os

TRAINING_CACHE = os.path.join(CACHE_DIR, "training_dataset.parquet")
STRIKEOUT_TRAINING_CACHE = os.path.join(CACHE_DIR, "strikeout_training_dataset.parquet")
GAME_LOG_CACHE = os.path.join(CACHE_DIR, "raw_game_logs.parquet")


def fetch_season_schedule_with_pitchers(season: int) -> pd.DataFrame:
    """
    Pulls every completed game in a season with home/away teams, final
    score, and (where available) the starting pitcher line via the MLB
    Stats API boxscore endpoint. This is the single slowest step.
    """
    cache_path = os.path.join(CACHE_DIR, f"game_logs_{season}.parquet")
    if os.path.exists(cache_path):
        return pd.read_parquet(cache_path)

    start = f"{season}-03-01"
    end = f"{season}-11-15"
    url = f"{MLB_STATS_API}/schedule"
    params = {"sportId": 1, "startDate": start, "endDate": end, "gameType": "R"}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    game_pks = []  # (gamePk, date) — the schedule response's date-block is the
    # only reliable source for this; the boxscore endpoint doesn't carry a date field at all
    for d in data.get("dates", []):
        for g in d.get("games", []):
            if g.get("status", {}).get("detailedState") == "Final":
                game_pks.append((g["gamePk"], d["date"]))

    print(f"[{season}] {len(game_pks)} completed games found. Pulling boxscores...")

    rows = []
    for i, (pk, game_date) in enumerate(game_pks):
        if i % 50 == 0:
            print(f"  ...{i}/{len(game_pks)}")
        try:
            box = requests.get(f"{MLB_STATS_API}/game/{pk}/boxscore", timeout=15).json()
            live = requests.get(f"{MLB_STATS_API}/game/{pk}/linescore", timeout=15).json()

            away_team = box["teams"]["away"]["team"]["abbreviation"]
            home_team = box["teams"]["home"]["team"]["abbreviation"]

            away_pitchers = box["teams"]["away"].get("pitchers", [])
            home_pitchers = box["teams"]["home"].get("pitchers", [])
            if not away_pitchers or not home_pitchers:
                continue
            away_sp_id = away_pitchers[0]
            home_sp_id = home_pitchers[0]

            away_sp_stats = box["teams"]["away"]["players"].get(f"ID{away_sp_id}", {}).get("stats", {}).get("pitching", {})
            home_sp_stats = box["teams"]["home"]["players"].get(f"ID{home_sp_id}", {}).get("stats", {}).get("pitching", {})

            home_team_ip = box["teams"]["home"].get("teamStats", {}).get("pitching", {}).get("inningsPitched", 0)
            away_team_ip = box["teams"]["away"].get("teamStats", {}).get("pitching", {}).get("inningsPitched", 0)

            # Team's own batting line for the game (distinct from home_h/away_h above, which are
            # the opposing PITCHER's hits allowed) — free from the same already-fetched boxscore,
            # feeds recent team batting form (see _recent_team_avg_from_history).
            home_team_batting = box["teams"]["home"].get("teamStats", {}).get("batting", {})
            away_team_batting = box["teams"]["away"].get("teamStats", {}).get("batting", {})

            home_runs = live.get("teams", {}).get("home", {}).get("runs")
            away_runs = live.get("teams", {}).get("away", {}).get("runs")
            if home_runs is None or away_runs is None:
                continue

            rows.append({
                "game_pk": pk,
                "game_date": game_date,
                "season": season,
                "home_team": home_team,
                "away_team": away_team,
                "home_pitcher_id": home_sp_id,
                "away_pitcher_id": away_sp_id,
                "home_win": 1 if home_runs > away_runs else 0,
                "home_ip": home_sp_stats.get("inningsPitched", 0),
                "home_er": home_sp_stats.get("earnedRuns", 0),
                "home_h": home_sp_stats.get("hits", 0),
                "home_bb": home_sp_stats.get("baseOnBalls", 0),
                "home_k": home_sp_stats.get("strikeOuts", 0),
                "home_hr": home_sp_stats.get("homeRuns", 0),
                "home_hbp": home_sp_stats.get("hitBatsmen", 0),
                "home_bf": home_sp_stats.get("battersFaced", 0),
                "away_ip": away_sp_stats.get("inningsPitched", 0),
                "away_er": away_sp_stats.get("earnedRuns", 0),
                "away_h": away_sp_stats.get("hits", 0),
                "away_bb": away_sp_stats.get("baseOnBalls", 0),
                "away_k": away_sp_stats.get("strikeOuts", 0),
                "away_hr": away_sp_stats.get("homeRuns", 0),
                "away_hbp": away_sp_stats.get("hitBatsmen", 0),
                "away_bf": away_sp_stats.get("battersFaced", 0),
                # bullpen IP = team total IP minus the starter's own IP — used to
                # track how heavily each team's pen has been leaning in recent
                # days (see _bullpen_fatigue_from_history)
                "home_bullpen_ip": max(0.0, _parse_ip(home_team_ip) - _parse_ip(home_sp_stats.get("inningsPitched", 0))),
                "away_bullpen_ip": max(0.0, _parse_ip(away_team_ip) - _parse_ip(away_sp_stats.get("inningsPitched", 0))),
                "home_team_hits": home_team_batting.get("hits", 0),
                "home_team_ab": home_team_batting.get("atBats", 0),
                "away_team_hits": away_team_batting.get("hits", 0),
                "away_team_ab": away_team_batting.get("atBats", 0),
            })
        except Exception as e:
            continue

    df = pd.DataFrame(rows)
    if len(df) > 0:
        df.to_parquet(cache_path)
    return df


def _parse_ip(ip_str):
    """MLB API innings pitched comes as e.g. '6.2' meaning 6 and 2/3 innings."""
    try:
        ip_str = str(ip_str)
        if "." in ip_str:
            whole, frac = ip_str.split(".")
            return int(whole) + int(frac) / 3.0
        return float(ip_str)
    except (ValueError, TypeError):
        return 0.0


def _recent_stats_from_history(starts: list, n: int = 5) -> dict:
    """
    Same last-n-starts ERA/FIP/K9/BB9/IP-per-start aggregation as
    data_collection's live version, but sourced from the pitcher's own
    prior rows in this training set (walk-forward — only starts strictly
    before the game being featurized are ever in `starts`, so there's no
    leakage).

    starts entries are (ip, er, bb, k, hr, hbp, bf, h) tuples.

    Every entry here is a genuine start (pitcher_history is only ever
    populated from a game's actual starting pitcher), so sample_type is
    always "starts" — these fields exist so build_matchup_features' recent-
    form reliability weighting sees the same shape of dict here as it does
    from the live get_pitcher_recent_starts (which does have an
    appearances fallback).
    """

    last_n = starts[-n:]
    total_ip = sum(s[0] for s in last_n)
    if total_ip <= 0:
        return {"era": np.nan, "fip": np.nan, "k9": np.nan, "bb9": np.nan,
                "whip": np.nan, "k_pct": np.nan, "bb_pct": np.nan, "hr9": np.nan, "h9": np.nan,
                "ip_per_start": np.nan,
                "sample_size": len(last_n), "sample_type": "starts"}
    total_er = sum(s[1] for s in last_n)
    total_bb = sum(s[2] for s in last_n)
    total_k = sum(s[3] for s in last_n)
    total_hr = sum(s[4] for s in last_n)
    total_hbp = sum(s[5] for s in last_n)
    has_bf = len(last_n[0]) > 6
    has_h = len(last_n[0]) > 7
    total_bf = sum(s[6] for s in last_n) if has_bf else 0
    total_h = sum(s[7] for s in last_n) if has_h else 0
    return {
        "era": total_er / total_ip * 9,
        "fip": (13 * total_hr + 3 * (total_bb + total_hbp) - 2 * total_k) / total_ip + 3.10,
        "k9": total_k / total_ip * 9,
        "bb9": total_bb / total_ip * 9,
        "whip": (total_bb + total_h) / total_ip if has_h else np.nan,
        "k_pct": (total_k / total_bf * 100) if total_bf > 0 else np.nan,
        "bb_pct": (total_bb / total_bf * 100) if total_bf > 0 else np.nan,
        "hr9": total_hr / total_ip * 9,
        "h9": total_h / total_ip * 9 if has_h else np.nan,
        "ip_per_start": total_ip / len(last_n),
        "sample_size": len(last_n),
        "sample_type": "starts",
    }


def _season_to_date_stats_from_history(starts: list, batted_ball_mix: dict = None) -> dict:
    """
    Cumulative season FIP/K-BB%/IP from ALL of a pitcher's starts strictly
    before the game being featurized — walk-forward, same principle as
    _recent_stats_from_history above but over the whole season-to-date
    rather than just the last 5.

    This replaces feeding every training row the pitcher's full, final
    season line from get_season_pitching_stats (fetched "now", after the
    season's already happened) — that was real look-ahead leakage: an
    April game would see starts from July that hadn't occurred yet. A live
    prediction never has that advantage, so training shouldn't either.

    starts entries are (ip, er, bb, k, hr, hbp, bf, h) tuples, oldest first.

    batted_ball_mix, if given, is that SAME pitcher's already-walk-forward-safe
    statcast_cumulative_as_of(..., before_date=this_game_date) dict — its gb_pct/fb_pct/pu_pct
    feed compute_xfip_siera below for a genuine current-season xFIP/SIERA. Before this param
    existed, this dict had no "xfip"/"siera" keys at all, so blend_with_prior_season's per-key
    loop always fell through to the PRIOR season's value for those two (never blending in any
    current-season signal, no matter how far into the season a pitcher was) — xera has no
    walk-forward equivalent (Statcast's contact-quality model isn't public), so it still falls
    back to prior-season-only, same as before; only xfip/siera are fixed here.
    """
    empty = {"fip": np.nan, "k_bb_pct": np.nan, "k9": np.nan, "hr9": np.nan, "h9": np.nan,
              "whip": np.nan, "k_pct": np.nan, "bb_pct": np.nan, "ip": 0.0, "ip_per_start": np.nan,
              "xfip": np.nan, "siera": np.nan}
    if not starts:
        return empty
    total_ip = sum(s[0] for s in starts)
    if total_ip <= 0:
        return empty
    total_bb = sum(s[2] for s in starts)
    total_k = sum(s[3] for s in starts)
    total_hr = sum(s[4] for s in starts)
    total_hbp = sum(s[5] for s in starts)
    has_h = len(starts[0]) > 7
    total_bf = sum(s[6] for s in starts) if len(starts[0]) > 6 else 0
    total_h = sum(s[7] for s in starts) if has_h else 0
    fip = (13 * total_hr + 3 * (total_bb + total_hbp) - 2 * total_k) / total_ip + 3.10
    k_bb_pct = (total_k - total_bb) / total_bf * 100 if total_bf > 0 else np.nan
    k9 = total_k / total_ip * 9
    hr9 = total_hr / total_ip * 9
    h9 = total_h / total_ip * 9 if has_h else np.nan
    whip = (total_bb + total_h) / total_ip if has_h else np.nan
    k_pct = (total_k / total_bf * 100) if total_bf > 0 else np.nan
    bb_pct = (total_bb / total_bf * 100) if total_bf > 0 else np.nan
    # Every entry in `starts` is one actual start (see build_full_training_set), so len(starts)
    # IS the games-started count for this walk-forward window — same "how deep do they usually
    # go" signal as data_collection.season_stat_row_lookup's IP_per_GS, computed walk-forward here.
    ip_per_start = total_ip / len(starts)
    batted_ball_mix = batted_ball_mix or {}
    xfip, siera = compute_xfip_siera(
        bb=total_bb, so=total_k, hr=total_hr, hbp=total_hbp, bf=total_bf, ip=total_ip,
        gb_pct=batted_ball_mix.get("gb_pct"), fb_pct=batted_ball_mix.get("fb_pct"),
        pu_pct=batted_ball_mix.get("pu_pct"),
    )
    return {"fip": fip, "k_bb_pct": k_bb_pct, "k9": k9, "hr9": hr9, "h9": h9,
            "whip": whip, "k_pct": k_pct, "bb_pct": bb_pct, "ip": total_ip, "ip_per_start": ip_per_start,
            "xfip": xfip, "siera": siera}


def _h2h_stats_from_history(starts: list) -> dict:
    """
    A pitcher's own ERA/FIP/K9 against ONE specific opponent, from every start
    they've made against that team strictly before the game being featurized —
    walk-forward, same principle as _recent_stats_from_history/_season_to_date_
    stats_from_history above, but keyed to (pitcher, opponent) pairs rather than
    just the pitcher, and — unlike those two — deliberately NOT reset at a
    season boundary, since a head-to-head history spanning last season and this
    one is exactly the signal being captured here (see build_full_training_set's
    pitcher_vs_team_history, a separate dict from the season-reset pitcher_history).

    starts entries are (ip, er, bb, k, hr, hbp) tuples, oldest first.
    """
    if not starts:
        return {"era": np.nan, "fip": np.nan, "k9": np.nan, "bb9": np.nan, "starts": 0, "ip": 0.0}
    total_ip = sum(s[0] for s in starts)
    if total_ip <= 0:
        return {"era": np.nan, "fip": np.nan, "k9": np.nan, "bb9": np.nan, "starts": len(starts), "ip": 0.0}
    total_er = sum(s[1] for s in starts)
    total_bb = sum(s[2] for s in starts)
    total_k = sum(s[3] for s in starts)
    total_hr = sum(s[4] for s in starts)
    total_hbp = sum(s[5] for s in starts)
    return {
        "era": total_er / total_ip * 9,
        "fip": (13 * total_hr + 3 * (total_bb + total_hbp) - 2 * total_k) / total_ip + 3.10,
        "k9": total_k / total_ip * 9,
        "bb9": total_bb / total_ip * 9,
        "starts": len(starts),
        "ip": total_ip,
    }


BULLPEN_FATIGUE_LOOKBACK_DAYS = 3


def _bullpen_fatigue_from_history(usage_history: list, as_of_date: str) -> float:
    """
    Sum of bullpen innings a team has thrown in the BULLPEN_FATIGUE_
    LOOKBACK_DAYS calendar days strictly before as_of_date — walk-forward,
    entries are (date, bullpen_ip) tuples for that team's games so far.
    """
    if not usage_history:
        return 0.0
    as_of_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    cutoff = as_of_dt - timedelta(days=BULLPEN_FATIGUE_LOOKBACK_DAYS)
    return sum(
        ip for date_str, ip in usage_history
        if cutoff <= datetime.strptime(date_str, "%Y-%m-%d") < as_of_dt
    )


RECENT_TEAM_BATTING_GAMES = 7  # matches data_collection.RECENT_TEAM_BATTING_GAMES — kept
# separate since this module has no data_collection import cycle concern, same pattern as
# IL_RETURN_WINDOW_DAYS elsewhere in this app
RECENT_TEAM_BATTING_GAMES_30D = 26  # matches data_collection.RECENT_TEAM_BATTING_GAMES_30D


def _recent_team_avg_from_history(batting_history: list, n: int = RECENT_TEAM_BATTING_GAMES) -> dict:
    """
    A team's own batting average (H/AB) over its last `n` games strictly
    before the game being featurized — walk-forward, same principle as
    _recent_stats_from_history but for a team's OWN hitting rather than a
    pitcher's own pitching. Catches a lineup that's genuinely hot or cold
    right now, distinct from its season-long wOBA.

    batting_history entries are (hits, at_bats) tuples, oldest first.
    """
    last_n = batting_history[-n:]
    if not last_n:
        return {"avg": np.nan, "games": 0}
    total_h = sum(h for h, ab in last_n)
    total_ab = sum(ab for h, ab in last_n)
    return {"avg": (total_h / total_ab) if total_ab > 0 else np.nan, "games": len(last_n)}


def _load_line_movement_by_game() -> dict:
    """{game_pk: closing_minus_opening_devigged_home_prob} from backfill_historical_odds.py's
    cache — feeds line_movement_diff (see features.py). Missing/NaN entries mean "no signal,"
    not zero movement, same graceful-missing-data handling as every other odds-derived feature."""
    path = os.path.join(CACHE_DIR, "historical_market_probs.parquet")
    if not os.path.exists(path):
        print("No historical_market_probs.parquet found — line_movement_diff will be NaN for all rows.")
        return {}
    odds_df = pd.read_parquet(path)
    if "market_home_prob_open" not in odds_df.columns:
        print("historical_market_probs.parquet predates opening-line tracking — "
              "line_movement_diff will be NaN for all rows until backfill_historical_odds.py is re-run.")
        return {}
    movement = {}
    for _, r in odds_df.iterrows():
        close, open_ = r.get("market_home_prob"), r.get("market_home_prob_open")
        if pd.notna(close) and pd.notna(open_):
            movement[r["game_pk"]] = close - open_
    print(f"Loaded line movement for {len(movement)} games.")
    return movement


def _load_market_divergence_by_game() -> dict:
    """{game_pk: pinnacle_movement_minus_draftkings_movement} from backfill_historical_odds.py's
    cache — feeds market_divergence_diff (see features.py). Same "missing means no signal"
    handling as _load_line_movement_by_game; also NaN for any cache written before the
    DK columns existed (pre market-expansion schema)."""
    path = os.path.join(CACHE_DIR, "historical_market_probs.parquet")
    if not os.path.exists(path):
        print("No historical_market_probs.parquet found — market_divergence_diff will be NaN for all rows.")
        return {}
    odds_df = pd.read_parquet(path)
    required = {"market_home_prob", "market_home_prob_open", "market_home_prob_dk", "market_home_prob_dk_open"}
    if not required.issubset(odds_df.columns):
        print("historical_market_probs.parquet predates the DraftKings columns — "
              "market_divergence_diff will be NaN for all rows until backfill_historical_odds.py is re-run.")
        return {}
    divergence = {}
    for _, r in odds_df.iterrows():
        sharp_close, sharp_open = r.get("market_home_prob"), r.get("market_home_prob_open")
        retail_close, retail_open = r.get("market_home_prob_dk"), r.get("market_home_prob_dk_open")
        if pd.notna(sharp_close) and pd.notna(sharp_open) and pd.notna(retail_close) and pd.notna(retail_open):
            divergence[r["game_pk"]] = (sharp_close - sharp_open) - (retail_close - retail_open)
    print(f"Loaded market divergence for {len(divergence)} games.")
    return divergence


def _load_prediction_market_by_game() -> dict:
    """{game_pk: avg_prediction_market_prob_minus_pinnacle_prob} from backfill_historical_odds.py's
    cache — feeds prediction_market_diff (see features.py). Averages across whichever of
    Kalshi/Polymarket (USA) has data for that game (not a hard requirement both exist), current
    price only — never the opening price, which is a confirmed artifact for these books (see
    odds_fetcher.py's PREDICTION_MARKET_BOOKS docstring)."""
    path = os.path.join(CACHE_DIR, "historical_market_probs.parquet")
    if not os.path.exists(path):
        print("No historical_market_probs.parquet found — prediction_market_diff will be NaN for all rows.")
        return {}
    odds_df = pd.read_parquet(path)
    required = {"market_home_prob", "market_home_prob_kalshi", "market_home_prob_polymarket"}
    if not required.issubset(odds_df.columns):
        print("historical_market_probs.parquet predates the prediction-market columns — "
              "prediction_market_diff will be NaN for all rows until backfill_historical_odds.py is re-run.")
        return {}
    diff = {}
    for _, r in odds_df.iterrows():
        sharp = r.get("market_home_prob")
        if pd.isna(sharp):
            continue
        pred_probs = [p for p in (r.get("market_home_prob_kalshi"), r.get("market_home_prob_polymarket")) if pd.notna(p)]
        if pred_probs:
            diff[r["game_pk"]] = (sum(pred_probs) / len(pred_probs)) - sharp
    print(f"Loaded prediction-market signal for {len(diff)} games.")
    return diff


def _load_consensus_by_game() -> dict:
    """{game_pk: (consensus_prob, book_disagreement, book_movement_agreement, median_prob,
    book_prob_std, book_favor_diff)} from backfill_historical_odds.py's cache — feeds
    consensus_prob_diff/book_disagreement/book_movement_agreement/consensus_median_diff/
    book_prob_std/book_favor_diff (see features.py). consensus_prob is the average devigged
    home win prob across CONSENSUS_BOOKS at the time backfilled (a level, not a movement);
    book_disagreement is the max-min spread across those same books; book_movement_agreement is
    the signed fraction of those books that moved the same direction since open; median_prob is
    the median (robust to one outlier book); book_prob_std is the population std (a more
    holistic disagreement measure than the max-min range); book_favor_diff is the signed
    fraction of books currently favoring home vs away. Same "missing means no signal" handling
    as the other market loaders here."""
    path = os.path.join(CACHE_DIR, "historical_market_probs.parquet")
    if not os.path.exists(path):
        print("No historical_market_probs.parquet found — consensus/disagreement/movement/"
              "median/std/favor-diff features will be NaN for all rows.")
        return {}
    odds_df = pd.read_parquet(path)
    required = {
        "market_home_prob_consensus", "market_home_prob_book_disagreement",
        "market_home_prob_movement_agreement", "market_home_prob_median",
        "market_home_prob_std", "market_home_prob_favor_diff",
    }
    if not required.issubset(odds_df.columns):
        print("historical_market_probs.parquet predates the median/std/favor-diff columns — "
              "consensus/disagreement/movement/median/std/favor-diff features will be NaN for "
              "all rows until backfill_historical_odds.py is re-run.")
        return {}
    consensus = {}
    for _, r in odds_df.iterrows():
        prob = r.get("market_home_prob_consensus")
        if pd.notna(prob):
            consensus[r["game_pk"]] = (
                prob, r.get("market_home_prob_book_disagreement"), r.get("market_home_prob_movement_agreement"),
                r.get("market_home_prob_median"), r.get("market_home_prob_std"), r.get("market_home_prob_favor_diff"),
            )
    print(f"Loaded consensus odds for {len(consensus)} games.")
    return consensus


def _load_totals_by_game() -> dict:
    """{game_pk: (team_total_diff, market_total_runs)} from backfill_historical_odds.py's
    cache — feeds team_total_diff/market_total_runs (see features.py). team_total_diff is home
    Team Total minus away's (already home-perspective); market_total_runs is the game Total Runs
    line. Both averaged across CONSENSUS_BOOKS at backfill time. Same "missing means no signal"
    handling as the other market loaders here."""
    path = os.path.join(CACHE_DIR, "historical_market_probs.parquet")
    if not os.path.exists(path):
        print("No historical_market_probs.parquet found — team_total_diff/market_total_runs will be NaN for all rows.")
        return {}
    odds_df = pd.read_parquet(path)
    required = {"market_team_total_home", "market_team_total_away", "market_total_runs"}
    if not required.issubset(odds_df.columns):
        print("historical_market_probs.parquet predates the team-total/total-runs columns — "
              "team_total_diff/market_total_runs will be NaN for all rows until backfill_historical_odds.py is re-run.")
        return {}
    totals = {}
    for _, r in odds_df.iterrows():
        home_total, away_total = r.get("market_team_total_home"), r.get("market_team_total_away")
        team_total_diff = (home_total - away_total) if pd.notna(home_total) and pd.notna(away_total) else None
        market_total_runs = r.get("market_total_runs")
        if team_total_diff is not None or pd.notna(market_total_runs):
            totals[r["game_pk"]] = (team_total_diff, market_total_runs if pd.notna(market_total_runs) else None)
    print(f"Loaded totals odds for {len(totals)} games.")
    return totals


_PLAYER_PROP_LINE_KEYS = ("strikeout_line", "outs_line", "er_line", "hits_allowed_line")


def _load_player_prop_lines_by_game() -> dict:
    """{game_pk: {"home": {"strikeout_line":.., "outs_line":.., "er_line":.., "hits_allowed_line":..},
    "away": {...}}} from backfill_player_props.py's cache — feeds market_strikeout_line/
    market_outs_line/market_er_line/market_hits_allowed_line (strikeout model) and
    market_outs_line_diff/market_er_line_diff/market_hits_allowed_line_diff (win-prob model), see
    features.py. Missing/NaN entries mean "no signal," same convention as every other market
    loader here — not every game has a backfilled fixture or full prop coverage."""
    path = os.path.join(CACHE_DIR, "historical_player_prop_lines.parquet")
    if not os.path.exists(path):
        print("No historical_player_prop_lines.parquet found — player-prop features will be NaN for all rows.")
        return {}
    df = pd.read_parquet(path)
    required = {f"{side}_{key}" for side in ("home", "away") for key in _PLAYER_PROP_LINE_KEYS}
    if not required.issubset(df.columns):
        print("historical_player_prop_lines.parquet predates the current schema — "
              "player-prop features will be NaN for all rows until backfill_player_props.py is re-run.")
        return {}
    lines_by_game = {}
    for _, r in df.iterrows():
        entry = {"home": {}, "away": {}}
        has_any = False
        for side in ("home", "away"):
            for key in _PLAYER_PROP_LINE_KEYS:
                val = r.get(f"{side}_{key}")
                if pd.notna(val):
                    entry[side][key] = val
                    has_any = True
        if has_any:
            lines_by_game[r["game_pk"]] = entry
    print(f"Loaded player-prop lines for {len(lines_by_game)} games.")
    return lines_by_game


def build_full_training_set(seasons: list[int]) -> pd.DataFrame:
    all_games = []
    for season in seasons:
        df = fetch_season_schedule_with_pitchers(season)
        all_games.append(df)
    all_games = pd.concat(all_games, ignore_index=True).dropna(subset=["home_pitcher_id", "away_pitcher_id", "game_date"])
    all_games = all_games.sort_values("game_date").reset_index(drop=True)

    print("Fetching historical weather (one API call per team, covering the whole date range)...")
    team_weather = {}  # team_abbr -> {date_str: {"temp_max_f":.., "wind_mean_mph":..}}
    # Open-Meteo's archive API only has observed data up through today — cap the end date there
    # rather than the season's actual end, since a future/in-progress season's later dates haven't
    # happened yet anyway (this function only ever sees completed games).
    weather_start = f"{min(seasons)}-01-01"
    weather_end = min(f"{max(seasons)}-12-31", datetime.now().strftime("%Y-%m-%d"))
    for team in pd.unique(all_games["home_team"]):
        team_weather[team] = get_team_weather_range(team, weather_start, weather_end)

    print("Fetching historical IL-activation data (one API call per unique game date, league-wide)...")
    # IL activations are league-wide, not team-specific, so this is one call per unique DATE
    # in the dataset rather than one per team — a game date's activation window is fully
    # determined by that date alone (see data_collection.get_recent_il_activations).
    il_activations_by_date = {}
    unique_dates = pd.unique(all_games["game_date"])
    for i, date in enumerate(unique_dates):
        if i % 50 == 0:
            print(f"  ...{i}/{len(unique_dates)}")
        il_activations_by_date[date] = get_recent_il_activations(as_of_date=date)

    print("Building feature rows from game history...")
    # We build recent-form/season-to-date/rest-days state incrementally so
    # each game's features only use information as of BEFORE that game
    # (no lookahead leakage).
    feature_rows = []
    pitcher_history = {}  # pitcher_id -> list of (ip, er, bb, k, hr, hbp, bf) for THIS season's starts so far
    pitcher_current_season = {}  # pitcher_id -> which season pitcher_history currently holds (reset at the boundary)
    last_start_date = {}  # pitcher_id -> game_date of their most recent start so far
    team_bullpen_history = {}  # team_abbr -> list of (game_date, bullpen_ip) for every game they've played
    # (pitcher_id, opp_team_abbr) -> list of (ip, er, bb, k, hr, hbp) — head-to-head history, deliberately
    # NEVER reset at a season boundary (unlike pitcher_history above), since spanning last season and this
    # one is exactly the signal this feature captures. Built from all_games' own box-score rows, already
    # in memory — no extra API pull needed, unlike live serving's get_pitcher_vs_team_history.
    pitcher_vs_team_history = {}
    # team_abbr -> list of (hits, at_bats) for every game they've played, oldest first — not
    # reset at a season boundary (a team persists across seasons, unlike an individual pitcher's
    # role), self-corrects within the first ~7 games of a new season regardless.
    team_batting_history = {}
    # team_abbr -> venue name of their most recent game (home or away) — walk-forward, not reset
    # at a season boundary (a team's actual last game before spring training doesn't matter much
    # either way; this just needs SOME prior location to compute distance from, and treats a
    # missing one as "no signal" via team_travel_miles' NaN handling, not zero).
    team_last_venue = {}

    latest_team_batting = {s: get_team_batting_splits(s) for s in seasons}
    latest_bullpen = {s: get_team_bullpen_stats(s) for s in seasons}
    latest_high_leverage_bullpen = {s: get_team_high_leverage_bullpen_stats(s) for s in seasons}
    latest_team_defense = {s: get_team_defense_oaa(s) for s in seasons}
    latest_team_batting_vs_hand = {
        s: {"L": get_team_batting_vs_hand(s, "L"), "R": get_team_batting_vs_hand(s, "R")} for s in seasons
    }
    # Prior-season full stat lines, for blending into a pitcher's thin-current-season
    # numbers the same way live serving does (see features.blend_with_prior_season) —
    # this was the actual bug: pitcher_history used to accumulate across season
    # boundaries with no reset, silently blending in unweighted prior-season data
    # during training while live serving saw a genuinely single-season-only snapshot.
    # Explicit, discounted blending here replaces that accidental mismatch.
    prior_season_pitching_stats = {}
    for s in seasons:
        try:
            prior_season_pitching_stats[s] = get_season_pitching_stats(s - 1)
        except Exception:
            prior_season_pitching_stats[s] = pd.DataFrame()

    # Prior season's per-pitch-type batter splits (whiff%/wOBA vs FF/SL/CU/CH/etc) — same
    # walk-forward-safe reasoning as prior_season_pitching_stats above: a completed season's
    # numbers are fully known before this season's first game, unlike Baseball Savant's
    # in-season arsenal leaderboard (see get_batter_pitch_arsenal's docstring).
    prior_batter_arsenal = {}
    for s in seasons:
        try:
            prior_batter_arsenal[s] = get_batter_pitch_arsenal(s - 1)
        except Exception:
            prior_batter_arsenal[s] = pd.DataFrame()

    # Same prior-season-for-training pattern as prior_batter_arsenal above, for the batch of
    # batter-level expected-stats/exit-velo/percentile-rank/batted-ball tables added alongside it.
    prior_batter_expected, prior_batter_exitvelo = {}, {}
    prior_batter_percentile, prior_batter_batted_ball, prior_batter_team_map = {}, {}, {}
    for s in seasons:
        try:
            prior_batter_expected[s] = get_batter_expected_stats(s - 1)
        except Exception:
            prior_batter_expected[s] = pd.DataFrame()
        try:
            prior_batter_exitvelo[s] = get_batter_exitvelo_barrels(s - 1)
        except Exception:
            prior_batter_exitvelo[s] = pd.DataFrame()
        try:
            prior_batter_percentile[s] = get_batter_percentile_ranks(s - 1)
        except Exception:
            prior_batter_percentile[s] = pd.DataFrame()
        try:
            prior_batter_batted_ball[s] = get_batted_ball_profile(s - 1, "batter")
        except Exception:
            prior_batter_batted_ball[s] = pd.DataFrame()
        try:
            prior_batter_team_map[s] = get_batter_team_map(s - 1)
        except Exception:
            prior_batter_team_map[s] = {}

    line_movement_by_game = _load_line_movement_by_game()
    market_divergence_by_game = _load_market_divergence_by_game()
    prediction_market_by_game = _load_prediction_market_by_game()
    consensus_by_game = _load_consensus_by_game()
    totals_by_game = _load_totals_by_game()
    player_prop_lines_by_game = _load_player_prop_lines_by_game()

    unique_pitchers = pd.unique(pd.concat([all_games["home_pitcher_id"], all_games["away_pitcher_id"]]))
    print(f"Fetching pitcher handedness for {len(unique_pitchers)} pitchers...")
    pitcher_hands = {}
    for i, pid in enumerate(unique_pitchers):
        if i % 50 == 0:
            print(f"  ...{i}/{len(unique_pitchers)}")
        pitcher_hands[pid] = get_pitcher_hand(int(pid))

    print(f"Fetching Statcast pitch-level data for {len(unique_pitchers)} pitchers "
          f"(one call per pitcher-season, this is the slow part)...")
    pitcher_statcast_daily = {}
    pitcher_velocity_daily = {}
    pitcher_pitch_types_daily = {}
    for i, pid in enumerate(unique_pitchers):
        if i % 25 == 0:
            print(f"  ...{i}/{len(unique_pitchers)}")
        combined, combined_velo, combined_pt = {}, {}, {}
        for season in seasons:
            # Same cached raw pitch-level pull backs all three of these (get_statcast_pitcher_logs) —
            # no extra network cost beyond the one already needed for whiff%/chase%/hard-hit%/CSW%.
            combined.update(get_pitcher_statcast_daily(int(pid), season))
            combined_velo.update(get_pitcher_velocity_daily(int(pid), season))
            combined_pt.update(get_pitcher_pitch_types_daily(int(pid), season))
        pitcher_statcast_daily[pid] = combined
        pitcher_velocity_daily[pid] = combined_velo
        pitcher_pitch_types_daily[pid] = combined_pt

    for _, row in all_games.iterrows():
        season = row["season"]

        # Reset each pitcher's in-progress season history the moment we cross into a
        # new season for them — without this, pitcher_history silently keeps last
        # season's starts mixed in with this season's, since nothing else segments it.
        for pid in (row["home_pitcher_id"], row["away_pitcher_id"]):
            if pitcher_current_season.get(pid) != season:
                pitcher_history[pid] = []
                pitcher_current_season[pid] = season

        recent_stats = {
            row["home_pitcher_id"]: _recent_stats_from_history(pitcher_history.get(row["home_pitcher_id"], [])),
            row["away_pitcher_id"]: _recent_stats_from_history(pitcher_history.get(row["away_pitcher_id"], [])),
        }
        statcast = {
            row["home_pitcher_id"]: statcast_cumulative_as_of(
                pitcher_statcast_daily.get(row["home_pitcher_id"], {}), row["game_date"]
            ),
            row["away_pitcher_id"]: statcast_cumulative_as_of(
                pitcher_statcast_daily.get(row["away_pitcher_id"], {}), row["game_date"]
            ),
        }
        velocity_trend = {
            row["home_pitcher_id"]: statcast_velocity_trend(
                pitcher_velocity_daily.get(row["home_pitcher_id"], {}), row["game_date"]
            ),
            row["away_pitcher_id"]: statcast_velocity_trend(
                pitcher_velocity_daily.get(row["away_pitcher_id"], {}), row["game_date"]
            ),
        }
        pitch_diversity = {
            row["home_pitcher_id"]: statcast_pitch_diversity(
                pitcher_pitch_types_daily.get(row["home_pitcher_id"], {}), row["game_date"]
            ),
            row["away_pitcher_id"]: statcast_pitch_diversity(
                pitcher_pitch_types_daily.get(row["away_pitcher_id"], {}), row["game_date"]
            ),
        }
        pitch_mix = {
            row["home_pitcher_id"]: statcast_pitch_mix_as_of(
                pitcher_pitch_types_daily.get(row["home_pitcher_id"], {}), row["game_date"]
            ),
            row["away_pitcher_id"]: statcast_pitch_mix_as_of(
                pitcher_pitch_types_daily.get(row["away_pitcher_id"], {}), row["game_date"]
            ),
        }
        prior_stats_df = prior_season_pitching_stats.get(season, pd.DataFrame())
        season_stats = {
            row["home_pitcher_id"]: blend_with_prior_season(
                _season_to_date_stats_from_history(
                    pitcher_history.get(row["home_pitcher_id"], []), statcast.get(row["home_pitcher_id"])
                ),
                season_stat_row_lookup(prior_stats_df, row["home_pitcher_id"]),
            ),
            row["away_pitcher_id"]: blend_with_prior_season(
                _season_to_date_stats_from_history(
                    pitcher_history.get(row["away_pitcher_id"], []), statcast.get(row["away_pitcher_id"])
                ),
                season_stat_row_lookup(prior_stats_df, row["away_pitcher_id"]),
            ),
        }
        rest_days = {}
        game_dt = datetime.strptime(row["game_date"], "%Y-%m-%d")
        for pid in (row["home_pitcher_id"], row["away_pitcher_id"]):
            if pid in last_start_date:
                rest_days[pid] = (game_dt - datetime.strptime(last_start_date[pid], "%Y-%m-%d")).days
        bullpen_fatigue = {
            row["home_team"]: _bullpen_fatigue_from_history(team_bullpen_history.get(row["home_team"], []), row["game_date"]),
            row["away_team"]: _bullpen_fatigue_from_history(team_bullpen_history.get(row["away_team"], []), row["game_date"]),
        }
        game_weather = team_weather.get(row["home_team"], {}).get(row["game_date"], {})
        day_il_activations = il_activations_by_date.get(row["game_date"], {})
        il_return_days = {
            row["home_pitcher_id"]: days_since_il_return(row["home_pitcher_id"], row["game_date"], day_il_activations),
            row["away_pitcher_id"]: days_since_il_return(row["away_pitcher_id"], row["game_date"], day_il_activations),
        }
        # Raw (unblended) prior-season line for the new prior_season_fip_diff/prior_season_k_bb_pct_diff
        # features — no walk-forward concern here, since a prior/completed season's numbers are already
        # fully known before this (current) season's first game, unlike season_stats above.
        raw_prior_season_stats = {
            row["home_pitcher_id"]: season_stat_row_lookup(prior_stats_df, row["home_pitcher_id"]),
            row["away_pitcher_id"]: season_stat_row_lookup(prior_stats_df, row["away_pitcher_id"]),
        }
        # Head-to-head: each pitcher's own history against THEIR SPECIFIC opponent tonight, spanning
        # every season in this training run — see pitcher_vs_team_history above.
        h2h_stats = {
            row["home_pitcher_id"]: _h2h_stats_from_history(
                pitcher_vs_team_history.get((row["home_pitcher_id"], row["away_team"]), [])
            ),
            row["away_pitcher_id"]: _h2h_stats_from_history(
                pitcher_vs_team_history.get((row["away_pitcher_id"], row["home_team"]), [])
            ),
        }
        recent_team_batting = {
            row["home_team"]: _recent_team_avg_from_history(team_batting_history.get(row["home_team"], [])),
            row["away_team"]: _recent_team_avg_from_history(team_batting_history.get(row["away_team"], [])),
        }
        recent_team_batting_30d = {
            row["home_team"]: _recent_team_avg_from_history(
                team_batting_history.get(row["home_team"], []), n=RECENT_TEAM_BATTING_GAMES_30D
            ),
            row["away_team"]: _recent_team_avg_from_history(
                team_batting_history.get(row["away_team"], []), n=RECENT_TEAM_BATTING_GAMES_30D
            ),
        }
        # Distance each team traveled to get to tonight's venue (always the home team's park)
        # from wherever their last game was — see weather.venue_distance_miles.
        tonight_venue = TEAM_HOME_VENUE.get(row["home_team"])
        team_travel = {
            row["home_team"]: venue_distance_miles(team_last_venue.get(row["home_team"]), tonight_venue),
            row["away_team"]: venue_distance_miles(team_last_venue.get(row["away_team"]), tonight_venue),
        }
        line_movement = line_movement_by_game.get(row["game_pk"])
        market_divergence = market_divergence_by_game.get(row["game_pk"])
        prediction_market_signal = prediction_market_by_game.get(row["game_pk"])
        consensus_prob, book_disagreement, book_movement_agreement, consensus_median_prob, book_prob_std, book_favor_diff = (
            consensus_by_game.get(row["game_pk"], (None, None, None, None, None, None))
        )
        team_total_diff, market_total_runs = totals_by_game.get(row["game_pk"], (None, None))
        game_player_prop_lines = player_prop_lines_by_game.get(row["game_pk"], {})
        feats = build_matchup_features(
            home_pitcher_id=row["home_pitcher_id"],
            away_pitcher_id=row["away_pitcher_id"],
            home_team_abbr=row["home_team"],
            away_team_abbr=row["away_team"],
            season_stats=season_stats,
            team_batting=latest_team_batting.get(season, pd.DataFrame()),
            bullpen_stats=latest_bullpen.get(season, pd.DataFrame()),
            park_factor_lookup=get_park_factor,
            recent_stats=recent_stats,
            rest_days=rest_days,
            il_return_days=il_return_days,
            pitcher_hands=pitcher_hands,
            team_batting_vs_hand=latest_team_batting_vs_hand.get(season, {}),
            bullpen_fatigue=bullpen_fatigue,
            high_leverage_bullpen_stats=latest_high_leverage_bullpen.get(season, pd.DataFrame()),
            team_defense=latest_team_defense.get(season, pd.DataFrame()),
            statcast=statcast,
            velocity_trend=velocity_trend,
            pitch_diversity=pitch_diversity,
            game_weather=game_weather,
            prior_season_stats=raw_prior_season_stats,
            h2h_stats=h2h_stats,
            recent_team_batting=recent_team_batting,
            recent_team_batting_30d=recent_team_batting_30d,
            team_travel=team_travel,
            line_movement=line_movement,
            market_divergence=market_divergence,
            prediction_market_signal=prediction_market_signal,
            consensus_prob=consensus_prob,
            book_disagreement=book_disagreement,
            book_movement_agreement=book_movement_agreement,
            consensus_median_prob=consensus_median_prob,
            book_prob_std=book_prob_std,
            book_favor_diff=book_favor_diff,
            team_total_diff=team_total_diff,
            market_total_runs=market_total_runs,
            home_pitcher_market_lines=game_player_prop_lines.get("home"),
            away_pitcher_market_lines=game_player_prop_lines.get("away"),
            pitch_mix=pitch_mix,
            batter_arsenal=prior_batter_arsenal.get(season, pd.DataFrame()),
            batter_expected=prior_batter_expected.get(season, pd.DataFrame()),
            batter_exitvelo=prior_batter_exitvelo.get(season, pd.DataFrame()),
            batter_percentile=prior_batter_percentile.get(season, pd.DataFrame()),
            batter_batted_ball=prior_batter_batted_ball.get(season, pd.DataFrame()),
            batter_team_map=prior_batter_team_map.get(season, {}),
        )
        feats["game_date"] = row["game_date"]
        feats["home_win"] = row["home_win"]
        # Not used in FEATURE_COLUMNS (model.train() only selects those), but kept on
        # the saved dataset so other tooling (e.g. clv_backtest.py) can join a row back
        # to the real game it came from.
        feats["home_team"] = row["home_team"]
        feats["away_team"] = row["away_team"]
        feats["game_pk"] = row["game_pk"]
        feature_rows.append(feats)

        team_bullpen_history.setdefault(row["home_team"], []).append((row["game_date"], row.get("home_bullpen_ip", 0.0)))
        team_bullpen_history.setdefault(row["away_team"], []).append((row["game_date"], row.get("away_bullpen_ip", 0.0)))

        # Now update recent-form/rest-days history AFTER using pre-game state for features
        pitcher_history.setdefault(row["home_pitcher_id"], []).append(
            (_parse_ip(row["home_ip"]), row["home_er"], row["home_bb"], row["home_k"], row["home_hr"],
             row.get("home_hbp", 0), row.get("home_bf", 0), row.get("home_h", 0)))
        pitcher_history.setdefault(row["away_pitcher_id"], []).append(
            (_parse_ip(row["away_ip"]), row["away_er"], row["away_bb"], row["away_k"], row["away_hr"],
             row.get("away_hbp", 0), row.get("away_bf", 0), row.get("away_h", 0)))
        last_start_date[row["home_pitcher_id"]] = row["game_date"]
        last_start_date[row["away_pitcher_id"]] = row["game_date"]
        pitcher_vs_team_history.setdefault((row["home_pitcher_id"], row["away_team"]), []).append(
            (_parse_ip(row["home_ip"]), row["home_er"], row["home_bb"], row["home_k"], row["home_hr"],
             row.get("home_hbp", 0)))
        pitcher_vs_team_history.setdefault((row["away_pitcher_id"], row["home_team"]), []).append(
            (_parse_ip(row["away_ip"]), row["away_er"], row["away_bb"], row["away_k"], row["away_hr"],
             row.get("away_hbp", 0)))
        team_batting_history.setdefault(row["home_team"], []).append(
            (row.get("home_team_hits", 0), row.get("home_team_ab", 0)))
        team_batting_history.setdefault(row["away_team"], []).append(
            (row.get("away_team_hits", 0), row.get("away_team_ab", 0)))
        # Both teams are now physically at tonight's venue — feeds the NEXT game's travel calc.
        team_last_venue[row["home_team"]] = tonight_venue
        team_last_venue[row["away_team"]] = tonight_venue

    training_df = pd.DataFrame(feature_rows)
    training_df.to_parquet(TRAINING_CACHE)
    print(f"Training set built: {len(training_df)} rows -> {TRAINING_CACHE}")
    return training_df


def build_strikeout_training_set(seasons: list[int]) -> pd.DataFrame:
    """
    Builds a per-pitcher-outing training set for the strikeout-prop model:
    one row per starting pitcher's actual outing, labeled with the
    strikeouts they actually recorded. A single game contributes TWO rows
    (the home starter's outing vs. the away lineup, and vice versa) since
    this predicts one pitcher's own total, not a home/away comparison.
    Reuses the same cached box scores as build_full_training_set.
    """
    all_games = []
    for season in seasons:
        df = fetch_season_schedule_with_pitchers(season)
        all_games.append(df)
    all_games = pd.concat(all_games, ignore_index=True).dropna(subset=["home_pitcher_id", "away_pitcher_id", "game_date"])
    all_games = all_games.sort_values("game_date").reset_index(drop=True)

    # De-vigged closing moneyline home win prob per game_pk, from backfill_historical_odds.py —
    # feeds the team_market_win_prob feature (see features.py). Missing/NaN for any game_pk not
    # yet backfilled (or where OpticOdds had no coverage) rather than an error — the model treats
    # it like any other missing feature (median-imputed at train time).
    historical_odds_path = os.path.join(CACHE_DIR, "historical_market_probs.parquet")
    if os.path.exists(historical_odds_path):
        odds_df = pd.read_parquet(historical_odds_path)
        market_prob_by_game = dict(zip(odds_df["game_pk"], odds_df["market_home_prob"]))
        n_matched = sum(1 for v in market_prob_by_game.values() if v is not None and pd.notna(v))
        print(f"Loaded historical market odds for {n_matched} games.")
    else:
        market_prob_by_game = {}
        print("No historical_market_probs.parquet found — team_market_win_prob will be NaN for all rows "
              "until backfill_historical_odds.py has been run.")

    player_prop_lines_by_game = _load_player_prop_lines_by_game()

    print("Fetching historical weather (one API call per team, cached — fast if already pulled)...")
    team_weather = {}  # team_abbr -> {date_str: {"temp_max_f":.., "wind_mean_mph":..}}
    # Open-Meteo's archive API only has observed data up through today — cap the end date there
    # rather than the season's actual end, since a future/in-progress season's later dates haven't
    # happened yet anyway (this function only ever sees completed games).
    weather_start = f"{min(seasons)}-01-01"
    weather_end = min(f"{max(seasons)}-12-31", datetime.now().strftime("%Y-%m-%d"))
    for team in pd.unique(all_games["home_team"]):
        team_weather[team] = get_team_weather_range(team, weather_start, weather_end)

    # No IL-return discounting here (unlike build_full_training_set below) — the strikeout model's
    # recent_k9 is used raw, with no _recent_form_weight/_layoff_weight-style reliability shrinkage
    # applied anywhere yet, so bolting on IL-return discounting alone here would be an inconsistent,
    # narrow patch rather than fixing the same thing the win-prob model has. Out of scope for now;
    # revisit alongside adding general recent-form reliability weighting to the strikeout model.

    print("Building strikeout-prop feature rows...")
    pitcher_history = {}  # pitcher_id -> list of (ip, er, bb, k, hr, hbp, bf) for THIS season's starts so far
    pitcher_current_season = {}  # pitcher_id -> which season pitcher_history currently holds (reset at the boundary)
    pitcher_last_date = {}  # pitcher_id -> date of their last start, for walk-forward rest days
    pitcher_vs_team_history = {}  # (pitcher_id, opp_team_abbr) -> list of (ip, er, bb, k, hr, hbp) — never reset, see build_full_training_set
    rows = []

    latest_team_batting = {s: get_team_batting_splits(s) for s in seasons}
    latest_team_batting_vs_hand = {
        s: {"L": get_team_batting_vs_hand(s, "L"), "R": get_team_batting_vs_hand(s, "R")} for s in seasons
    }
    # Same prior-season blend as build_full_training_set — see that function's comment.
    prior_season_pitching_stats = {}
    for s in seasons:
        try:
            prior_season_pitching_stats[s] = get_season_pitching_stats(s - 1)
        except Exception:
            prior_season_pitching_stats[s] = pd.DataFrame()

    # Same prior-season batter-pitch-type-split reasoning as build_full_training_set.
    prior_batter_arsenal = {}
    for s in seasons:
        try:
            prior_batter_arsenal[s] = get_batter_pitch_arsenal(s - 1)
        except Exception:
            prior_batter_arsenal[s] = pd.DataFrame()

    unique_pitchers = pd.unique(pd.concat([all_games["home_pitcher_id"], all_games["away_pitcher_id"]]))
    print(f"Fetching pitcher handedness for {len(unique_pitchers)} pitchers...")
    pitcher_hands = {}
    for i, pid in enumerate(unique_pitchers):
        if i % 50 == 0:
            print(f"  ...{i}/{len(unique_pitchers)}")
        pitcher_hands[pid] = get_pitcher_hand(int(pid))

    print(f"Fetching Statcast pitch-level data for {len(unique_pitchers)} pitchers (cached, fast if already pulled)...")
    pitcher_statcast_daily = {}
    pitcher_velocity_daily = {}
    pitcher_pitch_types_daily = {}
    for i, pid in enumerate(unique_pitchers):
        if i % 25 == 0:
            print(f"  ...{i}/{len(unique_pitchers)}")
        combined, combined_velo, combined_pt = {}, {}, {}
        for season in seasons:
            combined.update(get_pitcher_statcast_daily(int(pid), season))
            combined_velo.update(get_pitcher_velocity_daily(int(pid), season))
            combined_pt.update(get_pitcher_pitch_types_daily(int(pid), season))
        pitcher_statcast_daily[pid] = combined
        pitcher_velocity_daily[pid] = combined_velo
        pitcher_pitch_types_daily[pid] = combined_pt

    for _, row in all_games.iterrows():
        season = row["season"]
        team_batting = latest_team_batting.get(season, pd.DataFrame())
        prior_stats_df = prior_season_pitching_stats.get(season, pd.DataFrame())

        # Same season-boundary reset as build_full_training_set — see that function's comment.
        for pid in (row["home_pitcher_id"], row["away_pitcher_id"]):
            if pitcher_current_season.get(pid) != season:
                pitcher_history[pid] = []
                pitcher_current_season[pid] = season

        game_weather = team_weather.get(row["home_team"], {}).get(row["game_date"], {})

        for pid, opp_team, is_home, actual_k in [
            (row["home_pitcher_id"], row["away_team"], True, row["home_k"]),
            (row["away_pitcher_id"], row["home_team"], False, row["away_k"]),
        ]:
            recent = _recent_stats_from_history(pitcher_history.get(pid, []))
            blended_season = blend_with_prior_season(
                _season_to_date_stats_from_history(pitcher_history.get(pid, [])),
                season_stat_row_lookup(prior_stats_df, pid),
            )
            season_k9 = blended_season.get("k9")
            statcast = {pid: statcast_cumulative_as_of(pitcher_statcast_daily.get(pid, {}), row["game_date"])}
            recent_statcast = {pid: statcast_recent_as_of(pitcher_statcast_daily.get(pid, {}), row["game_date"])}
            velocity_trend = {pid: statcast_velocity_trend(pitcher_velocity_daily.get(pid, {}), row["game_date"])}
            pitch_diversity = {pid: statcast_pitch_diversity(pitcher_pitch_types_daily.get(pid, {}), row["game_date"])}
            pitch_mix = {pid: statcast_pitch_mix_as_of(pitcher_pitch_types_daily.get(pid, {}), row["game_date"])}
            last_date = pitcher_last_date.get(pid)
            rest_days = (
                (datetime.strptime(row["game_date"], "%Y-%m-%d") - last_date).days
                if last_date is not None else None
            )
            h2h_stats = {pid: _h2h_stats_from_history(pitcher_vs_team_history.get((pid, opp_team), []))}
            game_market_home_prob = market_prob_by_game.get(row["game_pk"])
            team_market_prob = (
                None if game_market_home_prob is None or pd.isna(game_market_home_prob)
                else (game_market_home_prob if is_home else 1 - game_market_home_prob)
            )
            pitcher_market_lines = player_prop_lines_by_game.get(row["game_pk"], {}).get(
                "home" if is_home else "away"
            )
            feats = build_strikeout_features(
                pitcher_id=pid,
                opp_team_abbr=opp_team,
                is_home=is_home,
                season_k9=season_k9,
                team_batting=team_batting,
                recent_stats={pid: recent},
                statcast=statcast,
                recent_statcast=recent_statcast,
                rest_days=rest_days,
                velocity_trend=velocity_trend,
                pitch_diversity=pitch_diversity,
                game_weather=game_weather,
                pitcher_hand=pitcher_hands.get(pid),
                team_batting_vs_hand=latest_team_batting_vs_hand.get(season, {}),
                h2h_stats=h2h_stats,
                team_market_prob=team_market_prob,
                pitch_mix=pitch_mix,
                batter_arsenal=prior_batter_arsenal.get(season, pd.DataFrame()),
                pitcher_market_lines=pitcher_market_lines,
            )
            feats["game_date"] = row["game_date"]
            feats["strikeouts"] = actual_k
            rows.append(feats)

        # Now update recent-form history AFTER using pre-game state for features
        pitcher_last_date[row["home_pitcher_id"]] = datetime.strptime(row["game_date"], "%Y-%m-%d")
        pitcher_last_date[row["away_pitcher_id"]] = datetime.strptime(row["game_date"], "%Y-%m-%d")
        pitcher_history.setdefault(row["home_pitcher_id"], []).append(
            (_parse_ip(row["home_ip"]), row["home_er"], row["home_bb"], row["home_k"], row["home_hr"],
             row.get("home_hbp", 0), row.get("home_bf", 0), row.get("home_h", 0)))
        pitcher_history.setdefault(row["away_pitcher_id"], []).append(
            (_parse_ip(row["away_ip"]), row["away_er"], row["away_bb"], row["away_k"], row["away_hr"],
             row.get("away_hbp", 0), row.get("away_bf", 0), row.get("away_h", 0)))
        pitcher_vs_team_history.setdefault((row["home_pitcher_id"], row["away_team"]), []).append(
            (_parse_ip(row["home_ip"]), row["home_er"], row["home_bb"], row["home_k"], row["home_hr"],
             row.get("home_hbp", 0)))
        pitcher_vs_team_history.setdefault((row["away_pitcher_id"], row["home_team"]), []).append(
            (_parse_ip(row["away_ip"]), row["away_er"], row["away_bb"], row["away_k"], row["away_hr"],
             row.get("away_hbp", 0)))

    training_df = pd.DataFrame(rows)
    training_df.to_parquet(STRIKEOUT_TRAINING_CACHE)
    print(f"Strikeout training set built: {len(training_df)} rows -> {STRIKEOUT_TRAINING_CACHE}")
    return training_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int, default=[2025, 2026])
    args = parser.parse_args()
    build_full_training_set(args.seasons)
    build_strikeout_training_set(args.seasons)
