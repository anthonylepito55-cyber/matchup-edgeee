"""
main.py

FastAPI app that serves:
  GET  /api/today          -> today's games with predictions
  GET  /api/matchup        -> predict a specific pitcher matchup
  GET  /api/pitcher/{id}   -> a pitcher's full-season start-by-start trend (drill-down view)
  GET  /api/team/{abbr}    -> a team's current-season offense/bullpen/defense snapshot (drill-down view)
  GET  /api/model/status   -> is a model trained, what are its backtest metrics
  POST /api/retrain        -> kick off a retrain using cached historical data
  GET  /api/tennis/today   -> today's ATP/WTA singles matches with win-probability predictions

Run with:
    uvicorn main:app --reload --port 8000
"""

import os
import asyncio
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import numpy as np
import pandas as pd

from data_collection import (
    get_probable_pitchers, get_season_pitching_stats, get_team_batting_splits,
    get_team_bullpen_stats, get_park_factor, get_pitcher_recent_starts,
    get_team_batting_vs_hand, get_pitcher_hand, get_team_recent_bullpen_usage,
    get_team_high_leverage_bullpen_stats, get_team_defense_oaa,
    get_confirmed_lineup, get_player_batting_stats, get_batter_hand, get_player_batting_vs_hand,
    predict_team_lineup,
    get_pitcher_statcast_daily, statcast_cumulative_as_of, statcast_recent_as_of,
    get_pitcher_velocity_daily, statcast_velocity_trend,
    get_pitcher_pitch_types_daily, statcast_pitch_diversity, statcast_pitch_mix_as_of, get_batter_pitch_arsenal,
    get_batter_expected_stats, get_batter_exitvelo_barrels, get_batter_percentile_ranks,
    get_batted_ball_profile, get_batter_team_map,
    get_recent_il_activations, days_since_il_return,
    get_pitcher_season_log, get_pitcher_info, get_bulk_reliever_pattern,
    get_pitcher_vs_team_history, get_team_recent_batting_form, RECENT_TEAM_BATTING_GAMES_30D,
    CACHE_DIR,
)
from features import (
    build_matchup_features, features_to_row, build_strikeout_features, strikeout_features_to_row,
    MIN_RELIABLE_STARTS, MIN_RELIABLE_SEASON_IP, LONG_LAYOFF_DAYS, MIN_RELIABLE_IP_PER_START, FEATURE_COLUMNS,
    BASEBALL_ONLY_FEATURE_COLUMNS, STRIKEOUT_FEATURE_COLUMNS, STRIKEOUT_BASEBALL_ONLY_FEATURE_COLUMNS,
    blend_with_prior_season,
)
from odds_fetcher import (
    get_moneyline_odds, get_strikeout_prop_lines, get_prizepicks_strikeout_lines, devig_home_prob,
    get_market_snapshot, get_active_injuries, get_pitcher_market_lines, normalize_player_name,
)
from weather import get_rain_risk, get_game_weather_live, team_travel_miles, TEAM_HOME_VENUE
from prediction_log import (
    log_predictions, settle_predictions, get_track_record, get_logged_prediction, PRE_GAME_STATUSES,
    get_available_dates, get_games_for_date,
)
from strikeout_prediction_log import (
    log_strikeout_predictions, settle_strikeout_predictions, get_strikeout_track_record,
    get_logged_strikeout_prediction, get_strikeouts_for_date,
)
import model as model_module
import rating_system
import props as props_module

from tennis_data import (
    get_atp_match_history, get_wta_match_history, get_tennis_today_matches,
    get_tennis_moneyline_odds, build_tournament_metadata_lookup, lookup_tournament_metadata,
    build_player_name_index, match_player_name,
)
from tennis_features import get_or_compute_state, build_live_matchup_features, features_to_row as tennis_features_to_row
import tennis_model

app = FastAPI(title="MLB Pitcher Matchup Predictor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this if you deploy publicly
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gates /api/* behind a shared password when deployed (DASHBOARD_PASSWORD set as an env var on
# the host) — unset locally, so this is a no-op in dev. Static files (index.html/JS bundle) stay
# unauthenticated so the frontend's own password prompt can load before the user has entered
# anything; only the actual prediction data behind /api/* is gated. See frontend/src/auth.js +
# PasswordGate.jsx for the client side.
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD")
_last_log_error = None  # TEMPORARY diagnostic — see /api/_debug_last_log_error, remove after use


@app.middleware("http")
async def require_dashboard_password(request, call_next):
    if DASHBOARD_PASSWORD and request.url.path.startswith("/api/"):
        supplied = request.headers.get("x-dashboard-password", "")
        if not secrets.compare_digest(supplied, DASHBOARD_PASSWORD):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)

BACKGROUND_REFRESH_SECONDS = 3600  # once an hour — keeps strikeout/moneyline predictions logged and
# the track records settled against real results even with nobody actively loading the page. Without
# this, both only ever updated as a side effect of a browser hitting /api/today — fine while someone's
# actively using the app, but the "record" could sit stale (unsettled Finals, un-logged later games)
# for however long nobody happens to look.


async def _background_refresh_loop():
    while True:
        await asyncio.sleep(BACKGROUND_REFRESH_SECONDS)
        try:
            # today()/tennis_today() are sync functions doing real network I/O — run them in a
            # worker thread so this doesn't block the event loop for every other request meanwhile.
            await asyncio.get_event_loop().run_in_executor(None, today)
        except Exception as e:
            print(f"[background refresh] today() failed: {e}")
        try:
            await asyncio.get_event_loop().run_in_executor(None, tennis_today)
        except Exception as e:
            print(f"[background refresh] tennis_today() failed: {e}")


@app.on_event("startup")
async def _start_background_refresh():
    asyncio.create_task(_background_refresh_loop())


def _recent_stats_for_matchup(home_pitcher_id: int, away_pitcher_id: int, season: int) -> dict:
    """{pitcher_id: {"era":.., "k9":.., "bb9":..}} for both starters, last 5 starts each."""
    return {
        home_pitcher_id: get_pitcher_recent_starts(home_pitcher_id, season),
        away_pitcher_id: get_pitcher_recent_starts(away_pitcher_id, season),
    }


def _statcast_for_matchup(home_pitcher_id: int, away_pitcher_id: int, season: int) -> dict:
    """{pitcher_id: {"whiff_pct":.., "chase_pct":.., "hard_hit_pct":..}}, season-to-date (as of now,
    which is naturally the full season pulled so far — no walk-forward filtering needed live)."""
    return {
        home_pitcher_id: statcast_cumulative_as_of(get_pitcher_statcast_daily(home_pitcher_id, season)),
        away_pitcher_id: statcast_cumulative_as_of(get_pitcher_statcast_daily(away_pitcher_id, season)),
    }


def _recent_statcast_for_matchup(home_pitcher_id: int, away_pitcher_id: int, season: int) -> dict:
    """Same shape as _statcast_for_matchup, but each pitcher's last-few-starts window
    (see data_collection.statcast_recent_as_of) instead of season-to-date — feeds the
    strikeout model's recent_whiff_pct/recent_chase_pct features."""
    return {
        home_pitcher_id: statcast_recent_as_of(get_pitcher_statcast_daily(home_pitcher_id, season)),
        away_pitcher_id: statcast_recent_as_of(get_pitcher_statcast_daily(away_pitcher_id, season)),
    }


def _velocity_trend_for_matchup(home_pitcher_id: int, away_pitcher_id: int, season: int) -> dict:
    """{pitcher_id: {"season_avg_velo":.., "recent_avg_velo":.., "velo_trend":..}}, as of now."""
    return {
        home_pitcher_id: statcast_velocity_trend(get_pitcher_velocity_daily(home_pitcher_id, season)),
        away_pitcher_id: statcast_velocity_trend(get_pitcher_velocity_daily(away_pitcher_id, season)),
    }


def _pitch_diversity_for_matchup(home_pitcher_id: int, away_pitcher_id: int, season: int) -> dict:
    """{pitcher_id: {"pitch_diversity":..}}, season-to-date as of now."""
    return {
        home_pitcher_id: statcast_pitch_diversity(get_pitcher_pitch_types_daily(home_pitcher_id, season)),
        away_pitcher_id: statcast_pitch_diversity(get_pitcher_pitch_types_daily(away_pitcher_id, season)),
    }


def _pitch_mix_for_matchup(home_pitcher_id: int, away_pitcher_id: int, season: int) -> dict:
    """{pitcher_id: {pitch_type: share}}, season-to-date as of now — see data_collection.statcast_pitch_mix_as_of."""
    return {
        home_pitcher_id: statcast_pitch_mix_as_of(get_pitcher_pitch_types_daily(home_pitcher_id, season)),
        away_pitcher_id: statcast_pitch_mix_as_of(get_pitcher_pitch_types_daily(away_pitcher_id, season)),
    }


def _rest_days_for_matchup(recent_stats: dict, game_date: str) -> dict:
    """{pitcher_id: days_since_last_start}, relative to this game's date.
    None (missing) if we don't have a prior start on record this season —
    features.py treats missing rest days as neutral, not zero. Note: these
    are the RAW day counts — features.py caps them before feeding the
    model (see MAX_REST_DAYS there), but the raw value is what's worth
    showing a human, since "38 days" is the whole point, not "10."""
    game_dt = datetime.strptime(game_date, "%Y-%m-%d")
    rest_days = {}
    for pid, stats in recent_stats.items():
        last_date = stats.get("last_start_date")
        if not last_date:
            continue
        rest_days[pid] = (game_dt - datetime.strptime(last_date, "%Y-%m-%d")).days
    return rest_days


SHORT_OUTING_IP_THRESHOLD = 3.0  # a normal starter goes ~5+ IP/start; openers/piggyback arms go 1-3


def _is_opener(recent: dict) -> bool:
    """
    True when a pitcher's recent starts consistently run short enough (avg
    under SHORT_OUTING_IP_THRESHOLD, over a real multi-start sample) that
    they're very likely being used as an opener/short reliever rather than
    a traditional starter. This is a genuine blind spot, not just a
    reliability caveat: the model's win-probability prediction is built
    entirely around THIS pitcher's own stats as a proxy for who determines
    the game, but an opener typically throws one inning and hands off to a
    bulk/relief arm the app has no visibility into at all — confirmed
    directly on a real case (Bryan Hudson, CWS: 5 different starts this
    season, every single one 1.0-1.7 IP, never once going deeper). See
    _apply_confidence_override and the opener_affected response field for
    how this actually changes the served prediction, not just the warning
    text.
    """
    ip_per_start = recent.get("ip_per_start")
    return (
        recent.get("sample_type") == "starts" and recent.get("sample_size", 0) >= MIN_RELIABLE_STARTS
        and ip_per_start is not None and ip_per_start < SHORT_OUTING_IP_THRESHOLD
    )


def _resolve_effective_starter(pitcher_id: int, team_abbr: str, season: int, recent: dict) -> tuple:
    """
    For an opener, tries to find a single reliever who's consistently
    thrown the bulk of the game after them (see
    data_collection.get_bulk_reliever_pattern) — if found, THEIR stats
    should drive the win-probability matchup instead of the opener's own
    near-meaningless 1-2-inning numbers, since they're the one who
    actually faces most of the opposing lineup tonight. Only affects the
    win-probability side; strikeout props stay on the actually-announced
    pitcher (that's who the real bet is on). Returns
    (effective_pitcher_id, substituted: bool, bulk_pitcher_name: str|None).
    """
    if not _is_opener(recent):
        return pitcher_id, False, None
    bulk_id = get_bulk_reliever_pattern(pitcher_id, team_abbr, season)
    if bulk_id is None:
        return pitcher_id, False, None
    bulk_name = get_pitcher_info(bulk_id).get("name")
    return bulk_id, True, bulk_name


def _opener_substitution_warning(pitcher_name: str, bulk_name: str) -> list[str]:
    return [
        f"{pitcher_name} is opening, not starting a full game — {bulk_name} has thrown the bulk of the "
        f"innings after {pitcher_name} in most of their recent short outings, so this game's win "
        f"probability is built from {bulk_name}'s own stats instead (still an approximation: those stats "
        f"come from {bulk_name}'s own starts/appearances, not specifically pitching in relief right after "
        f"{pitcher_name}). The strikeout prop below is still about {pitcher_name} specifically."
    ]


def _prior_season_blend_warning(pitcher_name: str, current_ip, blended_ip) -> list[str]:
    """Flags when a pitcher's season stats leaned meaningfully on their prior season because
    this year's own sample is too thin to trust alone (see features.blend_with_prior_season) —
    same transparency spirit as _pitcher_warnings, just for the season-stats side rather than
    recent-form. Caught directly from a real case: a pitcher back from injury with one bad
    start looked like a toss-up instead of the above-average pitcher his 2025 season said he was."""
    current_ip = current_ip or 0.0
    if blended_ip is None or pd.isna(blended_ip) or blended_ip <= current_ip + 0.1:
        return []
    if current_ip >= MIN_RELIABLE_SEASON_IP:
        return []
    return [
        f"{pitcher_name} has only {current_ip:.1f} innings this season, so their season stats are "
        f"blended with last season's performance to avoid overreacting to a tiny sample."
    ]


def _il_return_warning(pitcher_name: str, days_since_return) -> list[str]:
    if days_since_return is None:
        return []
    return [
        f"{pitcher_name} was activated off the injured list {days_since_return} day"
        f"{'s' if days_since_return != 1 else ''} ago — recent form may still reflect a return "
        f"trajectory rather than where they've settled, regardless of how good or bad the "
        f"underlying numbers look."
    ]


def _pitcher_warnings(pitcher_name: str, rest_days_val, recent: dict) -> list[str]:
    """
    Flags situations where a pitcher's recent-form/season stats are likely
    unreliable predictors of tonight's start:
      - no outings at all on record this season
      - recent form built from relief appearances, not starts, because
        real starts were too sparse (see get_pitcher_recent_starts) — a
        real, current signal, but an imperfect proxy since relief outings
        tend to run a bit better than the same pitcher's start numbers
      - long layoff since their last actual START (IL return, rehab
        assignment — or simply a swingman who's been pitching in relief
        this whole time and is now making a rare/first start, which looks
        identical from a "days since last start" measurement alone)
      - "opener" usage: recent starts averaging only 1-2 innings means
        their own K/BB/IP numbers describe an opener's workload, not a
        real start — and there's no way to confirm from box scores alone
        whether tonight they're pitching a normal game or opening again,
        so this is a caveat, not a correction.
    """
    warnings = []
    starts = recent.get("starts", 0)
    sample_size = recent.get("sample_size", 0)
    sample_type = recent.get("sample_type", "starts")

    if sample_size == 0:
        warnings.append(f"{pitcher_name} has no outings on record this season — limited data for this prediction.")
        return warnings

    if sample_type == "appearances":
        warnings.append(
            f"{pitcher_name} has made only {starts} start{'s' if starts != 1 else ''} this season, so their "
            f"recent-form numbers are based on their last {sample_size} appearances (including relief) instead — "
            f"relief outings tend to run a bit better than the same pitcher's numbers as a starter, so treat "
            f"this as an approximation."
        )
    elif sample_size < MIN_RELIABLE_STARTS:
        warnings.append(
            f"{pitcher_name} has only {sample_size} start{'s' if sample_size != 1 else ''} on record this "
            f"season — too small a sample for reliable recent-form numbers."
        )

    if rest_days_val is not None and rest_days_val >= LONG_LAYOFF_DAYS:
        warnings.append(
            f"{pitcher_name} hasn't started in {rest_days_val} days — likely returning from injury/minors, "
            f"or has been pitching in relief this whole time; treat this prediction with extra caution."
        )

    if _is_opener(recent):
        ip_per_start = recent["ip_per_start"]
        warnings.append(
            f"{pitcher_name} has averaged only {ip_per_start:.1f} IP over their last {sample_size} starts — "
            f"almost certainly an opener/short-reliever role, not a traditional start. This game's win "
            f"probability is built around {pitcher_name}'s own stats, but they'll likely hand off after "
            f"1-2 innings to a bulk/relief arm the model has no visibility into at all — treat the whole "
            f"prediction for this game, not just the strikeout number, as low-confidence."
        )

    return warnings


def _weather_warnings(venue: str, game_time_utc: str) -> list[str]:
    """
    Flags meaningful rain risk during the game window at an outdoor park.
    Not a model input — there's no reliable historical weather archive to
    backtest a "rain shortens starts" adjustment against, so this is a
    caveat for a human to weigh, same spirit as the layoff/small-sample
    warnings: a rain-shortened outing means fewer innings and fewer
    strikeouts than the matchup alone would predict, regardless of how
    good the pitcher looks on paper tonight.
    """
    risk = get_rain_risk(venue, game_time_utc)
    if risk is None:
        return []
    return [
        f"Rain in the forecast ({risk['max_precip_prob']}% chance) around first pitch at {risk['venue']} — "
        f"either starter could be pulled early if it hits, which would cut their strikeout total short "
        f"regardless of the matchup."
    ]


def _json_safe(stats: dict) -> dict:
    """NaN isn't valid JSON; swap it for None at the API boundary (internal code still uses NaN
    via pandas' notna() checks). Also casts numpy scalar types to native Python ones — FastAPI's
    encoder doesn't reliably handle numpy.int64 specifically (confirmed live: crashes the whole
    endpoint with "'numpy.int64' object is not iterable" once its dict()/vars() fallbacks both
    fail — /api/matchup's exposed "features" dict was the first place this actually got hit,
    via defense_oaa_diff, since OAA is a genuinely integer stat, unlike every other diff feature
    here which happens to come out as numpy.float64 and pass through fine)."""
    out = {}
    for k, v in stats.items():
        if isinstance(v, float) and pd.isna(v):
            out[k] = None
        elif isinstance(v, np.integer):
            out[k] = int(v)
        elif isinstance(v, np.floating):
            out[k] = float(v)
        elif isinstance(v, np.bool_):
            out[k] = bool(v)
        else:
            out[k] = v
    return out


# Human-readable labels for FEATURE_COLUMNS, shown in the UI's data-completeness
# warning so a missing feature reads as "opponent lineup quality" not "opp_lineup_woba_diff".
_FEATURE_LABELS = {
    "home_field": "home field",
    "park_factor_home": "park factor",
    "fip_diff": "season FIP",
    "k_bb_pct_diff": "season K-BB%",
    "recent_fip_diff": "recent FIP",
    "recent_k9_diff": "recent K/9",
    "recent_bb9_diff": "recent BB/9",
    "bullpen_fip_diff": "bullpen quality",
    "opp_lineup_woba_diff": "opponent lineup quality",
    "opp_platoon_woba_diff": "opponent platoon matchup",
    "bullpen_fatigue_diff": "bullpen fatigue",
    "high_leverage_bullpen_fip_diff": "closer/setup quality",
    "defense_oaa_diff": "team defense",
    "whiff_pct_diff": "whiff%",
    "chase_pct_diff": "chase%",
    "hard_hit_pct_diff": "hard-hit%",
    "csw_pct_diff": "CSW%",
    "rest_days_diff": "rest days",
}


def _data_completeness(feats: dict) -> dict:
    """Which model features came back NaN for this matchup, surfaced explicitly rather than
    silently letting XGBoost's native missing-value handling absorb them. A team-abbreviation
    mismatch once nulled bullpen/defense/lineup/park-factor features for ~25% of games with no
    visible symptom other than a prediction that looked slightly off — this is the guardrail that
    would have caught it without a manual spot-check."""
    missing = [col for col in FEATURE_COLUMNS if pd.isna(feats.get(col, np.nan))]
    total = len(FEATURE_COLUMNS)
    return {
        "complete": len(missing) == 0,
        "completeness_pct": round((total - len(missing)) / total * 100, 1),
        "missing_features": missing,
        "missing_labels": [_FEATURE_LABELS.get(c, c) for c in missing],
    }


def _season_stat_lookup(season_pitching_stats: pd.DataFrame, pid: int) -> dict:
    """Raw (non-JSON-safe) season era/ip/fip/k_bb_pct/k9/hr9/whip/k_pct/bb_pct for one pitcher
    from the flat, season-to-date Baseball-Reference table. This is fetched "now" for a live
    prediction, which is exactly the season-to-date a real prediction should see — unlike
    training, where the same flat table used for every historical game would be leakage (see
    build_training_data._season_to_date_stats_from_history for the walk-forward fix there)."""
    era = ip = fip = k_bb_pct = k9 = hr9 = h9 = whip = k_pct = bb_pct = ip_per_start = None
    xera = xfip = siera = None
    if season_pitching_stats is not None and "mlbID" in season_pitching_stats.columns:
        row = season_pitching_stats[season_pitching_stats["mlbID"] == pid]
        if not row.empty:
            era, ip = row.iloc[0].get("ERA"), row.iloc[0].get("IP_float")
            fip, k_bb_pct = row.iloc[0].get("FIP"), row.iloc[0].get("K-BB%")
            k9 = row.iloc[0].get("K9")
            hr9 = row.iloc[0].get("HR9")
            h9 = row.iloc[0].get("H9")
            whip = row.iloc[0].get("WHIP")
            k_pct = row.iloc[0].get("K_pct")
            bb_pct = row.iloc[0].get("BB_pct")
            ip_per_start = row.iloc[0].get("IP_per_GS")
            xera = row.iloc[0].get("xera")
            xfip = row.iloc[0].get("xFIP")
            siera = row.iloc[0].get("SIERA")
    return {
        "era": era, "ip": ip, "fip": fip, "k_bb_pct": k_bb_pct, "k9": k9, "hr9": hr9, "h9": h9,
        "whip": whip, "k_pct": k_pct, "bb_pct": bb_pct, "ip_per_start": ip_per_start,
        "xera": xera, "xfip": xfip, "siera": siera,
    }


def _season_stat_lookup_blended(season_pitching_stats: pd.DataFrame, prior_season_pitching_stats: pd.DataFrame,
                                 pid: int) -> dict:
    """_season_stat_lookup, blended with the pitcher's prior season when this season's
    innings are too thin to trust alone — see features.blend_with_prior_season."""
    current = _season_stat_lookup(season_pitching_stats, pid)
    prior = _season_stat_lookup(prior_season_pitching_stats, pid)
    return blend_with_prior_season(current, prior)


def _season_stats_for_matchup(season_pitching_stats: pd.DataFrame, prior_season_pitching_stats: pd.DataFrame,
                               home_pitcher_id: int, away_pitcher_id: int) -> dict:
    """Display-friendly (JSON-safe) season stats for both starters — same source the model's
    fip_diff/k_bb_pct_diff features use, so what's displayed matches what actually drives the prediction."""
    return {
        "home": _json_safe(_season_stat_lookup_blended(season_pitching_stats, prior_season_pitching_stats, home_pitcher_id)),
        "away": _json_safe(_season_stat_lookup_blended(season_pitching_stats, prior_season_pitching_stats, away_pitcher_id)),
    }


def _team_stat_row(df: pd.DataFrame, team_abbr: str, col: str, decimals: int = 3):
    if df is None or df.empty or "Team" not in df.columns:
        return None
    row = df[df["Team"] == team_abbr]
    if row.empty:
        return None
    val = row.iloc[0].get(col)
    return None if pd.isna(val) else round(float(val), decimals)


def _team_stats_for_matchup(team_batting: pd.DataFrame, bullpen_stats: pd.DataFrame,
                             high_leverage_bullpen_stats: pd.DataFrame, recent_team_batting: dict,
                             home_team_abbr: str, away_team_abbr: str) -> dict:
    """Display-friendly (JSON-safe) team-level context for both sides — the same offense/
    bullpen signals the model's opp_lineup_woba_diff/bullpen_fip_diff/recent_team_batting_diff
    features use, logged alongside each prediction so a later look-back (e.g. the previous-
    day tab) can see the full picture, not just the pitcher-vs-pitcher numbers."""
    def side(team_abbr):
        recent_avg = (recent_team_batting or {}).get(team_abbr, {}).get("avg")
        return {
            "season_avg": _team_stat_row(team_batting, team_abbr, "AVG"),
            "season_woba": _team_stat_row(team_batting, team_abbr, "wOBA"),
            "season_k_pct": _team_stat_row(team_batting, team_abbr, "K_pct", 1),
            "bullpen_fip": _team_stat_row(bullpen_stats, team_abbr, "bullpen_fip", 2),
            "bullpen_era": _team_stat_row(bullpen_stats, team_abbr, "bullpen_era", 2),
            "high_leverage_bullpen_fip": _team_stat_row(high_leverage_bullpen_stats, team_abbr, "high_leverage_fip", 2),
            "recent_batting_avg": None if pd.isna(recent_avg) else recent_avg,
        }
    return {"home": side(home_team_abbr), "away": side(away_team_abbr)}


def _lineup_breakdown(batter_ids: list, opp_pitcher_hand: str, season: int,
                       player_batting: pd.DataFrame, batter_hands: dict) -> list[dict]:
    """
    Every confirmed batter in tonight's lineup, in batting-order, with
    their own season AVG and their own split specifically against the
    hand tonight's opposing starter throws — the real per-player platoon
    picture, not a team-wide average that blends in bench bats and the
    opposite-hand split nobody's actually facing tonight. Empty list if
    no lineup has posted yet.
    """
    # Both calls below are blocking network requests (each individually cached on disk, but the
    # per-batter cache all expires together every 24h — see get_player_batting_vs_hand), so a full
    # slate's worth of lineups done one batter at a time serially is the single biggest latency
    # cost in /api/today on the first refresh of a new day (500+ sequential requests across 16
    # games). Threaded here since these are pure I/O waits with no shared mutable state between
    # batters — same values as the sequential version, just fetched concurrently.
    def _fetch_one(bid):
        vs_hand = get_player_batting_vs_hand(bid, season, opp_pitcher_hand)
        # Prefer the MLB Stats API name (clean UTF-8) over Baseball-Reference's "Name" column,
        # which pybaseball's scraper returns already mangled/mojibake for accented names.
        name = get_pitcher_info(bid).get("name")  # generic /people/{id} lookup, works for any player
        return bid, name, vs_hand

    ids = list(batter_ids or [])
    fetched = {}
    if ids:
        with ThreadPoolExecutor(max_workers=min(len(ids), 12)) as pool:
            for bid, name, vs_hand in pool.map(_fetch_one, ids):
                fetched[bid] = (name, vs_hand)

    out = []
    for bid in ids:
        row = player_batting[player_batting["mlbID"] == bid] if player_batting is not None and not player_batting.empty else None
        season_avg = row.iloc[0].get("player_AVG") if row is not None and not row.empty else None
        name, vs_hand = fetched[bid]
        if name is None:
            name = row.iloc[0]["Name"] if row is not None and not row.empty else None
        out.append({
            "batter_id": int(bid),
            "name": name,
            "hand": batter_hands.get(bid, "R"),
            "season_avg": None if season_avg is None or pd.isna(season_avg) else round(float(season_avg), 3),
            "vs_hand_avg": None if pd.isna(vs_hand.get("avg")) else round(float(vs_hand["avg"]), 3),
            "vs_hand_pa": vs_hand.get("pa", 0),
        })
    return out


def _resolve_lineup(confirmed_ids: list, team_abbr: str) -> tuple:
    """
    Falls back to predict_team_lineup (built from the team's actual last-5-games batting
    orders) when the official lineup hasn't posted yet — this feeds both the display AND
    build_matchup_features' real-lineup wOBA upgrade, so a good guess at who's actually
    playing tonight beats the season-wide team average even before MLB confirms it.
    Returns (batter_ids, is_predicted).
    """
    if confirmed_ids:
        return confirmed_ids, False
    predicted = predict_team_lineup(team_abbr)
    return predicted, bool(predicted)


def _season_stats_dict_for_matchup(season_pitching_stats: pd.DataFrame, prior_season_pitching_stats: pd.DataFrame,
                                    home_pitcher_id: int, away_pitcher_id: int) -> dict:
    """{pitcher_id: {"fip":.., "k_bb_pct":.., "ip":..}} shape build_matchup_features expects."""
    return {
        home_pitcher_id: _season_stat_lookup_blended(season_pitching_stats, prior_season_pitching_stats, home_pitcher_id),
        away_pitcher_id: _season_stat_lookup_blended(season_pitching_stats, prior_season_pitching_stats, away_pitcher_id),
    }


def _raw_prior_season_stats_dict_for_matchup(prior_season_pitching_stats: pd.DataFrame,
                                              home_pitcher_id: int, away_pitcher_id: int) -> dict:
    """{pitcher_id: {"fip":.., "k_bb_pct":.., "ip":..}} — the RAW prior season, unblended, for
    build_matchup_features' prior_season_fip_diff/prior_season_k_bb_pct_diff features. Distinct
    from _season_stats_dict_for_matchup above, which blends prior season INTO the current-season
    number rather than exposing it as an independent signal."""
    return {
        home_pitcher_id: _season_stat_lookup(prior_season_pitching_stats, home_pitcher_id),
        away_pitcher_id: _season_stat_lookup(prior_season_pitching_stats, away_pitcher_id),
    }


H2H_SEASONS_LOOKBACK = 2025  # earliest season included in a pitcher's own head-to-head history — see
# data_collection.get_pitcher_vs_team_history; combined with the current season below


def _h2h_stats_dict_for_matchup(home_pitcher_id: int, away_pitcher_id: int, home_team_abbr: str,
                                 away_team_abbr: str, season: int) -> dict:
    """{pitcher_id: {"fip":.., "k9":.., "starts":.., "ip":..}} — each pitcher's OWN history
    against the SPECIFIC opponent they're facing tonight (home pitcher vs away team, away
    pitcher vs home team), covering H2H_SEASONS_LOOKBACK through the current season."""
    seasons = sorted(set([H2H_SEASONS_LOOKBACK, season]))
    return {
        home_pitcher_id: get_pitcher_vs_team_history(home_pitcher_id, away_team_abbr, seasons),
        away_pitcher_id: get_pitcher_vs_team_history(away_pitcher_id, home_team_abbr, seasons),
    }


def _natural_strikeout_line(mean_k: float) -> float:
    """
    When there's no real sportsbook line to show against, pick the half-
    integer line whose over-probability is closest to 50/50 — this is
    roughly what a book's own line-setting would land on, so the displayed
    number reads the same way a real prop line would (a "coin flip" line
    at the pitcher's own median, not just their raw mean).
    """
    candidates = [max(round(mean_k) - 0.5, 0.5), round(mean_k) + 0.5]
    return min(candidates, key=lambda l: abs(props_module.over_under_prob(mean_k, l)["over"] - 0.5))


def _one_strikeout_prediction(pitcher_id: int, pitcher_name: str, opp_team_abbr: str, is_home: bool,
                               season_stats: pd.DataFrame, team_batting: pd.DataFrame, recent_stats: dict,
                               prop_lines: dict, statcast: dict = None, opp_lineup: list = None,
                               player_batting: pd.DataFrame = None, prizepicks_lines: dict = None,
                               recent_statcast: dict = None, rest_days: dict = None,
                               prior_season_stats: pd.DataFrame = None,
                               velocity_trend: dict = None, pitch_diversity: dict = None,
                               game_weather: dict = None, pitcher_hand: str = None,
                               team_batting_vs_hand: dict = None, h2h_stats: dict = None,
                               team_market_prob: float = None, pitch_mix: dict = None,
                               batter_arsenal: pd.DataFrame = None,
                               pitcher_market_lines: dict = None,
                               strikeout_market_model_trained: bool = False) -> dict:
    feats = build_strikeout_features(
        pitcher_id=pitcher_id, opp_team_abbr=opp_team_abbr, is_home=is_home,
        season_k9=_season_stat_lookup_blended(season_stats, prior_season_stats, pitcher_id).get("k9"),
        team_batting=team_batting, recent_stats=recent_stats, statcast=statcast,
        opp_lineup=opp_lineup, player_batting=player_batting,
        recent_statcast=recent_statcast, rest_days=(rest_days or {}).get(pitcher_id),
        velocity_trend=velocity_trend, pitch_diversity=pitch_diversity, game_weather=game_weather,
        pitcher_hand=pitcher_hand, team_batting_vs_hand=team_batting_vs_hand, h2h_stats=h2h_stats,
        team_market_prob=team_market_prob, pitch_mix=pitch_mix, batter_arsenal=batter_arsenal,
        pitcher_market_lines=pitcher_market_lines,
    )
    row = strikeout_features_to_row(feats)
    # Model A (baseball-only) is the PRIMARY served prediction — same reasoning as the win-prob
    # model (see the plan doc): a model that's partly learned the player-prop market can't
    # credibly claim to find value against that same market. Model B (full, incl. market
    # features) only ever feeds the secondary market_model_predicted_k comparison field below.
    predicted = props_module.predict_strikeouts(
        row, model_path=props_module.STRIKEOUT_BASELINE_MODEL_PATH,
        feature_columns=STRIKEOUT_BASEBALL_ONLY_FEATURE_COLUMNS,
    )
    market_model_predicted_k = None
    if strikeout_market_model_trained:
        try:
            market_model_predicted_k = round(props_module.predict_strikeouts(
                row, model_path=props_module.STRIKEOUT_MODEL_PATH, feature_columns=STRIKEOUT_FEATURE_COLUMNS,
            ), 1)
        except Exception:
            market_model_predicted_k = None

    book_line = prop_lines.get(normalize_player_name(pitcher_name))
    if book_line:
        line, line_source = book_line["line"], "book"
        bookmaker, over_price, under_price = book_line["bookmaker"], book_line["over_price"], book_line["under_price"]
    else:
        line, line_source = _natural_strikeout_line(predicted), "model"
        bookmaker = over_price = under_price = None

    probs = props_module.over_under_prob(predicted, line)

    # PrizePicks priced separately from prop_lines above (a DFS pick'em
    # product, not a sportsbook — its line and pricing convention routinely
    # diverge from FanDuel/DraftKings on the same pitcher/night), so it gets
    # its own over/under probability against its own line rather than
    # reusing the traditional-book one.
    prizepicks = None
    pp_line = (prizepicks_lines or {}).get(normalize_player_name(pitcher_name))
    if pp_line:
        pp_probs = props_module.over_under_prob(predicted, pp_line["line"])
        prizepicks = {
            "line": pp_line["line"],
            "over_prob": pp_probs["over"], "under_prob": pp_probs["under"],
            "over_price": pp_line["over_price"], "under_price": pp_line["under_price"],
            "deep_link": pp_line.get("deep_link"),
        }

    return {
        "predicted": round(predicted, 1),
        "line": line, "line_source": line_source,
        "over_prob": probs["over"], "under_prob": probs["under"],
        "bookmaker": bookmaker, "over_price": over_price, "under_price": under_price,
        "prizepicks": prizepicks,
        "market_model_predicted_k": market_model_predicted_k,
    }


def _strikeout_predictions(home_pitcher_id: int, away_pitcher_id: int, home_pitcher_name: str, away_pitcher_name: str,
                            home_team_abbr: str, away_team_abbr: str, season_stats: pd.DataFrame,
                            team_batting: pd.DataFrame, recent_stats: dict, prop_lines: dict = None,
                            statcast: dict = None, lineups: dict = None, player_batting: pd.DataFrame = None,
                            prizepicks_lines: dict = None, recent_statcast: dict = None,
                            rest_days: dict = None, prior_season_stats: pd.DataFrame = None,
                            velocity_trend: dict = None, pitch_diversity: dict = None,
                            game_weather: dict = None, pitcher_hands: dict = None,
                            team_batting_vs_hand: dict = None, h2h_stats: dict = None,
                            market_home_prob: float = None, pitch_mix: dict = None,
                            batter_arsenal: pd.DataFrame = None,
                            pitcher_market_lines_by_name: dict = None) -> dict | None:
    """{"home": {...}, "away": {...}}, or None if the strikeout model isn't trained. See
    _one_strikeout_prediction for the shape of each side."""
    # Model A (baseball-only) is the primary strikeout model now — same reasoning as win-prob,
    # see the plan doc. Model B loads too, purely for the market_model_predicted_k comparison.
    if props_module.load_strikeout_model(props_module.STRIKEOUT_BASELINE_MODEL_PATH)[0] is None:
        return None
    strikeout_market_model_trained = props_module.load_strikeout_model(props_module.STRIKEOUT_MODEL_PATH)[0] is not None
    prop_lines = prop_lines or {}
    lineups = lineups or {}
    pitcher_hands = pitcher_hands or {}
    pitcher_market_lines_by_name = pitcher_market_lines_by_name or {}
    team_market_prob_home = market_home_prob
    team_market_prob_away = (1 - market_home_prob) if market_home_prob is not None else None
    home_pitcher_market_lines = pitcher_market_lines_by_name.get(normalize_player_name(home_pitcher_name))
    away_pitcher_market_lines = pitcher_market_lines_by_name.get(normalize_player_name(away_pitcher_name))
    return {
        "home": _one_strikeout_prediction(
            home_pitcher_id, home_pitcher_name, away_team_abbr, True, season_stats, team_batting, recent_stats,
            prop_lines, statcast, opp_lineup=lineups.get("away"), player_batting=player_batting,
            prizepicks_lines=prizepicks_lines, recent_statcast=recent_statcast, rest_days=rest_days,
            prior_season_stats=prior_season_stats, velocity_trend=velocity_trend, pitch_diversity=pitch_diversity,
            game_weather=game_weather, pitcher_hand=pitcher_hands.get(home_pitcher_id),
            team_batting_vs_hand=team_batting_vs_hand, h2h_stats=h2h_stats,
            team_market_prob=team_market_prob_home, pitch_mix=pitch_mix, batter_arsenal=batter_arsenal,
            pitcher_market_lines=home_pitcher_market_lines,
            strikeout_market_model_trained=strikeout_market_model_trained,
        ),
        "away": _one_strikeout_prediction(
            away_pitcher_id, away_pitcher_name, home_team_abbr, False, season_stats, team_batting, recent_stats,
            prop_lines, statcast, opp_lineup=lineups.get("home"), player_batting=player_batting,
            prizepicks_lines=prizepicks_lines, recent_statcast=recent_statcast, rest_days=rest_days,
            prior_season_stats=prior_season_stats, velocity_trend=velocity_trend, pitch_diversity=pitch_diversity,
            game_weather=game_weather, pitcher_hand=pitcher_hands.get(away_pitcher_id),
            team_batting_vs_hand=team_batting_vs_hand, h2h_stats=h2h_stats,
            team_market_prob=team_market_prob_away, pitch_mix=pitch_mix, batter_arsenal=batter_arsenal,
            pitcher_market_lines=away_pitcher_market_lines,
            strikeout_market_model_trained=strikeout_market_model_trained,
        ),
    }


# --- Confidence override -------------------------------------------------
#
# NOT part of the trained model — a transparent, explicit adjustment
# layered on top of it. The model itself is deliberately cautious on rare,
# extreme multi-signal-agreement matchups: it's trained on ~3,800 games,
# and validated testing (looser regularization, an added "agreement"
# feature) showed that trying to make the trained model itself more
# decisive on these cases makes accuracy WORSE, both overall and on the
# specific subset of extreme mismatches — it's a real data-volume
# ceiling, not a bug. So instead of corrupting the model, this nudges the
# DISPLAYED number when every underlying stat already agrees, strongly,
# in the same direction — capped so it can't manufacture false certainty,
# and always reported alongside the model's own uncalibrated number so
# it's visible, not hidden.
_AGREEMENT_SCALES = {
    "fip_diff": 0.25, "k_bb_pct_diff": 2.0, "recent_fip_diff": 0.4,
    "recent_k9_diff": 1.0, "recent_bb9_diff": 0.7, "bullpen_fip_diff": 0.3,
    "opp_lineup_woba_diff": 0.015, "rest_days_diff": 5.0,
    # Added later than the set above (originally built before these features existed) — a real gap
    # confirmed directly: Casey Mize (home, 24 days off IL) vs Cristopher Sánchez, where season FIP/
    # K-BB%/bullpen alone scored -7.0 (just under the 8.0 threshold, no override), but chase_pct_diff
    # (-8.0) and gb_pct_diff (-21.6) alone were huge, unseen signals also favoring the away pitcher —
    # the override was blind to entire feature categories added later in the same session.
    #
    # Scales calibrated against each feature's actual training-data standard deviation (not picked
    # by feel like the original 8 above) — a first pass using scale ~= 0.6x std made the override fire
    # on 12 of 14 games in one slate, several at the max shift, once these 8 extra terms were summed
    # alongside the original 8. Loosened to ~0.9x std (process/quality signals — noisier and less
    # directly tied to run prevention than FIP/K-BB%, so a bigger relative move should be required to
    # count as "agreeing") plus a raised AGREEMENT_OVERRIDE_THRESHOLD below, re-validated against a
    # live slate until the override rate matched this session's established baseline (rare — a
    # handful of games, not most of them).
    "whiff_pct_diff": 4.2, "chase_pct_diff": 3.2, "hard_hit_pct_diff": 5.9,
    "gb_pct_diff": 8.4, "barrel_pct_diff": 2.3, "csw_pct_diff": 2.3,
    # Prior (e.g. 2025) season FIP/K-BB% — a year stale, so given a wider "notable" scale (~0.5x std)
    # than their current-season counterparts (needs a bigger gap to count as equally meaningful).
    "prior_season_fip_diff": 0.55, "prior_season_k_bb_pct_diff": 3.5,
}
_RECENT_FORM_KEYS = {"recent_fip_diff", "recent_k9_diff", "recent_bb9_diff"}
# Statcast rate diffs share fip_diff/k_bb_pct_diff's season_weight (see build_matchup_features), so
# they're gated by the same current-season-IP reliability check.
_SEASON_KEYS = {
    "fip_diff", "k_bb_pct_diff", "whiff_pct_diff", "chase_pct_diff",
    "hard_hit_pct_diff", "gb_pct_diff", "barrel_pct_diff", "csw_pct_diff",
}
# Prior-season FIP/K-BB% are weighted by their OWN (prior-season) innings, independent of how much
# a pitcher has thrown THIS season — so they're not gated by season_reliable's current-season-IP
# check. They're still tied to a specific pitcher's identity, though: excluded only when that
# identity itself is in question (an opener with no resolved bulk reliever, see any_unresolved_opener).
_PRIOR_SEASON_KEYS = {"prior_season_fip_diff", "prior_season_k_bb_pct_diff"}
# MIN_RELIABLE_STARTS / MIN_RELIABLE_SEASON_IP / LONG_LAYOFF_DAYS now live in features.py, imported above —
# they're also used there to shrink unreliable diffs toward 0 before the model ever sees them, so the raw
# model and this display-layer override agree on what counts as "reliable."
AGREEMENT_OVERRIDE_THRESHOLD = 11.0   # sum of standardized diffs needed before any adjustment kicks in — raised
# from 8.0 alongside the 8 new features added to _AGREEMENT_SCALES above: summing twice as many terms
# pushes typical (non-extreme) games' scores higher just from aggregate noise, so the bar needs to move
# with the term count, not stay fixed. Picked from the actual score distribution on a live 14-game
# slate, not a round-number guess: scores clustered into two clean groups with a wide natural gap —
# nine games at |score| >= 15.0 (including both hand-verified real cases, Hudson/Fedde at -15.03 and
# Mize/Sánchez at -15.30) and the rest at |score| <= 7.83. 11.0 sits centered in that gap. Earlier
# attempts (14.0, 16.0, 20.0) were picked before actually inspecting the score distribution and either
# let through too much of the slate or, at 16.0/20.0, cut off both verified cases along with everything
# else in that same natural cluster.
AGREEMENT_OVERRIDE_MAX_SHIFT = 0.18  # largest probability nudge the override can ever apply


def _agreement_score(feats: dict, recent_form_reliable: bool = True, season_reliable: bool = True,
                      identity_reliable: bool = True) -> float:
    """
    Signed sum of each diff feature normalized by its own 'notable' scale
    (same scales used for the reason-generation thresholds) — a positive
    score means most/all signals favor home, negative means away.

    When recent_form_reliable is False (either pitcher has fewer than
    MIN_RELIABLE_STARTS starts logged, or an active long-layoff makes that
    window stale), the recent-form components are excluded entirely.
    When season_reliable is False (either pitcher has under
    MIN_RELIABLE_SEASON_IP innings on the season), the season FIP/K-BB%/
    whiff%/chase%/hard-hit%/GB%/barrel%/CSW% components are excluded too —
    for a pitcher with only a handful of starts all year, "season" and
    "recent form" are the same small sample, so trusting both isn't two
    independent confirmations, it's the same noise counted twice.
    When identity_reliable is False (an opener with no resolved bulk
    reliever — see any_unresolved_opener), the prior-season components are
    excluded too: they're tied to a specific pitcher's own track record,
    and that identity is exactly what's in question here.
    """
    total = 0.0
    for col, scale in _AGREEMENT_SCALES.items():
        if col in _RECENT_FORM_KEYS and not recent_form_reliable:
            continue
        if col in _SEASON_KEYS and not season_reliable:
            continue
        if col in _PRIOR_SEASON_KEYS and not identity_reliable:
            continue
        val = feats.get(col)
        if val is not None and pd.notna(val):
            total += val / scale
    return total


def _apply_confidence_override(home_win_prob: float, feats: dict, recent_form_out: dict,
                                season_stats_out: dict = None, any_long_layoff: bool = False,
                                any_recent_il_return: bool = False, any_unresolved_opener: bool = False) -> dict:
    """Returns {"home_win_prob", "away_win_prob", "model_home_win_prob", "overridden"}.

    DISABLED as of 2026-07-14 — kept as a passthrough (always returns the raw model probability
    unchanged) rather than deleted, since the scoring machinery below (_agreement_score /
    _AGREEMENT_SCALES) still backs _generate_reason's "why" explanations. Measured against the
    full ~3,800-game walk-forward set (analyze_override_calibration.py) against every metric that
    actually matters — not "feels more intuitive" — the override made things worse across the
    board on the 1,365 games (42.5%) it touched: Brier 0.2431->0.2639, log loss 0.6793->0.7280,
    ECE 0.0115->0.1409 (12x worse), precision on its own 65%+-confidence calls 61.9%->59.0%, and
    flat-stake ROI vs. the market's closing line +5.2%->-4.2% while silently flipping the pick on
    304 of 944 games with a matched closing line. The model's own calibration (CalibratedClassifierCV
    sigmoid, see model.py train()) already does the real calibration work; this was a second,
    uncalibrated adjustment layered on top guessing at the same thing with less data. Do not
    re-enable without the same backtest showing an improvement on Brier/log loss/ECE/CLV — not
    just a plausible-sounding rationale for a specific game.
    """
    return {"home_win_prob": round(home_win_prob, 4), "away_win_prob": round(1 - home_win_prob, 4),
            "model_home_win_prob": round(home_win_prob, 4), "overridden": False}


def _generate_reason(favored_is_home: bool, season_stats_out: dict, recent_form_out: dict,
                      any_long_layoff: bool = False, team_stats_out: dict = None) -> str:
    """
    Explains the pick using the same numbers already shown on the card —
    not a black-box importance score, just "here's what's actually
    different between these two pitchers, in the favored team's favor."
    Each candidate reason is only used if it actually points toward the
    team the model favors; ranked by how far past a "notable" threshold
    each one is, so the 2-3 most decisive factors surface first.

    team_stats_out adds bullpen/recent-batting as candidate reasons — added after a user-flagged
    case (2026-07-18, PIT@CLE) where the displayed reason ("more strikeouts lately") looked like a
    thin justification for a ~60% favorite. It wasn't wrong, just incomplete: the away starter
    (Jones) actually graded out slightly BETTER on season/recent FIP and BB/9, so none of those
    could be cited — but bullpen_fip_diff is the single most heavily-weighted feature in the whole
    trained model (confirmed via feature importance), and Cleveland's bullpen edge here was real
    and large (2.98 vs 4.46 high-leverage FIP). The reason text had no way to say so, because
    bullpen/batting were never candidates at all — only pitcher FIP/K-BB%/K9/BB9 were.
    """
    fav_side, other_side = ("home", "away") if favored_is_home else ("away", "home")
    candidates = []  # (score, phrase)

    def add(fav_val, other_val, threshold, lower_is_better, phrase_fn):
        if fav_val is None or other_val is None:
            return
        gap = (other_val - fav_val) if lower_is_better else (fav_val - other_val)
        if gap <= 0:
            return  # doesn't actually favor the predicted side; don't cite it
        candidates.append((gap / threshold, phrase_fn(fav_val, other_val)))

    if season_stats_out:
        s_fav, s_other = season_stats_out[fav_side], season_stats_out[other_side]
        fav_ip, other_ip = s_fav.get("ip"), s_other.get("ip")
        if (fav_ip is not None and fav_ip >= MIN_RELIABLE_SEASON_IP and
                other_ip is not None and other_ip >= MIN_RELIABLE_SEASON_IP):
            add(s_fav.get("fip"), s_other.get("fip"), 0.25, True,
                lambda f, o: f"better season FIP ({f:.2f} vs {o:.2f})")
            add(s_fav.get("k_bb_pct"), s_other.get("k_bb_pct"), 2.0, False,
                lambda f, o: f"better K-BB% ({f:.1f}% vs {o:.1f}%)")

    r_fav, r_other = recent_form_out[fav_side], recent_form_out[other_side]
    # A "last N starts" stat from a tiny sample (e.g. one 3-inning outing
    # after an injury), one backfilled from relief appearances, one made up
    # of short-leash/bulk-relief stints that never actually go deep, or one
    # that predates an active long layoff (stale — no read on how it'll
    # look now), isn't solid enough to cite as a reason someone's favored.
    if (not any_long_layoff and
            r_fav.get("sample_type") == "starts" and r_fav.get("sample_size", 0) >= MIN_RELIABLE_STARTS and
            (r_fav.get("ip_per_start") or 0) >= MIN_RELIABLE_IP_PER_START and
            r_other.get("sample_type") == "starts" and r_other.get("sample_size", 0) >= MIN_RELIABLE_STARTS and
            (r_other.get("ip_per_start") or 0) >= MIN_RELIABLE_IP_PER_START):
        n_fav, n_other = r_fav["sample_size"], r_other["sample_size"]
        add(r_fav.get("fip"), r_other.get("fip"), 0.4, True,
            lambda f, o: f"better recent form — {f:.2f} FIP vs {o:.2f} over their last {n_fav}/{n_other} starts")
        add(r_fav.get("k9"), r_other.get("k9"), 1.0, False,
            lambda f, o: f"more strikeouts lately ({f:.1f} vs {o:.1f} K/9 over last {n_fav}/{n_other} starts)")
        add(r_fav.get("bb9"), r_other.get("bb9"), 0.7, True,
            lambda f, o: f"better command lately ({f:.1f} vs {o:.1f} BB/9 over last {n_fav}/{n_other} starts)")

    # Bullpen and recent-team-hitting reasons — same "cite it if it actually favors the pick"
    # logic as the pitcher-only checks above, just pulling from team_stats_out instead of a
    # single starter's own numbers. See this function's docstring for why these were missing.
    if team_stats_out:
        t_fav, t_other = team_stats_out.get(fav_side, {}), team_stats_out.get(other_side, {})
        # high-leverage only, not also the whole-bullpen average — the two are correlated enough
        # that citing both reads as repetitive ("a stronger bullpen... a stronger bullpen"), and
        # high-leverage is the more decision-relevant of the two (who actually pitches the 7th-9th
        # of a close game, not the average across the whole depth chart, mop-up arms included —
        # same reasoning bullpen_edge_when_close_diff's own docstring already uses).
        add(t_fav.get("high_leverage_bullpen_fip"), t_other.get("high_leverage_bullpen_fip"), 0.5, True,
            lambda f, o: f"a stronger late-game bullpen ({f:.2f} vs {o:.2f} FIP)")
        add(t_fav.get("recent_batting_avg"), t_other.get("recent_batting_avg"), 0.02, False,
            lambda f, o: f"better recent hitting ({f:.3f} vs {o:.3f} over their last ~7 games)")

    if not candidates:
        return "No single stat stands out — this one's close."

    candidates.sort(key=lambda c: c[0], reverse=True)
    phrases = [p for _, p in candidates[:3]]
    if len(phrases) == 1:
        return phrases[0].capitalize() + "."
    return (", ".join(phrases[:-1]) + ", and " + phrases[-1]).capitalize() + "."


def _tennis_reason(feats: dict, player_1_favored: bool) -> str:
    """Same spirit as _generate_reason above — cite the biggest gaps in the
    features that actually point toward the favored player, in the favored
    player's own terms, so it reads as 'here's what's different' rather than
    a black-box score."""
    sign = 1 if player_1_favored else -1
    candidates = []

    def add(diff, threshold, phrase_fn):
        if diff is None or pd.isna(diff):
            return
        signed = diff * sign
        if signed <= 0:
            return
        candidates.append((signed / threshold, phrase_fn(signed)))

    add(feats.get("elo_diff"), 100, lambda v: f"a {v:.0f}-point overall Elo edge")
    add(feats.get("surface_elo_diff"), 100, lambda v: f"a {v:.0f}-point Elo edge on this surface")
    add(feats.get("surface_form_diff"), 0.2, lambda v: f"a better recent record on this surface ({v*100:.0f} pts better win rate over their last matches)")
    add(feats.get("opponent_quality_diff"), 50, lambda v: "a track record against tougher recent competition")
    add(feats.get("h2h_diff"), 0.3, lambda v: "a head-to-head edge")

    if not candidates:
        return "No single factor stands out — this one's close."
    candidates.sort(key=lambda c: c[0], reverse=True)
    phrases = [p for _, p in candidates[:2]]
    if len(phrases) == 1:
        return phrases[0].capitalize() + "."
    return (" and ".join(phrases)).capitalize() + "."


@app.get("/api/tennis/today")
def tennis_today(date: str = None):
    """
    Today's ATP + WTA singles matches with win-probability predictions.
    Built from a free historical dataset (surface/Elo/form/opponent-
    quality/H2H/rest days only — no serve/return stats, see
    tennis_features.py's module docstring for the full scope note) and
    live odds/schedule via OpticOdds. Each league gets its own model
    (see tennis_model.py).
    """
    date = date or datetime.now().strftime("%Y-%m-%d")
    live_odds = get_tennis_moneyline_odds(date)
    all_matches = get_tennis_today_matches(date)

    results = []
    for league, history_fn in (("atp", get_atp_match_history), ("wta", get_wta_match_history)):
        league_matches = [m for m in all_matches if m["league"] == league]
        if not league_matches:
            continue

        model_trained = tennis_model.load_model(league)[0] is not None
        feat_df, player_states, h2h = get_or_compute_state(league, history_fn, as_of_date=pd.Timestamp(date))
        history = history_fn()
        tournament_meta = build_tournament_metadata_lookup(history)
        name_index = build_player_name_index(history)

        for m in league_matches:
            p1_name = match_player_name(m["player_1"], name_index)
            p2_name = match_player_name(m["player_2"], name_index)

            meta = lookup_tournament_metadata(m["tournament"], tournament_meta)
            surface = meta["surface"] if meta else "Hard"  # most common surface tour-wide; reasonable default
            surface_known = meta is not None
            best_of_5 = bool(meta and meta.get("series") == "Grand Slam" and league == "atp")

            prediction = None
            reason = None
            feats_out = None
            if model_trained and p1_name and p2_name:
                feats = build_live_matchup_features(
                    p1_name, p2_name, surface, best_of_5, player_states, h2h,
                    as_of_date=pd.Timestamp(date),
                )
                row = tennis_features_to_row(feats)
                prediction = tennis_model.predict_proba(row, league)
                reason = _tennis_reason(feats, prediction["player_1_win_prob"] >= 0.5)
                feats_out = _json_safe(feats)

            odds_entry = live_odds.get(m["fixture_id"])
            note = None
            if not model_trained:
                note = "Model not trained yet"
            elif not p1_name or not p2_name:
                note = "No historical match data for one or both players (qualifier/wildcard with no tracked tour-level matches)"

            results.append({
                **m,
                "surface": surface, "surface_estimated": not surface_known,
                "best_of_5": best_of_5,
                "live_odds": {
                    "player_1": odds_entry["player_1"], "player_2": odds_entry["player_2"],
                    "bookmaker": odds_entry["bookmaker"],
                } if odds_entry else None,
                "prediction": prediction,
                "reason": reason,
                "features": feats_out,
                "note": note,
            })

    return {"date": date, "matches": results}


@app.get("/api/pitcher/{pitcher_id}")
def pitcher_detail(pitcher_id: int, season: int = None):
    """
    A pitcher's full-season start-by-start trend line — every start with
    its own FIP/K9/BB9 plus that start's own whiff%/chase%/hard-hit%
    (from the same walk-forward-safe Statcast pull the model itself uses,
    see data_collection.get_pitcher_statcast_daily). This is a display-only
    view, not a model input — no leakage concerns here since nothing here
    trains anything.
    """
    season = season or datetime.now().year
    info = get_pitcher_info(pitcher_id)
    log_df = get_pitcher_season_log(pitcher_id, season)
    statcast_daily = get_pitcher_statcast_daily(pitcher_id, season)

    starts = []
    if log_df is not None and not log_df.empty:
        for _, row in log_df.iterrows():
            date = row["game_date"]
            counts = statcast_daily.get(date)
            whiff_pct = chase_pct = hard_hit_pct = csw_pct = None
            if counts:
                swings, whiffs, ooz, chases, batted, hard_hit = counts[:6]
                called_strikes, total_pitches = counts[6:8] if len(counts) >= 8 else (0, 0)
                whiff_pct = round(whiffs / swings * 100, 1) if swings > 0 else None
                chase_pct = round(chases / ooz * 100, 1) if ooz > 0 else None
                hard_hit_pct = round(hard_hit / batted * 100, 1) if batted > 0 else None
                csw_pct = round((whiffs + called_strikes) / total_pitches * 100, 1) if total_pitches > 0 else None
            starts.append({
                "date": date,
                "opponent": row.get("opponent"),
                "ip": round(float(row["ip"]), 1),
                "k": int(row["k"]), "bb": int(row["bb"]), "er": int(row["er"]),
                "era": round(float(row["era"]), 2),
                "fip": round(float(row["fip"]), 2),
                "k9": round(float(row["k9"]), 1),
                "bb9": round(float(row["bb9"]), 1),
                "whiff_pct": whiff_pct, "chase_pct": chase_pct, "hard_hit_pct": hard_hit_pct, "csw_pct": csw_pct,
                "is_win": bool(row["is_win"]) if pd.notna(row.get("is_win")) else None,
            })

    season_totals = statcast_cumulative_as_of(statcast_daily)
    return {
        "pitcher_id": pitcher_id,
        "name": info.get("name"),
        "hand": info.get("hand"),
        "season": season,
        "starts": starts,
        "season_whiff_pct": round(season_totals["whiff_pct"], 1) if pd.notna(season_totals["whiff_pct"]) else None,
        "season_chase_pct": round(season_totals["chase_pct"], 1) if pd.notna(season_totals["chase_pct"]) else None,
        "season_hard_hit_pct": round(season_totals["hard_hit_pct"], 1) if pd.notna(season_totals["hard_hit_pct"]) else None,
        "season_csw_pct": round(season_totals["csw_pct"], 1) if pd.notna(season_totals["csw_pct"]) else None,
    }


@app.get("/api/team/{team_abbr}")
def team_detail(team_abbr: str, season: int = None):
    """
    Team-level snapshot for the drill-down view: the same offense/bullpen/defense
    quality signals the matchup model itself uses. Unlike the pitcher drill-down,
    this isn't a day-by-day trend — no walk-forward per-game team history is built
    or cached anywhere in this app (team quality is treated as a season-long
    constant, like park factor, not something that needs a start-by-start line),
    so there's nothing to chart across time here.
    """
    season = season or datetime.now().year

    def _row(df, col, decimals=2):
        if df is None or df.empty or "Team" not in df.columns:
            return None
        r = df[df["Team"] == team_abbr]
        if r.empty:
            return None
        val = r.iloc[0].get(col)
        return None if pd.isna(val) else round(float(val), decimals)

    team_batting = get_team_batting_splits(season)
    vs_l = get_team_batting_vs_hand(season, "L")
    vs_r = get_team_batting_vs_hand(season, "R")
    bullpen = get_team_bullpen_stats(season)
    high_leverage = get_team_high_leverage_bullpen_stats(season)
    defense = get_team_defense_oaa(season)
    bullpen_fatigue_ip = get_team_recent_bullpen_usage(team_abbr)

    return {
        "team": team_abbr,
        "season": season,
        "batting": {
            "woba": _row(team_batting, "wOBA", 3),
            "k_pct": _row(team_batting, "K_pct", 1),
            "woba_vs_lhp": _row(vs_l, "wOBA_vs_hand", 3),
            "woba_vs_rhp": _row(vs_r, "wOBA_vs_hand", 3),
        },
        "bullpen": {
            "fip": _row(bullpen, "bullpen_fip"),
            "era": _row(bullpen, "bullpen_era"),
            "k9": _row(bullpen, "bullpen_k9"),
            "ip": _row(bullpen, "bullpen_ip", 1),
            "high_leverage_fip": _row(high_leverage, "high_leverage_fip"),
            "recent_fatigue_ip_last_3d": round(bullpen_fatigue_ip, 1),
        },
        "defense": {
            "oaa": _row(defense, "team_oaa", 1),
        },
        "park_factor": get_park_factor(team_abbr),
    }


@app.get("/api/model/status")
def model_status():
    # "trained"/"metrics" describe Model A (baseball-only) — the model that actually drives
    # every served prediction, see the plan doc. market_model_* describes Model B (baseball +
    # market features), which only ever feeds the secondary market_model_prob comparison field.
    m, medians, metrics = model_module.load_model(model_module.BASELINE_MODEL_PATH)
    market_m, market_medians, market_metrics = model_module.load_model(model_module.MODEL_PATH)
    # Same primary/secondary split for the strikeout model — see props.STRIKEOUT_BASELINE_MODEL_PATH.
    k_model, k_medians, k_metrics = props_module.load_strikeout_model(props_module.STRIKEOUT_BASELINE_MODEL_PATH)
    k_market_model, _, k_market_metrics = props_module.load_strikeout_model(props_module.STRIKEOUT_MODEL_PATH)
    return {
        "trained": m is not None,
        "metrics": metrics,
        "market_model_trained": market_m is not None,
        "market_model_metrics": market_metrics,
        "strikeout_model_trained": k_model is not None,
        "strikeout_metrics": k_metrics,
        "strikeout_market_model_trained": k_market_model is not None,
        "strikeout_market_model_metrics": k_market_metrics,
    }


@app.get("/api/_debug_last_log_error")
def _debug_last_log_error():
    """TEMPORARY — remove once the Railway logging-failure investigation is done."""
    return {"error": _last_log_error}


@app.get("/api/history/dates")
def history_dates():
    """Every date with at least one logged prediction, most recent first — powers the
    previous-day tab's date picker."""
    return {"dates": get_available_dates()}


@app.get("/api/history/{date}")
def history_for_date(date: str):
    """
    Read-only view of what was actually predicted (and, once settled, what
    happened) for a past date — straight from the frozen prediction logs,
    never recomputed. This is the real forward-test record: a completed
    game's prediction here is exactly what was shown before the game
    started, not a fresh re-run with the benefit of hindsight.
    """
    win_rows = get_games_for_date(date)
    k_rows = get_strikeouts_for_date(date)
    k_by_game = {}
    for k in k_rows:
        k_by_game.setdefault(k["game_pk"], []).append(k)

    games = []
    for g in win_rows:
        g = dict(g)
        g["strikeouts"] = k_by_game.get(g["game_pk"], [])
        games.append(g)

    settled = [g for g in games if g["settled"]]
    win_prob_record = None
    if settled:
        win_prob_record = {
            "total": len(settled),
            "correct": sum(1 for g in settled if g["correct"]),
        }
    k_settled = [k for k in k_rows if k["settled"] and k["correct"] is not None]
    strikeout_record = None
    if k_settled:
        strikeout_record = {
            "total": len(k_settled),
            "correct": sum(1 for k in k_settled if k["correct"]),
        }

    return {
        "date": date,
        "games": games,
        "win_prob_record": win_prob_record,
        "strikeout_record": strikeout_record,
    }


@app.get("/api/today")
def today(date: str = None):
    games = get_probable_pitchers(date)
    season = datetime.now().year
    resolved_date = date or datetime.now().strftime("%Y-%m-%d")

    # Model A (baseball-only) is the PRIMARY served prediction — a model that's partly learned
    # the market can't credibly claim to find value against that same market, see the plan doc
    # ("Market-data expansion...") for the full reasoning. Model B (full, incl. market features)
    # loads too, purely for the secondary market_model_prob comparison field below.
    model_trained = model_module.load_model(model_module.BASELINE_MODEL_PATH)[0] is not None
    market_model_trained = model_module.load_model(model_module.MODEL_PATH)[0] is not None
    rating_fitted = rating_system.load_rating_system()  # display-only "why" breakdown, see rating_system.py

    # All 7 of these are independent live/market fetches with no shared state — each already
    # tolerates its own failure internally (returns {} / [] rather than raising), so running them
    # concurrently is a pure latency win with no change in behavior. Same reasoning as the
    # per-batter lineup fix below: on a cold cache (e.g. a fresh Railway deploy with no persisted
    # data_cache/), doing 7+ independent network round-trips one at a time is the difference
    # between a few seconds and a minute-plus.
    with ThreadPoolExecutor(max_workers=7) as _setup_pool:
        _live_odds_f = _setup_pool.submit(get_moneyline_odds, date)
        # One shared fetch backing line_movement/market_divergence/consensus/book-by-book/
        # prediction markets — see odds_fetcher.get_market_snapshot for why this replaced 3-4 calls.
        _market_snapshot_f = _setup_pool.submit(get_market_snapshot, date)
        _injuries_f = _setup_pool.submit(get_active_injuries)  # live-only, display-only
        _prop_lines_f = _setup_pool.submit(get_strikeout_prop_lines, date)
        _prizepicks_f = _setup_pool.submit(get_prizepicks_strikeout_lines, date)
        # {normalized_pitcher_name: {"strikeout_line":.., "outs_line":.., "er_line":..,
        # "hits_allowed_line":..}} — feeds market_outs_line_diff/etc. (win-prob) and
        # market_outs_line/etc. (strikeout model).
        _pitcher_market_lines_f = _setup_pool.submit(get_pitcher_market_lines, date)

        def _il_activations_safe():
            try:
                return get_recent_il_activations(as_of_date=resolved_date)
            except Exception:
                return {}
        _il_activations_f = _setup_pool.submit(_il_activations_safe)

        live_odds = _live_odds_f.result()
        market_snapshot = _market_snapshot_f.result()
        injuries_by_team = _injuries_f.result()
        prop_lines = _prop_lines_f.result()
        prizepicks_lines = _prizepicks_f.result()
        pitcher_market_lines = _pitcher_market_lines_f.result()
        il_activations = _il_activations_f.result()

    # Baseball-Reference is an external scrape target and occasionally
    # blocks/fails; when that happens, we can't build model features, so
    # predictions are skipped for this request rather than 500ing.
    season_stats = team_batting = bullpen_stats = team_batting_vs_hand = None
    high_leverage_bullpen_stats = team_defense = player_batting = prior_season_stats = None
    data_error = None
    if model_trained:
        try:
            # Same concurrency reasoning as the setup fetches above — these 13 calls are
            # independent of each other (different endpoints/data sources), so fetching them one
            # at a time serially was pure wasted wall-clock time, most painful on a cold cache.
            def _prior_season_safe():
                # Falls back gracefully to "no prior-season blending" if the previous year's
                # Baseball-Reference data isn't available for some reason (e.g. a rookie's debut
                # season) — see features.blend_with_prior_season.
                try:
                    return get_season_pitching_stats(season - 1)
                except Exception:
                    return None

            with ThreadPoolExecutor(max_workers=13) as _stats_pool:
                _season_stats_f = _stats_pool.submit(get_season_pitching_stats, season)
                _prior_season_f = _stats_pool.submit(_prior_season_safe)
                _team_batting_f = _stats_pool.submit(get_team_batting_splits, season)
                _bullpen_stats_f = _stats_pool.submit(get_team_bullpen_stats, season)
                _tbvh_l_f = _stats_pool.submit(get_team_batting_vs_hand, season, "L")
                _tbvh_r_f = _stats_pool.submit(get_team_batting_vs_hand, season, "R")
                _hl_bullpen_f = _stats_pool.submit(get_team_high_leverage_bullpen_stats, season)
                _team_defense_f = _stats_pool.submit(get_team_defense_oaa, season)
                _player_batting_f = _stats_pool.submit(get_player_batting_stats, season)
                # Current season, live — unlike training (which uses the PRIOR season for
                # walk-forward safety, see build_training_data.py), this is safe to use as-is:
                # it's always "today," and Baseball Savant's leaderboard can't include games that
                # haven't happened yet.
                _batter_arsenal_f = _stats_pool.submit(get_batter_pitch_arsenal, season)
                _batter_expected_f = _stats_pool.submit(get_batter_expected_stats, season)
                _batter_exitvelo_f = _stats_pool.submit(get_batter_exitvelo_barrels, season)
                _batter_percentile_f = _stats_pool.submit(get_batter_percentile_ranks, season)
                _batter_batted_ball_f = _stats_pool.submit(get_batted_ball_profile, season, "batter")
                _batter_team_map_f = _stats_pool.submit(get_batter_team_map, season)

                season_stats = _season_stats_f.result()
                prior_season_stats = _prior_season_f.result()
                team_batting = _team_batting_f.result()
                bullpen_stats = _bullpen_stats_f.result()
                team_batting_vs_hand = {"L": _tbvh_l_f.result(), "R": _tbvh_r_f.result()}
                high_leverage_bullpen_stats = _hl_bullpen_f.result()
                team_defense = _team_defense_f.result()
                player_batting = _player_batting_f.result()
                batter_arsenal = _batter_arsenal_f.result()
                batter_expected = _batter_expected_f.result()
                batter_exitvelo = _batter_exitvelo_f.result()
                batter_percentile = _batter_percentile_f.result()
                batter_batted_ball = _batter_batted_ball_f.result()
                batter_team_map = _batter_team_map_f.result()
        except Exception as e:
            model_trained = False
            data_error = f"Season stats unavailable, predictions skipped this refresh: {e}"

    pitcher_hands = {}
    bullpen_fatigue = {}
    recent_team_batting = {}
    recent_team_batting_30d = {}
    team_travel = {}
    batter_hands = {}
    results = []
    for g in games:
        odds_entry = live_odds.get((g["away_team"], g["home_team"]))
        live_odds_out = {
            "home": odds_entry["home"],
            "away": odds_entry["away"],
            "bookmaker": odds_entry["bookmaker"],
        } if odds_entry else None
        game_snapshot = market_snapshot.get((g["away_team"], g["home_team"])) or {}
        game_line_movement = game_snapshot.get("line_movement")
        game_market_divergence = game_snapshot.get("market_divergence")
        game_prediction_market_signal = game_snapshot.get("prediction_market_diff")
        game_consensus_prob = game_snapshot.get("consensus_prob")
        game_book_disagreement = game_snapshot.get("book_disagreement")
        game_book_movement_agreement = game_snapshot.get("book_movement_agreement")
        game_consensus_median_prob = game_snapshot.get("book_median_prob")
        game_book_prob_std = game_snapshot.get("book_prob_std")
        game_book_favor_diff = game_snapshot.get("book_favor_diff")
        game_team_total_diff = game_snapshot.get("team_total_diff")
        game_market_total_runs = game_snapshot.get("market_total_runs")
        # Book-by-book display data (CONSENSUS_BOOKS' current devigged home prob) — display-only,
        # for line-shopping transparency in the "market odds" panel, not a model feature itself
        # (consensus_prob_diff/book_disagreement above ARE features, derived from the same data).
        book_odds_out = game_snapshot.get("book_probs") or None
        # Live-only, display-only injury report — see odds_fetcher.get_active_injuries. Shown even
        # before a game has started or a probable pitcher is announced, unlike the model-feature
        # fields below, since it's just today's real-time roster context, not a leakage risk.
        injuries_out = {
            "home": injuries_by_team.get(g["home_team_abbr"], []),
            "away": injuries_by_team.get(g["away_team_abbr"], []),
        }

        if not g["home_pitcher_id"] or not g["away_pitcher_id"]:
            results.append({
                **g, "prediction": None, "live_odds": live_odds_out, "injuries": injuries_out,
                "book_odds": book_odds_out, "note": "Probable pitcher not yet announced",
            })
            continue

        # This game's starters' own posted player-prop lines (outs/ER/hits-allowed/strikeouts) —
        # feeds market_outs_line_diff/etc. below and market_outs_line/etc. in strikeout_predictions.
        home_pitcher_market_lines = pitcher_market_lines.get(normalize_player_name(g["home_pitcher_name"]))
        away_pitcher_market_lines = pitcher_market_lines.get(normalize_player_name(g["away_pitcher_name"]))

        recent_stats = _recent_stats_for_matchup(g["home_pitcher_id"], g["away_pitcher_id"], season)
        recent_form_out = {
            "home": _json_safe(recent_stats[g["home_pitcher_id"]]),
            "away": _json_safe(recent_stats[g["away_pitcher_id"]]),
        }
        rest_days = _rest_days_for_matchup(recent_stats, g["game_date"])
        days_since_il_home = days_since_il_return(g["home_pitcher_id"], g["game_date"], il_activations)
        days_since_il_away = days_since_il_return(g["away_pitcher_id"], g["game_date"], il_activations)
        any_recent_il_return = days_since_il_home is not None or days_since_il_away is not None

        # Opener handling: if either starter's own recent form looks like a consistent
        # opener pattern (see _is_opener), try to find a specific reliever who's thrown
        # the bulk of the game after them — and if found, use THEIR stats (not the
        # opener's own near-meaningless 1-2-inning numbers) for the win-probability side
        # of the matchup. effective_*_id feeds every win-prob feature lookup below;
        # strikeout props stay on the real announced pitcher (g["*_pitcher_id"]), since
        # that's who the actual prop bet is on. See _resolve_effective_starter.
        effective_home_id, home_substituted, home_bulk_name = _resolve_effective_starter(
            g["home_pitcher_id"], g["home_team_abbr"], season, recent_form_out["home"]
        )
        effective_away_id, away_substituted, away_bulk_name = _resolve_effective_starter(
            g["away_pitcher_id"], g["away_team_abbr"], season, recent_form_out["away"]
        )
        opener_sub_warnings = (
            _opener_substitution_warning(g["home_pitcher_name"], home_bulk_name) if home_substituted else []
        ) + (
            _opener_substitution_warning(g["away_pitcher_name"], away_bulk_name) if away_substituted else []
        )
        if home_substituted or away_substituted:
            # Re-fetch recent form under the effective ids so what's DISPLAYED (and what
            # the reason text cites) matches what's actually driving the prediction —
            # otherwise this recreates the exact reason/display mismatch bug already
            # found and fixed earlier tonight, just for a different cause. rest_days
            # deliberately stays tied to the real announced pitcher throughout (a bulk
            # reliever doesn't follow a rotation schedule the same way, so "days since
            # their last start" isn't a meaningful concept for them here).
            effective_recent = _recent_stats_for_matchup(effective_home_id, effective_away_id, season)
            if home_substituted:
                recent_form_out["home"] = _json_safe(effective_recent[effective_home_id])
            if away_substituted:
                recent_form_out["away"] = _json_safe(effective_recent[effective_away_id])
        any_opener = home_substituted or away_substituted  # only true once a substitution actually happened — an
        # opener pattern with no identifiable bulk reliever still falls back to the opener's own numbers (already
        # discounted via the existing thin-sample/reliability machinery), not a second, redundant flag here.
        #
        # Distinct from any_opener above, and NOT interchangeable with it: any_unresolved_opener is true
        # exactly when an opener pattern is present and substitution did NOT resolve it, so the win-prob
        # features are still built from that pitcher's own near-meaningless 1-2-inning numbers — the case
        # _apply_confidence_override's reliability gates need to distrust. any_opener means the opposite
        # (a real bulk reliever's own reliable start data is now driving the matchup), so passing any_opener
        # into that function was backwards: it blocked the override exactly when substitution handed it
        # trustworthy data, while leaving the override unguarded in the one case (no reliever found, stuck
        # with the opener's own numbers) it was actually meant to catch. Caught directly: Bryan Hudson ->
        # Erick Fedde (CWS vs ATH) — every single pitching-quality feature (season FIP, K-BB%, recent FIP/K9,
        # whiff%, chase%, GB%, barrel%, CSW%) agreed Fedde was clearly worse than the opposing starter
        # (agreement score ~-24 against an 8.0 threshold), yet the override never fired because any_opener
        # was True purely from the substitution having succeeded.
        any_unresolved_opener = (
            (not home_substituted and _is_opener(recent_form_out["home"])) or
            (not away_substituted and _is_opener(recent_form_out["away"]))
        )
        season_stats_out = _season_stats_for_matchup(
            season_stats, prior_season_stats, effective_home_id, effective_away_id
        ) if model_trained else None
        blend_warnings = []
        if season_stats_out:
            # Skip the prior-season-blend warning on a substituted side — it would compare the
            # ANNOUNCED pitcher's raw IP against the EFFECTIVE (bulk reliever's) blended IP, a
            # mismatch that doesn't describe either pitcher correctly. The opener-substitution
            # warning already explains what's actually happening for that side.
            if not home_substituted:
                blend_warnings += _prior_season_blend_warning(
                    g["home_pitcher_name"], _season_stat_lookup(season_stats, g["home_pitcher_id"]).get("ip"),
                    season_stats_out["home"].get("ip"),
                )
            if not away_substituted:
                blend_warnings += _prior_season_blend_warning(
                    g["away_pitcher_name"], _season_stat_lookup(season_stats, g["away_pitcher_id"]).get("ip"),
                    season_stats_out["away"].get("ip"),
                )
        il_warnings = (
            _il_return_warning(g["home_pitcher_name"], days_since_il_home) +
            _il_return_warning(g["away_pitcher_name"], days_since_il_away)
        )
        pitcher_warnings = (
            _pitcher_warnings(g["home_pitcher_name"], rest_days.get(g["home_pitcher_id"]), recent_form_out["home"]) +
            _pitcher_warnings(g["away_pitcher_name"], rest_days.get(g["away_pitcher_id"]), recent_form_out["away"]) +
            _weather_warnings(g["venue"], g["game_time_utc"]) +
            blend_warnings + il_warnings + opener_sub_warnings
        ) or None

        prediction = None
        reason = None
        strikeout_predictions = None
        h2h_out = None
        team_stats_out = None
        lineup_breakdown_out = None
        rating_out = None
        market_model_prob = None
        if model_trained:
            for pid in (effective_home_id, effective_away_id, g["home_pitcher_id"], g["away_pitcher_id"]):
                if pid not in pitcher_hands:
                    pitcher_hands[pid] = get_pitcher_hand(pid)
            for team_abbr in (g["home_team_abbr"], g["away_team_abbr"]):
                if team_abbr not in bullpen_fatigue:
                    bullpen_fatigue[team_abbr] = get_team_recent_bullpen_usage(team_abbr)
                if team_abbr not in recent_team_batting:
                    recent_team_batting[team_abbr] = get_team_recent_batting_form(team_abbr)
                if team_abbr not in recent_team_batting_30d:
                    recent_team_batting_30d[team_abbr] = get_team_recent_batting_form(
                        team_abbr, n_games=RECENT_TEAM_BATTING_GAMES_30D
                    )
                if team_abbr not in team_travel:
                    team_travel[team_abbr] = team_travel_miles(team_abbr, TEAM_HOME_VENUE.get(g["home_team_abbr"]))
            team_stats_out = _team_stats_for_matchup(
                team_batting, bullpen_stats, high_leverage_bullpen_stats, recent_team_batting,
                g["home_team_abbr"], g["away_team_abbr"],
            )
            lineups_raw = get_confirmed_lineup(g["game_pk"]) if g.get("game_pk") else {"home": [], "away": []}
            # Falls back to a predicted lineup (from the team's actual last-5-games batting
            # orders) whenever the official one hasn't posted — feeds build_matchup_features'
            # real-lineup wOBA upgrade below too, not just the display, so a good guess at
            # tonight's actual hitters beats the season-wide team average even hours before
            # MLB confirms it.
            home_lineup_ids, home_lineup_predicted = _resolve_lineup(lineups_raw.get("home"), g["home_team_abbr"])
            away_lineup_ids, away_lineup_predicted = _resolve_lineup(lineups_raw.get("away"), g["away_team_abbr"])
            lineups = {"home": home_lineup_ids, "away": away_lineup_ids}
            for bid in home_lineup_ids + away_lineup_ids:
                if bid not in batter_hands:
                    batter_hands[bid] = get_batter_hand(bid)
            # Every batter tonight (confirmed or predicted), with their own season AVG and their
            # own split vs the REAL announced opposing starter's hand (not an opener-substituted
            # bulk reliever's — the lineup's actual matchup tonight is against whoever's really
            # pitching, same reasoning as the strikeout props staying on the real pitcher).
            lineup_breakdown_out = {
                "home": {
                    "batters": _lineup_breakdown(
                        home_lineup_ids, pitcher_hands.get(g["away_pitcher_id"], "R"), season, player_batting, batter_hands
                    ),
                    "predicted": home_lineup_predicted,
                },
                "away": {
                    "batters": _lineup_breakdown(
                        away_lineup_ids, pitcher_hands.get(g["home_pitcher_id"], "R"), season, player_batting, batter_hands
                    ),
                    "predicted": away_lineup_predicted,
                },
            }
            # Everything below uses effective_home_id/effective_away_id — the announced pitcher unless
            # an opener substitution resolved to a specific bulk reliever, in which case it's THEIR
            # data driving the win-probability matchup (see _resolve_effective_starter above).
            statcast = _statcast_for_matchup(effective_home_id, effective_away_id, season)
            recent_statcast = _recent_statcast_for_matchup(effective_home_id, effective_away_id, season)
            velocity_trend = _velocity_trend_for_matchup(effective_home_id, effective_away_id, season)
            pitch_diversity = _pitch_diversity_for_matchup(effective_home_id, effective_away_id, season)
            pitch_mix = _pitch_mix_for_matchup(effective_home_id, effective_away_id, season)
            # recent_form_out already holds the right (possibly-substituted) data per side, keyed to
            # match whichever id (effective_home_id/effective_away_id) build_matchup_features looks up.
            matchup_recent_stats = {effective_home_id: recent_form_out["home"], effective_away_id: recent_form_out["away"]}
            # Same effective-id substitution for IL-return timing: if a bulk reliever is standing in
            # for an opener, it's THEIR IL-return status (if any) that should discount their recent
            # form, not the announced opener's — il_activations already covers every recent activation
            # league-wide, so this is just a different key lookup, no extra fetch.
            il_return_days_matchup = {
                effective_home_id: days_since_il_return(effective_home_id, g["game_date"], il_activations),
                effective_away_id: days_since_il_return(effective_away_id, g["game_date"], il_activations),
            }
            game_weather = get_game_weather_live(g["venue"], g["game_date"]) or {}
            feats = build_matchup_features(
                home_pitcher_id=effective_home_id,
                away_pitcher_id=effective_away_id,
                home_team_abbr=g["home_team_abbr"],
                away_team_abbr=g["away_team_abbr"],
                season_stats=_season_stats_dict_for_matchup(season_stats, prior_season_stats, effective_home_id, effective_away_id),
                team_batting=team_batting,
                bullpen_stats=bullpen_stats,
                park_factor_lookup=get_park_factor,
                recent_stats=matchup_recent_stats,
                rest_days=rest_days,
                bullpen_fatigue=bullpen_fatigue,
                pitcher_hands=pitcher_hands,
                team_batting_vs_hand=team_batting_vs_hand or {},
                high_leverage_bullpen_stats=high_leverage_bullpen_stats,
                team_defense=team_defense,
                lineups=lineups,
                player_batting=player_batting,
                batter_hands=batter_hands,
                statcast=statcast,
                velocity_trend=velocity_trend,
                pitch_diversity=pitch_diversity,
                game_weather=game_weather,
                il_return_days=il_return_days_matchup,
                prior_season_stats=_raw_prior_season_stats_dict_for_matchup(
                    prior_season_stats, effective_home_id, effective_away_id
                ),
                recent_team_batting=recent_team_batting,
                recent_team_batting_30d=recent_team_batting_30d,
                team_travel=team_travel,
                line_movement=game_line_movement,
                market_divergence=game_market_divergence,
                prediction_market_signal=game_prediction_market_signal,
                consensus_prob=game_consensus_prob,
                book_disagreement=game_book_disagreement,
                book_movement_agreement=game_book_movement_agreement,
                consensus_median_prob=game_consensus_median_prob,
                book_prob_std=game_book_prob_std,
                book_favor_diff=game_book_favor_diff,
                team_total_diff=game_team_total_diff,
                market_total_runs=game_market_total_runs,
                home_pitcher_market_lines=home_pitcher_market_lines,
                away_pitcher_market_lines=away_pitcher_market_lines,
                pitch_mix=pitch_mix,
                batter_arsenal=batter_arsenal,
                batter_expected=batter_expected,
                batter_exitvelo=batter_exitvelo,
                batter_percentile=batter_percentile,
                batter_batted_ball=batter_batted_ball,
                batter_team_map=batter_team_map,
            )
            row = features_to_row(feats)
            raw_prediction = model_module.predict_proba(
                row, model_path=model_module.BASELINE_MODEL_PATH, feature_columns=BASEBALL_ONLY_FEATURE_COLUMNS
            )
            # Model B (baseball + market features) run purely for comparison — see
            # market_model_prob below. Never drives the primary prediction/override/reason.
            market_model_prob = None
            if market_model_trained:
                try:
                    market_model_prob = model_module.predict_proba(
                        row, model_path=model_module.MODEL_PATH, feature_columns=FEATURE_COLUMNS
                    )["home_win_prob"]
                except Exception:
                    market_model_prob = None
            any_long_layoff = any(
                (rest_days.get(pid) or 0) >= LONG_LAYOFF_DAYS
                for pid in (g["home_pitcher_id"], g["away_pitcher_id"])
            )
            prediction = _apply_confidence_override(
                raw_prediction["home_win_prob"], feats, recent_form_out, season_stats_out, any_long_layoff,
                any_recent_il_return, any_unresolved_opener,
            )
            reason = _generate_reason(
                prediction["home_win_prob"] >= 0.5, season_stats_out, recent_form_out, any_long_layoff,
                team_stats_out,
            )
            # Display-only "why" breakdown from the separate hand-weighted rating system (see
            # rating_system.py) — NOT what drives the model's own win-prob above (that backtested
            # worse than the trained model, see the plan doc), just a transparent, category-by-
            # category view of the same underlying signals for whoever wants to see the reasoning.
            rating_out = (
                rating_system.score_matchup(rating_fitted, feats) if rating_fitted is not None else None
            )
            # Strikeout props are about the actually-announced pitcher specifically (that's who the
            # real bet is on), never the substituted bulk reliever — so this needs its own statcast/
            # velocity/pitch-diversity pull keyed to the real ids, distinct from the win-prob versions
            # above which may be keyed to an effective (substituted) id instead.
            if home_substituted or away_substituted:
                k_statcast = _statcast_for_matchup(g["home_pitcher_id"], g["away_pitcher_id"], season)
                k_recent_statcast = _recent_statcast_for_matchup(g["home_pitcher_id"], g["away_pitcher_id"], season)
                k_velocity_trend = _velocity_trend_for_matchup(g["home_pitcher_id"], g["away_pitcher_id"], season)
                k_pitch_diversity = _pitch_diversity_for_matchup(g["home_pitcher_id"], g["away_pitcher_id"], season)
                k_pitch_mix = _pitch_mix_for_matchup(g["home_pitcher_id"], g["away_pitcher_id"], season)
            else:
                k_statcast, k_recent_statcast, k_velocity_trend, k_pitch_diversity = (
                    statcast, recent_statcast, velocity_trend, pitch_diversity
                )
                k_pitch_mix = pitch_mix
            # Strikeout props' head-to-head uses the REAL announced pitcher ids too, same reasoning
            # as k_statcast etc. above — a substituted bulk reliever's history against this opponent
            # isn't relevant to a strikeout prop that's about the actually-announced pitcher.
            k_h2h_stats = _h2h_stats_dict_for_matchup(
                g["home_pitcher_id"], g["away_pitcher_id"], g["home_team_abbr"], g["away_team_abbr"], season
            )
            strikeout_predictions = _strikeout_predictions(
                g["home_pitcher_id"], g["away_pitcher_id"], g["home_pitcher_name"], g["away_pitcher_name"],
                g["home_team_abbr"], g["away_team_abbr"], season_stats, team_batting, recent_stats, prop_lines,
                k_statcast, lineups=lineups, player_batting=player_batting, prizepicks_lines=prizepicks_lines,
                recent_statcast=k_recent_statcast, rest_days=rest_days, prior_season_stats=prior_season_stats,
                velocity_trend=k_velocity_trend, pitch_diversity=k_pitch_diversity, game_weather=game_weather,
                pitcher_hands=pitcher_hands, team_batting_vs_hand=team_batting_vs_hand, h2h_stats=k_h2h_stats,
                market_home_prob=(
                    devig_home_prob(live_odds_out["home"], live_odds_out["away"]) if live_odds_out else None
                ),
                pitch_mix=k_pitch_mix, batter_arsenal=batter_arsenal,
                pitcher_market_lines_by_name=pitcher_market_lines,
            )
            # Display-only (not a model feature — see the ablation note on h2h_fip_diff/h2h_k9 in
            # features.py): each pitcher's own head-to-head record against tonight's specific
            # opponent, real ids (not the opener-substituted ones), same reasoning as k_h2h_stats.
            h2h_out = {
                "home": _json_safe(k_h2h_stats.get(g["home_pitcher_id"], {})),
                "away": _json_safe(k_h2h_stats.get(g["away_pitcher_id"], {})),
            }
            data_quality = _data_completeness(feats)
        else:
            data_quality = None

        # Once a game has actually started, its starters' own "recent form" and
        # eventually "season stats" naturally come to include THIS game's own
        # outing — recomputing fresh at that point means using the game's own
        # result as an input to "predict" it, silently and with no warning.
        # Caught directly: a completed game's displayed favorite flipped to the
        # other team hours after the fact. Once a prediction's been logged
        # (see prediction_log.py), a no-longer-pre-game request for that same
        # game serves the frozen version instead of a fresh, contaminated one.
        #
        # This freeze covers reason/recent_form/season_stats too, not just the
        # probability — freezing only the number while still live-recomputing
        # the reason text let the two silently disagree (the reason ends up
        # citing whichever team a later, contaminated recompute favored, even
        # when it's the opposite team from the frozen probability being shown
        # right next to it). Once we know a frozen prediction exists, never
        # fall back to a fresh recompute for any of these fields — a missing
        # pre-game snapshot should render as "not captured," not as leakage.
        prediction_frozen = False
        if g["status"] not in PRE_GAME_STATUSES:
            # h2h_out isn't logged to the prediction log the way recent_form/season_stats are, so
            # there's no frozen snapshot to fall back to here — same leakage risk as those two
            # (get_pitcher_season_log has no date cutoff, so a started/finished game's own outing
            # would already be baked into "head-to-head vs this opponent" by the time this request
            # runs), but with no logged history to restore, the honest move is just not to show a
            # live-recomputed value at all rather than silently include this game's own result.
            h2h_out = None
            # rating_out (the display-only category breakdown) isn't logged either, same leakage
            # exposure as h2h_out — honest move is the same: don't show a live-recomputed value
            # for an already-decided game.
            rating_out = None
            # market_model_prob (Model B's comparison probability) is a live re-inference off the
            # same feats dict as h2h_out/rating_out above and isn't logged anywhere either — same
            # leakage exposure, same honest fix: don't show a live-recomputed value once the
            # game's own outing may already be baked into the inputs that produced it.
            market_model_prob = None
            # recent_team_batting is a live "last 7 games" computation with no date cutoff, same
            # leakage exposure as h2h_out above — a decided game's own batting line would already
            # be baked into "recent form" by the time this request runs. team_stats_out is IS
            # logged (see log_predictions' team_stats_json), so it gets restored from the frozen
            # snapshot below when one exists, same as recent_form/season_stats.
            team_stats_out = None
            # Same reasoning again: a batter's vs-hand split and season AVG are season snapshots
            # (low leakage risk on their own), but this is still keyed to the confirmed lineup at
            # prediction time — restored from the frozen log below when logged, null otherwise.
            lineup_breakdown_out = None
            frozen = get_logged_prediction(resolved_date, g.get("game_pk")) if g.get("game_pk") else None
            if frozen:
                prediction = {k: frozen[k] for k in ("home_win_prob", "away_win_prob", "model_home_win_prob", "overridden")}
                reason = frozen.get("reason") or "Original reasoning wasn't captured for this game."
                if frozen.get("recent_form"):
                    recent_form_out = frozen["recent_form"]
                if frozen.get("season_stats"):
                    season_stats_out = frozen["season_stats"]
                if frozen.get("team_stats"):
                    team_stats_out = frozen["team_stats"]
                if frozen.get("lineup_breakdown"):
                    lineup_breakdown_out = frozen["lineup_breakdown"]
                prediction_frozen = True

            # Same freeze, same reason, for the K-prop card — it was still being
            # live-recomputed for decided games even after the moneyline fix above,
            # which is the exact same leakage risk (a pitcher's own in-progress or
            # just-finished start feeding the recent-form/season-stat inputs behind
            # their own K prediction). No logged history to restore means the same
            # honest move as h2h_out/rating_out/etc. above: null the side out rather
            # than silently falling through to a live, potentially-contaminated recompute.
            if strikeout_predictions and g.get("game_pk"):
                for side, pid_key in (("home", "home_pitcher_id"), ("away", "away_pitcher_id")):
                    frozen_k = get_logged_strikeout_prediction(resolved_date, g["game_pk"], g.get(pid_key))
                    strikeout_predictions[side] = frozen_k if frozen_k else None

        # Recomputed here (not reused from earlier) so it reflects whichever recent_form_out is
        # actually being displayed — the frozen pre-game snapshot for a decided game, not a fresh
        # live recompute of it. Note: any_opener itself is still a live check (computed earlier this
        # request, before the freeze block) — for an already-decided game this is a display-only field
        # that doesn't feed back into the frozen prediction number, so it's a minor, bounded imprecision
        # rather than the kind of leakage this freeze system exists to prevent.
        results.append({
            **g, "prediction": prediction, "live_odds": live_odds_out,
            "recent_form": recent_form_out, "season_stats": season_stats_out, "reason": reason,
            "strikeout_predictions": strikeout_predictions, "pitcher_warnings": pitcher_warnings,
            "data_quality": data_quality, "prediction_frozen": prediction_frozen,
            "opener_affected": any_opener, "h2h": h2h_out, "team_stats": team_stats_out,
            "lineup_breakdown": lineup_breakdown_out, "rating_breakdown": rating_out,
            "market_model_prob": market_model_prob, "injuries": injuries_out,
            "book_odds": book_odds_out,
            "note": None if prediction else "Model not trained yet — run train.py",
        })

    try:
        log_predictions(resolved_date, results)
        settle_predictions()
        log_strikeout_predictions(resolved_date, results)
        settle_strikeout_predictions()
    except Exception:
        import traceback
        global _last_log_error
        _last_log_error = traceback.format_exc()

    return {
        "date": resolved_date,
        "games": results,
        "warning": data_error,
    }


@app.get("/api/track-record")
def track_record():
    return get_track_record()


@app.get("/api/strikeout-track-record")
def strikeout_track_record():
    return get_strikeout_track_record()


@app.get("/api/matchup")
def matchup(home_pitcher_id: int, away_pitcher_id: int, home_team: str, away_team: str):
    season = datetime.now().year
    season_stats = get_season_pitching_stats(season)
    try:
        prior_season_stats = get_season_pitching_stats(season - 1)
    except Exception:
        prior_season_stats = None
    team_batting = get_team_batting_splits(season)
    bullpen_stats = get_team_bullpen_stats(season)
    batter_arsenal = get_batter_pitch_arsenal(season)
    batter_expected = get_batter_expected_stats(season)
    batter_exitvelo = get_batter_exitvelo_barrels(season)
    batter_percentile = get_batter_percentile_ranks(season)
    batter_batted_ball = get_batted_ball_profile(season, "batter")
    batter_team_map = get_batter_team_map(season)

    result = {}

    recent_stats = _recent_stats_for_matchup(home_pitcher_id, away_pitcher_id, season)
    result["recent_form"] = {
        "home": _json_safe(recent_stats[home_pitcher_id]),
        "away": _json_safe(recent_stats[away_pitcher_id]),
    }
    today_str = datetime.now().strftime("%Y-%m-%d")
    rest_days = _rest_days_for_matchup(recent_stats, today_str)
    try:
        il_activations = get_recent_il_activations(as_of_date=today_str)
    except Exception:
        il_activations = {}
    days_since_il_home = days_since_il_return(home_pitcher_id, today_str, il_activations)
    days_since_il_away = days_since_il_return(away_pitcher_id, today_str, il_activations)
    any_recent_il_return = days_since_il_home is not None or days_since_il_away is not None
    any_opener = _is_opener(result["recent_form"]["home"]) or _is_opener(result["recent_form"]["away"])
    result["opener_affected"] = any_opener
    result["pitcher_warnings"] = (
        _pitcher_warnings(f"Home starter ({home_team})", rest_days.get(home_pitcher_id), result["recent_form"]["home"]) +
        _pitcher_warnings(f"Away starter ({away_team})", rest_days.get(away_pitcher_id), result["recent_form"]["away"]) +
        _il_return_warning(f"Home starter ({home_team})", days_since_il_home) +
        _il_return_warning(f"Away starter ({away_team})", days_since_il_away)
    ) or None

    # Same primary-model choice as /api/today — Model A (baseball-only), see the plan doc.
    model_trained = model_module.load_model(model_module.BASELINE_MODEL_PATH)[0] is not None
    if model_trained:
        result["season_stats"] = _season_stats_for_matchup(season_stats, prior_season_stats, home_pitcher_id, away_pitcher_id)
        h2h_stats_display = _h2h_stats_dict_for_matchup(home_pitcher_id, away_pitcher_id, home_team, away_team, season)
        result["h2h"] = {
            "home": _json_safe(h2h_stats_display.get(home_pitcher_id, {})),
            "away": _json_safe(h2h_stats_display.get(away_pitcher_id, {})),
        }
        team_batting_vs_hand = {"L": get_team_batting_vs_hand(season, "L"), "R": get_team_batting_vs_hand(season, "R")}
        pitcher_hands = {home_pitcher_id: get_pitcher_hand(home_pitcher_id), away_pitcher_id: get_pitcher_hand(away_pitcher_id)}
        bullpen_fatigue = {home_team: get_team_recent_bullpen_usage(home_team), away_team: get_team_recent_bullpen_usage(away_team)}
        recent_team_batting = {home_team: get_team_recent_batting_form(home_team), away_team: get_team_recent_batting_form(away_team)}
        recent_team_batting_30d = {
            home_team: get_team_recent_batting_form(home_team, n_games=RECENT_TEAM_BATTING_GAMES_30D),
            away_team: get_team_recent_batting_form(away_team, n_games=RECENT_TEAM_BATTING_GAMES_30D),
        }
        team_travel = {
            home_team: team_travel_miles(home_team, TEAM_HOME_VENUE.get(home_team)),
            away_team: team_travel_miles(away_team, TEAM_HOME_VENUE.get(home_team)),
        }
        high_leverage_bullpen_stats = get_team_high_leverage_bullpen_stats(season)
        team_stats_out = _team_stats_for_matchup(
            team_batting, bullpen_stats, high_leverage_bullpen_stats, recent_team_batting, home_team, away_team
        )
        team_defense = get_team_defense_oaa(season)
        statcast = _statcast_for_matchup(home_pitcher_id, away_pitcher_id, season)
        velocity_trend = _velocity_trend_for_matchup(home_pitcher_id, away_pitcher_id, season)
        pitch_diversity = _pitch_diversity_for_matchup(home_pitcher_id, away_pitcher_id, season)
        pitch_mix = _pitch_mix_for_matchup(home_pitcher_id, away_pitcher_id, season)
        feats = build_matchup_features(
            home_pitcher_id=home_pitcher_id,
            away_pitcher_id=away_pitcher_id,
            home_team_abbr=home_team,
            away_team_abbr=away_team,
            bullpen_fatigue=bullpen_fatigue,
            high_leverage_bullpen_stats=high_leverage_bullpen_stats,
            team_defense=team_defense,
            statcast=statcast,
            velocity_trend=velocity_trend,
            pitch_diversity=pitch_diversity,
            season_stats=_season_stats_dict_for_matchup(season_stats, prior_season_stats, home_pitcher_id, away_pitcher_id),
            team_batting=team_batting,
            bullpen_stats=bullpen_stats,
            park_factor_lookup=get_park_factor,
            pitcher_hands=pitcher_hands,
            team_batting_vs_hand=team_batting_vs_hand,
            recent_stats=recent_stats,
            rest_days=rest_days,
            il_return_days={home_pitcher_id: days_since_il_home, away_pitcher_id: days_since_il_away},
            prior_season_stats=_raw_prior_season_stats_dict_for_matchup(prior_season_stats, home_pitcher_id, away_pitcher_id),
            h2h_stats=h2h_stats_display,
            recent_team_batting=recent_team_batting,
            recent_team_batting_30d=recent_team_batting_30d,
            team_travel=team_travel,
            pitch_mix=pitch_mix,
            batter_arsenal=batter_arsenal,
            batter_expected=batter_expected,
            batter_exitvelo=batter_exitvelo,
            batter_percentile=batter_percentile,
            batter_batted_ball=batter_batted_ball,
            batter_team_map=batter_team_map,
        )
        row = features_to_row(feats)
        raw_prediction = model_module.predict_proba(
            row, model_path=model_module.BASELINE_MODEL_PATH, feature_columns=BASEBALL_ONLY_FEATURE_COLUMNS
        )
        any_long_layoff = any(
            (rest_days.get(pid) or 0) >= LONG_LAYOFF_DAYS
            for pid in (home_pitcher_id, away_pitcher_id)
        )
        result["model"] = _apply_confidence_override(
            raw_prediction["home_win_prob"], feats, result["recent_form"], result.get("season_stats"), any_long_layoff,
            any_recent_il_return, any_opener,
        )
        result["features"] = _json_safe(feats)
        result["data_quality"] = _data_completeness(feats)
        result["team_stats"] = (
            {"home": _json_safe(team_stats_out["home"]), "away": _json_safe(team_stats_out["away"])}
            if team_stats_out else None
        )
        result["reason"] = _generate_reason(
            result["model"]["home_win_prob"] >= 0.5, result.get("season_stats"), result["recent_form"], any_long_layoff,
            team_stats_out,
        )
        rating_fitted = rating_system.load_rating_system()
        result["rating_breakdown"] = (
            rating_system.score_matchup(rating_fitted, feats) if rating_fitted is not None else None
        )
        # No pitcher names available on this endpoint (ID/team-abbr only), so strikeout
        # lines fall back to the model-generated "natural" line rather than a real book
        # line — /api/today (which has names) gets the real prop line when one exists.
        recent_statcast = _recent_statcast_for_matchup(home_pitcher_id, away_pitcher_id, season)
        result["strikeout_predictions"] = _strikeout_predictions(
            home_pitcher_id, away_pitcher_id, None, None, home_team, away_team, season_stats, team_batting, recent_stats,
            statcast=statcast, recent_statcast=recent_statcast, rest_days=rest_days, prior_season_stats=prior_season_stats,
            velocity_trend=velocity_trend, pitch_diversity=pitch_diversity,
            pitcher_hands=pitcher_hands, team_batting_vs_hand=team_batting_vs_hand,
            pitch_mix=pitch_mix, batter_arsenal=batter_arsenal,
        )

    return result


@app.post("/api/retrain")
def retrain(seasons: str = "2025,2026"):
    from build_training_data import build_full_training_set, build_strikeout_training_set
    season_list = [int(s) for s in seasons.split(",")]
    training_df = build_full_training_set(season_list)
    _, _, metrics = model_module.train(training_df)

    k_training_df = build_strikeout_training_set(season_list)
    _, _, k_metrics = props_module.train_strikeout_model(k_training_df)

    return {
        "status": "trained", "metrics": metrics, "rows": len(training_df),
        "strikeout_metrics": k_metrics, "strikeout_rows": len(k_training_df),
    }


_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_STATIC_DIR):
    # Serves the built frontend (frontend/npm run build, copied here) so Railway can run this as
    # one service instead of needing a separate Node host + CORS setup for a personal single-user
    # app. Mounted last so it only catches requests none of the /api/* routes above matched — see
    # README/deploy notes for the "rebuild + copy static/ before deploying" step this requires
    # whenever the frontend changes. Falls back to the plain status JSON below if static/ was
    # never populated (e.g. local dev without running the frontend build).
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
else:
    @app.get("/")
    def root():
        return {"status": "ok", "message": "MLB Pitcher Matchup Predictor API. See /docs for endpoints."}
