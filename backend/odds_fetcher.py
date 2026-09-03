"""
odds_fetcher.py

Pulls live MLB moneyline odds from OpticOdds. Requires OPTICODDS_API_KEY
in backend/.env. Docs: https://developer.opticodds.com
"""

import os
import json
import time
import unicodedata
import statistics
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv

from data_collection import CACHE_DIR, _get_mlb_team_name_to_abbr, _ESPN_TEAM_ABBR_FIX, _OPTICODDS_TEAM_NAME_FIX, MLB_STATS_API, todays_date_et

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

OPTICODDS_API_KEY = os.environ.get("OPTICODDS_API_KEY")
OPTICODDS_BASE_URL = "https://api.opticodds.com/api/v3"

# Tried in order per fixture — not every book prices every game, so fall
# back down the list rather than showing nothing.
PREFERRED_SPORTSBOOKS = ["FanDuel", "DraftKings", "BetMGM"]
# Books whose raw prices get_moneyline_odds ALSO pulls for Model E's best-price shopping (the
# "books" key) -- PREFERRED_SPORTSBOOKS above still decides the primary displayed line and the
# strikeout-prop default, unchanged. 5 = OpticOdds' per-request sportsbook cap. Pinnacle/Circa
# are sharp and rarely the best price, but "best of 5" can only be >= "best of 3".
MONEYLINE_SHOP_BOOKS = PREFERRED_SPORTSBOOKS + ["Pinnacle", "Circa Sports"]
# Second shopping panel (OpticOdds caps 5 books/request, so widening the shop needs a second
# request per batch). Every additional book can only raise "best of" -- one cent of price is pure
# ROI. LowVig/Betcris are known-good from Model C's panel; Caesars from PROP_CONSENSUS_BOOKS;
# BetRivers/ESPN BET are speculative and simply return nothing if OpticOdds doesn't carry them.
MONEYLINE_SHOP_BOOKS_2 = ["LowVig", "Betcris", "Caesars", "BetRivers", "ESPN BET"]

# Kept separate from PREFERRED_SPORTSBOOKS rather than folded into that
# fallback chain — PrizePicks is a pick'em DFS product, not a sportsbook,
# and its lines/pricing convention routinely differ from FanDuel/DraftKings
# (often meaningfully, on the same pitcher, same night). Fetched and shown
# as its own explicit line so a PrizePicks bettor sees the number that
# actually matters to them instead of a traditional-book line silently
# standing in for it.
PRIZEPICKS_SPORTSBOOK = ["PrizePicks"]

# /fixtures/odds caps fixture_id at 5 per request, so a day's ~10-15 games
# need a few batched calls.
FIXTURE_BATCH_SIZE = 5

_CACHE_MAX_AGE_MIN = 5  # odds move fast; tightened from 15 -- still clear of the historical-panel
# pacing floor (~72s/full refresh at 45 requests * HISTORICAL_RATE_LIMIT_SLEEP) and of the free
# quota, just fresher than a cold-start gap can look stale for

# --- Historical/movement odds (opening vs current-or-closing) ---------------
#
# Shared by clv_backtest.py, backfill_historical_odds.py, and get_line_movement below —
# originally lived in clv_backtest.py alone, moved here so live serving (main.py, via
# get_line_movement) doesn't have to import that whole backtest/training-analysis script just
# to reuse two small HTTP helpers.
CLOSING_BOOK = "Pinnacle"  # the standard "sharp" reference book for closing-line value
HISTORICAL_RATE_LIMIT_SLEEP = 0.5  # /fixtures/odds/historical's real cap (confirmed live via
# x-ratelimit-* response headers, 2026-08-18) is 50 requests/~15s, not the 10/15s this constant
# was originally calibrated for -- 0.5s leaves ~3x headroom under the real ceiling (safety margin
# for concurrent production traffic sharing the same API key), down from the prior 1.6s that was
# throttling every backfill in this project by roughly 5x more than actually necessary.

# Retail counterpart to CLOSING_BOOK for line_movement/CLOSING_BOOK-specific uses — heavy public
# volume, since OpticOdds has no actual bet-count/handle endpoint (confirmed: /betting-splits,
# /public-betting, /consensus, /handle all 404).
PUBLIC_BOOK = "DraftKings"

# market_divergence's actual sharp-vs-public split, one full CONSENSUS_BOOKS partition — when the
# SHARP_BOOKS' average movement since open differs from PUBLIC_BOOKS' average, that's a reverse-
# line-movement proxy for "sharp money vs. public money disagree." Originally just CLOSING_BOOK
# (Pinnacle) vs PUBLIC_BOOK (DraftKings) — a single book on each side is noisy (either book's own
# idiosyncratic pricing quirks read as "divergence" with nothing to average them out); using both
# sharp books and all three public books the same way get_consensus_odds already averages across
# CONSENSUS_BOOKS gives a more robust read of the same signal.
SHARP_BOOKS = ["Pinnacle", "Circa Sports"]
PUBLIC_BOOKS = ["DraftKings", "FanDuel", "BetMGM"]

# Prediction-market event contracts, queryable via the same /fixtures/odds/historical
# endpoint as regular sportsbooks. Their *opening* (olv) price is a degenerate artifact for
# Kalshi and plain "Polymarket" (both sides showed identical extreme prices, e.g. -2043 both
# teams — a thin-liquidity placeholder before real trading starts, not a real quote) —
# get_prediction_market_signal below only ever reads their current (clv) price, never olv.
# "Polymarket (USA)" specifically (not plain "Polymarket") gave sane opening prices too, but
# is still treated the same way for consistency since Kalshi can't be.
PREDICTION_MARKET_BOOKS = ["Kalshi", "Polymarket (USA)"]

# Sportsbook panel for consensus_prob_diff/book_disagreement_diff (see get_market_snapshot) and
# for line_movement_diff/market_divergence_diff (CLOSING_BOOK/PUBLIC_BOOK are both members, so
# one panel call covers all four features). Capped at exactly 5 — OpticOdds hard-limits
# /fixtures/odds/historical to 5 sportsbooks per request (confirmed live: a 6th book 400s with
# "sportsbook must have at most 5 items"). Pinnacle + Circa Sports (both "sharp") alongside
# FanDuel/DraftKings/BetMGM (the same three PREFERRED_SPORTSBOOKS used for live moneyline
# display) gives a reasonably representative cross-section, not just retail books.
CONSENSUS_BOOKS = ["Pinnacle", "DraftKings", "FanDuel", "BetMGM", "Circa Sports"]

# Model C's own curated 6-book panel (user-specified, distinct from CONSENSUS_BOOKS above) --
# FanDuel/Pinnacle/Circa Sports already confirmed real+active via a direct OpticOdds sportsbooks
# lookup; LowVig and Betcris confirmed too (both real, active, and returned live MLB moneyline
# data in a direct test). Kalshi is a prediction-market contract, not a bookmaker -- same
# olv-artifact caveat as PREDICTION_MARKET_BOOKS above applies, so it's fetched in its own
# 1-book panel (MODEL_C_PREDICTION_BOOKS) rather than folded into the 5-book moneyline batch,
# keeping MODEL_C_MONEYLINE_BOOKS at exactly 5 -- the same per-request cap CONSENSUS_BOOKS is
# already sized around (confirmed live: a 6th book 400s).
MODEL_C_MONEYLINE_BOOKS = ["FanDuel", "Pinnacle", "LowVig", "Betcris", "Circa Sports"]
MODEL_C_PREDICTION_BOOKS = ["Kalshi"]
MODEL_C_BOOKS = MODEL_C_MONEYLINE_BOOKS + MODEL_C_PREDICTION_BOOKS

# Model C deliberately has NO sharp/public split (unlike SHARP_BOOKS/PUBLIC_BOOKS above) --
# an earlier version split MODEL_C_BOOKS into 4 sharp vs. 1 public (FanDuel alone), but a
# single-book "public" side meant that HALF of market_divergence's contrast could be swung
# entirely by FanDuel moving on its own, no matter how many books protected the other half or
# consensus_prob/book_median_prob/book_favor_diff elsewhere. Averaging movement across all 6
# tracked books instead (get_model_c_snapshot's avg_movement, >=2-book minimum, same threshold
# as every other level feature) dilutes any single book's move the same way consensus_prob
# already does -- trades the sharp-vs-public CONTRAST signal for a fully symmetric one, but
# closes the single-book vulnerability completely instead of leaving one side of it exposed by
# construction.

# Sharp-weighted consensus PROBABILITY LEVEL (distinct from the movement-divergence issue above --
# this still blends ALL >=2 available books, just unevenly, so it never degrades to one book's
# raw value the way a sharp-vs-public CONTRAST would). Backtested as an add-on feature alongside
# the existing flat consensus_prob (_backtest_model_c_accuracy_ideas.py): +0.0073 AUC / -0.0010
# Brier pooled, held up in 4/5 walk-forward folds on both metrics. Weights are a simple 2x/1x
# split, not fit -- Pinnacle/Circa Sports/LowVig/Betcris are all sharp/low-margin books, FanDuel
# is the one retail/public book in the panel.
MODEL_C_SHARP_BOOKS = {"Pinnacle", "Circa Sports", "LowVig", "Betcris"}
MODEL_C_BOOK_WEIGHTS = {b: (2.0 if b in MODEL_C_SHARP_BOOKS else 1.0) for b in MODEL_C_MONEYLINE_BOOKS}
# Kalshi weighted the same as the sharp moneyline books (2.0) when folded into the consensus/
# sharp-weighted blend below -- it's a real-money, CFTC-regulated event-contract market, not a
# bookmaker's fixed line, so it belongs with the sharp/low-margin side, not treated as public.
MODEL_C_BOOK_WEIGHTS["Kalshi"] = 2.0

# Model C is meant to be checked ~every 30s (a live tracker, not an opportunistic per-request
# cache) -- much shorter than _CACHE_MAX_AGE_MIN's 5 minutes. The background poller (main.py)
# always passes force_refresh=True on its own 30s cadence; this TTL is just the fallback for any
# other caller that doesn't.
_MODEL_C_CACHE_MAX_AGE_MIN = 1

# Player-prop markets whose posted LINE (not the over/under price around it) is itself a
# specialized per-pitcher-per-night forecast — outs recorded (~depth expectation), earned runs
# and hits allowed (~run-prevention/contact-quality expectation), alongside the strikeout line
# already used elsewhere. Verified live: full historical coverage back through the 2025 season,
# same /fixtures/odds/historical endpoint. _fetch_player_prop_lines averages (consensus) across
# whichever of PROP_CONSENSUS_BOOKS has data for each pitcher/market — not every book prices
# every reliever, but the two starters are reliably covered across most/all 5 books.
PLAYER_PROP_MARKETS = ["Player Strikeouts", "Player Outs", "Player Earned Runs", "Player Hits Allowed"]

# Separate 5-book panel just for PLAYER_PROP_MARKETS -- swaps Circa Sports (a CONSENSUS_BOOKS
# member) for Caesars. Confirmed live across 6 fixtures: Circa Sports had 0/6 coverage on
# Player Outs/Earned Runs/Hits Allowed while Pinnacle/DraftKings/FanDuel/BetMGM/Caesars/ESPN
# Bet/Bally Bet all had 6/6 -- Circa is a real sharp book for moneyline (kept in CONSENSUS_BOOKS
# for that), just doesn't post these specific props. This is a separate API call from the
# moneyline/totals panels (_fetch_player_prop_lines, its own request), so swapping the book list
# here doesn't touch CONSENSUS_BOOKS' moneyline-consensus sharp/retail balance or add any extra
# requests.
PROP_CONSENSUS_BOOKS = ["Pinnacle", "DraftKings", "FanDuel", "BetMGM", "Caesars"]


def _fetch_fixtures_full(start_date: str, end_date: str, statuses: tuple = ("unplayed", "live")) -> list:
    """Full fixture objects (not just ids) for every MLB fixture in range matching `statuses`.

    Exists because get_market_snapshot / get_model_c_snapshot both iterated /fixtures/active,
    which silently drops any fixture OpticOdds no longer considers active. That is NOT the same
    boundary as MLB's PRE_GAME_STATUSES, which decides when a bet freezes -- so a game could still
    be pre-game by our rules (still updating its frozen bet) while already gone from the market
    snapshot, leaving Model E to price it with no market block at all. Measured 2026-08-22: 19 of
    80 tracked game-days (23.8%) hit that state, and /fixtures returned 38 fixtures for a window
    where /fixtures/active returned 16. See model_e.CORE_MARKET_COLUMNS for the NYM@CWS bet that
    surfaced it (Castillo 5.74 recent FIP favored over Scott 2.42, 5u staked, lost)."""
    out = []
    page = 1
    while True:
        resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures", params={
            "league": "mlb", "start_date_after": start_date, "start_date_before": end_date, "page": page,
        }, headers={"X-Api-Key": OPTICODDS_API_KEY}, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        for f in payload.get("data", []):
            if f.get("status") in statuses:
                out.append(f)
        total_pages = (payload.get("meta") or {}).get("total_pages") or 1
        if page >= total_pages:
            break
        page += 1
    return out


def _fetch_fixture_map(start_date: str, end_date: str, statuses: tuple = ("completed",)) -> dict:
    """{(date, home_abbr, away_abbr): fixture_id} for every MLB fixture in range matching one of
    `statuses` — defaults to completed-only (clv_backtest.py/backfill_historical_odds.py's use
    case: known-final games). get_line_movement passes ("unplayed",) too, for today's not-yet-
    played games."""
    fixture_map = {}
    page = 1
    while True:
        resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures", params={
            "league": "mlb", "start_date_after": start_date, "start_date_before": end_date, "page": page,
        }, headers={"X-Api-Key": OPTICODDS_API_KEY}, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        for f in payload.get("data", []):
            if f.get("status") not in statuses:
                continue
            game_date = f["start_date"][:10]
            # OpticOdds uses ESPN-style abbreviations (ARI/WSN/CHW/OAK) for the same 4 teams this
            # app already normalizes elsewhere (see data_collection._ESPN_TEAM_ABBR_FIX) — every
            # caller here keys lookups by OUR abbreviations (AZ/WSH/CWS/ATH), so any fixture
            # involving one of these 4 teams as home or away silently never matched, on either
            # side of the lookup. Confirmed directly: CHC @ ARI (2025-03-28) has real odds data
            # that a raw "AZ" key lookup never found. Normalizing here, once, at the source.
            home_abbr = _ESPN_TEAM_ABBR_FIX.get(f["home_competitors"][0]["abbreviation"], f["home_competitors"][0]["abbreviation"])
            away_abbr = _ESPN_TEAM_ABBR_FIX.get(f["away_competitors"][0]["abbreviation"], f["away_competitors"][0]["abbreviation"])
            fixture_map[(game_date, home_abbr, away_abbr)] = f["id"]
            # games starting late evening local time land on the next UTC date —
            # also index under the day before, so our MLB-Stats-API game_date
            # (which uses the local game date) still matches
            prev_date = (pd.Timestamp(game_date) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            fixture_map.setdefault((prev_date, home_abbr, away_abbr), f["id"])
        if not payload.get("has_more"):
            break
        page += 1
    return fixture_map


def _resolve_doubleheader_overrides(games_df: pd.DataFrame) -> dict:
    """
    {game_pk: fixture_id} for games that share a (game_date, home_team, away_team) key with
    another row in games_df -- i.e. doubleheaders. _fetch_fixture_map's dict is keyed by
    (date, home_abbr, away_abbr) with no time component, so both games of a doubleheader collide
    on the same key and fixture_map.get(...) silently returns one game's fixture id for both.
    Confirmed live 2026-08-17 (see the get_market_snapshot fix earlier the same day) and confirmed
    here in training data: 162/6724 rows (81 doubleheader date/matchup pairs) share a collided key.

    games_df needs game_date/home_team/away_team/game_pk columns (same shape every caller already
    has). Rows with no duplicate key are a no-op -- this only does work when doubleheaders are
    actually present in the input, so it's cheap to call unconditionally.

    Resolution: MLB's own gameNumber (1 or 2) per game_pk, matched against OpticOdds' fixtures for
    that exact (date, home, away) sorted chronologically -- game 1 is always first pitch of the
    day, so gameNumber order and chronological order always agree. Skips (falls back to the
    caller's normal fixture_map lookup, same as before this existed) any group it can't fully
    resolve, rather than guessing.
    """
    dupe_mask = games_df.duplicated(subset=["game_date", "home_team", "away_team"], keep=False)
    dupes = games_df[dupe_mask]
    if dupes.empty:
        return {}

    overrides = {}
    for (game_date, home_abbr, away_abbr), group in dupes.groupby(["game_date", "home_team", "away_team"]):
        game_pks = group["game_pk"].tolist()

        pk_to_game_number = {}
        for pk in game_pks:
            try:
                resp = requests.get(f"{MLB_STATS_API}/schedule", params={"gamePk": int(pk)}, timeout=15)
                resp.raise_for_status()
                for d in resp.json().get("dates", []):
                    for g in d.get("games", []):
                        if g.get("gamePk") == int(pk):
                            pk_to_game_number[pk] = g.get("gameNumber", 1)
            except requests.exceptions.RequestException:
                continue
        if len(pk_to_game_number) != len(game_pks):
            continue

        end = (pd.Timestamp(game_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        try:
            resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures", params={
                "league": "mlb", "start_date_after": game_date, "start_date_before": end,
            }, headers={"X-Api-Key": OPTICODDS_API_KEY}, timeout=20)
            resp.raise_for_status()
            optic_fixtures = []
            for f in resp.json().get("data", []):
                f_home = _ESPN_TEAM_ABBR_FIX.get(f["home_competitors"][0]["abbreviation"], f["home_competitors"][0]["abbreviation"])
                f_away = _ESPN_TEAM_ABBR_FIX.get(f["away_competitors"][0]["abbreviation"], f["away_competitors"][0]["abbreviation"])
                if f_home == home_abbr and f_away == away_abbr:
                    optic_fixtures.append(f)
        except requests.exceptions.RequestException:
            continue
        optic_fixtures.sort(key=lambda f: f["start_date"])
        if len(optic_fixtures) < len(game_pks):
            continue

        for pk, gnum in pk_to_game_number.items():
            idx = gnum - 1
            if 0 <= idx < len(optic_fixtures):
                overrides[pk] = optic_fixtures[idx]["id"]

    return overrides


def _fetch_closing_line(fixture_id: str, sportsbook: str = CLOSING_BOOK) -> dict:
    """{"home": american_odds, "away": american_odds} most-recent (CLV) price from `sportsbook`
    (defaults to Pinnacle), plus "home_open"/"away_open" opening (OLV) price from the same
    response — OpticOdds' historical endpoint returns both in one call, no extra request needed.
    Works for both completed games (true closing line) and still-unplayed ones (current line as
    of the query) — "clv" just means "most recent tracked price," not strictly "final." {} if
    unavailable. See PREDICTION_MARKET_BOOKS' docstring above for why callers using those books
    should ignore the "*_open" keys in the result rather than trust them."""
    try:
        resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures/odds/historical", params={
            "fixture_id": fixture_id, "sportsbook": sportsbook, "market": "Moneyline", "odds_format": "american",
        }, headers={"X-Api-Key": OPTICODDS_API_KEY}, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return {}
        fixture = data[0]
        home_team = fixture.get("home_team_display")
        away_team = fixture.get("away_team_display")
        prices, open_prices = {}, {}
        for o in fixture.get("odds", []):
            clv = o.get("clv") or {}
            olv = o.get("olv") or {}
            if clv.get("price") is not None:
                prices[o.get("name")] = clv["price"]
            if olv.get("price") is not None:
                open_prices[o.get("name")] = olv["price"]
        # Identical home/away prices are essentially never a genuine two-sided line -- see
        # get_moneyline_odds' equivalent guard for the confirmed real case (logged -108/-108 that
        # turned out to bear no resemblance to the book's actual closing line). Treated as no
        # signal here too, same as a missing price.
        if home_team in prices and away_team in prices and prices[home_team] != prices[away_team]:
            result = {"home": prices[home_team], "away": prices[away_team]}
            if home_team in open_prices and away_team in open_prices:
                result["home_open"] = open_prices[home_team]
                result["away_open"] = open_prices[away_team]
            return result
    except requests.exceptions.RequestException:
        pass
    return {}


def _fetch_current_panel_odds(fixture_id: str, sportsbooks: list, home_team: str, away_team: str) -> dict:
    """{book: {"home": price, "away": price}} sourced from /fixtures/odds (the plain LIVE endpoint,
    not /fixtures/odds/historical) — confirmed live 2026-08-18: /fixtures/odds/historical's "clv"
    (current live value) field can sit empty for a fixture for hours even close to first pitch
    (a real fixture showed home_open/away_open populated for all 5 books but zero clv data at all),
    while /fixtures/odds/is_main=true always has the live price -- it's the same endpoint
    get_moneyline_odds already relies on for the card's displayed live_odds, which never showed
    this gap. Used by _fetch_panel_odds below as the CURRENT-price source; /fixtures/odds/historical
    is kept only for the opening (olv) side, which it does have reliably.

    Same identical-price corruption guard as get_moneyline_odds (a genuine two-sided line is never
    priced identically on both sides)."""
    try:
        resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures/odds", params={
            "league": "mlb", "market": "moneyline", "sportsbook": sportsbooks,
            "is_main": "true", "fixture_id": [fixture_id],
        }, headers={"X-Api-Key": OPTICODDS_API_KEY}, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return {}
        odds_list = data[0].get("odds") or []
        by_book = {}
        for o in odds_list:
            if o.get("market_id") != "moneyline":
                continue
            book = o.get("sportsbook")
            name = o.get("name")
            side = "home" if name == home_team else "away" if name == away_team else None
            if side is None:
                continue
            by_book.setdefault(book, {})[side] = o.get("price")
        return {
            book: v for book, v in by_book.items()
            if "home" in v and "away" in v and v["home"] != v["away"]
        }
    except requests.exceptions.RequestException:
        return {}


def _fetch_panel_odds(fixture_id: str, sportsbooks: list) -> dict:
    """{book: {"home":.., "away":.., "home_open":.., "away_open":..}} for up to 5 sportsbooks
    in ONE request — OpticOdds allows a list for the `sportsbook` param on
    /fixtures/odds/historical, capped at 5/call (see CONSENSUS_BOOKS). Far cheaper than one
    _fetch_closing_line call per book — get_market_snapshot below uses this instead of N
    separate requests. {} if the fixture has no data for any of the requested books.

    "home"/"away" (the CURRENT price) come from _fetch_current_panel_odds (the live /fixtures/odds
    endpoint) instead of this endpoint's own "clv" field -- see that function's docstring for why:
    clv can be empty for hours even on fixtures close to first pitch, silently forcing every
    consensus-style feature (consensus_prob, book_disagreement, etc.) to fall back to OPENING
    lines and serve a stale read as if it were current. "home_open"/"away_open" still come from
    this endpoint's "olv" field, which doesn't have that gap."""
    try:
        resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures/odds/historical", params={
            "fixture_id": fixture_id, "sportsbook": sportsbooks, "market": "Moneyline", "odds_format": "american",
        }, headers={"X-Api-Key": OPTICODDS_API_KEY}, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return {}
        fixture = data[0]
        home_team = fixture.get("home_team_display")
        away_team = fixture.get("away_team_display")
        by_book = {}
        for o in fixture.get("odds", []):
            book = o.get("sportsbook")
            name = o.get("name")
            side = "home" if name == home_team else "away" if name == away_team else None
            if side is None:
                continue
            entry = by_book.setdefault(book, {})
            olv = o.get("olv") or {}
            if olv.get("price") is not None:
                entry[f"{side}_open"] = olv["price"]

        time.sleep(HISTORICAL_RATE_LIMIT_SLEEP)
        current_by_book = _fetch_current_panel_odds(fixture_id, sportsbooks, home_team, away_team)
        for book, prices in current_by_book.items():
            by_book.setdefault(book, {}).update(prices)

        # Identical home/away prices from the same book are essentially never a genuine two-sided
        # line -- see get_moneyline_odds' equivalent guard for the confirmed real case. Drop just
        # the corrupted pair (current or opening, whichever matched) rather than the whole book, so
        # a good current price alongside a bad opening one (or vice versa) doesn't get thrown out
        # unnecessarily.
        for entry in by_book.values():
            if "home" in entry and "away" in entry and entry["home"] == entry["away"]:
                del entry["home"], entry["away"]
            if "home_open" in entry and "away_open" in entry and entry["home_open"] == entry["away_open"]:
                del entry["home_open"], entry["away_open"]
        # Keep a book if it has a usable price pair from EITHER source — current (home/away) or,
        # when OpticOdds hasn't synced a current price yet, opening (home_open/away_open). Used to
        # require "home"+"away" specifically, which silently dropped a book's opening price too
        # whenever only its current price was missing — get_market_snapshot's olv fallback for
        # level features (consensus_prob/book_disagreement/etc.) never saw the opening data as a
        # result, even though this same odds entry carried it.
        return {
            book: v for book, v in by_book.items()
            if ("home" in v and "away" in v) or ("home_open" in v and "away_open" in v)
        }
    except requests.exceptions.RequestException:
        return {}


def _fetch_totals_panel(fixture_id: str, sportsbooks: list = None) -> dict:
    """{book: {"total_runs":.., "home_team_total":.., "away_team_total":..}} for up to 5
    sportsbooks in ONE request — "Total Runs" (game total) and "Team Total" (each team's own
    projected runs) fetched together (verified live: a combined sportsbook-list + market-list
    call works the same way the player-prop panel does). Reads `clv.points` (the posted line
    itself, not the over/under price around it — same convention as PLAYER_PROP_MARKETS).
    Sportsbooks/markets with no data for this fixture are simply absent from the result."""
    sportsbooks = sportsbooks or CONSENSUS_BOOKS
    try:
        resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures/odds/historical", params={
            "fixture_id": fixture_id, "sportsbook": sportsbooks, "market": ["Total Runs", "Team Total"],
            "odds_format": "american", "is_main": "true",
        }, headers={"X-Api-Key": OPTICODDS_API_KEY}, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return {}
        fixture = data[0]
        home_team = fixture.get("home_team_display")
        away_team = fixture.get("away_team_display")
        by_book = {}
        for o in fixture.get("odds", []):
            book = o.get("sportsbook")
            clv, olv = o.get("clv") or {}, o.get("olv") or {}
            # Falls back to the opening line when OpticOdds hasn't synced a current price yet —
            # same pattern _fetch_player_prop_lines already uses. team_total_diff/market_total_runs
            # are pure level features (no movement variant depends on totals), so this fallback is
            # safe here unconditionally, unlike the moneyline panel's now-vs-open split below.
            points = clv.get("points") if clv.get("points") is not None else olv.get("points")
            if points is None:
                continue
            entry = by_book.setdefault(book, {})
            if o.get("market_id") == "total_runs":
                entry["total_runs"] = points
            elif o.get("market_id") == "team_total":
                selection = o.get("selection")
                if selection == home_team:
                    entry["home_team_total"] = points
                elif selection == away_team:
                    entry["away_team_total"] = points
        return by_book
    except requests.exceptions.RequestException:
        return {}


_MARKET_ID_TO_NAME = {
    "player_strikeouts": "Player Strikeouts", "player_outs": "Player Outs",
    "player_earned_runs": "Player Earned Runs", "player_hits_allowed": "Player Hits Allowed",
}


def normalize_player_name(name: str) -> str:
    """Strips diacritics and lowercases, e.g. "Carlos Rodón" -> "carlos rodon" — OpticOdds'
    player-prop `selection` field uses unaccented ASCII names ("Carlos Rodon") while MLB Stats
    API (get_pitcher_info, used to resolve pitcher_id -> name for the historical backfill) returns
    proper accented names ("Carlos Rodón"). Caught directly: Rodón/Peralta matched fine on one
    side and silently produced all-None lines on the other until both sides were normalized the
    same way before comparison. Callers doing ANY pitcher-name-keyed lookup against
    _fetch_player_prop_lines'/get_pitcher_market_lines' output must normalize their own key with
    this function first — the returned dicts are keyed by the normalized form, not the raw name."""
    if not name:
        return name
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _fetch_player_prop_lines(fixture_id: str, markets: list = None, sportsbooks: list = None) -> dict:
    """{market_name: {normalized_pitcher_name: points}} for all of `markets` (defaults to
    PLAYER_PROP_MARKETS), averaged (consensus) across all of `sportsbooks` (defaults to
    PROP_CONSENSUS_BOOKS) that have data for that pitcher/market — one combined request for the whole
    5-book x 4-market panel (verified live: sportsbook list + market list together in one call
    works the same way the totals panel does, 60 entries back for 5 books x 4 markets x 2
    pitchers). `points` is the posted LINE (e.g. 18.5 outs, 1.5 earned runs), not the over/under
    price around it — see PLAYER_PROP_MARKETS' docstring on why the line itself is the signal.
    Reads `clv.points`, falling back to `olv.points` if a fixture has no current price yet.
    Markets/pitchers with no data from any book end up absent from the returned dict entirely —
    same "no signal" convention as everywhere else in this app. Keys are run through
    normalize_player_name — see its docstring for why."""
    markets = markets or PLAYER_PROP_MARKETS
    sportsbooks = sportsbooks or PROP_CONSENSUS_BOOKS

    try:
        resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures/odds/historical", params={
            "fixture_id": fixture_id, "sportsbook": sportsbooks, "market": markets, "odds_format": "american",
            "is_main": "true",
        }, headers={"X-Api-Key": OPTICODDS_API_KEY}, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return {}
        by_market_player = {}  # market_name -> pitcher_name -> [points, ...] across books
        for o in data[0].get("odds", []):
            market_name = _MARKET_ID_TO_NAME.get(o.get("market_id"))
            # "selection" is the clean player name ("Reid Detmers") — "name" concatenates
            # selection+side+sometimes-the-alt-line ("Reid Detmers Under 17.5"), not usable
            # as a lookup key. is_main=true (server-side filter, same param already used by
            # get_moneyline_odds/get_strikeout_prop_lines) excludes alt-line duplicates.
            name = normalize_player_name(o.get("selection"))
            if not market_name or not name:
                continue
            clv = o.get("clv") or {}
            olv = o.get("olv") or {}
            points = clv.get("points") if clv.get("points") is not None else olv.get("points")
            if points is not None:
                by_market_player.setdefault(market_name, {}).setdefault(name, []).append(points)
        return {
            market: {name: sum(vals) / len(vals) for name, vals in players.items()}
            for market, players in by_market_player.items()
        }
    except requests.exceptions.RequestException:
        return {}


def get_market_snapshot(date: str = None, force_refresh: bool = False) -> dict:
    """
    {(start_date_utc, away_team_full_name, home_team_full_name): {
        "line_movement": .., "market_divergence": .., "consensus_prob": ..,
        "book_disagreement": .., "book_probs": {book: devigged_home_prob},
        "prediction_market_diff": .., "prediction_market_probs": {book: devigged_home_prob},
    }} — the single shared fetch behind get_line_movement/get_market_divergence/
    get_consensus_odds/get_prediction_market_signal below (all thin wrappers over this), so a
    request needing several of these fields doesn't pay for the same panel twice. Two API calls
    per game: one 5-book CONSENSUS_BOOKS panel (covers line movement, divergence, consensus,
    book-by-book — CLOSING_BOOK/PUBLIC_BOOK are both members), one 2-book PREDICTION_MARKET_BOOKS
    panel. Any field can be missing/absent per game — same "NaN means no signal" convention as
    everywhere else in this app, not an error.

    Key includes start_date_utc (matches get_probable_pitchers' game_time_utc string exactly,
    confirmed live) because the fetch window spans date..date+2 -- any 2+ game series has the
    SAME (away_team, home_team) pair appear on multiple days within that window, and a
    team-name-only key let a later, not-yet-lined fixture (no book panels posted yet, all fields
    None) silently overwrite an earlier day's real data in this dict. Confirmed live: this
    dropped every market feature for a same-day game to None while a later date's game in the
    window occupied the key instead. Also disambiguates genuine same-day doubleheaders, which
    have distinct start times.
    """
    if not OPTICODDS_API_KEY:
        return {}
    date = date or todays_date_et()
    cache_path = os.path.join(CACHE_DIR, f"market_snapshot_{date}.json")
    # Last-known-good store, merged under every rebuild below. The market block was observed
    # FLAPPING on 2026-08-22 -- for a single pre-game game, consensus/median/spread/std/favor
    # would vanish and return roughly every 7 minutes all day, same status, same price (see
    # game_pk 823910's prediction_history). Whatever the upstream cause (a partial page, a
    # transient panel fetch, a fixture briefly absent), a game that HAD a market read a few
    # minutes ago should not silently become market-blind: Model E's 13 features were pruned on
    # the assumption a price is present, and prediction_log freezes whichever snapshot happens to
    # be current at first pitch. Sticky-merging means the freeze can no longer land on a hole.
    sticky_path = os.path.join(CACHE_DIR, f"market_snapshot_sticky_{date}.json")
    if not force_refresh and os.path.exists(cache_path):
        age_min = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_min < _CACHE_MAX_AGE_MIN:
            with open(cache_path) as f:
                raw = json.load(f)
            return {tuple(k.split("|||")): v for k, v in raw.items()}  # (start_date, away, home)

    # +2 calendar days, not +1 day 12h — see _get_active_fixture_ids' comment on why a date-only
    # bound can't represent a same-day hour offset (it gets silently truncated away).
    end_date = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=2)).strftime("%Y-%m-%d")
    try:
        fixture_map = _fetch_fixture_map(date, end_date, statuses=("unplayed", "live", "completed"))
    except requests.exceptions.RequestException:
        return {}

    # /fixtures (unplayed + live), NOT /fixtures/active -- that endpoint silently dropped games
    # that were still pre-game by our own freeze rules. See _fetch_fixtures_full.
    # Guarded like _fetch_fixture_map above: main._compute_today_response calls this from a
    # thread pool whose .result() has no try around it (by documented contract every fetch
    # "tolerates its own failure internally"), so a transient OpticOdds 429/5xx here must
    # degrade to a market-less response, not 500 the whole /api/today for a cache-TTL window.
    try:
        fixtures_full = _fetch_fixtures_full(date, end_date, statuses=("unplayed", "live"))
    except requests.exceptions.RequestException:
        return {}
    snapshot = {}
    try:
        for f in fixtures_full:
            game_date = f["start_date"][:10]
            home_abbr = f.get("home_competitors", [{}])[0].get("abbreviation")
            away_abbr = f.get("away_competitors", [{}])[0].get("abbreviation")
            # f["id"] (this fixture's own id, straight from /fixtures/active) wins over
            # fixture_map's cross-reference -- fixture_map is keyed by (date, home_abbr,
            # away_abbr) with no time component, so a doubleheader's two fixtures collide there
            # too and it silently returns one game's id for both. Confirmed live on a real
            # STL@CIN doubleheader: fixture_map resolved BOTH the 17:40Z and 22:40Z games to the
            # same (second) fixture id. f["id"] is always fixture-specific and never ambiguous,
            # so it's the right default; fixture_map is now just a defensive fallback for the
            # (should be impossible) case where a fixture is missing its own id.
            fixture_id = f.get("id") or fixture_map.get((game_date, home_abbr, away_abbr))
            if fixture_id is None:
                continue

            panel = _fetch_panel_odds(fixture_id, CONSENSUS_BOOKS)
            time.sleep(HISTORICAL_RATE_LIMIT_SLEEP)
            pred_panel = _fetch_panel_odds(fixture_id, PREDICTION_MARKET_BOOKS)
            time.sleep(HISTORICAL_RATE_LIMIT_SLEEP)
            totals_panel = _fetch_totals_panel(fixture_id, CONSENSUS_BOOKS)
            time.sleep(HISTORICAL_RATE_LIMIT_SLEEP)

            probs_now, probs_open = {}, {}
            for book, o in panel.items():
                p_now = devig_home_prob(o.get("home"), o.get("away"))
                if p_now is not None:
                    probs_now[book] = p_now
                if "home_open" in o and "away_open" in o:
                    p_open = devig_home_prob(o["home_open"], o["away_open"])
                    if p_open is not None:
                        probs_open[book] = p_open

            line_movement = None
            if CLOSING_BOOK in probs_now and CLOSING_BOOK in probs_open:
                line_movement = probs_now[CLOSING_BOOK] - probs_open[CLOSING_BOOK]

            # Reverse-line-movement proxy: SHARP_BOOKS' average movement since open minus
            # PUBLIC_BOOKS' average movement — see SHARP_BOOKS' docstring on why this averages
            # across both sides instead of comparing a single book pair.
            sharp_movements = [
                probs_now[b] - probs_open[b] for b in SHARP_BOOKS if b in probs_now and b in probs_open
            ]
            public_movements = [
                probs_now[b] - probs_open[b] for b in PUBLIC_BOOKS if b in probs_now and b in probs_open
            ]
            # >=2 books per side (same threshold as every other level feature) -- with a single
            # book on either side, half of this CONTRAST is one book's private drift passed off
            # as "sharp money" or "public money". Flagged from a live CWS@HOU case (2026-09-01)
            # where this feature single-handedly carried a 20-pt Model E edge: that night's
            # reading was legitimately 2v2, but the 1-book degenerate case was still open here
            # even though get_model_c_snapshot closed its equivalent a week earlier.
            market_divergence = (
                (sum(sharp_movements) / len(sharp_movements)) - (sum(public_movements) / len(public_movements))
                if len(sharp_movements) >= 2 and len(public_movements) >= 2 else None
            )

            # Level features (a snapshot of where the market sits right now) can fall back to a
            # book's opening price when OpticOdds hasn't synced a current one yet — same olv
            # fallback _fetch_player_prop_lines/_fetch_totals_panel already use, just applied here
            # per-book instead of per-field, since a game can have some books synced and others
            # not. probs_now wins where both exist (dict merge order). Movement features below
            # (line_movement/market_divergence/book_movement_agreement) deliberately do NOT use
            # this — they need a genuinely distinct now-vs-open pair, and silently treating a
            # fallback price as "now" would compute a fake zero movement instead of leaving it NaN.
            probs_effective = {**probs_open, **probs_now}

            # >=2-book minimum -- same fix already applied to get_model_c_snapshot (flagged live
            # 2026-08-17, see that function's "Same single-book vulnerability" comment), never
            # backported here even though the vulnerability is identical: with only 1 book's price
            # available, "consensus" was silently just that single book's raw number, and it
            # swinging in/out of sync between requests (common with thin pre-game coverage) looked
            # like the market moving when it hadn't. book_disagreement/book_prob_std already had
            # this threshold; consensus_prob/book_median_prob/book_favor_diff didn't.
            consensus_prob = (
                (sum(probs_effective.values()) / len(probs_effective)) if len(probs_effective) >= 2 else None
            )
            book_disagreement = (
                (max(probs_effective.values()) - min(probs_effective.values())) if len(probs_effective) >= 2 else None
            )

            # Median (robust to one outlier book skewing the mean) and population std (a more
            # holistic disagreement measure than book_disagreement's max-min range, which is
            # driven entirely by the two most extreme books and ignores everything in between).
            book_median_prob = statistics.median(probs_effective.values()) if len(probs_effective) >= 2 else None
            book_prob_std = statistics.pstdev(probs_effective.values()) if len(probs_effective) >= 2 else None

            # Signed fraction of CONSENSUS_BOOKS currently favoring home vs. away (>50%/<50%) —
            # distinct from consensus_prob_diff (the average PROBABILITY LEVEL, which one extreme
            # book can skew) and from book_movement_agreement (about movement direction, not
            # current-price side). +1.0 = every book favors home right now, -1.0 = every book
            # favors away.
            book_favor_diff = None
            if len(probs_effective) >= 2:
                favor_home = sum(1 for p in probs_effective.values() if p > 0.5)
                favor_away = sum(1 for p in probs_effective.values() if p < 0.5)
                book_favor_diff = (favor_home - favor_away) / len(probs_effective)

            # Signed fraction of CONSENSUS_BOOKS that moved the same direction since open —
            # +1.0 means every book with both open+current data moved toward home, -1.0 means
            # every book moved toward away, near 0 means the books are split/mixed. Answers
            # "how many sportsbooks are moving together" (OpticOdds has no timestamps anywhere
            # on odds or fixture objects — confirmed live, checked both — so speed/rate of
            # movement isn't computable; this is the piece of that ask that actually is).
            book_movements = {
                book: probs_now[book] - probs_open[book]
                for book in probs_now if book in probs_open
            }
            book_movement_agreement = None
            if book_movements:
                toward_home = sum(1 for m in book_movements.values() if m > 0)
                toward_away = sum(1 for m in book_movements.values() if m < 0)
                book_movement_agreement = (toward_home - toward_away) / len(book_movements)

            # Prediction markets: current (clv) price only, never opening — see
            # PREDICTION_MARKET_BOOKS' docstring on the confirmed opening-price artifact. Keeps
            # the per-book breakdown (prediction_market_probs), not just the averaged diff used
            # as a model feature — the previous-day/live display wants to show "Kalshi: 55%"
            # directly, not just its distance from Pinnacle.
            pred_probs = []
            prediction_market_probs = {}
            for book, o in pred_panel.items():
                p = devig_home_prob(o.get("home"), o.get("away"))
                if p is not None:
                    pred_probs.append(p)
                    prediction_market_probs[book] = p
            prediction_market_diff = None
            if pred_probs and CLOSING_BOOK in probs_effective:
                prediction_market_diff = (sum(pred_probs) / len(pred_probs)) - probs_effective[CLOSING_BOOK]

            # Market-implied score differential (who does the market expect to outscore whom
            # tonight) and scoring environment (combined expected runs) — averaged across
            # whichever CONSENSUS_BOOKS members have each field, since Team Total/Total Runs
            # coverage doesn't always match Moneyline's exactly game to game.
            home_totals = [o["home_team_total"] for o in totals_panel.values() if "home_team_total" in o]
            away_totals = [o["away_team_total"] for o in totals_panel.values() if "away_team_total" in o]
            game_totals = [o["total_runs"] for o in totals_panel.values() if "total_runs" in o]
            team_total_diff = (
                (sum(home_totals) / len(home_totals)) - (sum(away_totals) / len(away_totals))
                if home_totals and away_totals else None
            )
            market_total_runs = (sum(game_totals) / len(game_totals)) if game_totals else None

            # Normalized to MLB Stats API's own team-name convention (e.g. "Athletics", not
            # OpticOdds' "Oakland Athletics") -- this dict is looked up by main.py using
            # get_probable_pitchers' names directly, same reasoning as _ESPN_TEAM_ABBR_FIX above.
            home_team = _OPTICODDS_TEAM_NAME_FIX.get(f.get("home_team_display"), f.get("home_team_display"))
            away_team = _OPTICODDS_TEAM_NAME_FIX.get(f.get("away_team_display"), f.get("away_team_display"))
            snapshot_key = (f.get("start_date"), away_team, home_team)
            if snapshot_key in snapshot:
                # Should be impossible post-fix (start_date makes the key unique per fixture) --
                # if this ever fires, OpticOdds is returning a genuine duplicate fixture, or the
                # key stopped being unique again. Either way, silently overwriting real data with
                # whatever came second is exactly the bug that produced 57% instead of ~69% for a
                # PHI game with zero actual market signal behind it (see git blame on this line).
                # Loud and skipped beats silent and wrong.
                print(f"[get_market_snapshot] WARNING: duplicate snapshot key {snapshot_key!r} -- keeping first, dropping this one")
                continue
            snapshot[snapshot_key] = {
                "line_movement": line_movement,
                "market_divergence": market_divergence,
                "consensus_prob": consensus_prob,
                "book_median_prob": book_median_prob,
                "book_prob_std": book_prob_std,
                "book_disagreement": book_disagreement,
                "book_movement_agreement": book_movement_agreement,
                "book_favor_diff": book_favor_diff,
                "book_probs": probs_now,
                "prediction_market_diff": prediction_market_diff,
                "prediction_market_probs": prediction_market_probs,
                "team_total_diff": team_total_diff,
                "market_total_runs": market_total_runs,
            }
    except requests.exceptions.RequestException:
        pass

    # Merge with last-known-good before returning: any game whose market fields came back empty
    # this pass keeps its most recent non-empty read instead of going market-blind. See the
    # sticky_path comment at the top of this function for the flapping this defends against.
    try:
        prev = {}
        if os.path.exists(sticky_path):
            with open(sticky_path) as f:
                prev = {tuple(k.split("|||")): v for k, v in json.load(f).items()}
        for key, old_v in prev.items():
            cur = snapshot.get(key)
            if cur is None:
                snapshot[key] = old_v
            elif cur.get("consensus_prob") is None and old_v.get("consensus_prob") is not None:
                merged = dict(old_v)
                merged.update({k: v for k, v in cur.items() if v is not None})
                snapshot[key] = merged
        good = {f"{k[0]}|||{k[1]}|||{k[2]}": v for k, v in snapshot.items()
                if (v or {}).get("consensus_prob") is not None}
        with open(sticky_path, "w") as f:
            json.dump(good, f)
    except (OSError, ValueError) as e:
        print(f"[market snapshot] sticky merge skipped: {e}")

    raw = {f"{start_date}|||{away}|||{home}": v for (start_date, away, home), v in snapshot.items()}
    with open(cache_path, "w") as f:
        json.dump(raw, f)
    return snapshot


def get_model_c_snapshot(date: str = None, force_refresh: bool = False) -> dict:
    """
    Model C's own version of get_market_snapshot -- same shape and mostly the same feature
    computations, but sourced from MODEL_C_MONEYLINE_BOOKS + MODEL_C_PREDICTION_BOOKS (FanDuel,
    Pinnacle, LowVig, Betcris, Circa Sports, Kalshi) instead of CONSENSUS_BOOKS +
    PREDICTION_MARKET_BOOKS. Meant to be polled on a tight ~30s cadence by main.py's background
    loop (force_refresh=True each time) rather than the opportunistic per-request caching
    get_market_snapshot uses -- _MODEL_C_CACHE_MAX_AGE_MIN is 1 minute, just a fallback for any
    caller that doesn't force_refresh.

    One deliberate difference from get_market_snapshot: "avg_movement" replaces
    "market_divergence" -- average movement across all MODEL_C_MONEYLINE_BOOKS (>=2-book minimum)
    instead of a sharp-vs-public contrast, since Model C's book list only has one public/retail
    book (FanDuel), which would leave that half of a divergence contrast as a single point of
    failure. See MODEL_C_BOOKS' comment above.

    Same "NaN means no signal" convention, same doubleheader-safe (start_date, away, home) key,
    same collision guard, same team-name normalization -- copied over deliberately rather than
    parameterizing get_market_snapshot itself, so a change to Model C's cadence/book list can
    never accidentally affect Model A/B's serving path.
    """
    if not OPTICODDS_API_KEY:
        return {}
    date = date or todays_date_et()
    cache_path = os.path.join(CACHE_DIR, f"model_c_snapshot_{date}.json")
    if not force_refresh and os.path.exists(cache_path):
        age_min = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_min < _MODEL_C_CACHE_MAX_AGE_MIN:
            with open(cache_path) as f:
                raw = json.load(f)
            return {tuple(k.split("|||")): v for k, v in raw.items()}

    end_date = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=2)).strftime("%Y-%m-%d")
    try:
        fixture_map = _fetch_fixture_map(date, end_date, statuses=("unplayed", "live", "completed"))
    except requests.exceptions.RequestException:
        return {}

    # Last genuinely-live price seen per (fixture, book), persisted across polls -- see below for
    # why this exists. Keyed by fixture_id (stable per game, available before the team-name/
    # snapshot_key computation further down) rather than the snapshot_key tuple.
    last_live_path = os.path.join(CACHE_DIR, f"model_c_last_live_{date}.json")
    try:
        with open(last_live_path) as lf:
            last_live_by_fixture = json.load(lf)
    except (FileNotFoundError, json.JSONDecodeError):
        last_live_by_fixture = {}

    # /fixtures (unplayed + live), NOT /fixtures/active -- that endpoint silently dropped games
    # that were still pre-game by our own freeze rules. See _fetch_fixtures_full.
    # Guarded like _fetch_fixture_map above: main._compute_today_response calls this from a
    # thread pool whose .result() has no try around it (by documented contract every fetch
    # "tolerates its own failure internally"), so a transient OpticOdds 429/5xx here must
    # degrade to a market-less response, not 500 the whole /api/today for a cache-TTL window.
    try:
        fixtures_full = _fetch_fixtures_full(date, end_date, statuses=("unplayed", "live"))
    except requests.exceptions.RequestException:
        return {}
    snapshot = {}
    try:
        for f in fixtures_full:
            game_date = f["start_date"][:10]
            home_abbr = f.get("home_competitors", [{}])[0].get("abbreviation")
            away_abbr = f.get("away_competitors", [{}])[0].get("abbreviation")
            fixture_id = f.get("id") or fixture_map.get((game_date, home_abbr, away_abbr))
            if fixture_id is None:
                continue

            panel = _fetch_panel_odds(fixture_id, MODEL_C_MONEYLINE_BOOKS)
            time.sleep(HISTORICAL_RATE_LIMIT_SLEEP)
            pred_panel = _fetch_panel_odds(fixture_id, MODEL_C_PREDICTION_BOOKS)
            time.sleep(HISTORICAL_RATE_LIMIT_SLEEP)
            totals_panel = _fetch_totals_panel(fixture_id, MODEL_C_MONEYLINE_BOOKS)
            time.sleep(HISTORICAL_RATE_LIMIT_SLEEP)

            probs_now, probs_open = {}, {}
            for book, o in panel.items():
                p_now = devig_home_prob(o.get("home"), o.get("away"))
                if p_now is not None:
                    probs_now[book] = p_now
                if "home_open" in o and "away_open" in o:
                    p_open = devig_home_prob(o["home_open"], o["away_open"])
                    if p_open is not None:
                        probs_open[book] = p_open

            # Live coverage across the 6 tracked books is commonly partial on any given ~30s poll
            # (confirmed live 2026-08-18: most games show 2-4/6 books with a "now" price, never
            # 6/6) -- see _fetch_panel_odds' docstring on why "now" can gap even when "open"
            # doesn't. Falling straight back to a book's OPENING line (possibly set days earlier)
            # for whichever books are missing THIS poll means the blended consensus/sharp-weighted
            # probability's composition silently shifts between "genuinely current" and "stale
            # open" as coverage flickers poll to poll -- producing swings that reflect coverage
            # gaps, not real market movement (flagged live: MIA@PHI moved 64->67->53 in minutes
            # with no corresponding news). Holding a book at its own LAST KNOWN LIVE price when
            # this poll has no fresh read for it (falling back to the opening line only if we've
            # never seen a live price for that book at all) keeps the blend responsive to genuine
            # movement while removing the coverage-flicker noise.
            last_live = last_live_by_fixture.get(fixture_id, {})
            probs_effective = {**probs_open, **last_live, **probs_now}
            last_live_by_fixture[fixture_id] = {**last_live, **probs_now}

            line_movement = None
            if CLOSING_BOOK in probs_now and CLOSING_BOOK in probs_open:
                line_movement = probs_now[CLOSING_BOOK] - probs_open[CLOSING_BOOK]

            # Average movement across ALL of MODEL_C_MONEYLINE_BOOKS (no sharp-vs-public split --
            # see the MODEL_C_BOOKS comment above on why: a single-book "public" side would let
            # that one book's move show up undiluted, the exact single-book vulnerability found
            # live in Model B). >=2-book minimum, same threshold as every other level feature
            # below, so this can't degrade to a single book's movement passed off as a market
            # read either.
            all_movements = [
                probs_now[b] - probs_open[b] for b in MODEL_C_MONEYLINE_BOOKS if b in probs_now and b in probs_open
            ]
            avg_movement = (sum(all_movements) / len(all_movements)) if len(all_movements) >= 2 else None

            pred_probs = []
            prediction_market_probs = {}
            for book, o in pred_panel.items():
                p = devig_home_prob(o.get("home"), o.get("away"))
                if p is not None:
                    pred_probs.append(p)
                    prediction_market_probs[book] = p

            # Kalshi folded into the core consensus/sharp-weighted blend as a genuine market
            # participant, not just the divergence check below -- it's real-money, CFTC-regulated
            # event-contract pricing, not a bookmaker's line, and there's no principled reason to
            # track what it thinks the market is (prediction_market_diff) while excluding it from
            # what WE call the market's consensus. Kept in a separate dict from probs_effective
            # (used for line_movement/avg_movement/book_movements, moneyline-book-only by
            # definition) rather than merged into it, since Kalshi has no "open" price the same
            # way and isn't part of the last-known-live persistence built for the moneyline panel.
            consensus_inputs = dict(probs_effective)
            if pred_probs:
                consensus_inputs["Kalshi"] = sum(pred_probs) / len(pred_probs)

            # Same single-book vulnerability as get_market_snapshot -- flagged live 2026-08-17:
            # consensus_prob/book_median_prob/book_favor_diff only required 1 book, so a
            # "consensus" could silently be just whichever single book happened to be synced.
            # Model C requires at least 2 of its 6 tracked books before treating these as a real
            # signal, same threshold book_disagreement/book_prob_std already used -- a live tracker
            # polled every 30s is exactly the situation where partial coverage is common, so this
            # matters more here than anywhere else in the app.
            consensus_prob = (
                (sum(consensus_inputs.values()) / len(consensus_inputs)) if len(consensus_inputs) >= 2 else None
            )
            sharp_weighted_prob = None
            if len(consensus_inputs) >= 2:
                total_w = sum(MODEL_C_BOOK_WEIGHTS[b] for b in consensus_inputs)
                sharp_weighted_prob = sum(MODEL_C_BOOK_WEIGHTS[b] * p for b, p in consensus_inputs.items()) / total_w
            book_disagreement = (
                (max(consensus_inputs.values()) - min(consensus_inputs.values())) if len(consensus_inputs) >= 2 else None
            )
            book_median_prob = (
                statistics.median(consensus_inputs.values()) if len(consensus_inputs) >= 2 else None
            )
            book_prob_std = statistics.pstdev(consensus_inputs.values()) if len(consensus_inputs) >= 2 else None

            book_favor_diff = None
            if len(consensus_inputs) >= 2:
                favor_home = sum(1 for p in consensus_inputs.values() if p > 0.5)
                favor_away = sum(1 for p in consensus_inputs.values() if p < 0.5)
                book_favor_diff = (favor_home - favor_away) / len(consensus_inputs)

            book_movements = {
                book: probs_now[book] - probs_open[book]
                for book in probs_now if book in probs_open
            }
            book_movement_agreement = None
            if book_movements:
                toward_home = sum(1 for m in book_movements.values() if m > 0)
                toward_away = sum(1 for m in book_movements.values() if m < 0)
                book_movement_agreement = (toward_home - toward_away) / len(book_movements)

            # Kept as a Kalshi-vs-Pinnacle-specifically comparison (not vs the now-Kalshi-inclusive
            # consensus_prob above) -- still meaningful and distinct: this measures whether Kalshi
            # is an outlier relative to the market's own sharpest single book, not how much it
            # moved a blend it's now also a member of.
            prediction_market_diff = None
            if pred_probs and CLOSING_BOOK in probs_effective:
                prediction_market_diff = (sum(pred_probs) / len(pred_probs)) - probs_effective[CLOSING_BOOK]

            home_totals = [o["home_team_total"] for o in totals_panel.values() if "home_team_total" in o]
            away_totals = [o["away_team_total"] for o in totals_panel.values() if "away_team_total" in o]
            game_totals = [o["total_runs"] for o in totals_panel.values() if "total_runs" in o]
            team_total_diff = (
                (sum(home_totals) / len(home_totals)) - (sum(away_totals) / len(away_totals))
                if home_totals and away_totals else None
            )
            market_total_runs = (sum(game_totals) / len(game_totals)) if game_totals else None

            home_team = _OPTICODDS_TEAM_NAME_FIX.get(f.get("home_team_display"), f.get("home_team_display"))
            away_team = _OPTICODDS_TEAM_NAME_FIX.get(f.get("away_team_display"), f.get("away_team_display"))
            snapshot_key = (f.get("start_date"), away_team, home_team)
            if snapshot_key in snapshot:
                print(f"[get_model_c_snapshot] WARNING: duplicate snapshot key {snapshot_key!r} -- keeping first, dropping this one")
                continue
            snapshot[snapshot_key] = {
                "line_movement": line_movement,
                "avg_movement": avg_movement,
                "consensus_prob": consensus_prob,
                "sharp_weighted_prob": sharp_weighted_prob,
                "book_median_prob": book_median_prob,
                "book_prob_std": book_prob_std,
                "book_disagreement": book_disagreement,
                "book_movement_agreement": book_movement_agreement,
                "book_favor_diff": book_favor_diff,
                "book_probs": probs_now,
                "prediction_market_diff": prediction_market_diff,
                "prediction_market_probs": prediction_market_probs,
                "team_total_diff": team_total_diff,
                "market_total_runs": market_total_runs,
                "n_books": len(consensus_inputs),
            }
    except requests.exceptions.RequestException:
        pass

    raw = {f"{start_date}|||{away}|||{home}": v for (start_date, away, home), v in snapshot.items()}
    with open(cache_path, "w") as f:
        json.dump(raw, f)
    with open(last_live_path, "w") as lf:
        json.dump(last_live_by_fixture, lf)
    return snapshot


def get_line_movement(date: str = None, force_refresh: bool = False) -> dict:
    """{(start_date_utc, away_team_full_name, home_team_full_name): movement} — devigged current-minus-opening
    home win prob from CLOSING_BOOK (Pinnacle). Thin wrapper over get_market_snapshot; positive
    means the market has moved toward home since the line opened. Missing entries follow the
    same "no signal" convention as the rest of this app."""
    snapshot = get_market_snapshot(date, force_refresh)
    return {k: v["line_movement"] for k, v in snapshot.items() if v.get("line_movement") is not None}


def get_market_divergence(date: str = None, force_refresh: bool = False) -> dict:
    """{(start_date_utc, away_team_full_name, home_team_full_name): divergence} — SHARP_BOOKS' average movement
    since open minus PUBLIC_BOOKS' average movement since open. Thin wrapper over
    get_market_snapshot; positive means the sharp books have moved toward home MORE than the
    public books have — a rough proxy for "sharp money is on home, public hasn't followed," since
    OpticOdds has no actual bet-count/handle data (see PUBLIC_BOOK's docstring)."""
    snapshot = get_market_snapshot(date, force_refresh)
    return {k: v["market_divergence"] for k, v in snapshot.items() if v.get("market_divergence") is not None}


def get_consensus_odds(date: str = None, force_refresh: bool = False) -> dict:
    """{(start_date_utc, away_team_full_name, home_team_full_name): {"consensus_prob": .., "book_median_prob": ..,
    "book_prob_std": .., "book_disagreement": .., "book_movement_agreement": ..,
    "book_favor_diff": .., "book_probs": {book: devigged_home_prob}}} — consensus_prob is the
    mean devigged home win probability across CONSENSUS_BOOKS right now (not a movement/diff —
    the market's own current read on the game); book_median_prob is the same but median (robust
    to one outlier book skewing the mean); book_prob_std is the population standard deviation
    across those books (a more holistic disagreement measure than book_disagreement's max-min
    range, which only looks at the two most extreme books); book_disagreement is that max-min
    spread; book_movement_agreement is the signed fraction of those books that have moved the
    SAME direction since open (+1 = all toward home, -1 = all toward away); book_favor_diff is
    the signed fraction CURRENTLY favoring home vs. away (>50%/<50%, a different axis from the
    average probability level — one book can be far out and still not flip who's "favored");
    book_probs is the full per-book breakdown, for book-shopping display. Thin wrapper over
    get_market_snapshot."""
    snapshot = get_market_snapshot(date, force_refresh)
    return {
        k: {
            "consensus_prob": v["consensus_prob"], "book_median_prob": v.get("book_median_prob"),
            "book_prob_std": v.get("book_prob_std"), "book_disagreement": v.get("book_disagreement"),
            "book_movement_agreement": v.get("book_movement_agreement"),
            "book_favor_diff": v.get("book_favor_diff"), "book_probs": v.get("book_probs") or {},
        }
        for k, v in snapshot.items() if v.get("consensus_prob") is not None
    }


def get_prediction_market_signal(date: str = None, force_refresh: bool = False) -> dict:
    """{(start_date_utc, away_team_full_name, home_team_full_name): diff} — average devigged home prob across
    whichever of PREDICTION_MARKET_BOOKS has data for that game, minus Pinnacle's current
    devigged home prob. Thin wrapper over get_market_snapshot. Positive means the prediction
    markets are pricing home HIGHER than the sharp sportsbook right now."""
    snapshot = get_market_snapshot(date, force_refresh)
    return {
        k: v["prediction_market_diff"] for k, v in snapshot.items() if v.get("prediction_market_diff") is not None
    }


_INJURIES_CACHE_MAX_AGE_MIN = 30  # injury status doesn't change minute-to-minute like odds do


def get_active_injuries(force_refresh: bool = False) -> dict:
    """
    {team_abbr: [{"player": name, "position": pos, "status": "out"/etc., "type": injury type}]}
    for every MLB team with a currently-listed injury, straight from OpticOdds' live /injuries
    snapshot. Display-only — see the plan doc: this endpoint has no historical/date filtering
    (confirmed live: passing date/start_date params doesn't change the result), so there's no
    way to reconstruct "who was hurt on past date X" for walk-forward-safe training. Used purely
    to show the user a real-time injury report alongside each game, not fed into any feature.
    """
    if not OPTICODDS_API_KEY:
        return {}
    cache_path = os.path.join(CACHE_DIR, "active_injuries.json")
    if not force_refresh and os.path.exists(cache_path):
        age_min = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_min < _INJURIES_CACHE_MAX_AGE_MIN:
            with open(cache_path) as f:
                return json.load(f)

    name_to_abbr = _get_mlb_team_name_to_abbr()
    injuries_by_team = {}
    try:
        cursor = None
        for _ in range(20):  # hard cap on pages — a full injury report is at most a few hundred entries
            params = {"league": "MLB"}
            if cursor:
                params["cursor"] = cursor
            resp = requests.get(f"{OPTICODDS_BASE_URL}/injuries", params=params,
                                 headers={"X-Api-Key": OPTICODDS_API_KEY}, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
            for entry in payload.get("data", []):
                team_name = (entry.get("team") or {}).get("name")
                team_abbr = name_to_abbr.get(team_name)
                player = entry.get("player") or {}
                if not team_abbr or not player.get("name"):
                    continue
                injuries_by_team.setdefault(team_abbr, []).append({
                    "player": player.get("name"),
                    "position": player.get("position"),
                    "status": entry.get("status"),
                    "type": entry.get("type"),
                })
            cursor = payload.get("cursor")
            if not cursor:
                break
    except requests.exceptions.RequestException:
        pass

    with open(cache_path, "w") as f:
        json.dump(injuries_by_team, f)
    return injuries_by_team


def devig_home_prob(home_odds, away_odds):
    """American odds -> de-vigged (no-juice) implied home win probability, or None if
    either side is missing/invalid. Shared by prediction_log.py (logging what the market
    thought pre-game) and main.py (feeding the strikeout model's game-lopsidedness feature)."""
    def implied(odds):
        if odds is None:
            return None
        return 100 / (odds + 100) if odds > 0 else -odds / (-odds + 100)
    ph, pa = implied(home_odds), implied(away_odds)
    if ph is None or pa is None or (ph + pa) <= 0:
        return None
    return ph / (ph + pa)


def _cache_path(date: str) -> str:
    return os.path.join(CACHE_DIR, f"live_odds_{date}.json")


def _read_cache(date: str):
    path = _cache_path(date)
    if not os.path.exists(path):
        return None
    age_min = (time.time() - os.path.getmtime(path)) / 60
    if age_min >= _CACHE_MAX_AGE_MIN:
        return None
    with open(path) as f:
        raw = json.load(f)
    return {tuple(k.split("|||")): v for k, v in raw.items()}


def _write_cache(date: str, odds_by_matchup: dict):
    raw = {f"{start}|||{away}|||{home}": v for (start, away, home), v in odds_by_matchup.items()}
    with open(_cache_path(date), "w") as f:
        json.dump(raw, f)


def moneyline_cache_age_seconds(date: str = None):
    """Seconds since the live moneyline cache for `date` was last written, or None if it has
    never been fetched. Surfaced in /api/today so the UI can show how stale the prices behind a
    bet actually are -- a frozen bet is only as good as the market data it was priced from."""
    date = date or todays_date_et()
    path = _cache_path(date)
    if not os.path.exists(path):
        return None
    return max(0.0, time.time() - os.path.getmtime(path))


def _get_active_fixture_ids(date: str) -> list:
    """Fixture ids for unplayed MLB games on the given US-local calendar date."""
    # Games on a given US-local calendar date can start anywhere from
    # mid-afternoon to nearly midnight local, which crosses into the next
    # UTC day for evening/West-coast games — pad the window on both sides.
    #
    # BUG (fixed): this used to add timedelta(days=1, hours=12) and then format straight to a
    # date-only string via strftime("%Y-%m-%d") — the +12h component gets silently discarded by
    # that truncation (adding 12h to a midnight-aligned date just lands on noon of the SAME
    # resulting calendar date), so the "padding" never actually did anything; start_before was
    # always exactly date+1, identical to no padding at all. Caught directly: an SF@SD game
    # posted at 2026-07-31T01:40:00Z (an evening Pacific-time start) was invisible to every
    # date='2026-07-30' query — get_pitcher_market_lines, get_strikeout_prop_lines, and this
    # function's other callers all silently excluded it, well past the point real props existed
    # for it (a sportsbook already had a strikeout line up for the away starter). Fixed by
    # padding a full extra CALENDAR day (date+2) instead of a same-day time-of-day offset that a
    # date-only param can't represent — guaranteed to cover any real-world US-timezone crossing.
    start_after = date
    start_before = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=2)).strftime("%Y-%m-%d")
    # /fixtures (paginated, status-filtered client-side), NOT /fixtures/active — that endpoint
    # silently drops fixtures OpticOdds no longer considers active even while they are still
    # pre-game by our own freeze rules (measured 2026-08-22: 19 of 80 tracked game-days, ~24%).
    # This function feeds get_moneyline_odds/get_f5_odds — the calls that PRICE the frozen
    # bets — so a dropped fixture here meant a bet kept updating with no market at all. Same
    # migration get_market_snapshot/get_model_c_snapshot already made; see _fetch_fixtures_full.
    # Keeps the unplayed-only filter: this path prices pre-game bets, and an OpticOdds-"live"
    # fixture's moneyline is an in-play price we must never freeze as a pre-game line.
    try:
        fixtures = _fetch_fixtures_full(start_after, start_before, statuses=("unplayed",))
    except requests.exceptions.RequestException:
        return []
    return [f["id"] for f in fixtures]


def get_moneyline_odds(date: str = None, force_refresh: bool = False) -> dict:
    """
    Returns { (start_date_utc, away_team_full_name, home_team_full_name): {"home": american_odds,
    "away": american_odds, "bookmaker": title} } for the given date (defaults
    to today, 'YYYY-MM-DD'). Empty dict if no key is configured or the
    request fails — callers should treat that as "no live odds available"
    rather than an error. Key includes start_date_utc, not just team names, for the same
    same-day-doubleheader/multi-game-series reason as get_market_snapshot's key.
    """
    if not OPTICODDS_API_KEY:
        return {}

    date = date or todays_date_et()

    if not force_refresh:
        cached = _read_cache(date)
        if cached is not None:
            return cached

    headers = {"X-Api-Key": OPTICODDS_API_KEY}
    fixture_ids = _get_active_fixture_ids(date)
    if not fixture_ids:
        return {}

    fixtures_with_odds = []
    for i in range(0, len(fixture_ids), FIXTURE_BATCH_SIZE):
        batch = fixture_ids[i:i + FIXTURE_BATCH_SIZE]
        try:
            odds_resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures/odds", params={
                "league": "mlb",
                "market": "moneyline",
                "sportsbook": MONEYLINE_SHOP_BOOKS,
                "is_main": "true",
                "fixture_id": batch,
            }, headers=headers, timeout=20)
            odds_resp.raise_for_status()
            fixtures_with_odds.extend(odds_resp.json().get("data", []))
        except requests.exceptions.RequestException:
            continue
        # second panel purely for best-price shopping (see MONEYLINE_SHOP_BOOKS_2). Failure here
        # never blocks the primary panel above -- fewer books just means a slightly worse "best".
        try:
            odds_resp2 = requests.get(f"{OPTICODDS_BASE_URL}/fixtures/odds", params={
                "league": "mlb",
                "market": "moneyline",
                "sportsbook": MONEYLINE_SHOP_BOOKS_2,
                "is_main": "true",
                "fixture_id": batch,
            }, headers=headers, timeout=20)
            odds_resp2.raise_for_status()
            extra_by_id = {f.get("id"): f for f in odds_resp2.json().get("data", [])}
            for f in fixtures_with_odds:
                ex = extra_by_id.get(f.get("id"))
                if ex and ex.get("odds"):
                    f.setdefault("odds", []).extend(ex["odds"])
        except requests.exceptions.RequestException:
            pass
        # Third panel: Kalshi (2026-08-24, user bets there). A prediction-market contract, not a
        # bookmaker -- parsed into its own "kalshi" key below, NEVER folded into "books" (the
        # sportsbook best-price shop), because Kalshi adds a ~7%*p*(1-p) trading fee the quoted
        # price doesn't include. Same never-blocks-the-primary contract as panel 2.
        try:
            odds_resp3 = requests.get(f"{OPTICODDS_BASE_URL}/fixtures/odds", params={
                "league": "mlb",
                "market": "moneyline",
                "sportsbook": ["Kalshi"],
                "is_main": "true",
                "fixture_id": batch,
            }, headers=headers, timeout=20)
            odds_resp3.raise_for_status()
            extra_by_id3 = {f.get("id"): f for f in odds_resp3.json().get("data", [])}
            for f in fixtures_with_odds:
                ex = extra_by_id3.get(f.get("id"))
                if ex and ex.get("odds"):
                    f.setdefault("odds", []).extend(ex["odds"])
        except requests.exceptions.RequestException:
            pass

    odds_by_matchup = {}
    for fixture in fixtures_with_odds:
        home_team = fixture.get("home_team_display")
        away_team = fixture.get("away_team_display")
        start_date = fixture.get("start_date")
        odds_list = fixture.get("odds") or []
        if not home_team or not away_team or not odds_list:
            continue

        # Group by sportsbook, then use the first preferred book that has
        # both sides priced for this fixture.
        by_book = {}
        for o in odds_list:
            if o.get("market_id") != "moneyline":
                continue
            by_book.setdefault(o.get("sportsbook"), {})[o.get("name")] = o.get("price")

        for book in PREFERRED_SPORTSBOOKS:
            prices = by_book.get(book, {})
            if home_team in prices and away_team in prices:
                home_price, away_price = prices[home_team], prices[away_team]
                # A genuine two-sided moneyline essentially never prices both teams identically --
                # confirmed corrupted live: a logged -108/-108 (and, on other dates, -104/-104) for
                # the same matchup turned out to bear no resemblance to the book's real closing
                # line (+116/-126) once checked against the historical endpoint. Root cause not
                # fully traced (a live-API timing/staleness quirk on one side is the leading
                # suspect), but the fix that matters is not serving it: try the next preferred book
                # instead of returning obviously-bad data, same "no signal" fallback as a missing
                # price entirely.
                if home_price == away_price:
                    continue
                # Normalized to MLB Stats API's own team-name convention for the OUTPUT key only
                # -- home_team/away_team above must stay as OpticOdds' raw names since they're
                # used to match against odds_list's own o["name"] entries (also OpticOdds' raw
                # naming); normalizing those too would break that internal match instead of fixing
                # anything. Only the dict key main.py looks this up by needs to match MLB's names.
                #
                # Keyed by start_date too, not just team names -- same fix already applied to
                # get_market_snapshot/get_model_c_snapshot for the identical bug: the fetch window
                # spans multiple days, so any 2+ game series has the SAME (away, home) pair appear
                # more than once, and a team-name-only key let whichever fixture got processed
                # last silently overwrite the other -- confirmed live (STL@CIN, 2026-08-19):
                # tonight's real game showed a "live odds" badge that was actually tomorrow's
                # continuation game's price (-106/-110, devigging to ~49.6%) instead of tonight's
                # real ~56.7% line. Display-only (see get_market_snapshot's book_probs for what
                # actually feeds predictions), but still a real, misleading bug on its own.
                norm_home = _OPTICODDS_TEAM_NAME_FIX.get(home_team, home_team)
                norm_away = _OPTICODDS_TEAM_NAME_FIX.get(away_team, away_team)
                # Kalshi: separated from the sportsbook shop (see panel-3 comment above). The
                # contract price IS the probability (65c = 65%), so no devig -- but keep the
                # identical-price guard plus a two-sided-sum sanity window: prediction-market rows
                # through OpticOdds have shown corrupt both-sides-identical extremes before
                # (PREDICTION_MARKET_BOOKS docstring), and a pair not summing near 1.0 +/- spread
                # is that artifact, not a real market.
                kal = by_book.pop("Kalshi", None)
                kalshi = None
                if kal and home_team in kal and away_team in kal and kal[home_team] != kal[away_team]:
                    def _ap(o):
                        try:
                            o = float(o)
                        except (TypeError, ValueError):
                            return None
                        return 100.0 / (o + 100.0) if o > 0 else (-o) / ((-o) + 100.0)
                    hp, ap = _ap(kal[home_team]), _ap(kal[away_team])
                    if hp and ap and 0.90 <= hp + ap <= 1.12:
                        kalshi = {"home_prob": round(hp, 4), "away_prob": round(ap, 4),
                                  "home_cents": int(round(hp * 100)), "away_cents": int(round(ap * 100))}
                # "books": EVERY preferred book's raw two-sided price for this fixture (same
                # identical-price guard as above), not just the first one -- Model E's betting
                # layer shops the best available price per side across these (see
                # model_e.compute_bet). Additive key; every existing reader of this dict only
                # looks at home/away/bookmaker.
                books = {
                    b: {"home": pr[home_team], "away": pr[away_team]}
                    for b, pr in by_book.items()
                    if home_team in pr and away_team in pr and pr[home_team] != pr[away_team]
                }
                odds_by_matchup[(start_date, norm_away, norm_home)] = {
                    "home": home_price,
                    "away": away_price,
                    "bookmaker": book,
                    "books": books,
                    "kalshi": kalshi,
                }
                break

    _write_cache(date, odds_by_matchup)
    return odds_by_matchup


_PLAYER_PROP_LINE_KEYS = {
    "Player Strikeouts": "strikeout_line",
    "Player Outs": "outs_line",
    "Player Earned Runs": "er_line",
    "Player Hits Allowed": "hits_allowed_line",
}


def get_pitcher_market_lines(date: str = None, force_refresh: bool = False) -> dict:
    """
    {normalized_pitcher_name: {"strikeout_line":.., "outs_line":.., "er_line":..,
    "hits_allowed_line":..}} for every starter with posted PLAYER_PROP_MARKETS lines on the given
    date — the market's own per-pitcher-per-night point estimate for each stat, averaged
    (consensus) across PROP_CONSENSUS_BOOKS (see PLAYER_PROP_MARKETS' docstring on why the line
    itself, not the over/under price, is the signal). Keyed by normalize_player_name(pitcher full
    name) — callers must normalize their own lookup key the same way (see normalize_player_name's
    docstring on why: OpticOdds uses unaccented ASCII names, MLB Stats API doesn't).
    Uses /fixtures/odds/historical (via _fetch_player_prop_lines) rather than the live
    /fixtures/odds endpoint, since that's what exposes points cleanly per book — same choice
    already made for get_market_snapshot.
    """
    if not OPTICODDS_API_KEY:
        return {}
    date = date or todays_date_et()
    cache_path = os.path.join(CACHE_DIR, f"pitcher_market_lines_{date}.json")
    if not force_refresh and os.path.exists(cache_path):
        age_min = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_min < _CACHE_MAX_AGE_MIN:
            with open(cache_path) as f:
                return json.load(f)

    # +2 calendar days, not +1 day 12h — see _get_active_fixture_ids' comment on why a date-only
    # bound can't represent a same-day hour offset (it gets silently truncated away).
    end_date = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=2)).strftime("%Y-%m-%d")
    try:
        fixture_map = _fetch_fixture_map(date, end_date, statuses=("unplayed", "live", "completed"))
    except requests.exceptions.RequestException:
        return {}

    lines_by_pitcher = {}
    try:
        # /fixtures (unplayed + live) rather than /fixtures/active -- same dropped-fixture bug
        # fixed in get_market_snapshot; see _fetch_fixtures_full.
        for f in _fetch_fixtures_full(date, end_date, statuses=("unplayed", "live")):
            game_date = f["start_date"][:10]
            home_abbr = f.get("home_competitors", [{}])[0].get("abbreviation")
            away_abbr = f.get("away_competitors", [{}])[0].get("abbreviation")
            # f["id"] (this fixture's own id, straight from /fixtures/active) wins over
            # fixture_map's cross-reference -- fixture_map is keyed by (date, home_abbr,
            # away_abbr) with no time component, so a doubleheader's two fixtures collide there
            # too and it silently returns one game's id for both. Confirmed live on a real
            # STL@CIN doubleheader: fixture_map resolved BOTH the 17:40Z and 22:40Z games to the
            # same (second) fixture id. f["id"] is always fixture-specific and never ambiguous,
            # so it's the right default; fixture_map is now just a defensive fallback for the
            # (should be impossible) case where a fixture is missing its own id.
            fixture_id = f.get("id") or fixture_map.get((game_date, home_abbr, away_abbr))
            if fixture_id is None:
                continue
            by_market = _fetch_player_prop_lines(fixture_id)
            time.sleep(HISTORICAL_RATE_LIMIT_SLEEP)
            for market, key in _PLAYER_PROP_LINE_KEYS.items():
                for pitcher_name, points in by_market.get(market, {}).items():
                    lines_by_pitcher.setdefault(pitcher_name, {})[key] = points
    except requests.exceptions.RequestException:
        pass

    with open(cache_path, "w") as f:
        json.dump(lines_by_pitcher, f)
    return lines_by_pitcher


def get_strikeout_prop_lines(date: str = None, force_refresh: bool = False, sportsbooks: list = None) -> dict:
    """
    Returns {pitcher_name: {"line": 5.5, "over_price": american_odds,
    "under_price": american_odds, "bookmaker": title, "deep_link": url or
    None}} for starters with a posted strikeout prop on the given date.
    Keyed by pitcher full name (OpticOdds' own player ids don't match the
    MLB Stats API ids used throughout the rest of the app, but starter
    names are unambiguous within a single day's slate) run through
    normalize_player_name — callers must normalize their own lookup key
    the same way (see normalize_player_name's docstring).

    sportsbooks defaults to PREFERRED_SPORTSBOOKS (traditional books, first
    match wins); pass PRIZEPICKS_SPORTSBOOK to get PrizePicks' own line
    instead — see get_prizepicks_strikeout_lines.
    """
    if not OPTICODDS_API_KEY:
        return {}

    sportsbooks = sportsbooks or PREFERRED_SPORTSBOOKS
    date = date or todays_date_et()
    cache_key = "_".join(sportsbooks).lower().replace(" ", "-")
    cache_path = os.path.join(CACHE_DIR, f"strikeout_props_{date}_{cache_key}.json")

    if not force_refresh and os.path.exists(cache_path):
        age_min = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_min < _CACHE_MAX_AGE_MIN:
            with open(cache_path) as f:
                return json.load(f)

    headers = {"X-Api-Key": OPTICODDS_API_KEY}
    fixture_ids = _get_active_fixture_ids(date)
    if not fixture_ids:
        return {}

    lines_by_pitcher = {}
    for i in range(0, len(fixture_ids), FIXTURE_BATCH_SIZE):
        batch = fixture_ids[i:i + FIXTURE_BATCH_SIZE]
        try:
            resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures/odds", params={
                "league": "mlb",
                "market": "player_strikeouts",
                "sportsbook": sportsbooks,
                "is_main": "true",
                "fixture_id": batch,
            }, headers=headers, timeout=20)
            resp.raise_for_status()
            fixtures = resp.json().get("data", [])
        except requests.exceptions.RequestException:
            continue

        for fixture in fixtures:
            by_player_book = {}
            for o in fixture.get("odds") or []:
                if o.get("market_id") != "player_strikeouts":
                    continue
                player, book, side = o.get("selection"), o.get("sportsbook"), o.get("selection_line")
                if not player or not book or side not in ("over", "under"):
                    continue
                player = normalize_player_name(player)
                by_player_book.setdefault(player, {}).setdefault(book, {})[side] = o

            for player, books in by_player_book.items():
                if player in lines_by_pitcher:
                    continue
                for book in sportsbooks:
                    entry = books.get(book, {})
                    if "over" in entry and "under" in entry:
                        deep_link = (entry["over"].get("deep_link") or {}).get("desktop")
                        lines_by_pitcher[player] = {
                            "line": entry["over"].get("points"),
                            "over_price": entry["over"].get("price"),
                            "under_price": entry["under"].get("price"),
                            "bookmaker": book,
                            "deep_link": deep_link,
                        }
                        break

    with open(cache_path, "w") as f:
        json.dump(lines_by_pitcher, f)
    return lines_by_pitcher


def get_prizepicks_strikeout_lines(date: str = None, force_refresh: bool = False) -> dict:
    """PrizePicks' own strikeout line per pitcher — see get_strikeout_prop_lines."""
    return get_strikeout_prop_lines(date, force_refresh, sportsbooks=PRIZEPICKS_SPORTSBOOK)


# ============================================================================================
# First-5-innings ("1st Half") moneyline -- live prices for the F5 model (see model_f5.py)
# ============================================================================================

F5_MARKET_ID = "1st_half_moneyline"
F5_LIVE_BOOKS = PREFERRED_SPORTSBOOKS + ["Pinnacle", "Circa Sports"]  # 5 = OpticOdds per-request cap


def get_f5_odds(date: str = None, force_refresh: bool = False) -> dict:
    """
    { (start_date_utc, away_full_name, home_full_name): {"home": american, "away": american,
    "bookmaker": first preferred book with both sides, "books": {book: {"home","away"}},
    "home_prob": de-vigged consensus home F5 win prob across books} } for the given date.
    Same fixture lookup, keying, identical-price guard and team-name normalization as
    get_moneyline_odds -- only the market differs. Own cache file (f5_odds_<date>.json, same TTL)
    so it can't collide with the full-game moneyline cache. {} when no key / no fixtures.
    """
    if not OPTICODDS_API_KEY:
        return {}
    date = date or todays_date_et()
    cache_path = os.path.join(os.path.dirname(_cache_path(date)), f"f5_odds_{date}.json")
    if not force_refresh and os.path.exists(cache_path) and (time.time() - os.path.getmtime(cache_path)) / 60 < _CACHE_MAX_AGE_MIN:
        with open(cache_path) as f:
            return {tuple(k.split("|||")): v for k, v in json.load(f).items()}

    fixture_ids = _get_active_fixture_ids(date)
    if not fixture_ids:
        return {}
    headers = {"X-Api-Key": OPTICODDS_API_KEY}
    fixtures = []
    for i in range(0, len(fixture_ids), FIXTURE_BATCH_SIZE):
        try:
            resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures/odds", params={
                "league": "mlb", "market": F5_MARKET_ID, "sportsbook": F5_LIVE_BOOKS,
                "is_main": "true", "fixture_id": fixture_ids[i:i + FIXTURE_BATCH_SIZE],
            }, headers=headers, timeout=20)
            resp.raise_for_status()
            fixtures.extend(resp.json().get("data", []))
        except requests.exceptions.RequestException:
            continue

    out = {}
    for fx in fixtures:
        home, away, start = fx.get("home_team_display"), fx.get("away_team_display"), fx.get("start_date")
        by_book = {}
        for o in fx.get("odds") or []:
            if o.get("market_id") != F5_MARKET_ID:
                continue
            by_book.setdefault(o.get("sportsbook"), {})[o.get("name")] = o.get("price")
        books = {b: {"home": pr[home], "away": pr[away]} for b, pr in by_book.items()
                 if home in pr and away in pr and pr[home] != pr[away]}
        if not books:
            continue
        primary = next((b for b in F5_LIVE_BOOKS if b in books), next(iter(books)))
        probs = [p for p in (devig_home_prob(v["home"], v["away"]) for v in books.values()) if p is not None]
        out[(start, _OPTICODDS_TEAM_NAME_FIX.get(away, away), _OPTICODDS_TEAM_NAME_FIX.get(home, home))] = {
            "home": books[primary]["home"], "away": books[primary]["away"], "bookmaker": primary,
            "books": books, "home_prob": (sum(probs) / len(probs)) if probs else None,
        }
    with open(cache_path, "w") as f:
        json.dump({f"{k[0]}|||{k[1]}|||{k[2]}": v for k, v in out.items()}, f)
    return out
