"""
data_collection.py

Pulls all the raw data the model needs:
  - Pitcher game logs (Statcast, via pybaseball)
  - Season & rolling pitcher stats (FanGraphs, via pybaseball)
  - Team batting splits vs L/R
  - Bullpen stats
  - Park factors
  - Today's probable pitchers & schedule (MLB Stats API, no key needed)

All functions cache results to backend/data_cache/ as parquet files so
you're not re-hitting the source on every run. Delete data_cache/ to
force a refresh, or pass force_refresh=True.

Run this file directly to do a full data pull:
    python data_collection.py
"""

import os
import io
import time
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from pybaseball import (
    statcast,
    statcast_pitcher,
    statcast_batter_pitch_arsenal,
    statcast_batter_expected_stats,
    statcast_pitcher_expected_stats,
    statcast_batter_exitvelo_barrels,
    statcast_batter_percentile_ranks,
    statcast_outs_above_average,
    pitching_stats_bref,
    batting_stats_bref,
    schedule_and_record,
    playerid_lookup,
    cache,
)

cache.enable()  # pybaseball's own on-disk cache, in addition to ours

# FanGraphs now sits behind a Cloudflare JS challenge that pybaseball's
# plain requests-based scraper can't solve, so season-level stats are
# pulled from Baseball-Reference instead (pitching_stats_bref /
# batting_stats_bref). BR doesn't publish xFIP/SIERA/wOBA directly, so
# we derive equivalents from raw counting stats below. BR's "Tm" column
# is a city name (not a 3-letter abbreviation) and is ambiguous for
# Chicago/LA/NY, so it's combined with the league ("Lev") column to
# resolve to a standard abbreviation; mid-season multi-team stints
# (comma-joined Tm values) are dropped from team-level aggregates since
# they can't be cleanly attributed to one team.
_BREF_CITY_TO_ABBR = {
    # Values match the MLB Stats API's own team abbreviations (the source of truth
    # for home_team_abbr/away_team_abbr everywhere else in this app), NOT
    # Baseball-Reference's own abbreviation style — four of these differ (AZ not
    # ARI, WSH not WSN, CWS not CHW, ATH not OAK) and silently broke every
    # BR-sourced team-level feature (bullpen, defense, lineup wOBA, park factor)
    # for those four teams until caught via a NYY@WSH matchup check.
    "Arizona": "AZ", "Atlanta": "ATL", "Baltimore": "BAL", "Boston": "BOS",
    "Cincinnati": "CIN", "Cleveland": "CLE", "Colorado": "COL", "Detroit": "DET",
    "Houston": "HOU", "Kansas City": "KC", "Miami": "MIA", "Milwaukee": "MIL",
    "Minnesota": "MIN", "Philadelphia": "PHI", "Pittsburgh": "PIT", "San Diego": "SD",
    "San Francisco": "SF", "Seattle": "SEA", "St. Louis": "STL", "Tampa Bay": "TB",
    "Texas": "TEX", "Toronto": "TOR", "Washington": "WSH", "Athletics": "ATH",
}
_BREF_AMBIGUOUS_CITY_BY_LEAGUE = {
    ("Chicago", "NL"): "CHC", ("Chicago", "AL"): "CWS",
    ("Los Angeles", "NL"): "LAD", ("Los Angeles", "AL"): "LAA",
    ("New York", "NL"): "NYM", ("New York", "AL"): "NYY",
}


def _bref_team_abbr(tm: str, lev: str = "") -> str | None:
    if not isinstance(tm, str) or "," in tm:
        return None  # mid-season multi-team stint; can't attribute to one team
    if tm in _BREF_CITY_TO_ABBR:
        return _BREF_CITY_TO_ABBR[tm]
    league = "NL" if "NL" in str(lev) else ("AL" if "AL" in str(lev) else None)
    return _BREF_AMBIGUOUS_CITY_BY_LEAGUE.get((tm, league))


def _parse_ip(ip_val) -> float:
    """Baseball-Reference IP notation: '166.1' means 166 and 1/3 innings."""
    try:
        s = str(ip_val)
        if "." in s:
            whole, frac = s.split(".")
            return float(whole) + float(frac) / 3.0
        return float(s)
    except (ValueError, TypeError):
        return 0.0

CACHE_DIR = os.path.join(os.path.dirname(__file__), "data_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

MLB_STATS_API = "https://statsapi.mlb.com/api/v1"

# Rough park factors (runs, 100 = neutral). These drift year to year;
# treat as a reasonable prior, not gospel. You can refresh from
# https://www.fangraphs.com/guts.aspx?type=pf annually.
PARK_FACTORS = {
    # Keyed to match the MLB Stats API's team abbreviations — see the comment on
    # _BREF_CITY_TO_ABBR above for why this isn't just Baseball-Reference's own style.
    "COL": 112, "CIN": 106, "TEX": 104, "PHI": 103, "BOS": 103,
    "BAL": 102, "TOR": 101, "CHC": 101, "AZ": 101, "MIN": 100,
    "HOU": 100, "MIL": 100, "WSH": 100, "ATL": 99, "LAA": 99,
    "CWS": 99, "STL": 99, "KC": 99, "TB": 98, "NYY": 98,
    "CLE": 98, "SD": 97, "LAD": 97, "SF": 96, "SEA": 96,
    "DET": 96, "NYM": 96, "PIT": 95, "MIA": 94, "ATH": 94,
}


def _cache_path(name: str) -> str:
    return os.path.join(CACHE_DIR, f"{name}.parquet")


def _load_or_fetch(name: str, fetch_fn, force_refresh: bool = False, max_age_hours: int = 12):
    """
    FastAPI runs each request's sync route handler in its own threadpool thread, and /api/today
    fetches lineups (1-hour TTL, so genuinely re-written often) for every game on the slate — two
    concurrent requests can land on the same cache file at once. Reading mid-write used to crash
    with "Parquet file size is 0 bytes" (confirmed live: pandas.to_parquet isn't atomic — it
    truncates the destination before writing, so a reader landing in that window sees a 0-byte
    file). Fixed two ways: writes go to a per-write-unique temp file then os.replace (atomic on
    both POSIX and Windows — a concurrent reader either sees the old complete file or the new
    complete file, never a partial one); reads that still hit a corrupt/truncated file for any
    OTHER reason (e.g. a leftover from before this fix, a disk hiccup) fall through to a live
    re-fetch instead of crashing the whole endpoint.
    """
    path = _cache_path(name)
    if not force_refresh and os.path.exists(path):
        age_hours = (time.time() - os.path.getmtime(path)) / 3600
        if age_hours < max_age_hours:
            try:
                return pd.read_parquet(path)
            except Exception:
                pass  # corrupt/truncated cache file — treat as a miss and refetch below
    df = fetch_fn()
    if df is not None and len(df) > 0:
        tmp_path = f"{path}.{os.getpid()}.{time.time_ns()}.tmp"
        # data_cache lives under OneDrive, whose sync engine transiently interferes with
        # just-created temp files — confirmed live in two different shapes: PermissionError
        # (WinError 5, file locked mid-sync) and FileNotFoundError (WinError 2, OneDrive
        # grabbed/moved the tmp file before os.replace could run). Both are OSError subclasses.
        # Retry the whole write (re-creating tmp_path each time, since a vanished file can't be
        # replaced no matter how long you wait) a few times; if OneDrive is still interfering
        # after that, fall back to a direct non-atomic write so caching degrades to "best effort
        # with the original rare read-race" rather than a hard crash on every write.
        for attempt in range(5):
            try:
                df.to_parquet(tmp_path)
                os.replace(tmp_path, path)
                break
            except OSError:
                if attempt == 4:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                    try:
                        df.to_parquet(path)
                    except OSError:
                        pass
                    break
                time.sleep(0.2 * (attempt + 1))
    return df


LEAGUE_HR_PER_FB_RATE = 0.115  # roughly modern-MLB league-average HR/FB rate — fixed constant
# approximation feeding xFIP below, same spirit as FIP's own fixed 3.10 constant (the "real"
# year-specific league rate would need a whole separate league-wide aggregation; a fixed
# reasonable constant is the same tradeoff already made elsewhere in this file).


def compute_xfip_siera(bb: float, so: float, hr: float, hbp: float, bf: float, ip: float,
                        gb_pct: float, fb_pct: float, pu_pct: float) -> tuple:
    """
    Same xFIP/SIERA formulas as get_season_pitching_stats below, factored out so both the
    season-snapshot version there AND a genuine walk-forward current-season version (see
    statcast_cumulative_as_of's fb_pct/pu_pct, added specifically to make this possible — see
    build_training_data.py's season_stats construction) compute them identically. Previously
    xfip_diff/siera_diff could only ever reflect a pitcher's PRIOR season (blend_with_prior_season
    had no current-season value to blend against, since nothing computed one) — this is what
    closes that gap. Returns (xfip, siera), either NaN if bf/ip are 0 or the batted-ball mix is
    unavailable (gb_pct/fb_pct/pu_pct all come from actual batted balls, so a pitcher with zero
    balls in play this window has no basis for either estimate).
    """
    if not bf or bf <= 0 or not ip or ip <= 0 or any(pd.isna(v) for v in (gb_pct, fb_pct, pu_pct)):
        return np.nan, np.nan
    bip_estimate = max(bf - bb - so - hbp, 0)
    estimated_fb = bip_estimate * (fb_pct / 100)
    estimated_hr = estimated_fb * LEAGUE_HR_PER_FB_RATE
    xfip = (13 * estimated_hr + 3 * (bb + hbp) - 2 * so) / ip + 3.10

    k_pct_frac = so / bf
    bb_pct_frac = bb / bf
    net_gb_frac = (gb_pct - fb_pct - pu_pct) / 100
    siera = (
        6.145 - 16.986 * k_pct_frac + 11.434 * bb_pct_frac - 1.858 * net_gb_frac
        + 7.653 * (k_pct_frac ** 2) + 6.664 * (net_gb_frac ** 2)
        + 10.130 * k_pct_frac * net_gb_frac - 5.195 * bb_pct_frac * net_gb_frac
    )
    return xfip, siera


def get_season_pitching_stats(season: int, force_refresh: bool = False) -> pd.DataFrame:
    """
    Season-level pitching stats from Baseball-Reference, with FIP and K-BB%
    derived from raw counting stats (BR doesn't publish xFIP/SIERA; FIP is
    the closest free equivalent, using a fixed ~3.10 constant rather than
    the year-specific one FanGraphs uses — a reasonable approximation, not
    exact). Indexed by "mlbID" (MLB Stats API player id) so callers can
    match on the same pitcher_id used throughout the rest of the app.
    """
    def fetch():
        df = pitching_stats_bref(season)
        if df.empty:
            return df
        df = df.copy()
        df["mlbID"] = pd.to_numeric(df["mlbID"], errors="coerce")
        df = df.dropna(subset=["mlbID"])
        df["mlbID"] = df["mlbID"].astype(int)

        ip = df["IP"].apply(_parse_ip)
        df["IP_float"] = ip
        for col in ["ER", "BB", "SO", "HR", "HBP", "BF", "G", "GS", "ERA", "H"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["FIP"] = ((13 * df["HR"] + 3 * (df["BB"] + df["HBP"]) - 2 * df["SO"]) / ip.replace(0, np.nan)) + 3.10
        df["K-BB%"] = (df["SO"] - df["BB"]) / df["BF"].replace(0, np.nan) * 100
        df["K9"] = df["SO"] / ip.replace(0, np.nan) * 9
        df["HR9"] = df["HR"] / ip.replace(0, np.nan) * 9
        # Hits allowed per 9 — distinct from WHIP (which folds in walks too) and NOT captured by
        # FIP at all (FIP deliberately excludes hits on balls in play, treating that as mostly
        # defense/luck-driven). A pitcher who consistently allows more hard/frequent contact than
        # his FIP alone suggests is a real, separate signal from strikeout/walk/homer rate.
        df["H9"] = df["H"] / ip.replace(0, np.nan) * 9
        df["WHIP"] = (df["BB"] + df["H"]) / ip.replace(0, np.nan)
        df["K_pct"] = df["SO"] / df["BF"].replace(0, np.nan) * 100
        df["BB_pct"] = df["BB"] / df["BF"].replace(0, np.nan) * 100
        # How deep a pitcher typically goes before the bullpen takes over — a starter who
        # reliably works into the 7th exposes the bullpen far less than one who's usually
        # pulled in the 4th, independent of raw quality (FIP doesn't capture depth at all).
        # Baseball-Reference's IP is a season TOTAL across every role, not just starts — a
        # swingman with one spot start and thirty relief outings would otherwise show up with
        # a nonsensical "70 innings per start." Guarded to pitchers who are mostly starters
        # (GS/G >= 0.5) with a real sample (GS >= MIN_RELIABLE_STARTS-equivalent of 3), so a
        # reliever's mixed-role total innings never gets divided by a token GS of 1.
        mostly_starter = (df["GS"] / df["G"].replace(0, np.nan) >= 0.5) & (df["GS"] >= 3)
        df["IP_per_GS"] = (ip / df["GS"].replace(0, np.nan)).where(mostly_starter)
        lev = df["Lev"] if "Lev" in df.columns else pd.Series([""] * len(df), index=df.index)
        df["Team"] = [_bref_team_abbr(tm, l) for tm, l in zip(df["Tm"], lev)]

        # xFIP/SIERA: Baseball-Reference doesn't publish either, so both are approximated here —
        # explicitly NOT authoritative FanGraphs numbers, same "reasonable approximation, not
        # exact" spirit as the fixed 3.10 FIP constant above. Both need a batted-ball mix
        # (GB%/FB%/pop-up%) that only Statcast's leaderboard has, merged in by mlbID.
        try:
            batted_ball = get_batted_ball_profile(season, "pitcher")
        except Exception:
            batted_ball = pd.DataFrame()
        if batted_ball is not None and not batted_ball.empty:
            df = df.merge(batted_ball.rename(columns={
                "gb_pct": "bb_gb_pct", "fb_pct": "bb_fb_pct", "pu_pct": "bb_pu_pct",
            })[["mlbID", "bb_gb_pct", "bb_fb_pct", "bb_pu_pct"]], on="mlbID", how="left")
        else:
            df["bb_gb_pct"] = df["bb_fb_pct"] = df["bb_pu_pct"] = np.nan

        # xERA (Statcast's contact-quality-based expected ERA) — a separate Savant leaderboard,
        # merged in the same way as the batted-ball profile above.
        try:
            expected = get_pitcher_expected_stats(season)
        except Exception:
            expected = pd.DataFrame()
        if expected is not None and not expected.empty:
            df = df.merge(expected[["mlbID", "xera"]], on="mlbID", how="left")
        else:
            df["xera"] = np.nan

        # xFIP: FIP with an ESTIMATED home-run total substituted for the pitcher's own actual HR
        # — a league-average HR/FB rate applied to an estimated fly-ball count, since a single
        # season's actual HR/FB is heavily park/luck-driven and xFIP exists specifically to smooth
        # that out. Fly balls estimated from balls-in-play (BF minus BB/SO/HBP) x FB%, both
        # already-available/just-merged columns — no new raw pitch-level pull needed.
        bip_estimate = (df["BF"] - df["BB"] - df["SO"] - df["HBP"]).clip(lower=0)
        estimated_fb = bip_estimate * (df["bb_fb_pct"] / 100)
        estimated_hr = estimated_fb * LEAGUE_HR_PER_FB_RATE
        # Uses df["IP_float"] (a real column, carried through the merges above row-aligned),
        # NOT the standalone `ip` Series computed pre-merge — that Series' index no longer lines
        # up with df's post-merge index (pandas merge resets the index), which silently paired
        # each row's numerator with a DIFFERENT row's innings total. Caught directly: Wheeler's
        # xFIP came out as -13.475 using the stale `ip` Series, vs. a sane ~2.46 recomputed by
        # hand from his own row's own IP_float.
        df["xFIP"] = (
            (13 * estimated_hr + 3 * (df["BB"] + df["HBP"]) - 2 * df["SO"]) / df["IP_float"].replace(0, np.nan)
        ) + 3.10

        # SIERA: best-effort implementation of the publicly documented formula (K%, BB%, and a
        # ground-ball-minus-air-ball mix term, all as fractions of batters faced) — coefficients
        # recalled from public sabermetric write-ups, not verified against FanGraphs' own
        # internal calculation, so treat this as directionally useful, not decimal-precise.
        k_pct_frac = df["SO"] / df["BF"].replace(0, np.nan)
        bb_pct_frac = df["BB"] / df["BF"].replace(0, np.nan)
        net_gb_frac = (df["bb_gb_pct"] - df["bb_fb_pct"] - df["bb_pu_pct"]) / 100
        df["SIERA"] = (
            6.145
            - 16.986 * k_pct_frac
            + 11.434 * bb_pct_frac
            - 1.858 * net_gb_frac
            + 7.653 * (k_pct_frac ** 2)
            + 6.664 * (net_gb_frac ** 2)
            + 10.130 * k_pct_frac * net_gb_frac
            - 5.195 * bb_pct_frac * net_gb_frac
        )
        return df
    return _load_or_fetch(f"bref_pitching_{season}", fetch, force_refresh, max_age_hours=24)


def season_stat_row_lookup(season_pitching_stats: pd.DataFrame, pid: int) -> dict:
    """Raw era/ip/fip/k_bb_pct/k9/hr9/whip/k_pct/bb_pct for one pitcher from a
    get_season_pitching_stats table — shared by live serving (main.py) and training
    (build_training_data.py's prior-season blend) so both read a pitcher's flat
    season line the exact same way."""
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


def get_statcast_pitcher_logs(pitcher_id: int, start_date: str, end_date: str,
                               force_refresh: bool = False) -> pd.DataFrame:
    """
    Pitch-level Statcast data for one pitcher over a date range — trimmed
    to just what's needed to compute whiff%/chase%/hard-hit% ourselves,
    per start, walk-forward (see build_training_data._pitches_to_daily_
    counts). Season-aggregate Statcast leaderboards (e.g.
    statcast_pitcher_percentile_ranks) are NOT used for this: applying a
    single end-of-season snapshot to every game that pitcher threw this
    season would repeat the exact look-ahead leakage already found and
    fixed for FIP/K-BB% elsewhere in this app.
    """
    def fetch():
        try:
            df = statcast_pitcher(start_date, end_date, pitcher_id)
        except Exception:
            # Baseball Savant occasionally returns a malformed/empty CSV response for a
            # given pitcher-range (rate limiting, a pitcher with ~zero pitches in range,
            # a transient server hiccup) — pybaseball doesn't handle that gracefully and
            # raises a raw parser error. One flaky pitcher shouldn't crash a run that's
            # otherwise pulling hundreds of others; treat it the same as "no data."
            return pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame()
        keep = df[["game_date", "description", "zone", "launch_speed", "launch_angle", "release_speed", "pitch_type", "pitch_number"]].copy()
        keep["game_date"] = keep["game_date"].astype(str)
        return keep
    name = f"statcast_pitcher_{pitcher_id}_{start_date}_{end_date}"
    return _load_or_fetch(name, fetch, force_refresh, max_age_hours=12)


_SWING_DESCRIPTIONS = {"hit_into_play", "foul", "swinging_strike", "foul_tip"}
_WHIFF_DESCRIPTIONS = {"swinging_strike"}
_OUT_OF_ZONE_CODES = {11, 12, 13, 14}  # Statcast's 9-zone strike zone grid is 1-9; these four are the "shadow" area just outside it
_HARD_HIT_MPH = 95.0  # standard hard-hit threshold


_CALLED_STRIKE_DESCRIPTIONS = {"called_strike"}

_GROUND_BALL_MAX_LA = 10.0  # standard batted-ball classification: launch angle below this is a ground ball
_FLY_BALL_MIN_LA = 25.0  # 10-25 degrees is a line drive (untracked here — see _pitches_to_daily_counts); 25+ is a fly ball
_POPUP_MIN_LA = 50.0  # steep enough to be an infield/shallow pop-up rather than a regular fly ball


def _is_barrel(ev, la) -> bool:
    """
    Approximates Statcast's official "barrel" classification (a batted ball
    struck hard enough, at the right launch angle, to have historically
    produced a .500+ AVG / 1.500+ SLG). MLB publishes this as a lookup
    table (98 mph -> a narrow 26-30 degree window, widening as exit velo
    climbs, up to a full 8-50 degree window at 116+ mph) rather than a
    formula, so this is a linear interpolation of that published table, not
    an exact reproduction — close enough to be a real signal, not precise
    enough to match Baseball Savant's own barrel% to the decimal.
    """
    if pd.isna(ev) or pd.isna(la) or ev < 98:
        return False
    ev_capped = min(ev, 116)
    lower = max(8.0, 26.0 - (ev_capped - 98))
    upper = min(50.0, 30.0 + (ev_capped - 98) * (20.0 / 18.0))
    return lower <= la <= upper


def _pitches_to_daily_counts(pitches: pd.DataFrame) -> dict:
    """
    {game_date: (swings, whiffs, out_of_zone_pitches, chases, batted_balls,
    hard_hit_batted_balls, called_strikes, total_pitches, ground_balls,
    barrels, first_pitches, first_pitch_strikes, fly_balls, pop_ups)} — per-start pitch-level
    counts, the building blocks for walk-forward whiff%/chase%/hard-hit%/
    CSW%/GB%/barrel%/zone%/contact%/first-pitch-strike%/FB%/PU% (see
    statcast_cumulative_as_of). "Chase" is the standard definition: a swing
    at a pitch outside the strike zone. CSW% (called + swinging strike
    rate, per total pitches) is a command signal distinct from whiff%
    (swing-and-miss rate per SWING) — a pitcher can miss bats well but
    work behind in counts, or vice versa; it's the same raw `description`
    field already being read here, just one more category counted, no new
    data pull needed. Ground-ball% and barrel% both come from the same
    batted-ball subset already used for hard-hit%, using launch_angle
    (added alongside launch_speed) rather than a separate pull. Zone%
    (in-zone pitches / total) and contact% (contacted swings / total
    swings) are direct complements of out_of_zone_pitches and whiffs
    already computed above — no new tracking needed, just exposed at the
    aggregation step (see statcast_cumulative_as_of). First-pitch-strike%
    is the one genuinely new count here: pitch_number == 1 identifies the
    first pitch of each at-bat (confirmed against real Statcast data — it
    resets per at-bat, not a running game-long pitch count), and a "strike"
    on it is any swing (including foul/in-play) or called strike, same
    description sets already used above.
    """
    if pitches is None or pitches.empty:
        return {}
    daily = {}
    for date, group in pitches.groupby("game_date"):
        is_swing = group["description"].isin(_SWING_DESCRIPTIONS)
        is_whiff = group["description"].isin(_WHIFF_DESCRIPTIONS)
        is_ooz = group["zone"].isin(_OUT_OF_ZONE_CODES)
        is_batted = group["description"] == "hit_into_play"
        is_hard_hit = is_batted & (group["launch_speed"] >= _HARD_HIT_MPH)
        is_called_strike = group["description"].isin(_CALLED_STRIKE_DESCRIPTIONS)
        is_ground_ball = is_batted & (group["launch_angle"] < _GROUND_BALL_MAX_LA)
        batted = group[is_batted]
        barrel_count = int(sum(
            _is_barrel(ev, la) for ev, la in zip(batted["launch_speed"], batted["launch_angle"])
        ))
        is_fly_ball = is_batted & (group["launch_angle"] >= _FLY_BALL_MIN_LA) & (group["launch_angle"] < _POPUP_MIN_LA)
        is_popup = is_batted & (group["launch_angle"] >= _POPUP_MIN_LA)
        is_first_pitch = group["pitch_number"] == 1
        is_first_pitch_strike = is_first_pitch & (is_swing | is_called_strike)
        daily[str(date)] = (
            int(is_swing.sum()), int(is_whiff.sum()),
            int(is_ooz.sum()), int((is_ooz & is_swing).sum()),
            int(is_batted.sum()), int(is_hard_hit.sum()),
            int(is_called_strike.sum()), int(len(group)),
            int(is_ground_ball.sum()), barrel_count,
            int(is_first_pitch.sum()), int(is_first_pitch_strike.sum()),
            int(is_fly_ball.sum()), int(is_popup.sum()),
        )
    return daily


def get_pitcher_statcast_daily(pitcher_id: int, season: int, force_refresh: bool = False) -> dict:
    """Per-start pitch-level counts for a pitcher's whole season — see _pitches_to_daily_counts.
    One API call per pitcher-season (not per start), then aggregated locally."""
    pitches = get_statcast_pitcher_logs(pitcher_id, f"{season}-01-01", f"{season}-12-31", force_refresh)
    return _pitches_to_daily_counts(pitches)


_FASTBALL_TYPES = {"FF", "SI", "FC"}  # four-seam/sinker/cutter — the "primary" velocity-bearing pitches;
# offspeed/breaking velocity isn't comparable across pitchers or informative the same way for a fatigue/decline read


def _pitches_to_daily_velocity(pitches: pd.DataFrame) -> dict:
    """{game_date: (sum_release_speed, pitch_count)} for fastball-family pitches only — building
    block for a recent-vs-season velocity trend (a widening gap, recent below season, is a real
    fatigue/decline signal that tends to lead results-level regression, not follow it)."""
    if pitches is None or pitches.empty or "release_speed" not in pitches.columns or "pitch_type" not in pitches.columns:
        return {}
    fb = pitches[pitches["pitch_type"].isin(_FASTBALL_TYPES) & pitches["release_speed"].notna()]
    if fb.empty:
        return {}
    daily = {}
    for date, group in fb.groupby("game_date"):
        daily[str(date)] = (float(group["release_speed"].sum()), int(len(group)))
    return daily


def get_pitcher_velocity_daily(pitcher_id: int, season: int, force_refresh: bool = False) -> dict:
    """Per-start fastball velocity sums for a pitcher's whole season — see _pitches_to_daily_velocity.
    Reuses the same cached raw pitch-level pull as get_pitcher_statcast_daily, no extra fetch."""
    pitches = get_statcast_pitcher_logs(pitcher_id, f"{season}-01-01", f"{season}-12-31", force_refresh)
    return _pitches_to_daily_velocity(pitches)


def statcast_velocity_trend(daily: dict, before_date: str = None, recent_n: int = 3) -> dict:
    """Season-to-date avg fastball velocity vs the last `recent_n` starts' avg, walk-forward.
    `velo_trend` = recent - season; negative means velocity is trending down from where it's
    been all year, which is the kind of thing that shows up before ERA/FIP do."""
    eligible = {d: v for d, v in daily.items() if before_date is None or d < before_date}
    if not eligible:
        return {"season_avg_velo": np.nan, "recent_avg_velo": np.nan, "velo_trend": np.nan}

    total_sum = sum(v[0] for v in eligible.values())
    total_count = sum(v[1] for v in eligible.values())
    season_avg = (total_sum / total_count) if total_count > 0 else np.nan

    recent_dates = sorted(eligible.keys())[-recent_n:]
    recent_sum = sum(eligible[d][0] for d in recent_dates)
    recent_count = sum(eligible[d][1] for d in recent_dates)
    recent_avg = (recent_sum / recent_count) if recent_count > 0 else np.nan

    trend = (recent_avg - season_avg) if pd.notna(recent_avg) and pd.notna(season_avg) else np.nan
    return {"season_avg_velo": season_avg, "recent_avg_velo": recent_avg, "velo_trend": trend}


def _pitches_to_daily_pitch_types(pitches: pd.DataFrame) -> dict:
    """{game_date: {pitch_type: count}} — building block for pitch-mix diversity. Note: this is
    NOT a "pitch mix vs this lineup" matchup feature — that would need batter-side performance
    against each pitch type, and no free data source for that was found (see features.py's
    STRIKEOUT_FEATURE_COLUMNS / FEATURE_COLUMNS docstrings). This is the narrower, still-useful
    signal that's actually feasible with what's available: how balanced a pitcher's own arsenal
    is, independent of who they're facing — a one/two-pitch pitcher is easier for any lineup to
    sit on than one with a deep, even mix."""
    if pitches is None or pitches.empty or "pitch_type" not in pitches.columns:
        return {}
    daily = {}
    for date, group in pitches.groupby("game_date"):
        counts = {pt: int(c) for pt, c in group["pitch_type"].value_counts().items() if pd.notna(pt)}
        if counts:
            daily[str(date)] = counts
    return daily


def get_pitcher_pitch_types_daily(pitcher_id: int, season: int, force_refresh: bool = False) -> dict:
    """Per-start pitch-type counts for a pitcher's whole season — see _pitches_to_daily_pitch_types.
    Reuses the same cached raw pitch-level pull as get_pitcher_statcast_daily, no extra fetch."""
    pitches = get_statcast_pitcher_logs(pitcher_id, f"{season}-01-01", f"{season}-12-31", force_refresh)
    return _pitches_to_daily_pitch_types(pitches)


def statcast_pitch_diversity(daily: dict, before_date: str = None) -> dict:
    """1 - (most-thrown pitch type's share of total pitches), season-to-date, walk-forward.
    Higher means a more balanced, harder-to-prepare-for arsenal; a pitcher who's ~70% fastball
    scores low here regardless of how good that fastball is."""
    eligible = {d: v for d, v in daily.items() if before_date is None or d < before_date}
    if not eligible:
        return {"pitch_diversity": np.nan}

    totals = {}
    for counts in eligible.values():
        for pt, c in counts.items():
            totals[pt] = totals.get(pt, 0) + c
    if not totals:
        return {"pitch_diversity": np.nan}

    total_pitches = sum(totals.values())
    max_share = max(totals.values()) / total_pitches
    return {"pitch_diversity": 1.0 - max_share}


def statcast_pitch_mix_as_of(daily: dict, before_date: str = None) -> dict:
    """{pitch_type: share of this pitcher's total pitches}, season-to-date, walk-forward — the
    full breakdown behind statcast_pitch_diversity's single max-share number, needed to weight
    a pitcher's own arsenal mix against an opponent's per-pitch-type weakness (see features.py's
    _arsenal_matchup_score). Empty dict if there's no eligible data yet."""
    eligible = {d: v for d, v in daily.items() if before_date is None or d < before_date}
    totals = {}
    for counts in eligible.values():
        for pt, c in counts.items():
            totals[pt] = totals.get(pt, 0) + c
    total_pitches = sum(totals.values())
    if total_pitches == 0:
        return {}
    return {pt: c / total_pitches for pt, c in totals.items()}


# Baseball Savant's pitch-arsenal batter leaderboard is season-to-date when queried mid-season
# (it can't include games that haven't happened yet), so it's safe to use directly for LIVE
# serving — "today" is always after every game the leaderboard reflects. It is NOT walk-forward
# for historical TRAINING rows, though: an April game would see the batter's full-season(-so-far)
# numbers, including games that hadn't happened yet as of April — the same look-ahead leakage
# already fixed for FIP/K-BB% elsewhere. Training uses the PRIOR season's version of this same
# table instead (see build_training_data.py), the same safe pattern already used for
# prior_season_fip_diff/prior_season_k_bb_pct_diff.
BATTER_ARSENAL_MIN_PA = 25  # pybaseball's own default — below this, a batter's per-pitch-type split is mostly noise


def get_batter_pitch_arsenal(season: int, force_refresh: bool = False) -> pd.DataFrame:
    """
    Every qualified batter's whiff%/wOBA/hard-hit% broken out by pitch type (FF/SI/FC/SL/CU/CH/
    FS/ST) for one season — "this lineup crushes fastballs but chases sliders" made concrete, per
    batter. Indexed by "mlbID" (MLB Stats API player id, matching pitch_type's own player_id
    field 1:1) so callers can match on the same batter ids used throughout the rest of the app.
    One CSV pull per season (a leaderboard, not a per-player call), same shape as
    get_season_pitching_stats.
    """
    def fetch():
        df = statcast_batter_pitch_arsenal(season, minPA=BATTER_ARSENAL_MIN_PA)
        if df.empty:
            return df
        df = df.rename(columns={"player_id": "mlbID"})
        return df[["mlbID", "team_name_alt", "pitch_type", "pitch_usage", "whiff_percent", "woba", "hard_hit_percent"]].copy()
    return _load_or_fetch(f"batter_pitch_arsenal_{season}", fetch, force_refresh, max_age_hours=24)


def get_batter_team_map(season: int, force_refresh: bool = False) -> dict:
    """{mlbID: team_abbr} — reuses get_batter_pitch_arsenal's own team_name_alt column rather
    than a separate roster fetch, since none of the other batter-level Statcast leaderboards
    below (expected stats, exit velo/barrels, percentile ranks) carry a team column at all."""
    arsenal = get_batter_pitch_arsenal(season, force_refresh)
    if arsenal is None or arsenal.empty:
        return {}
    return dict(zip(arsenal["mlbID"], arsenal["team_name_alt"]))


def get_batter_expected_stats(season: int, force_refresh: bool = False) -> pd.DataFrame:
    """
    Each qualified batter's xBA/xSLG/xwOBA — Statcast's "expected" stats, derived from the
    quality of contact (exit velo + launch angle) rather than what actually fell in for a hit,
    the classic argument for these being a truer, faster-stabilizing read on a hitter than raw
    BA/SLG/wOBA over a partial season. Indexed by "mlbID", same shape as get_batter_pitch_arsenal.
    """
    def fetch():
        df = statcast_batter_expected_stats(season, minPA=BATTER_ARSENAL_MIN_PA)
        if df.empty:
            return df
        df = df.rename(columns={"player_id": "mlbID", "est_ba": "xba", "est_slg": "xslg", "est_woba": "xwoba"})
        return df[["mlbID", "xba", "xslg", "xwoba"]].copy()
    return _load_or_fetch(f"batter_expected_stats_{season}", fetch, force_refresh, max_age_hours=24)


def get_batter_exitvelo_barrels(season: int, force_refresh: bool = False) -> pd.DataFrame:
    """
    Each qualified batter's hard-hit% (95+ mph batted balls), barrel%, and sweet-spot% (launch
    angle 8-32°, the "good" contact-quality window) — season-to-date, indexed by "mlbID".
    """
    def fetch():
        df = statcast_batter_exitvelo_barrels(season, minBBE=BATTER_ARSENAL_MIN_PA)
        if df.empty:
            return df
        df = df.rename(columns={
            "player_id": "mlbID", "ev95percent": "hard_hit_pct",
            "brl_percent": "barrel_pct", "anglesweetspotpercent": "sweet_spot_pct",
        })
        return df[["mlbID", "hard_hit_pct", "barrel_pct", "sweet_spot_pct"]].copy()
    return _load_or_fetch(f"batter_exitvelo_barrels_{season}", fetch, force_refresh, max_age_hours=24)


def get_batter_percentile_ranks(season: int, force_refresh: bool = False) -> pd.DataFrame:
    """
    Each qualified batter's chase%/contact% as league PERCENTILE RANKS (0-100), not raw rates —
    Baseball Savant doesn't publish a raw-rate batter chase%/contact% leaderboard (only a
    percentile-rank one, same page as the player-card percentile bars). Kept clearly labeled as
    percentile-scale in every column/feature name downstream so it's never confused with the
    rate-scale features (whiff_pct_diff etc.) already in the model. Indexed by "mlbID".
    """
    def fetch():
        df = statcast_batter_percentile_ranks(season)
        if df.empty:
            return df
        df = df.rename(columns={
            "player_id": "mlbID", "chase_percent": "chase_percentile", "whiff_percent": "contact_percentile_inv",
        })
        # whiff_percent here is a percentile rank of WHIFF rate (higher = whiffs more = worse
        # contact) — flipped to a "contact percentile" (higher = better contact) so its sign
        # convention matches every other "higher is better for the batter" feature in this app.
        if "contact_percentile_inv" in df.columns:
            df["contact_percentile"] = 100 - df["contact_percentile_inv"]
        return df[["mlbID", "chase_percentile", "contact_percentile"]].copy()
    return _load_or_fetch(f"batter_percentile_ranks_{season}", fetch, force_refresh, max_age_hours=24)


def get_batted_ball_profile(season: int, player_type: str, force_refresh: bool = False) -> pd.DataFrame:
    """
    Ground-ball%, fly-ball%, pop-up%, and pull% for every qualified batter or pitcher
    (player_type: "batter" or "pitcher") — Baseball Savant's batted-ball-profile leaderboard.
    Not wrapped by pybaseball as a named function (unlike the pitch-arsenal/expected-stats ones
    above), but the same CSV-export URL pattern works directly — verified live. Feeds the
    batter-side pull%/GB% features and the pitcher-side FB%/pop-up% components SIERA/xFIP need.
    Indexed by "mlbID".
    """
    def fetch():
        resp = requests.get(
            "https://baseballsavant.mlb.com/leaderboard/batted-ball",
            params={"type": player_type, "year": season, "csv": "true"}, timeout=20,
        )
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.content.decode("utf-8")))
        if df.empty:
            return df
        df = df.rename(columns={
            "id": "mlbID", "gb_rate": "gb_pct", "fb_rate": "fb_pct",
            "pu_rate": "pu_pct", "pull_rate": "pull_pct",
        })
        for col in ("gb_pct", "fb_pct", "pu_pct", "pull_pct"):
            if col in df.columns:
                df[col] = df[col] * 100  # Savant returns these as 0-1 fractions, not 0-100 like every other %-stat here
        return df[["mlbID", "gb_pct", "fb_pct", "pu_pct", "pull_pct"]].copy()
    return _load_or_fetch(f"batted_ball_{player_type}_{season}", fetch, force_refresh, max_age_hours=24)


def get_pitcher_expected_stats(season: int, force_refresh: bool = False) -> pd.DataFrame:
    """
    Each qualified pitcher's xERA (and xBA/xSLG/xwOBA allowed) — Statcast's contact-quality-based
    "expected" ERA, distinct from FIP (which only looks at K/BB/HR, ignoring contact quality
    entirely) and from actual ERA (which includes defense/sequencing luck). A pitcher can run a
    high ERA while allowing weak contact (bad luck/defense) or the reverse — xERA is meant to
    separate those. Indexed by "mlbID".
    """
    def fetch():
        df = statcast_pitcher_expected_stats(season, minPA=BATTER_ARSENAL_MIN_PA)
        if df.empty:
            return df
        df = df.rename(columns={"player_id": "mlbID", "xera": "xera", "est_ba": "xba_allowed",
                                 "est_slg": "xslg_allowed", "est_woba": "xwoba_allowed"})
        return df[["mlbID", "xera", "xba_allowed", "xslg_allowed", "xwoba_allowed"]].copy()
    return _load_or_fetch(f"pitcher_expected_stats_{season}", fetch, force_refresh, max_age_hours=24)


def statcast_cumulative_as_of(daily: dict, before_date: str = None) -> dict:
    """
    Cumulative whiff%/chase%/hard-hit% from every start in `daily` (as
    returned by get_pitcher_statcast_daily) with a date strictly before
    `before_date` — walk-forward, no leakage. Pass before_date=None for
    live serving: "today" is inherently after every pulled start, so the
    full season-to-date sum is exactly what's wanted, no filtering needed.
    """
    swings = whiffs = ooz = chases = batted = hard_hit = called_strikes = total_pitches = 0
    ground_balls = barrels = first_pitches = first_pitch_strikes = 0
    fly_balls = pop_ups = 0
    num_starts = 0
    for date, counts in daily.items():
        if before_date is not None and date >= before_date:
            continue
        s, w, o, c, b, h = counts[:6]
        cs, tp = counts[6:8] if len(counts) >= 8 else (0, 0)
        gb, br = counts[8:10] if len(counts) >= 10 else (0, 0)
        fp, fps = counts[10:12] if len(counts) >= 12 else (0, 0)
        fb, pu = counts[12:14] if len(counts) >= 14 else (0, 0)
        swings += s
        whiffs += w
        ooz += o
        chases += c
        batted += b
        hard_hit += h
        called_strikes += cs
        total_pitches += tp
        ground_balls += gb
        barrels += br
        first_pitches += fp
        first_pitch_strikes += fps
        fly_balls += fb
        pop_ups += pu
        num_starts += 1
    return {
        "whiff_pct": (whiffs / swings * 100) if swings > 0 else np.nan,
        "chase_pct": (chases / ooz * 100) if ooz > 0 else np.nan,
        "hard_hit_pct": (hard_hit / batted * 100) if batted > 0 else np.nan,
        "csw_pct": ((whiffs + called_strikes) / total_pitches * 100) if total_pitches > 0 else np.nan,
        "pitches_per_start": (total_pitches / num_starts) if num_starts > 0 else np.nan,
        "gb_pct": (ground_balls / batted * 100) if batted > 0 else np.nan,
        "barrel_pct": (barrels / batted * 100) if batted > 0 else np.nan,
        # in-zone pitches / total — direct complement of chase%'s out-of-zone denominator, no new tracking
        "zone_pct": ((total_pitches - ooz) / total_pitches * 100) if total_pitches > 0 else np.nan,
        # contacted swings / total swings — direct complement of whiff_pct, no new tracking
        "contact_pct": ((swings - whiffs) / swings * 100) if swings > 0 else np.nan,
        "first_pitch_strike_pct": (first_pitch_strikes / first_pitches * 100) if first_pitches > 0 else np.nan,
        # fb_pct/pu_pct: see _pitches_to_daily_counts — feeds compute_xfip_siera for a genuine
        # walk-forward xFIP/SIERA, not the batted count itself needed anywhere else on its own.
        "fb_pct": (fly_balls / batted * 100) if batted > 0 else np.nan,
        "pu_pct": (pop_ups / batted * 100) if batted > 0 else np.nan,
        "batters_faced_est": batted,  # exposed only so callers can sanity-check sample size, not a feature itself
    }


RECENT_STATCAST_STARTS = 3  # short enough to catch a real stuff trend, long enough that one weird outing doesn't dominate


def statcast_recent_as_of(daily: dict, before_date: str = None, n: int = RECENT_STATCAST_STARTS) -> dict:
    """
    Same shape as statcast_cumulative_as_of, but only the pitcher's most
    recent `n` starts strictly before `before_date` — a recent-form window
    on the process stats, same pairing as recent_k9 vs season_k9 elsewhere
    in this app. Season-to-date whiff%/chase% smooths over a pitcher's
    stuff trending up or down over the last few outings; this catches that
    the way recent_k9 already catches results-level hot/cold streaks.
    """
    eligible_dates = sorted(d for d in daily if before_date is None or d < before_date)
    recent_dates = eligible_dates[-n:]
    swings = whiffs = ooz = chases = batted = hard_hit = called_strikes = total_pitches = 0
    ground_balls = barrels = first_pitches = first_pitch_strikes = 0
    for date in recent_dates:
        counts = daily[date]
        s, w, o, c, b, h = counts[:6]
        cs, tp = counts[6:8] if len(counts) >= 8 else (0, 0)
        gb, br = counts[8:10] if len(counts) >= 10 else (0, 0)
        fp, fps = counts[10:12] if len(counts) >= 12 else (0, 0)
        swings += s
        whiffs += w
        ooz += o
        chases += c
        batted += b
        hard_hit += h
        called_strikes += cs
        total_pitches += tp
        ground_balls += gb
        barrels += br
        first_pitches += fp
        first_pitch_strikes += fps
    num_starts = len(recent_dates)
    return {
        "whiff_pct": (whiffs / swings * 100) if swings > 0 else np.nan,
        "chase_pct": (chases / ooz * 100) if ooz > 0 else np.nan,
        "hard_hit_pct": (hard_hit / batted * 100) if batted > 0 else np.nan,
        "csw_pct": ((whiffs + called_strikes) / total_pitches * 100) if total_pitches > 0 else np.nan,
        "pitches_per_start": (total_pitches / num_starts) if num_starts > 0 else np.nan,
        "gb_pct": (ground_balls / batted * 100) if batted > 0 else np.nan,
        "barrel_pct": (barrels / batted * 100) if batted > 0 else np.nan,
        "zone_pct": ((total_pitches - ooz) / total_pitches * 100) if total_pitches > 0 else np.nan,
        "contact_pct": ((swings - whiffs) / swings * 100) if swings > 0 else np.nan,
        "first_pitch_strike_pct": (first_pitch_strikes / first_pitches * 100) if first_pitches > 0 else np.nan,
    }


MIN_STARTS_FOR_RECENT_FORM = 3  # fewer real starts than this and we fall back to recent appearances (see below)


def get_pitcher_recent_starts(pitcher_id: int, season: int, n: int = 5,
                               force_refresh: bool = False) -> dict:
    """
    ERA / FIP / K-per-9 / BB-per-9 over a pitcher's last n outings, from the
    MLB Stats API's per-game log (official box-score numbers — exact IP,
    not an approximation). Rate stats are computed from summed IP/ER/K/BB
    across those outings, not averaged per-game, so a couple of short
    outings don't get equal weight to a complete game.

    Prefers actual STARTS. But a pitcher can have plenty of recent, usable
    data while barely starting — e.g. a swingman or rotation call-up who's
    made 28 relief appearances and 1 start: their 1-start sample is noise,
    but their last several relief outings are a real, current read on their
    stuff. So when real starts are too sparse (< MIN_STARTS_FOR_RECENT_FORM),
    this falls back to the pitcher's last n appearances of ANY role. Relief
    outings do run a bit better than the same pitcher's start numbers (the
    "one time through the order" effect inflates K rate / suppresses ERA
    somewhat), so it's an imperfect proxy — sample_type says which one was
    used so callers can caveat it rather than present it as equivalent.

    FIP is included (not just ERA) because ERA is skewed by defense and
    sequencing luck — a pitcher can post a bad ERA over a short recent
    stretch while their actual peripherals (K, BB, HR) show they're
    pitching fine. FIP isolates what the pitcher actually controls, so
    it's what actually drives the model's "recent form" signal; ERA is
    shown for context but isn't what the prediction leans on.

    Returns {"era":.., "fip":.., "k9":.., "bb9":.., "ip_per_start":..,
    "starts": <actual starts on record>, "sample_size": <outings behind
    the rate stats>, "sample_type": "starts"|"appearances",
    "last_start_date":..} — last_start_date is always the most recent
    actual START (for rest-days purposes), independent of sample_type.
    """
    def fetch():
        resp = requests.get(
            f"{MLB_STATS_API}/people/{pitcher_id}/stats",
            params={"stats": "gameLog", "group": "pitching", "season": season},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        stats_blocks = data.get("stats", [])
        splits = stats_blocks[0].get("splits", []) if stats_blocks else []

        starts = sorted(
            [s for s in splits if s.get("stat", {}).get("gamesStarted") == 1],
            key=lambda s: s.get("date", ""),
        )
        last_start_date = starts[-1]["date"] if starts else None
        recent_starts = starts[-n:]

        if len(recent_starts) >= MIN_STARTS_FOR_RECENT_FORM:
            sample, sample_type = recent_starts, "starts"
        else:
            sample = sorted(splits, key=lambda s: s.get("date", ""))[-n:]
            sample_type = "appearances"

        total_ip = sum(_parse_ip(s["stat"].get("inningsPitched", 0)) for s in sample)
        total_er = sum(s["stat"].get("earnedRuns", 0) for s in sample)
        total_k = sum(s["stat"].get("strikeOuts", 0) for s in sample)
        total_bb = sum(s["stat"].get("baseOnBalls", 0) for s in sample)
        total_hr = sum(s["stat"].get("homeRuns", 0) for s in sample)
        total_hbp = sum(s["stat"].get("hitBatsmen", 0) for s in sample)
        total_h = sum(s["stat"].get("hits", 0) for s in sample)
        total_bf = sum(s["stat"].get("battersFaced", 0) for s in sample)

        if total_ip <= 0:
            return pd.DataFrame([{"era": np.nan, "fip": np.nan, "k9": np.nan, "bb9": np.nan,
                                   "whip": np.nan, "k_pct": np.nan, "bb_pct": np.nan, "hr9": np.nan, "h9": np.nan,
                                   "ip_per_start": np.nan, "starts": len(recent_starts), "sample_size": 0,
                                   "sample_type": "starts", "last_start_date": last_start_date}])

        return pd.DataFrame([{
            "era": total_er / total_ip * 9,
            "fip": (13 * total_hr + 3 * (total_bb + total_hbp) - 2 * total_k) / total_ip + 3.10,
            "k9": total_k / total_ip * 9,
            "bb9": total_bb / total_ip * 9,
            "whip": (total_bb + total_h) / total_ip,
            "k_pct": (total_k / total_bf * 100) if total_bf > 0 else np.nan,
            "bb_pct": (total_bb / total_bf * 100) if total_bf > 0 else np.nan,
            "hr9": total_hr / total_ip * 9,
            "h9": total_h / total_ip * 9,
            "ip_per_start": total_ip / len(sample),
            "starts": len(recent_starts),
            "sample_size": len(sample),
            "sample_type": sample_type,
            "last_start_date": last_start_date,
        }])

    name = f"recent_starts_{pitcher_id}_{season}_n{n}"
    df = _load_or_fetch(name, fetch, force_refresh, max_age_hours=6)
    if df is None or df.empty:
        return {"era": np.nan, "fip": np.nan, "k9": np.nan, "bb9": np.nan, "ip_per_start": np.nan,
                "starts": 0, "sample_size": 0, "sample_type": "starts", "last_start_date": None}
    result = df.iloc[0].to_dict()
    result["starts"] = int(result["starts"])  # parquet round-trip gives numpy.int64, not JSON-safe
    result["sample_size"] = int(result["sample_size"])
    return result


def get_pitcher_season_log(pitcher_id: int, season: int, force_refresh: bool = False) -> pd.DataFrame:
    """
    Every start a pitcher has made this season, one row each, with that
    start's own FIP/K9/BB9/IP — the full-season trend line
    get_pitcher_recent_starts deliberately doesn't give (it only keeps the
    last n). Used for the pitcher drill-down view, not for any model
    feature.
    """
    def fetch():
        resp = requests.get(
            f"{MLB_STATS_API}/people/{pitcher_id}/stats",
            params={"stats": "gameLog", "group": "pitching", "season": season},
            timeout=15,
        )
        resp.raise_for_status()
        # .get("stats", []) can come back as an empty list (not a missing key) when a pitcher made
        # zero MLB appearances that season — a rookie with no 2025 log, e.g. — so indexing [0]
        # unconditionally raised IndexError. Only triggered once get_pitcher_vs_team_history started
        # calling this for every pitcher across a fixed season list, some of whom hadn't debuted yet.
        stats_blocks = resp.json().get("stats", [])
        splits = stats_blocks[0].get("splits", []) if stats_blocks else []
        starts = sorted(
            [s for s in splits if s.get("stat", {}).get("gamesStarted") == 1],
            key=lambda s: s.get("date", ""),
        )
        rows = []
        for s in starts:
            stat = s.get("stat", {})
            ip = _parse_ip(stat.get("inningsPitched", 0))
            if ip <= 0:
                continue
            er = stat.get("earnedRuns", 0)
            k = stat.get("strikeOuts", 0)
            bb = stat.get("baseOnBalls", 0)
            hr = stat.get("homeRuns", 0)
            hbp = stat.get("hitBatsmen", 0)
            rows.append({
                "game_date": s.get("date"),
                "ip": ip, "k": k, "bb": bb, "er": er, "hr": hr, "hbp": hbp,
                "era": er / ip * 9,
                "fip": (13 * hr + 3 * (bb + hbp) - 2 * k) / ip + 3.10,
                "k9": k / ip * 9,
                "bb9": bb / ip * 9,
                "opponent": (s.get("opponent") or {}).get("name"),
                "is_win": s.get("isWin"),
            })
        return pd.DataFrame(rows)
    return _load_or_fetch(f"season_log_{pitcher_id}_{season}", fetch, force_refresh, max_age_hours=6)


def _get_mlb_team_name_to_abbr(force_refresh: bool = False) -> dict:
    """{full team name (e.g. "Cleveland Guardians"): team_abbr} — the gameLog endpoint's
    "opponent" field only gives a full name, not the abbreviation used everywhere else in
    this app, so this is the reverse of _get_mlb_team_ids' name, built from the same cached
    /teams pull (no extra API call)."""
    def fetch():
        resp = requests.get(f"{MLB_STATS_API}/teams", params={"sportId": 1}, timeout=15)
        resp.raise_for_status()
        teams = resp.json().get("teams", [])
        return pd.DataFrame([{"name": t["name"], "Team": t["abbreviation"]} for t in teams])
    df = _load_or_fetch("mlb_team_name_to_abbr", fetch, force_refresh, max_age_hours=24 * 30)
    if df is None or df.empty:
        return {}
    return dict(zip(df["name"], df["Team"]))


H2H_FULL_RELIABILITY_STARTS = 6  # roughly two seasons' worth of starts against a single divisional rival


def get_pitcher_vs_team_history(pitcher_id: int, opp_team_abbr: str, seasons: list[int],
                                 force_refresh: bool = False) -> dict:
    """
    A pitcher's own ERA/FIP/K9/BB9 specifically against the team they're
    facing tonight, aggregated across every start they've made against
    that team in the given seasons (e.g. this season + last season) — not
    a team-wide platoon split, but this SPECIFIC pitcher's own head-to-head
    track record against this SPECIFIC opponent. Reuses get_pitcher_season_log's
    already-cached per-start rows (no extra API call beyond what recent-form/
    season-log already pull), just filtered down to the relevant opponent.

    Sample sizes here are inherently tiny — a starter might face a given
    non-divisional opponent zero times in two years, or a divisional rival
    2-4 times a season — so this is always paired with a reliability weight
    (see features._h2h_weight) rather than trusted at face value the way a
    much larger season sample is.
    """
    name_to_abbr = _get_mlb_team_name_to_abbr(force_refresh)
    frames = []
    for season in seasons:
        log = get_pitcher_season_log(pitcher_id, season, force_refresh)
        if log is None or log.empty:
            continue
        frames.append(log)
    if not frames:
        return {"era": np.nan, "fip": np.nan, "k9": np.nan, "bb9": np.nan, "starts": 0, "ip": 0.0}
    combined = pd.concat(frames, ignore_index=True)
    combined["opp_abbr"] = combined["opponent"].map(name_to_abbr)
    vs_team = combined[combined["opp_abbr"] == opp_team_abbr]
    if vs_team.empty:
        return {"era": np.nan, "fip": np.nan, "k9": np.nan, "bb9": np.nan, "starts": 0, "ip": 0.0}

    total_ip = vs_team["ip"].sum()
    if total_ip <= 0:
        return {"era": np.nan, "fip": np.nan, "k9": np.nan, "bb9": np.nan, "starts": len(vs_team), "ip": 0.0}
    total_er = vs_team["er"].sum()
    total_k = vs_team["k"].sum()
    total_bb = vs_team["bb"].sum()
    total_hr = vs_team["hr"].sum()
    total_hbp = vs_team["hbp"].sum() if "hbp" in vs_team.columns else 0
    return {
        "era": total_er / total_ip * 9,
        "fip": (13 * total_hr + 3 * (total_bb + total_hbp) - 2 * total_k) / total_ip + 3.10,
        "k9": total_k / total_ip * 9,
        "bb9": total_bb / total_ip * 9,
        "starts": len(vs_team),
        "ip": float(total_ip),
    }


BULK_RELIEVER_MAJORITY = 0.6  # one reliever has to be "the bulk arm" in at least this share of the sample to count as a pattern


def get_bulk_reliever_pattern(pitcher_id: int, team_abbr: str, season: int, n: int = 5,
                               force_refresh: bool = False) -> int | None:
    """
    For a pitcher whose recent 'starts' are actually short opener stints
    (see main._is_opener), checks whether ONE specific reliever consistently
    threw the bulk of the game after them. If so, returns that reliever's
    pitcher_id — live serving can use THEIR stats as the effective starter
    for win-probability purposes, since they're the one who actually faces
    most of the opposing lineup, not the opener.

    Looks at the pitcher's last `n` start dates, pulls each game's box
    score, and finds whichever OTHER pitcher on the team threw the most
    innings that game. Returns None if there's no game log yet, or if the
    bulk innings are split across a genuinely inconsistent rotation of
    relievers with no pitcher appearing in at least BULK_RELIEVER_MAJORITY
    of the sample — confirmed on a real case (Bryan Hudson, CWS: bulk
    innings split between three different relievers across 5 starts, no
    reliable single answer) — in that case there's no more-specific data to
    substitute, and the team's overall bullpen quality features
    (bullpen_fip_diff etc.) are the honest fallback instead.
    """
    def fetch():
        log = get_pitcher_season_log(pitcher_id, season)
        if log.empty:
            return pd.DataFrame()
        dates = log.sort_values("game_date")["game_date"].tail(n).tolist()
        team_ids = _get_mlb_team_ids()
        team_id = team_ids.get(team_abbr)
        if not team_id:
            return pd.DataFrame()

        bulk_pitchers = []
        for date in dates:
            try:
                resp = requests.get(f"{MLB_STATS_API}/schedule", params={
                    "sportId": 1, "startDate": date, "endDate": date, "teamId": team_id,
                }, timeout=15)
                resp.raise_for_status()
                games_today = resp.json().get("dates", [{}])[0].get("games", [])
                if not games_today:
                    continue
                game_pk = games_today[0]["gamePk"]
                box = requests.get(f"{MLB_STATS_API}/game/{game_pk}/boxscore", timeout=15).json()
                team_side = None
                for side in ("home", "away"):
                    if box["teams"][side]["team"].get("id") == team_id:
                        team_side = box["teams"][side]
                        break
                if team_side is None:
                    continue
                best_pid, best_ip = None, -1.0
                for pid in team_side.get("pitchers", []):
                    if pid == pitcher_id:
                        continue
                    p = team_side["players"].get(f"ID{pid}", {})
                    ip = _parse_ip(p.get("stats", {}).get("pitching", {}).get("inningsPitched", "0.0"))
                    if ip > best_ip:
                        best_ip, best_pid = ip, pid
                if best_pid is not None:
                    bulk_pitchers.append(best_pid)
            except (requests.exceptions.RequestException, KeyError, IndexError):
                continue
        return pd.DataFrame({"bulk_pitcher_id": bulk_pitchers})

    df = _load_or_fetch(f"bulk_reliever_{pitcher_id}_{season}", fetch, force_refresh, max_age_hours=12)
    if df is None or df.empty:
        return None
    counts = df["bulk_pitcher_id"].value_counts()
    if counts.empty:
        return None
    top_pid, top_count = counts.index[0], counts.iloc[0]
    if top_count / len(df) >= BULK_RELIEVER_MAJORITY:
        return int(top_pid)
    return None


def get_pitcher_info(pitcher_id: int, force_refresh: bool = False) -> dict:
    """{"name":.., "hand": "L"/"R"} for the drill-down page header. Falls back to
    {"name": None, "hand": "R"} if the lookup fails."""
    def fetch():
        resp = requests.get(f"{MLB_STATS_API}/people/{pitcher_id}", timeout=10)
        resp.raise_for_status()
        people = resp.json().get("people", [])
        if not people:
            return pd.DataFrame([{"name": None, "hand": "R"}])
        return pd.DataFrame([{
            "name": people[0].get("fullName"),
            "hand": people[0].get("pitchHand", {}).get("code", "R"),
        }])
    df = _load_or_fetch(f"pitcher_info_{pitcher_id}", fetch, force_refresh, max_age_hours=24 * 90)
    if df is None or df.empty:
        return {"name": None, "hand": "R"}
    return df.iloc[0].to_dict()


# Standard (non-year-specific) FanGraphs wOBA linear weights. These drift
# slightly season to season; fixed constants are a reasonable prior here,
# same spirit as the static PARK_FACTORS table below.
_WOBA_WEIGHTS = {"uBB": 0.690, "HBP": 0.722, "1B": 0.888, "2B": 1.271, "3B": 1.616, "HR": 2.101}


def get_team_batting_splits(season: int, force_refresh: bool = False) -> pd.DataFrame:
    """
    Team-level batting stats (used for opponent quality). FanGraphs'
    team-level wOBA isn't available from Baseball-Reference, so it's
    computed from raw team-summed counting stats via the standard wOBA
    formula instead. Also includes team strikeout rate (K%, SO/PA) —
    used as the opponent-quality signal for strikeout-prop predictions —
    and ISO (isolated power, SLG - AVG via extra-base-hit weighting), a
    genuinely different signal from wOBA: wOBA blends power in with
    on-base ability and contact quality generally, so a lineup can have
    an average wOBA while still being unusually home-run-heavy (or the
    reverse — high-average, low-power) in a way wOBA alone doesn't
    surface. Same raw counting stats already being pulled for wOBA, no
    extra fetch.
    """
    def fetch():
        df = batting_stats_bref(season)
        if df.empty:
            return df
        df = df.copy()
        lev = df["Lev"] if "Lev" in df.columns else pd.Series([""] * len(df), index=df.index)
        df["Team"] = [_bref_team_abbr(tm, l) for tm, l in zip(df["Tm"], lev)]
        df = df.dropna(subset=["Team"])

        for col in ["AB", "H", "2B", "3B", "HR", "BB", "IBB", "HBP", "SF", "SO", "PA"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        agg = df.groupby("Team")[["AB", "H", "2B", "3B", "HR", "BB", "IBB", "HBP", "SF", "SO", "PA"]].sum().reset_index()
        singles = agg["H"] - agg["2B"] - agg["3B"] - agg["HR"]
        ubb = agg["BB"] - agg["IBB"]
        numerator = (
            _WOBA_WEIGHTS["uBB"] * ubb + _WOBA_WEIGHTS["HBP"] * agg["HBP"] +
            _WOBA_WEIGHTS["1B"] * singles + _WOBA_WEIGHTS["2B"] * agg["2B"] +
            _WOBA_WEIGHTS["3B"] * agg["3B"] + _WOBA_WEIGHTS["HR"] * agg["HR"]
        )
        denominator = agg["AB"] + agg["BB"] - agg["IBB"] + agg["SF"] + agg["HBP"]
        agg["wOBA"] = numerator / denominator.replace(0, np.nan)
        agg["K_pct"] = agg["SO"] / agg["PA"].replace(0, np.nan) * 100
        agg["ISO"] = (agg["2B"] + 2 * agg["3B"] + 3 * agg["HR"]) / agg["AB"].replace(0, np.nan)
        # Plain batting average (H/AB) — not used as a model feature (wOBA is the better signal,
        # since it weights extra-base hits and walks properly), but a literal .270-style number
        # is what people actually mean by "team batting average" on a display, distinct from wOBA.
        agg["AVG"] = agg["H"] / agg["AB"].replace(0, np.nan)
        return agg[["Team", "wOBA", "K_pct", "ISO", "AVG"]]
    return _load_or_fetch(f"bref_team_batting_{season}", fetch, force_refresh, max_age_hours=24)


def get_player_batting_stats(season: int, force_refresh: bool = False) -> pd.DataFrame:
    """
    Same wOBA formula as get_team_batting_splits, but kept at the
    individual-player level (indexed by "mlbID", matching the MLB Stats
    API player ids used throughout the app) instead of aggregated to
    team — needed to weight an actual confirmed lineup by the real
    hitters in it rather than a team-wide average. Also carries each
    batter's own K% (SO/PA) for the same reason on the strikeout-prop
    side: a lineup's real K rate is whoever's actually starting tonight,
    not the team's whole-roster season average (bench bats, platoon
    personnel, etc. skew that).
    """
    def fetch():
        df = batting_stats_bref(season)
        if df.empty:
            return df
        df = df.copy()
        df["mlbID"] = pd.to_numeric(df["mlbID"], errors="coerce")
        df = df.dropna(subset=["mlbID"])
        df["mlbID"] = df["mlbID"].astype(int)
        for col in ["AB", "H", "2B", "3B", "HR", "BB", "IBB", "HBP", "SF", "SO", "PA"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        singles = df["H"] - df["2B"] - df["3B"] - df["HR"]
        ubb = df["BB"] - df["IBB"]
        numerator = (
            _WOBA_WEIGHTS["uBB"] * ubb + _WOBA_WEIGHTS["HBP"] * df["HBP"] +
            _WOBA_WEIGHTS["1B"] * singles + _WOBA_WEIGHTS["2B"] * df["2B"] +
            _WOBA_WEIGHTS["3B"] * df["3B"] + _WOBA_WEIGHTS["HR"] * df["HR"]
        )
        denominator = df["AB"] + df["BB"] - df["IBB"] + df["SF"] + df["HBP"]
        df["player_wOBA"] = numerator / denominator.replace(0, np.nan)
        df["player_k_pct"] = df["SO"] / df["PA"].replace(0, np.nan) * 100
        df["player_AVG"] = df["H"] / df["AB"].replace(0, np.nan)
        return df[["mlbID", "Name", "player_wOBA", "player_k_pct", "player_AVG", "PA"]]
    return _load_or_fetch(f"bref_player_batting_{season}", fetch, force_refresh, max_age_hours=24)


def get_batter_hand(batter_id: int, force_refresh: bool = False) -> str:
    """'L', 'R', or 'S' (switch) — batSide from MLB Stats API. Falls back to
    'R' (the more common case) if unavailable."""
    def fetch():
        resp = requests.get(f"{MLB_STATS_API}/people/{batter_id}", timeout=10)
        resp.raise_for_status()
        people = resp.json().get("people", [])
        hand = people[0].get("batSide", {}).get("code", "R") if people else "R"
        return pd.DataFrame([{"hand": hand}])
    df = _load_or_fetch(f"batter_hand_{batter_id}", fetch, force_refresh, max_age_hours=24 * 90)
    if df is None or df.empty:
        return "R"
    return df.iloc[0]["hand"]


def get_player_batting_vs_hand(batter_id: int, season: int, hand: str, force_refresh: bool = False) -> dict:
    """
    One batter's own AVG/wOBA specifically against left-handed (hand='L')
    or right-handed (hand='R') pitching this season — the real platoon
    signal for a lineup breakdown: a lefty masher can be well below his
    overall average against same-side pitching, or the reverse, and the
    team-wide vs-hand split (get_team_batting_vs_hand) averages that away
    across a whole roster including bench bats. Same MLB Stats API
    sitCodes mechanism as the team-level version, just at the person level.
    Returns {"avg": nan, "woba": nan, "pa": 0} if the batter has no
    recorded plate appearances against that hand yet.
    """
    sit_code = "vl" if hand == "L" else "vr"

    def fetch():
        try:
            # Note: "stats=season" silently IGNORES sitCodes on the person-level endpoint (it just
            # returns full-season totals with no error) — confirmed directly: querying vl vs vr both
            # came back with Aaron Judge's full 261 PA, not a split. "statSplits" is the stats type
            # that actually respects sitCodes at the player level (team-level splits, by contrast,
            # DO work with stats=season — see get_team_batting_vs_hand above, a different endpoint).
            resp = requests.get(f"{MLB_STATS_API}/people/{batter_id}/stats", params={
                "stats": "statSplits", "group": "hitting", "season": season, "sitCodes": sit_code,
            }, timeout=15)
            resp.raise_for_status()
            stats_blocks = resp.json().get("stats", [])
            splits = stats_blocks[0].get("splits", []) if stats_blocks else []
            if not splits:
                return pd.DataFrame([{"avg": np.nan, "woba": np.nan, "pa": 0}])
            stat = splits[0].get("stat", {})
            ab = stat.get("atBats", 0)
            h = stat.get("hits", 0)
            doubles = stat.get("doubles", 0)
            triples = stat.get("triples", 0)
            hr = stat.get("homeRuns", 0)
            bb = stat.get("baseOnBalls", 0)
            ibb = stat.get("intentionalWalks", 0)
            hbp = stat.get("hitByPitch", 0)
            sf = stat.get("sacFlies", 0)
            pa = stat.get("plateAppearances", 0)
            singles = h - doubles - triples - hr
            ubb = bb - ibb
            numerator = (
                _WOBA_WEIGHTS["uBB"] * ubb + _WOBA_WEIGHTS["HBP"] * hbp +
                _WOBA_WEIGHTS["1B"] * singles + _WOBA_WEIGHTS["2B"] * doubles +
                _WOBA_WEIGHTS["3B"] * triples + _WOBA_WEIGHTS["HR"] * hr
            )
            denominator = ab + bb - ibb + sf + hbp
            woba = numerator / denominator if denominator > 0 else np.nan
            avg = h / ab if ab > 0 else np.nan
            return pd.DataFrame([{"avg": avg, "woba": woba, "pa": pa}])
        except requests.exceptions.RequestException:
            return pd.DataFrame([{"avg": np.nan, "woba": np.nan, "pa": 0}])

    df = _load_or_fetch(f"batter_{sit_code}_{batter_id}_{season}", fetch, force_refresh, max_age_hours=24)
    if df is None or df.empty:
        return {"avg": np.nan, "woba": np.nan, "pa": 0}
    row = df.iloc[0]
    return {"avg": row["avg"], "woba": row["woba"], "pa": int(row["pa"])}


def get_confirmed_lineup(game_pk: int, force_refresh: bool = False) -> dict:
    """
    {"home": [batter_id, ...], "away": [batter_id, ...]} — the actual
    posted starting lineup for a game, in MLB Stats API player ids.
    Empty lists if not announced yet (lineups typically post ~1-3 hours
    before first pitch) — callers should treat that as "fall back to a
    team-wide average," not an error. Short cache TTL since this flips
    from empty to populated during the day.
    """
    def fetch():
        resp = requests.get(f"{MLB_STATS_API}/game/{game_pk}/boxscore", timeout=15)
        resp.raise_for_status()
        box = resp.json()
        home_order = box.get("teams", {}).get("home", {}).get("battingOrder", []) or []
        away_order = box.get("teams", {}).get("away", {}).get("battingOrder", []) or []
        return pd.DataFrame([{"home": home_order, "away": away_order}])
    df = _load_or_fetch(f"lineup_{game_pk}", fetch, force_refresh, max_age_hours=1)
    if df is None or df.empty:
        return {"home": [], "away": []}
    row = df.iloc[0]
    return {"home": list(row["home"]), "away": list(row["away"])}


def _get_mlb_team_ids(force_refresh: bool = False) -> dict:
    """{team_abbr: numeric MLB Stats API team id} for all 30 teams — needed because the
    per-team stats-splits endpoint takes a numeric id, not an abbreviation."""
    def fetch():
        resp = requests.get(f"{MLB_STATS_API}/teams", params={"sportId": 1}, timeout=15)
        resp.raise_for_status()
        teams = resp.json().get("teams", [])
        return pd.DataFrame([{"Team": t["abbreviation"], "team_id": t["id"]} for t in teams])
    df = _load_or_fetch("mlb_team_ids", fetch, force_refresh, max_age_hours=24 * 30)
    if df is None or df.empty:
        return {}
    return dict(zip(df["Team"], df["team_id"]))


def get_team_batting_vs_hand(season: int, hand: str, force_refresh: bool = False) -> pd.DataFrame:
    """
    Team wOBA (and K%) specifically against left-handed (hand='L') or
    right-handed (hand='R') pitching, via MLB Stats API sitCodes splits
    (vl/vr). This is the platoon signal proper: the plain season-long wOBA/
    K% from get_team_batting_splits treats a lineup the same regardless of
    who's on the mound, but some lineups (and some pitchers) have real,
    sizable same-handed-vs-opposite-handed splits — this captures the team
    side of that matchup specifically against tonight's starter's throwing
    hand. K% here uses the same raw response as wOBA (strikeOuts /
    plateAppearances) — no extra API call, feeds the strikeout model's
    opp_k_pct_vs_hand the same way opp_platoon_woba_diff already uses the
    wOBA column for the win-prob model.
    """
    sit_code = "vl" if hand == "L" else "vr"

    def fetch():
        team_ids = _get_mlb_team_ids()
        rows = []
        for abbr, tid in team_ids.items():
            try:
                resp = requests.get(f"{MLB_STATS_API}/teams/{tid}/stats", params={
                    "stats": "season", "group": "hitting", "season": season, "sitCodes": sit_code,
                }, timeout=15)
                resp.raise_for_status()
                stats_blocks = resp.json().get("stats", [])
                splits = stats_blocks[0].get("splits", []) if stats_blocks else []
                if not splits:
                    continue
                stat = splits[0].get("stat", {})
                ab = stat.get("atBats", 0)
                h = stat.get("hits", 0)
                doubles = stat.get("doubles", 0)
                triples = stat.get("triples", 0)
                hr = stat.get("homeRuns", 0)
                bb = stat.get("baseOnBalls", 0)
                ibb = stat.get("intentionalWalks", 0)
                hbp = stat.get("hitByPitch", 0)
                sf = stat.get("sacFlies", 0)
                so = stat.get("strikeOuts", 0)
                pa = stat.get("plateAppearances", 0)
                singles = h - doubles - triples - hr
                ubb = bb - ibb
                numerator = (
                    _WOBA_WEIGHTS["uBB"] * ubb + _WOBA_WEIGHTS["HBP"] * hbp +
                    _WOBA_WEIGHTS["1B"] * singles + _WOBA_WEIGHTS["2B"] * doubles +
                    _WOBA_WEIGHTS["3B"] * triples + _WOBA_WEIGHTS["HR"] * hr
                )
                denominator = ab + bb - ibb + sf + hbp
                woba = numerator / denominator if denominator > 0 else np.nan
                k_pct = (so / pa * 100) if pa > 0 else np.nan
                rows.append({"Team": abbr, "wOBA_vs_hand": woba, "K_pct_vs_hand": k_pct})
            except requests.exceptions.RequestException:
                continue
        return pd.DataFrame(rows)

    return _load_or_fetch(f"team_batting_{sit_code}_{season}", fetch, force_refresh, max_age_hours=24)


def get_pitcher_hand(pitcher_id: int, force_refresh: bool = False) -> str:
    """'L' or 'R' — which hand a pitcher throws with, from MLB Stats API. Falls back to
    'R' (the more common case) if unavailable, since callers need SOME hand to pick a split."""
    def fetch():
        resp = requests.get(f"{MLB_STATS_API}/people/{pitcher_id}", timeout=10)
        resp.raise_for_status()
        people = resp.json().get("people", [])
        hand = people[0].get("pitchHand", {}).get("code", "R") if people else "R"
        return pd.DataFrame([{"hand": hand}])
    df = _load_or_fetch(f"pitcher_hand_{pitcher_id}", fetch, force_refresh, max_age_hours=24 * 90)
    if df is None or df.empty:
        return "R"
    return df.iloc[0]["hand"]


def get_probable_pitchers(date: str = None) -> list[dict]:
    """
    Today's (or a given date's) probable starting pitchers + games,
    straight from the free MLB Stats API. No key required.

    date format: 'YYYY-MM-DD'. Defaults to today.
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    url = f"{MLB_STATS_API}/schedule"
    params = {
        "sportId": 1,
        "date": date,
        "hydrate": "probablePitcher,team,linescore",
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    games = []
    for date_block in data.get("dates", []):
        for game in date_block.get("games", []):
            teams = game.get("teams", {})
            away = teams.get("away", {})
            home = teams.get("home", {})

            games.append({
                "game_pk": game.get("gamePk"),
                "game_date": date,
                "game_time_utc": game.get("gameDate"),
                "venue": game.get("venue", {}).get("name"),
                "away_team": away.get("team", {}).get("name"),
                "away_team_abbr": away.get("team", {}).get("abbreviation"),
                "home_team": home.get("team", {}).get("name"),
                "home_team_abbr": home.get("team", {}).get("abbreviation"),
                "away_pitcher_id": (away.get("probablePitcher") or {}).get("id"),
                "away_pitcher_name": (away.get("probablePitcher") or {}).get("fullName"),
                "home_pitcher_id": (home.get("probablePitcher") or {}).get("id"),
                "home_pitcher_name": (home.get("probablePitcher") or {}).get("fullName"),
                "status": game.get("status", {}).get("detailedState"),
            })
    return games


IL_LOOKBACK_DAYS = 45  # how far back to look for an IL activation worth still flagging


def get_recent_il_activations(as_of_date: str = None, days_back: int = IL_LOOKBACK_DAYS,
                               force_refresh: bool = False) -> dict:
    """
    {player_id: activation_date_str} for every player activated off the
    injured list within the last `days_back` days of `as_of_date` — a
    real, confirmed signal for "this pitcher's recent numbers may not
    reflect where they are physically right now" distinct from (and more
    reliable than) inferring it purely from a gap between starts. A
    pitcher can make 2-3 starts since returning and no longer trip the
    generic long-layoff heuristic while still being in a genuine "building
    back up" window post-injury — caught directly from a case where a
    pitcher's rough current-season line (consistent with post-surgery
    recovery) looked identical to plain decline with no way to tell them
    apart.

    Source: MLB Stats API's own transactions log (free, no key) — each
    entry's plain-English description says exactly what happened
    ("activated ... from the 15-day injured list"), so this is a
    straightforward text match, not an inference.

    If a player has multiple activations in the window, the most recent
    one wins (that's the one relevant to "how are they doing since
    returning").
    """
    as_of = datetime.strptime(as_of_date, "%Y-%m-%d") if as_of_date else datetime.now()
    start = (as_of - timedelta(days=days_back)).strftime("%Y-%m-%d")
    end = as_of.strftime("%Y-%m-%d")

    def fetch():
        try:
            resp = requests.get(f"{MLB_STATS_API}/transactions", params={
                "startDate": start, "endDate": end, "sportId": 1,
            }, timeout=15)
            resp.raise_for_status()
        except requests.exceptions.RequestException:
            return pd.DataFrame()
        txns = resp.json().get("transactions", [])
        rows = []
        for t in txns:
            desc = (t.get("description") or "").lower()
            if "activated" not in desc or "injured list" not in desc:
                continue
            person = t.get("person") or {}
            pid = person.get("id")
            date = t.get("date")
            if pid is None or not date:
                continue
            rows.append({"player_id": pid, "date": date})
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        return df.sort_values("date").groupby("player_id").tail(1).reset_index(drop=True)

    # Short TTL: this window slides daily, and today's date needs to be part of
    # the cache key so a stale multi-day-old pull doesn't miss a fresh activation.
    df = _load_or_fetch(f"il_activations_{start}_{end}", fetch, force_refresh, max_age_hours=6)
    if df is None or df.empty:
        return {}
    return dict(zip(df["player_id"], df["date"]))


IL_RETURN_WINDOW_DAYS = 30  # inside this many days since activation, "recent form" may still be a return trajectory, not settled current form


def days_since_il_return(pitcher_id: int, game_date: str, il_activations: dict, window_days: int = IL_RETURN_WINDOW_DAYS):
    """Days since this pitcher was activated off the IL, if that happened within
    `window_days` of game_date — else None. A confirmed activation is a stronger,
    more specific signal than inferring "something's off" purely from a gap
    between starts — a pitcher can already be 2-3 starts into their return (no
    longer tripping the generic long-layoff heuristic) while still genuinely
    trending, not yet a clean read on where they've settled. Shared between live
    serving (main.py) and training data construction (build_training_data.py) so
    both compute this identically — see features._il_return_weight for how it
    actually discounts the recent-form features, not just a display warning."""
    activation_date = il_activations.get(pitcher_id)
    if not activation_date:
        return None
    days = (datetime.strptime(game_date, "%Y-%m-%d") - datetime.strptime(activation_date, "%Y-%m-%d")).days
    return days if 0 <= days <= window_days else None


def get_team_bullpen_stats(season: int, force_refresh: bool = False) -> pd.DataFrame:
    """
    Approximates bullpen quality per team by pulling season pitching
    stats and filtering to relievers (IP/G < 2.5), then aggregating.
    """
    def fetch():
        df = get_season_pitching_stats(season, force_refresh)
        if df.empty or "IP_float" not in df.columns or "G" not in df.columns:
            return pd.DataFrame()
        # IP_float > 0 excludes token/0-inning appearances (e.g. a position player mop-up
        # outing) — a single 0-IP row with NaN FIP poisons np.average's whole weighted
        # result below (0 * NaN = NaN in IEEE754, not 0), silently nulling a team's entire
        # bullpen_fip_diff feature. Caught via the data-completeness check flagging CWS.
        relievers = df[(df["G"] > 0) & (df["IP_float"] / df["G"].replace(0, np.nan) < 2.5) & df["Team"].notna() & (df["IP_float"] > 0)]
        if relievers.empty:
            return pd.DataFrame()
        agg = relievers.groupby("Team").apply(
            lambda g: pd.Series({
                "bullpen_ip": g["IP_float"].sum(),
                "bullpen_era": np.average(g["ERA"], weights=g["IP_float"]) if g["IP_float"].sum() > 0 else np.nan,
                "bullpen_fip": np.average(g["FIP"], weights=g["IP_float"]) if g["IP_float"].sum() > 0 else np.nan,
                "bullpen_k9": np.average(g["K9"], weights=g["IP_float"]) if g["IP_float"].sum() > 0 else np.nan,
            })
        ).reset_index()
        return agg
    return _load_or_fetch(f"bullpen_{season}", fetch, force_refresh, max_age_hours=24)


HIGH_LEVERAGE_ARMS_PER_TEAM = 3  # closer + primary setup men — the relievers who actually pitch the close, late innings


def get_team_high_leverage_bullpen_stats(season: int, force_refresh: bool = False) -> pd.DataFrame:
    """
    Same reliever pool as get_team_bullpen_stats, but instead of blending
    every reliever a team has used (mop-up arms included), ranks each
    team's relievers by saves-then-innings and keeps only the top
    HIGH_LEVERAGE_ARMS_PER_TEAM — a proxy for "the arms who actually
    pitch the 7th-9th of a close game," since that's what matters late in
    a tight one, not how deep or shallow the roster's 8th man is. Saves
    is an imperfect proxy for who a manager trusts in high leverage (no
    real leverage-index data available here), but it reliably identifies
    the closer, and innings-pitched among the rest catches the primary
    setup arms even when they have zero saves themselves.
    """
    def fetch():
        df = get_season_pitching_stats(season, force_refresh)
        if df.empty or "IP_float" not in df.columns or "G" not in df.columns:
            return pd.DataFrame()
        # Same IP_float > 0 guard as get_team_bullpen_stats above — a 0-IP token
        # appearance can still land in a team's top-3-by-SV/IP if that team has
        # fewer than 3 real relievers, poisoning the weighted FIP average.
        relievers = df[(df["G"] > 0) & (df["IP_float"] / df["G"].replace(0, np.nan) < 2.5) & df["Team"].notna() & (df["IP_float"] > 0)].copy()
        if relievers.empty:
            return pd.DataFrame()
        relievers["SV"] = relievers["SV"].fillna(0)
        top = (
            relievers.sort_values(["Team", "SV", "IP_float"], ascending=[True, False, False])
            .groupby("Team").head(HIGH_LEVERAGE_ARMS_PER_TEAM)
        )
        agg = top.groupby("Team").apply(
            lambda g: pd.Series({
                "high_leverage_ip": g["IP_float"].sum(),
                "high_leverage_fip": np.average(g["FIP"], weights=g["IP_float"]) if g["IP_float"].sum() > 0 else np.nan,
            })
        ).reset_index()
        return agg
    return _load_or_fetch(f"bullpen_high_leverage_{season}", fetch, force_refresh, max_age_hours=24)


def get_team_defense_oaa(season: int, force_refresh: bool = False) -> pd.DataFrame:
    """
    Team-wide Outs Above Average (OAA) — Baseball Savant's Statcast catch-probability defensive
    metric (every batted ball's out probability given hang time/distance/direction, summed across
    every fielder on the roster), pulled directly from Savant's team fielding leaderboard.
    Replaces the previous defense_babip_diff proxy (team BABIP allowed): BABIP conflates fielding
    quality with the specific staff's own contact-quality-allowed (a groundball-heavy staff
    depresses BABIP regardless of the defense behind it), where OAA is purpose-built to isolate
    fielding skill from pitching. Indexed by "Team" (abbreviation, via the same numeric team_id
    join _get_mlb_team_ids uses elsewhere) with a single "team_oaa" column — higher is better D.

    Same season-snapshot caveat as get_batted_ball_profile/get_batter_percentile_ranks: Savant's
    leaderboard has no as-of-date filter, only a season total, so callers needing a walk-forward-
    safe (no-leakage) signal for training should pass season - 1 the same way those two do — see
    build_training_data.py. Live serving passes the current season since there's no leakage risk
    for "today."
    """
    def fetch():
        df = statcast_outs_above_average(season, "all", min_att="q", view="Fielding_Team")
        if df.empty or "team_id" not in df.columns or "outs_above_average" not in df.columns:
            return pd.DataFrame()
        id_to_abbr = {v: k for k, v in _get_mlb_team_ids(force_refresh).items()}
        out = df[["team_id", "outs_above_average"]].copy()
        out["Team"] = out["team_id"].map(id_to_abbr)
        out = out.dropna(subset=["Team"])
        return out[["Team", "outs_above_average"]].rename(columns={"outs_above_average": "team_oaa"})
    return _load_or_fetch(f"team_defense_oaa_{season}", fetch, force_refresh, max_age_hours=24)


def get_team_recent_bullpen_usage(team_abbr: str, lookback_days: int = 3, force_refresh: bool = False) -> float:
    """
    Total bullpen innings (team IP minus that game's starter's own IP) a
    team has thrown over its last `lookback_days` calendar days — a live
    fatigue signal, distinct from get_team_bullpen_stats' season-long
    quality average. A pen that just threw extra innings or covered a
    bullpen game is worse tonight than its season ERA/FIP suggests,
    regardless of how good it normally is. Short cache TTL (this changes
    daily, unlike the season-long stats above).
    """
    def fetch():
        team_ids = _get_mlb_team_ids()
        team_id = team_ids.get(team_abbr)
        if not team_id:
            return pd.DataFrame([{"bullpen_ip": 0.0}])

        end = datetime.now()
        start = end - timedelta(days=lookback_days)
        resp = requests.get(f"{MLB_STATS_API}/schedule", params={
            "sportId": 1, "teamId": team_id,
            "startDate": start.strftime("%Y-%m-%d"), "endDate": (end - timedelta(days=1)).strftime("%Y-%m-%d"),
        }, timeout=15)
        resp.raise_for_status()
        game_pks = [
            g["gamePk"] for d in resp.json().get("dates", []) for g in d.get("games", [])
            if g.get("status", {}).get("detailedState") == "Final"
        ]

        total_bullpen_ip = 0.0
        for pk in game_pks:
            try:
                box = requests.get(f"{MLB_STATS_API}/game/{pk}/boxscore", timeout=15).json()
            except requests.exceptions.RequestException:
                continue
            for side in ("home", "away"):
                team_info = box.get("teams", {}).get(side, {})
                if team_info.get("team", {}).get("abbreviation") != team_abbr:
                    continue
                team_ip = _parse_ip(team_info.get("teamStats", {}).get("pitching", {}).get("inningsPitched", 0))
                pitchers = team_info.get("pitchers", [])
                starter_ip = 0.0
                if pitchers:
                    starter_stats = team_info.get("players", {}).get(f"ID{pitchers[0]}", {}).get("stats", {}).get("pitching", {})
                    starter_ip = _parse_ip(starter_stats.get("inningsPitched", 0))
                total_bullpen_ip += max(0.0, team_ip - starter_ip)
        return pd.DataFrame([{"bullpen_ip": total_bullpen_ip}])

    df = _load_or_fetch(f"bullpen_fatigue_{team_abbr}_{lookback_days}d", fetch, force_refresh, max_age_hours=6)
    if df is None or df.empty:
        return 0.0
    return float(df.iloc[0]["bullpen_ip"])


RECENT_TEAM_BATTING_GAMES = 7  # within the user-requested 5-10 game window
RECENT_TEAM_BATTING_GAMES_30D = 26  # ~30 calendar days at MLB's typical near-daily game pace —
# a genuinely different window than the 7-game one: catches a month-long slump/hot streak a
# single bad or good week can't distinguish from noise, without waiting a full season to show up
# in the season-long wOBA. Kept as a game count (not literal calendar days) so training's
# walk-forward history slice (build_training_data._recent_team_avg_from_history) stays exactly
# consistent with live serving, same reasoning as the existing 7-game window.


def get_team_recent_batting_form(team_abbr: str, n_games: int = RECENT_TEAM_BATTING_GAMES,
                                  before_date: str = None, force_refresh: bool = False) -> dict:
    """
    A team's own batting average over its last `n_games` completed games —
    distinct from get_team_batting_splits' season-long average, this
    catches a lineup that's genuinely hot or cold RIGHT NOW (a full-season
    wOBA says nothing about a team that's been shut down for a week
    straight, whatever the underlying reason — cold streak, missing bats,
    tough recent pitching). before_date lets training pull this walk-
    forward (only games strictly before the game being featurized); live
    serving passes None, which just means "as of right now."
    """
    def fetch():
        team_ids = _get_mlb_team_ids()
        team_id = team_ids.get(team_abbr)
        if not team_id:
            return pd.DataFrame([{"h": 0, "ab": 0, "games": 0}])

        end = datetime.strptime(before_date, "%Y-%m-%d") if before_date else datetime.now()
        # n_games at ~1/day plus a healthy buffer for off-days/doubleheaders
        start = end - timedelta(days=n_games * 3 + 5)
        resp = requests.get(f"{MLB_STATS_API}/schedule", params={
            "sportId": 1, "teamId": team_id,
            "startDate": start.strftime("%Y-%m-%d"), "endDate": (end - timedelta(days=1)).strftime("%Y-%m-%d"),
        }, timeout=15)
        resp.raise_for_status()
        game_pks = [
            g["gamePk"] for d in resp.json().get("dates", []) for g in d.get("games", [])
            if g.get("status", {}).get("detailedState") == "Final"
        ][-n_games:]

        total_h = total_ab = 0
        games_counted = 0
        for pk in game_pks:
            try:
                box = requests.get(f"{MLB_STATS_API}/game/{pk}/boxscore", timeout=15).json()
            except requests.exceptions.RequestException:
                continue
            for side in ("home", "away"):
                team_info = box.get("teams", {}).get(side, {})
                if team_info.get("team", {}).get("abbreviation") != team_abbr:
                    continue
                batting = team_info.get("teamStats", {}).get("batting", {})
                total_h += batting.get("hits", 0)
                total_ab += batting.get("atBats", 0)
                games_counted += 1
        return pd.DataFrame([{"h": total_h, "ab": total_ab, "games": games_counted}])

    cache_key = f"recent_batting_{team_abbr}_{n_games}g" + (f"_{before_date}" if before_date else "")
    df = _load_or_fetch(cache_key, fetch, force_refresh, max_age_hours=6)
    if df is None or df.empty:
        return {"avg": np.nan, "games": 0}
    row = df.iloc[0]
    ab = row["ab"]
    return {"avg": (row["h"] / ab) if ab > 0 else np.nan, "games": int(row["games"])}


PREDICTED_LINEUP_GAMES = 5  # how many recent games to sample when guessing tonight's lineup


def get_team_recent_lineups(team_abbr: str, n_games: int = PREDICTED_LINEUP_GAMES,
                             before_date: str = None, force_refresh: bool = False) -> list[dict]:
    """
    The team's actual starting batting order (from the real boxscore) for
    each of its last `n_games` completed games — the raw material for
    predicting tonight's lineup before it's officially posted. before_date
    makes this walk-forward-safe for training/backfill use, same pattern
    as get_team_recent_batting_form.
    """
    def fetch():
        team_ids = _get_mlb_team_ids()
        team_id = team_ids.get(team_abbr)
        if not team_id:
            return pd.DataFrame()

        end = datetime.strptime(before_date, "%Y-%m-%d") if before_date else datetime.now()
        start = end - timedelta(days=n_games * 3 + 5)
        resp = requests.get(f"{MLB_STATS_API}/schedule", params={
            "sportId": 1, "teamId": team_id,
            "startDate": start.strftime("%Y-%m-%d"), "endDate": (end - timedelta(days=1)).strftime("%Y-%m-%d"),
        }, timeout=15)
        resp.raise_for_status()
        game_pks = [
            g["gamePk"] for d in resp.json().get("dates", []) for g in d.get("games", [])
            if g.get("status", {}).get("detailedState") == "Final"
        ][-n_games:]

        rows = []
        for pk in game_pks:
            try:
                box = requests.get(f"{MLB_STATS_API}/game/{pk}/boxscore", timeout=15).json()
            except requests.exceptions.RequestException:
                continue
            for side in ("home", "away"):
                team_info = box.get("teams", {}).get(side, {})
                if team_info.get("team", {}).get("abbreviation") != team_abbr:
                    continue
                order = team_info.get("battingOrder", []) or []
                if order:
                    rows.append({"game_pk": pk, "lineup": order})
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    cache_key = f"recent_lineups_{team_abbr}_{n_games}g" + (f"_{before_date}" if before_date else "")
    df = _load_or_fetch(cache_key, fetch, force_refresh, max_age_hours=6)
    if df is None or df.empty:
        return []
    return df.to_dict("records")


def predict_team_lineup(team_abbr: str, n_games: int = PREDICTED_LINEUP_GAMES,
                         before_date: str = None, force_refresh: bool = False) -> list[int]:
    """
    Best guess at tonight's starting lineup before the official one posts,
    built from who's actually started most consistently over the team's
    last `n_games` real games, ordered by their most common batting slot.
    A platoon bat who only starts against one throwing hand, or someone
    who was rested/hurt for a game or two, still clears the "started in
    at least half the sample" bar; a true one-off injury replacement
    doesn't. Returns fewer than 9 names if the recent sample doesn't
    support a full lineup (e.g. early season, lots of roster churn) —
    callers should treat this as a best-effort estimate, not a
    confirmation, and prefer the real posted lineup once it's out.
    """
    recent = get_team_recent_lineups(team_abbr, n_games, before_date, force_refresh)
    if not recent:
        return []
    appearances = {}
    slot_sum = {}
    for game in recent:
        for slot, bid in enumerate(game["lineup"], start=1):
            appearances[bid] = appearances.get(bid, 0) + 1
            slot_sum[bid] = slot_sum.get(bid, 0) + slot
    min_games = max(1, len(recent) // 2)
    candidates = [
        (bid, appearances[bid], slot_sum[bid] / appearances[bid])
        for bid in appearances if appearances[bid] >= min_games
    ]
    candidates.sort(key=lambda x: (-x[1], x[2]))  # most frequent starter first, ties by usual slot
    top9 = candidates[:9]
    top9.sort(key=lambda x: x[2])  # re-order by typical batting-order slot
    # int() cast: the "lineup" column round-trips through a DataFrame (see
    # get_team_recent_lineups), which can silently turn a list-of-plain-ints cell into
    # numpy.int64 elements — those aren't JSON-serializable by FastAPI's default encoder,
    # so a live /api/today request 500'd the first time this ran against real data.
    return [int(bid) for bid, _, _ in top9]


def get_park_factor(team_abbr: str) -> float:
    return PARK_FACTORS.get(team_abbr, 100) / 100.0


def full_data_refresh(season: int = None):
    """Convenience function: pulls everything needed for today's slate."""
    season = season or datetime.now().year
    print(f"Refreshing season pitching stats for {season}...")
    get_season_pitching_stats(season, force_refresh=True)
    print("Refreshing team batting splits...")
    get_team_batting_splits(season, force_refresh=True)
    print("Refreshing bullpen stats...")
    get_team_bullpen_stats(season, force_refresh=True)
    print("Pulling today's probable pitchers...")
    games = get_probable_pitchers()
    print(f"Found {len(games)} games today.")
    return games


if __name__ == "__main__":
    games = full_data_refresh()
    print(json.dumps(games, indent=2, default=str))
