"""
tennis_data.py

Data ingestion for the tennis moneyline predictor — mirrors the shape of
data_collection.py for the MLB side, but with two very different sources:

  1. Historical match results (ATP + WTA, 2000/2007-present): a free,
     no-signup-required, CC0 Kaggle dataset ("dissfya/atp-tennis-...",
     "dissfya/wta-tennis-...") that's updated daily. Columns: Tournament,
     Date, Series (tier), Court, Surface, Round, Best of, both players,
     Winner, both rankings/points at match time, both players' odds, and
     final score. This is what tennis_features.py builds Elo/surface-form/
     opponent-quality off of, walk-forward.

     NOTE on scope: this dataset does NOT include per-match serve/return
     box-score stats (aces, double faults, first-serve%, hold%, break%) —
     that data is not available for free anywhere found during research
     for this feature; a paid API (e.g. Matchstat via RapidAPI, ~$10/mo)
     would be needed to add it. Everything buildable from rankings/results/
     surface/odds alone is covered here; serve/return stats are a known,
     explicitly out-of-scope gap for a future pass.

  2. Live schedule + odds: OpticOdds (already paid for, used by the MLB
     side too) — leagues "atp" and "wta" under sport "tennis".

Player-name matching between the two sources is a real practical problem:
the Kaggle dataset uses "Last F." (e.g. "Quinn E."), OpticOdds uses full
names (e.g. "Ethan Quinn"). See match_player_name().
"""

import io
import os
import re
import zipfile
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from data_collection import CACHE_DIR, _load_or_fetch, todays_date_et
from odds_fetcher import OPTICODDS_API_KEY, OPTICODDS_BASE_URL

KAGGLE_ATP_DATASET = "dissfya/atp-tennis-2000-2023daily-pull"
KAGGLE_WTA_DATASET = "dissfya/wta-tennis-2007-2023-daily-update"

TENNIS_LEAGUES = ["atp", "wta", "atp_challenger"]  # challengers added 2026-09-26 (user: "we're
# missing a ton") -- cards get TennisRatio context + SR-DOG/SOS flags; no model prediction there.

HISTORY_CACHE_MAX_AGE_HOURS = 20  # source dataset updates ~daily
FIXTURE_BATCH_SIZE = 5


def _download_kaggle_csv(dataset_ref: str) -> pd.DataFrame:
    """
    Downloads a public Kaggle dataset's zip via the same signed-GCS-URL
    redirect the Kaggle website itself uses — confirmed to work with zero
    authentication for public CC0 datasets (no API key, no account, no
    signup). Returns the first CSV found in the archive as a DataFrame.
    """
    resp = requests.get(
        f"https://www.kaggle.com/api/v1/datasets/download/{dataset_ref}",
        timeout=30, allow_redirects=True,
    )
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            return pd.DataFrame()
        with zf.open(csv_names[0]) as f:
            return pd.read_csv(f)


def _parse_match_history(df: pd.DataFrame) -> pd.DataFrame:
    """Normalizes raw Kaggle columns into consistent dtypes, sorted chronologically
    (ascending) so every downstream walk-forward computation can rely on row order."""
    if df.empty:
        return df
    df = df.copy()
    df = df.rename(columns={"Best of": "Best_of"})  # itertuples() can't expose a name with a space
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    for col in ["Rank_1", "Rank_2", "Pts_1", "Pts_2", "Odd_1", "Odd_2", "Best_of"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Date", "Player_1", "Player_2", "Winner"])
    df = df.sort_values("Date", kind="stable").reset_index(drop=True)
    if "Series" not in df.columns:
        df["Series"] = None  # WTA dataset has no tier column; ATP does
    return df


def get_atp_match_history(force_refresh: bool = False) -> pd.DataFrame:
    """Full ATP match history, 2000-present, chronologically sorted. See module docstring."""
    def fetch():
        return _parse_match_history(_download_kaggle_csv(KAGGLE_ATP_DATASET))
    return _load_or_fetch("tennis_atp_history", fetch, force_refresh, max_age_hours=HISTORY_CACHE_MAX_AGE_HOURS)


def get_wta_match_history(force_refresh: bool = False) -> pd.DataFrame:
    """Full WTA match history, 2007-present, chronologically sorted. See module docstring."""
    def fetch():
        return _parse_match_history(_download_kaggle_csv(KAGGLE_WTA_DATASET))
    return _load_or_fetch("tennis_wta_history", fetch, force_refresh, max_age_hours=HISTORY_CACHE_MAX_AGE_HOURS)


def build_tournament_metadata_lookup(history: pd.DataFrame) -> dict:
    """
    {tournament_name: {"surface":, "series":}} from each tournament's most
    recent appearance in the historical data — tournaments are played at
    the same venue on the same surface essentially every year (grass at
    Wimbledon, clay at Roland Garros, etc.), so this is a reliable proxy
    for "what surface is today's OpticOdds fixture on" when OpticOdds
    itself doesn't expose a surface field (confirmed via a live fixture
    pull — it doesn't). "series" (ATP only; WTA dataset has no tier column)
    is what determines best-of-5 live: only ATP Grand Slams are best-of-5,
    OpticOdds' live fixtures don't carry that either.
    """
    if history.empty:
        return {}
    latest = history.sort_values("Date").groupby("Tournament").tail(1)
    return {
        row.Tournament: {"surface": row.Surface, "series": getattr(row, "Series", None)}
        for row in latest.itertuples(index=False)
    }


_TOURNAMENT_STOPWORDS = {
    "open", "cup", "championships", "championship", "international", "masters",
    "classic", "trophy", "and", "of", "the", "atp", "wta", "presented", "by",
    "men's", "women's", "tennis", "tour", "final", "finals", "series", "500", "250", "1000",
}

# Tournaments whose live (OpticOdds, "City, Country") name shares literally no
# word with any historical name they've ever been listed under — no amount of
# token/prefix matching below can bridge these, confirmed by direct lookup.
# Keyed by a distinctive lowercase word from the live name.
_TOURNAMENT_ALIASES = {
    "newport": "Hall of Fame Championships",  # ATP's Newport, RI event — WTA doesn't currently have a Newport stop
}


def _tournament_tokens(name: str) -> set:
    words = re.findall(r"[a-zA-Z]+", name.lower())
    return {w for w in words if w not in _TOURNAMENT_STOPWORDS and len(w) > 3}


def lookup_tournament_metadata(tournament_name: str, metadata: dict) -> dict | None:
    """
    Exact match first, then significant-word overlap — sponsorship names and
    city/venue naming drift a lot year to year (confirmed live: OpticOdds
    calls the same event 'Gstaad, Switzerland' while the historical dataset
    has called it 'Gstaad Open', 'Suisse Open Gstaad', and 'Crédit Agricole
    Suisse Open Gstaad' across different years — none of which is a
    substring of any other), so matching on the shared distinctive word
    (the city/proper-noun) rather than requiring one full string to contain
    the other is what actually works here. Ties broken by most recent
    match among the overlapping candidates, same "most recent surface"
    reasoning as build_tournament_metadata_lookup itself.
    """
    if not tournament_name:
        return None
    if tournament_name in metadata:
        return metadata[tournament_name]

    live_tokens = _tournament_tokens(tournament_name)
    if not live_tokens:
        return None

    for alias_word, hist_name in _TOURNAMENT_ALIASES.items():
        if alias_word in live_tokens and hist_name in metadata:
            return metadata[hist_name]

    for name, meta in metadata.items():
        if live_tokens & _tournament_tokens(name):
            return meta

    # Second pass: 4-character-prefix match, catches adjectival-vs-noun country
    # forms the exact-token pass misses (live "Sweden" vs historical "Swedish"
    # share "swed", not the full word — a fixed 5-char slice misses this pair
    # since they diverge at character 5).
    live_prefixes = {t[:4] for t in live_tokens if len(t) >= 4}
    if live_prefixes:
        for name, meta in metadata.items():
            hist_prefixes = {t[:4] for t in _tournament_tokens(name) if len(t) >= 4}
            if live_prefixes & hist_prefixes:
                return meta
    return None


_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}


def _normalize_kaggle_name(name: str) -> str | None:
    """'Quinn E.' -> ('quinn', 'e'). Kaggle's own format is always 'Last F.'"""
    if not isinstance(name, str) or not name.strip():
        return None
    m = re.match(r"^(.+?)\s+([A-Za-z])\.?$", name.strip())
    if not m:
        return None
    last, initial = m.group(1).strip().lower(), m.group(2).lower()
    return f"{last}|{initial}"


def _normalize_live_name(name: str) -> str | None:
    """'Ethan Quinn' -> ('quinn', 'e') — same key shape as _normalize_kaggle_name
    so the two sources can be joined on last name + first initial. Handles a
    hyphenated/multi-word last name (e.g. 'Carlos Alcaraz Garfia') by taking
    everything after the first token as the last name, matching how Kaggle's
    own 'Last F.' abbreviation is built from the same source rankings data."""
    if not isinstance(name, str) or not name.strip():
        return None
    parts = [p for p in name.strip().split() if p.lower().rstrip(".") not in _NAME_SUFFIXES]
    if len(parts) < 2:
        return None
    first, last = parts[0], " ".join(parts[1:])
    return f"{last.lower()}|{first[0].lower()}"


def build_player_name_index(history: pd.DataFrame) -> dict:
    """
    {normalized_key: canonical_kaggle_name} across every player who's ever
    appeared in the history. A last-name+first-initial key collides for two
    players who share both (rare, but real — e.g. two "Zverev A."s isn't
    a real case, but the risk exists) — kept simple since collisions are
    uncommon and this index is only used to bridge live OpticOdds fixtures
    to the Kaggle history's player identity, not as the source of truth.
    """
    if history.empty:
        return {}
    names = pd.concat([history["Player_1"], history["Player_2"]]).dropna().unique()
    index = {}
    for name in names:
        key = _normalize_kaggle_name(name)
        if key:
            index[key] = name
    return index


def match_player_name(live_full_name: str, name_index: dict) -> str | None:
    """Resolves an OpticOdds full name to its Kaggle-history canonical name, or
    None if no match — callers must treat None as 'no history available for
    this player' (e.g. a qualifier/wildcard with no top-tour match history
    yet) rather than guessing."""
    key = _normalize_live_name(live_full_name)
    if key is None:
        return None
    return name_index.get(key)


def _fetch_tennis_fixtures(date: str, leagues: list = None, sportsbooks: list = None) -> list:
    """Paginated /fixtures for the date window. /fixtures/active silently dropped roughly HALF
    the slate (19 vs 37 singles measured 2026-09-26) -- the same defect the MLB side fixed on
    2026-09-04 by migrating to the paginated endpoint; tennis was still on the broken one.
    `sportsbooks` (2026-10-02): the default /fixtures (no book filter) only returns fixtures
    the main books price -- it was dropping ~30 of 70 ITF games that ONLY Polymarket prices.
    Passing sportsbooks runs ADDITIONAL per-book fixture pulls and merges them in by id."""
    if not OPTICODDS_API_KEY:
        return []
    headers = {"X-Api-Key": OPTICODDS_API_KEY}
    # 48h window (2026-09-28 fix): the old [date, date+1) UTC window went EMPTY every US
    # evening -- late US matches and Europe/Asia's next morning sit on the next UTC date.
    # The board filters to unplayed/live anyway, so the wider pull just keeps it stocked.
    start_before = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=2)).strftime("%Y-%m-%d")
    _lgs = leagues or TENNIS_LEAGUES

    def _cursor_pull(extra):
        # CURSOR pagination (2026-09-28 fix): no total_pages key -> follow {cursor, has_more}.
        rows, cursor = [], None
        while True:
            params = {"league": _lgs, "start_date_after": date, "start_date_before": start_before}
            params.update(extra)
            if cursor:
                params["cursor"] = cursor
            try:
                resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures", params=params,
                                    headers=headers, timeout=15)
                resp.raise_for_status()
                j = resp.json()
            except requests.exceptions.RequestException:
                break
            data = j.get("data", [])
            rows += data
            cursor = j.get("cursor")
            if not data or not j.get("has_more") or not cursor or len(rows) > 3000:
                break
        return rows

    by_id = {f["id"]: f for f in _cursor_pull({}) if f.get("id")}
    for bk in (sportsbooks or []):
        for f in _cursor_pull({"sportsbook": bk}):
            if f.get("id"):
                by_id.setdefault(f["id"], f)
    return list(by_id.values())


def _get_active_tennis_fixture_ids(date: str, leagues: list = None, sportsbooks: list = None) -> list:
    """Fixture ids for scheduled ATP/WTA singles matches on the given date."""
    fixtures = _fetch_tennis_fixtures(date, leagues, sportsbooks)
    # Doubles fixtures have >1 competitor per side — singles-only for this model.
    return [
        f["id"] for f in fixtures
        if f.get("status") in ("unplayed", "live")
        and len(f.get("home_competitors") or []) == 1 and len(f.get("away_competitors") or []) == 1
    ]


def get_tennis_today_matches(date: str = None, leagues: list = None, sportsbooks: list = None) -> list[dict]:
    """
    Today's (or a given date's) scheduled/live ATP+WTA singles matches from
    OpticOdds — fixture metadata only, no odds (see get_tennis_moneyline_odds
    for that). {"fixture_id", "league", "tournament", "player_1", "player_2",
    "start_time_utc", "status"}.
    """
    date = date or todays_date_et()
    fixtures = _fetch_tennis_fixtures(date, leagues, sportsbooks)

    matches = []
    for f in fixtures:
        home, away = f.get("home_competitors") or [], f.get("away_competitors") or []
        if len(home) != 1 or len(away) != 1:
            continue  # doubles
        matches.append({
            "fixture_id": f.get("id"),
            "league": (f.get("league") or {}).get("id"),
            "tournament": (f.get("tournament") or {}).get("name"),
            "round": f.get("tournament_stage"),
            "player_1": home[0].get("name"),
            "player_2": away[0].get("name"),
            "start_time_utc": f.get("start_date"),
            "status": f.get("status"),
        })
    return matches


def _valid_two_way(o1, o2) -> bool:
    """Reject impossible AMERICAN two-way lines (2026-10-05): both-negative (two favorites)
    or an implied-prob overround outside a real book's ~[0.80, 1.25]. Guards against
    OpticOdds's Polymarket-USA mirror returning garbage like -337/-5212 (175% book)."""
    try:
        a, b = float(o1), float(o2)
    except (TypeError, ValueError):
        return False
    if a < 0 and b < 0:
        return False
    i1 = 1.0 / ((1 + a / 100.0) if a > 0 else (1 + 100.0 / abs(a)))
    i2 = 1.0 / ((1 + b / 100.0) if b > 0 else (1 + 100.0 / abs(b)))
    s = i1 + i2
    return 0.80 <= s <= 1.25


def get_tennis_moneyline_odds(date: str = None, force_refresh: bool = False, leagues: list = None,
                              sportsbooks: list = None) -> dict:
    """
    {fixture_id: {"player_1": american_odds, "player_2": american_odds,
    "bookmaker": title}} for scheduled ATP/WTA singles matches — same
    PREFERRED_SPORTSBOOKS fallback chain as the MLB moneyline fetch.
    """
    from odds_fetcher import PREFERRED_SPORTSBOOKS  # local import avoids a cycle at module load

    if not OPTICODDS_API_KEY:
        return {}
    date = date or todays_date_et()
    # books to try, in preference order (2026-10-02): ITF passes Polymarket/Kalshi so the
    # ~30 ITF games only those venues price still get a line (else they'd show no odds).
    books = list(sportsbooks) + [b for b in PREFERRED_SPORTSBOOKS if b not in sportsbooks] \
        if sportsbooks else list(PREFERRED_SPORTSBOOKS)
    _tag = "" if not leagues else "_" + "-".join(sorted(leagues))
    cache_path = os.path.join(CACHE_DIR, f"tennis_odds_{date}{_tag}.json")
    if not force_refresh and os.path.exists(cache_path):
        import time as _time
        if (_time.time() - os.path.getmtime(cache_path)) / 60 < 15:
            import json
            with open(cache_path) as f:
                return json.load(f)

    headers = {"X-Api-Key": OPTICODDS_API_KEY}
    fixture_ids = _get_active_tennis_fixture_ids(date, leagues, sportsbooks)
    if not fixture_ids:
        return {}

    odds_by_fixture = {}
    # OpticOdds caps 5 sportsbooks per odds request -> query in chunks of 5 books.
    for i in range(0, len(fixture_ids), FIXTURE_BATCH_SIZE):
        batch = fixture_ids[i:i + FIXTURE_BATCH_SIZE]
        by_book_all = {}
        for bi in range(0, len(books), 5):
            bchunk = books[bi:bi + 5]
            try:
                resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures/odds", params={
                    "league": (leagues or TENNIS_LEAGUES), "market": "moneyline",
                    "sportsbook": bchunk, "is_main": "true", "fixture_id": batch,
                }, headers=headers, timeout=20)
                resp.raise_for_status()
                fixtures = resp.json().get("data", [])
            except requests.exceptions.RequestException:
                continue
            for fixture in fixtures:
                fid = fixture.get("id")
                e = by_book_all.setdefault(fid, {"home": fixture.get("home_team_display"),
                                                 "away": fixture.get("away_team_display"), "bb": {}})
                for o in fixture.get("odds") or []:
                    if o.get("market_id") != "moneyline":
                        continue
                    e["bb"].setdefault(o.get("sportsbook"), {})[o.get("name")] = o.get("price")
        for fid, e in by_book_all.items():
            for book in books:
                prices = e["bb"].get(book, {})
                if e["home"] in prices and e["away"] in prices:
                    p1, p2 = prices[e["home"]], prices[e["away"]]
                    if not _valid_two_way(p1, p2):
                        continue  # corrupt line (e.g. Polymarket-USA mirror -337/-5212) -> try next book
                    odds_by_fixture[fid] = {"player_1": p1, "player_2": p2, "bookmaker": book}
                    break

    import json
    with open(cache_path, "w") as f:
        json.dump(odds_by_fixture, f)
    return odds_by_fixture
