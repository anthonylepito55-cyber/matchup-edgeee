"""
weather.py

Rain-risk check for a game: pulls a free, no-key hourly forecast (Open-
Meteo) for the venue's coordinates and looks at precipitation probability
across the game's likely window. This isn't a model feature — there's no
practical way to backtest "did rain shorten this start" against historical
weather with what's available here — it's a warning, same spirit as the
existing layoff/small-sample pitcher warnings: something a human should
weigh before trusting a strikeout prediction at face value, since a rain-
shortened outing means fewer innings and fewer strikeouts regardless of
how good the matchup looks on paper.

Keyed by venue NAME (not team), since that's what the MLB Stats API
schedule actually returns for a given game — this naturally handles a team
playing a home series somewhere other than its usual park (renovations,
international series, an out-of-market temporary home) without needing to
track that separately.
"""

import math
import pandas as pd
import requests
from datetime import datetime, timedelta

from data_collection import _load_or_fetch, _get_mlb_team_ids, MLB_STATS_API

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"  # same provider, actual observed weather for past dates

GAME_DURATION_HOURS = 3.5  # a typical 9-inning game; generous enough to catch a rain delay mid-game

RAIN_RISK_THRESHOLD = 40  # % precipitation probability at which it's worth flagging

FORECAST_CACHE_HOURS = 1  # Open-Meteo itself only updates hourly; no reason to hit it more often than that

# {venue_name: {"lat":, "lon":, "dome": bool}}. dome=True means fully enclosed,
# non-retractable — weather genuinely cannot affect the game, skip the check
# entirely. Retractable-roof parks are marked dome=False on purpose: whether
# the roof is open isn't knowable in advance, and a missed warning is worse
# than an occasional unnecessary one.
VENUE_INFO = {
    "Angel Stadium": {"lat": 33.8003, "lon": -117.8827, "dome": False},
    "Chase Field": {"lat": 33.4455, "lon": -112.0667, "dome": False},
    "Truist Park": {"lat": 33.8907, "lon": -84.4677, "dome": False},
    "Oriole Park at Camden Yards": {"lat": 39.2839, "lon": -76.6218, "dome": False},
    "Fenway Park": {"lat": 42.3467, "lon": -71.0972, "dome": False},
    "Wrigley Field": {"lat": 41.9484, "lon": -87.6553, "dome": False},
    "Guaranteed Rate Field": {"lat": 41.8300, "lon": -87.6338, "dome": False},
    "Great American Ball Park": {"lat": 39.0975, "lon": -84.5071, "dome": False},
    "Progressive Field": {"lat": 41.4962, "lon": -81.6852, "dome": False},
    "Coors Field": {"lat": 39.7559, "lon": -104.9942, "dome": False},
    "Comerica Park": {"lat": 42.3390, "lon": -83.0485, "dome": False},
    "Minute Maid Park": {"lat": 29.7573, "lon": -95.3555, "dome": False},
    "Daikin Park": {"lat": 29.7573, "lon": -95.3555, "dome": False},
    "Kauffman Stadium": {"lat": 39.0517, "lon": -94.4803, "dome": False},
    "Dodger Stadium": {"lat": 34.0739, "lon": -118.2400, "dome": False},
    "loanDepot park": {"lat": 25.7781, "lon": -80.2196, "dome": False},
    "American Family Field": {"lat": 43.0280, "lon": -87.9712, "dome": False},
    "Target Field": {"lat": 44.9817, "lon": -93.2776, "dome": False},
    "Citi Field": {"lat": 40.7571, "lon": -73.8458, "dome": False},
    "Yankee Stadium": {"lat": 40.8296, "lon": -73.9262, "dome": False},
    "Oakland Coliseum": {"lat": 37.7516, "lon": -122.2005, "dome": False},
    "Sutter Health Park": {"lat": 38.5802, "lon": -121.5137, "dome": False},
    "Citizens Bank Park": {"lat": 39.9061, "lon": -75.1665, "dome": False},
    "PNC Park": {"lat": 40.4469, "lon": -80.0057, "dome": False},
    "Petco Park": {"lat": 32.7073, "lon": -117.1566, "dome": False},
    "Oracle Park": {"lat": 37.7786, "lon": -122.3893, "dome": False},
    "T-Mobile Park": {"lat": 47.5914, "lon": -122.3325, "dome": False},
    "Busch Stadium": {"lat": 38.6226, "lon": -90.1928, "dome": False},
    "Tropicana Field": {"lat": 27.7683, "lon": -82.6534, "dome": True},
    "George M. Steinbrenner Field": {"lat": 27.9803, "lon": -82.5322, "dome": False},
    "Globe Life Field": {"lat": 32.7473, "lon": -97.0842, "dome": False},
    "Rogers Centre": {"lat": 43.6414, "lon": -79.3894, "dome": False},
    "Nationals Park": {"lat": 38.8730, "lon": -77.0074, "dome": False},
}


def _lookup_venue(venue: str) -> dict | None:
    """
    Exact match first; ballparks get renamed for sponsorship reasons
    fairly often ("Guaranteed Rate Field" -> "Rate Field", "Dodger
    Stadium" -> "UNIQLO Field at Dodger Stadium"), so fall back to
    substring matching in both directions before giving up — a missed
    match silently drops the rain check for that game, which is worse
    than a slightly loose match here.
    """
    if venue in VENUE_INFO:
        return VENUE_INFO[venue]
    venue_lower = venue.lower()
    for name, info in VENUE_INFO.items():
        name_lower = name.lower()
        if name_lower in venue_lower or venue_lower in name_lower:
            return info
    return None


def _fetch_hourly_forecast(lat: float, lon: float) -> tuple[list, list]:
    """
    Raw hourly precipitation-probability forecast for one venue's
    coordinates, cached ~1 hour (Open-Meteo's own forecast doesn't update
    faster than that). This used to be called fresh on every /api/today
    request — up to 15 uncached HTTPS round-trips per page load, ~0.7s
    each, the single largest chunk of that endpoint's latency. Cached per
    venue rather than per game, since the window-filtering below (which
    game hours to actually check) is cheap local computation on top of the
    same underlying forecast.
    """
    def fetch():
        resp = requests.get(OPEN_METEO_URL, params={
            "latitude": lat, "longitude": lon,
            "hourly": "precipitation_probability", "forecast_days": 3, "timezone": "UTC",
        }, timeout=10)
        resp.raise_for_status()
        hourly = resp.json().get("hourly", {})
        times, probs = hourly.get("time", []), hourly.get("precipitation_probability", [])
        if not times:
            return pd.DataFrame()
        return pd.DataFrame({"time": times, "precipitation_probability": probs})

    try:
        df = _load_or_fetch(f"weather_{lat}_{lon}", fetch, max_age_hours=FORECAST_CACHE_HOURS)
    except (requests.exceptions.RequestException, ValueError):
        return [], []
    if df is None or df.empty:
        return [], []
    return list(df["time"]), list(df["precipitation_probability"])


def get_rain_risk(venue: str, game_time_utc: str) -> dict | None:
    """
    Returns {"max_precip_prob": int, "venue": str} if there's meaningful
    rain risk during the game window at an outdoor venue, else None
    (unknown venue, indoor dome, forecast unavailable, or risk below
    RAIN_RISK_THRESHOLD). game_time_utc is the ISO8601 UTC string the MLB
    Stats API returns (e.g. "2026-07-10T22:40:00Z").
    """
    info = _lookup_venue(venue)
    if info is None or info["dome"] or not game_time_utc:
        return None

    try:
        start = datetime.strptime(game_time_utc, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    end = start + timedelta(hours=GAME_DURATION_HOURS)

    times, probs = _fetch_hourly_forecast(info["lat"], info["lon"])
    if not times:
        return None

    window_probs = [
        p for t, p in zip(times, probs)
        if start <= datetime.strptime(t, "%Y-%m-%dT%H:%M") <= end
    ]
    if not window_probs:
        return None

    max_prob = max(window_probs)
    if max_prob < RAIN_RISK_THRESHOLD:
        return None
    return {"max_precip_prob": max_prob, "venue": venue}


# --- Temperature / wind (model features, not just a warning) -------------
#
# Warmer air is less dense, so batted balls carry farther — a well-established,
# direction-agnostic physical effect (unlike wind, which only helps/hurts
# scoring depending on which way it's blowing relative to the park's
# orientation — verified orientation data for all 30 parks wasn't available
# from any source checked, so wind is included as a raw speed only, no
# in/out direction. The model can still pick up on "windy conditions in
# general" as a real, if weaker, signal without risking a systematically
# backwards effect from a wrong guessed orientation.
#
# Day-level max temp + mean wind speed (not hour-of-first-pitch) — the
# training pipeline doesn't currently track exact game times historically,
# and day-level is a simpler, still-meaningful proxy for "how hot/windy was
# game day" than adding a whole new time-tracking dependency for this.

# {team_abbr: venue_name} — reuses VENUE_INFO's lat/lon/dome by name, same
# abbreviations as data_collection.PARK_FACTORS. Historical training games
# use the team's own park (correct for the vast majority of games; a
# handful of neutral-site/international-series games will get a slightly
# wrong location, an acceptable trade-off for not needing per-game venue
# tracking in the training pipeline). TB and ATH point at Steinbrenner
# Field and Sutter Health Park respectively — their actual 2025+ home parks
# during the Tropicana Field rebuild and Oakland-to-Sacramento relocation.
TEAM_HOME_VENUE = {
    "COL": "Coors Field", "CIN": "Great American Ball Park", "TEX": "Globe Life Field",
    "PHI": "Citizens Bank Park", "BOS": "Fenway Park", "BAL": "Oriole Park at Camden Yards",
    "TOR": "Rogers Centre", "CHC": "Wrigley Field", "AZ": "Chase Field", "MIN": "Target Field",
    "HOU": "Daikin Park", "MIL": "American Family Field", "WSH": "Nationals Park",
    "ATL": "Truist Park", "LAA": "Angel Stadium", "CWS": "Guaranteed Rate Field",
    "STL": "Busch Stadium", "KC": "Kauffman Stadium", "TB": "George M. Steinbrenner Field",
    "NYY": "Yankee Stadium", "CLE": "Progressive Field", "SD": "Petco Park",
    "LAD": "Dodger Stadium", "SF": "Oracle Park", "SEA": "T-Mobile Park",
    "DET": "Comerica Park", "NYM": "Citi Field", "PIT": "PNC Park",
    "MIA": "loanDepot park", "ATH": "Sutter Health Park",
}

HISTORICAL_WEATHER_CACHE_HOURS = 24 * 365 * 5  # observed past weather never changes; cache effectively forever


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in miles — good enough for a travel-
    fatigue signal (actual flight-path distance is a bit longer, but the difference doesn't
    change which team traveled further)."""
    lat1_r, lon1_r, lat2_r, lon2_r = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2_r - lat1_r, lon2_r - lon1_r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    return 2 * 3958.8 * math.asin(math.sqrt(a))  # 3958.8 = Earth's radius in miles


def venue_distance_miles(venue_a: str, venue_b: str) -> float:
    """Distance between two named venues, or NaN if either is missing/unrecognized (e.g. a
    season-opener with no prior game to measure from) — see team_travel_miles for how this feeds
    the actual per-team travel-fatigue feature."""
    if not venue_a or not venue_b:
        return float("nan")
    info_a, info_b = _lookup_venue(venue_a), _lookup_venue(venue_b)
    if info_a is None or info_b is None:
        return float("nan")
    return haversine_miles(info_a["lat"], info_a["lon"], info_b["lat"], info_b["lon"])


def get_team_last_game_venue(team_abbr: str, before_date: str = None, force_refresh: bool = False) -> str | None:
    """The venue name of a team's most recent completed game before before_date (or today, for
    live serving) — None if no prior game is found (season opener, etc). Feeds team_travel_miles."""
    def fetch():
        team_ids = _get_mlb_team_ids()
        team_id = team_ids.get(team_abbr)
        if not team_id:
            return pd.DataFrame([{"venue": None}])
        end = datetime.strptime(before_date, "%Y-%m-%d") if before_date else datetime.now()
        start = end - timedelta(days=10)
        resp = requests.get(f"{MLB_STATS_API}/schedule", params={
            "sportId": 1, "teamId": team_id,
            "startDate": start.strftime("%Y-%m-%d"), "endDate": (end - timedelta(days=1)).strftime("%Y-%m-%d"),
        }, timeout=15)
        resp.raise_for_status()
        games = [
            g for d in resp.json().get("dates", []) for g in d.get("games", [])
            if g.get("status", {}).get("detailedState") == "Final"
        ]
        if not games:
            return pd.DataFrame([{"venue": None}])
        return pd.DataFrame([{"venue": games[-1].get("venue", {}).get("name")}])

    cache_key = f"team_last_venue_{team_abbr}" + (f"_{before_date}" if before_date else "")
    df = _load_or_fetch(cache_key, fetch, force_refresh, max_age_hours=6)
    return df.iloc[0]["venue"] if df is not None and not df.empty else None


def team_travel_miles(team_abbr: str, destination_venue: str, before_date: str = None,
                       force_refresh: bool = False) -> float:
    """
    Distance between a team's most recent game's venue and destination_venue (tonight's actual
    venue — the HOME team's park, for both sides, since the away team travels there too). A team
    that just flew cross-country is plausibly a bit more gassed than one that's been playing a
    homestand, independent of any pitcher's own rest days (which track that specific pitcher's
    turnaround, not the team's travel schedule). NaN for a season-opener or any team with no prior
    game found — the caller should treat that as "no signal," not zero distance.
    """
    last_venue = get_team_last_game_venue(team_abbr, before_date, force_refresh)
    if last_venue is None or destination_venue is None:
        return float("nan")
    return venue_distance_miles(last_venue, destination_venue)


def _fetch_daily_weather(lat: float, lon: float, date: str = None, historical: bool = False) -> pd.DataFrame:
    """Daily max temp (F) + mean wind speed (mph) for one venue — either the actual observed
    weather for one past date (historical=True, training) or the live 3-day forecast
    (historical=False, serving). Same free Open-Meteo provider as get_rain_risk, the daily-
    aggregate endpoint instead of hourly."""
    def fetch():
        if historical:
            params = {
                "latitude": lat, "longitude": lon, "start_date": date, "end_date": date,
                "daily": "temperature_2m_max,wind_speed_10m_mean",
                "temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "timezone": "UTC",
            }
            url = OPEN_METEO_ARCHIVE_URL
        else:
            params = {
                "latitude": lat, "longitude": lon,
                "daily": "temperature_2m_max,wind_speed_10m_mean",
                "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
                "forecast_days": 3, "timezone": "UTC",
            }
            url = OPEN_METEO_URL
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        daily = resp.json().get("daily", {})
        times = daily.get("time", [])
        if not times:
            return pd.DataFrame()
        return pd.DataFrame({
            "date": times,
            "temp_max_f": daily.get("temperature_2m_max", []),
            "wind_mean_mph": daily.get("wind_speed_10m_mean", []),
        })

    cache_key = f"weather_daily_{'hist' if historical else 'live'}_{lat}_{lon}_{date or 'forecast'}"
    max_age = HISTORICAL_WEATHER_CACHE_HOURS if historical else FORECAST_CACHE_HOURS
    try:
        df = _load_or_fetch(cache_key, fetch, max_age_hours=max_age)
    except (requests.exceptions.RequestException, ValueError):
        return pd.DataFrame()
    return df if df is not None else pd.DataFrame()


def get_game_weather_historical(team_abbr: str, game_date: str) -> dict | None:
    """{"temp_max_f":.., "wind_mean_mph":..} for a past game, keyed by the home team's own park —
    for training data. None for a dome (weather can't affect it), unmapped team, or unavailable data.
    Prefer get_team_weather_range + a local lookup when building a whole training set — this makes
    one archive API call per game, which is fine for a one-off check but far too slow (~1s each) over
    thousands of historical rows."""
    venue = TEAM_HOME_VENUE.get(team_abbr)
    info = VENUE_INFO.get(venue) if venue else None
    if info is None or info["dome"]:
        return None
    df = _fetch_daily_weather(info["lat"], info["lon"], date=game_date, historical=True)
    if df.empty:
        return None
    row = df.iloc[0]
    if pd.isna(row["temp_max_f"]) or pd.isna(row["wind_mean_mph"]):
        return None
    return {"temp_max_f": round(float(row["temp_max_f"]), 1), "wind_mean_mph": round(float(row["wind_mean_mph"]), 1)}


def get_team_weather_range(team_abbr: str, start_date: str, end_date: str) -> dict:
    """{date_str: {"temp_max_f":.., "wind_mean_mph":..}} for a team's home park across an entire
    date range — ONE archive API call instead of one per game, for building training data over
    many historical games at once. Empty dict for a dome or unmapped team."""
    venue = TEAM_HOME_VENUE.get(team_abbr)
    info = VENUE_INFO.get(venue) if venue else None
    if info is None or info["dome"]:
        return {}

    def fetch():
        resp = requests.get(OPEN_METEO_ARCHIVE_URL, params={
            "latitude": info["lat"], "longitude": info["lon"],
            "start_date": start_date, "end_date": end_date,
            "daily": "temperature_2m_max,wind_speed_10m_mean",
            "temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "timezone": "UTC",
        }, timeout=30)
        resp.raise_for_status()
        daily = resp.json().get("daily", {})
        times = daily.get("time", [])
        if not times:
            return pd.DataFrame()
        return pd.DataFrame({
            "date": times,
            "temp_max_f": daily.get("temperature_2m_max", []),
            "wind_mean_mph": daily.get("wind_speed_10m_mean", []),
        })

    cache_key = f"weather_daily_hist_range_{team_abbr}_{start_date}_{end_date}"
    try:
        df = _load_or_fetch(cache_key, fetch, max_age_hours=HISTORICAL_WEATHER_CACHE_HOURS)
    except (requests.exceptions.RequestException, ValueError):
        return {}
    if df is None or df.empty:
        return {}

    result = {}
    for _, row in df.iterrows():
        if pd.isna(row["temp_max_f"]) or pd.isna(row["wind_mean_mph"]):
            continue
        result[row["date"]] = {"temp_max_f": round(float(row["temp_max_f"]), 1), "wind_mean_mph": round(float(row["wind_mean_mph"]), 1)}
    return result


def get_game_weather_live(venue: str, game_date: str = None) -> dict | None:
    """Same shape as get_game_weather_historical, but the live forecast for today/upcoming days,
    keyed by the actual venue name from the live schedule (see module docstring on why venue name,
    not team, for live serving)."""
    info = _lookup_venue(venue)
    if info is None or info["dome"]:
        return None
    df = _fetch_daily_weather(info["lat"], info["lon"], historical=False)
    if df.empty:
        return None
    row = df[df["date"] == game_date].iloc[0] if game_date and (df["date"] == game_date).any() else df.iloc[0]
    if pd.isna(row["temp_max_f"]) or pd.isna(row["wind_mean_mph"]):
        return None
    return {"temp_max_f": round(float(row["temp_max_f"]), 1), "wind_mean_mph": round(float(row["wind_mean_mph"]), 1)}
