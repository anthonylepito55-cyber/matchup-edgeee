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

from data_collection import CACHE_DIR, _get_mlb_team_name_to_abbr

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

OPTICODDS_API_KEY = os.environ.get("OPTICODDS_API_KEY")
OPTICODDS_BASE_URL = "https://api.opticodds.com/api/v3"

# Tried in order per fixture — not every book prices every game, so fall
# back down the list rather than showing nothing.
PREFERRED_SPORTSBOOKS = ["FanDuel", "DraftKings", "BetMGM"]

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

_CACHE_MAX_AGE_MIN = 15  # odds move fast, but this keeps us well under the free quota

# --- Historical/movement odds (opening vs current-or-closing) ---------------
#
# Shared by clv_backtest.py, backfill_historical_odds.py, and get_line_movement below —
# originally lived in clv_backtest.py alone, moved here so live serving (main.py, via
# get_line_movement) doesn't have to import that whole backtest/training-analysis script just
# to reuse two small HTTP helpers.
CLOSING_BOOK = "Pinnacle"  # the standard "sharp" reference book for closing-line value
HISTORICAL_RATE_LIMIT_SLEEP = 1.6  # stays under OpticOdds' 10 req/15s cap on /fixtures/odds/historical

# Retail counterpart to CLOSING_BOOK for get_market_divergence — when Pinnacle (sharp) and
# DraftKings (heavy public volume) move differently since open, that's a rough proxy for
# "sharp money vs. public money disagree," since OpticOdds has no actual bet-count/handle
# endpoint (confirmed: /betting-splits, /public-betting, /consensus, /handle all 404).
PUBLIC_BOOK = "DraftKings"

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

# Player-prop markets whose posted LINE (not the over/under price around it) is itself a
# specialized per-pitcher-per-night forecast — outs recorded (~depth expectation), earned runs
# and hits allowed (~run-prevention/contact-quality expectation), alongside the strikeout line
# already used elsewhere. Verified live: full historical coverage back through the 2025 season,
# same /fixtures/odds/historical endpoint. _fetch_player_prop_lines averages (consensus) across
# whichever of CONSENSUS_BOOKS has data for each pitcher/market — not every book prices every
# reliever, but the two starters are reliably covered across most/all 5 books.
PLAYER_PROP_MARKETS = ["Player Strikeouts", "Player Outs", "Player Earned Runs", "Player Hits Allowed"]


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
            fixture_map[(game_date, f["home_competitors"][0]["abbreviation"], f["away_competitors"][0]["abbreviation"])] = f["id"]
            # games starting late evening local time land on the next UTC date —
            # also index under the day before, so our MLB-Stats-API game_date
            # (which uses the local game date) still matches
            prev_date = (pd.Timestamp(game_date) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            fixture_map.setdefault(
                (prev_date, f["home_competitors"][0]["abbreviation"], f["away_competitors"][0]["abbreviation"]), f["id"]
            )
        if not payload.get("has_more"):
            break
        page += 1
    return fixture_map


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
        if home_team in prices and away_team in prices:
            result = {"home": prices[home_team], "away": prices[away_team]}
            if home_team in open_prices and away_team in open_prices:
                result["home_open"] = open_prices[home_team]
                result["away_open"] = open_prices[away_team]
            return result
    except requests.exceptions.RequestException:
        pass
    return {}


def _fetch_panel_odds(fixture_id: str, sportsbooks: list) -> dict:
    """{book: {"home":.., "away":.., "home_open":.., "away_open":..}} for up to 5 sportsbooks
    in ONE request — OpticOdds allows a list for the `sportsbook` param on
    /fixtures/odds/historical, capped at 5/call (see CONSENSUS_BOOKS). Far cheaper than one
    _fetch_closing_line call per book — get_market_snapshot below uses this instead of N
    separate requests. {} if the fixture has no data for any of the requested books."""
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
            clv = o.get("clv") or {}
            olv = o.get("olv") or {}
            if clv.get("price") is not None:
                entry[side] = clv["price"]
            if olv.get("price") is not None:
                entry[f"{side}_open"] = olv["price"]
        return {book: v for book, v in by_book.items() if "home" in v and "away" in v}
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
            points = (o.get("clv") or {}).get("points")
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
    CONSENSUS_BOOKS) that have data for that pitcher/market — one combined request for the whole
    5-book x 4-market panel (verified live: sportsbook list + market list together in one call
    works the same way the totals panel does, 60 entries back for 5 books x 4 markets x 2
    pitchers). `points` is the posted LINE (e.g. 18.5 outs, 1.5 earned runs), not the over/under
    price around it — see PLAYER_PROP_MARKETS' docstring on why the line itself is the signal.
    Reads `clv.points`, falling back to `olv.points` if a fixture has no current price yet.
    Markets/pitchers with no data from any book end up absent from the returned dict entirely —
    same "no signal" convention as everywhere else in this app. Keys are run through
    normalize_player_name — see its docstring for why."""
    markets = markets or PLAYER_PROP_MARKETS
    sportsbooks = sportsbooks or CONSENSUS_BOOKS

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
    {(away_team_full_name, home_team_full_name): {
        "line_movement": .., "market_divergence": .., "consensus_prob": ..,
        "book_disagreement": .., "book_probs": {book: devigged_home_prob},
        "prediction_market_diff": ..,
    }} — the single shared fetch behind get_line_movement/get_market_divergence/
    get_consensus_odds/get_prediction_market_signal below (all thin wrappers over this), so a
    request needing several of these fields doesn't pay for the same panel twice. Two API calls
    per game: one 5-book CONSENSUS_BOOKS panel (covers line movement, divergence, consensus,
    book-by-book — CLOSING_BOOK/PUBLIC_BOOK are both members), one 2-book PREDICTION_MARKET_BOOKS
    panel. Any field can be missing/absent per game — same "NaN means no signal" convention as
    everywhere else in this app, not an error.
    """
    if not OPTICODDS_API_KEY:
        return {}
    date = date or datetime.now().strftime("%Y-%m-%d")
    cache_path = os.path.join(CACHE_DIR, f"market_snapshot_{date}.json")
    if not force_refresh and os.path.exists(cache_path):
        age_min = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_min < _CACHE_MAX_AGE_MIN:
            with open(cache_path) as f:
                raw = json.load(f)
            return {tuple(k.split("|||")): v for k, v in raw.items()}

    end_date = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1, hours=12)).strftime("%Y-%m-%d")
    try:
        fixture_map = _fetch_fixture_map(date, end_date, statuses=("unplayed", "live", "completed"))
    except requests.exceptions.RequestException:
        return {}

    fixtures_resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures/active", params={
        "league": "mlb", "start_date_after": date, "start_date_before": end_date,
    }, headers={"X-Api-Key": OPTICODDS_API_KEY}, timeout=15)
    snapshot = {}
    try:
        fixtures_resp.raise_for_status()
        for f in fixtures_resp.json().get("data", []):
            game_date = f["start_date"][:10]
            home_abbr = f.get("home_competitors", [{}])[0].get("abbreviation")
            away_abbr = f.get("away_competitors", [{}])[0].get("abbreviation")
            fixture_id = fixture_map.get((game_date, home_abbr, away_abbr)) or f.get("id")
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

            market_divergence = None
            if CLOSING_BOOK in probs_now and CLOSING_BOOK in probs_open and \
                    PUBLIC_BOOK in probs_now and PUBLIC_BOOK in probs_open:
                market_divergence = (
                    (probs_now[CLOSING_BOOK] - probs_open[CLOSING_BOOK])
                    - (probs_now[PUBLIC_BOOK] - probs_open[PUBLIC_BOOK])
                )

            consensus_prob = (sum(probs_now.values()) / len(probs_now)) if probs_now else None
            book_disagreement = (max(probs_now.values()) - min(probs_now.values())) if len(probs_now) >= 2 else None

            # Median (robust to one outlier book skewing the mean) and population std (a more
            # holistic disagreement measure than book_disagreement's max-min range, which is
            # driven entirely by the two most extreme books and ignores everything in between).
            book_median_prob = statistics.median(probs_now.values()) if probs_now else None
            book_prob_std = statistics.pstdev(probs_now.values()) if len(probs_now) >= 2 else None

            # Signed fraction of CONSENSUS_BOOKS currently favoring home vs. away (>50%/<50%) —
            # distinct from consensus_prob_diff (the average PROBABILITY LEVEL, which one extreme
            # book can skew) and from book_movement_agreement (about movement direction, not
            # current-price side). +1.0 = every book favors home right now, -1.0 = every book
            # favors away.
            book_favor_diff = None
            if probs_now:
                favor_home = sum(1 for p in probs_now.values() if p > 0.5)
                favor_away = sum(1 for p in probs_now.values() if p < 0.5)
                book_favor_diff = (favor_home - favor_away) / len(probs_now)

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
            # PREDICTION_MARKET_BOOKS' docstring on the confirmed opening-price artifact.
            pred_probs = []
            for book, o in pred_panel.items():
                p = devig_home_prob(o.get("home"), o.get("away"))
                if p is not None:
                    pred_probs.append(p)
            prediction_market_diff = None
            if pred_probs and CLOSING_BOOK in probs_now:
                prediction_market_diff = (sum(pred_probs) / len(pred_probs)) - probs_now[CLOSING_BOOK]

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

            home_team = f.get("home_team_display")
            away_team = f.get("away_team_display")
            snapshot[(away_team, home_team)] = {
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
                "team_total_diff": team_total_diff,
                "market_total_runs": market_total_runs,
            }
    except requests.exceptions.RequestException:
        pass

    raw = {f"{away}|||{home}": v for (away, home), v in snapshot.items()}
    with open(cache_path, "w") as f:
        json.dump(raw, f)
    return snapshot


def get_line_movement(date: str = None, force_refresh: bool = False) -> dict:
    """{(away_team_full_name, home_team_full_name): movement} — devigged current-minus-opening
    home win prob from CLOSING_BOOK (Pinnacle). Thin wrapper over get_market_snapshot; positive
    means the market has moved toward home since the line opened. Missing entries follow the
    same "no signal" convention as the rest of this app."""
    snapshot = get_market_snapshot(date, force_refresh)
    return {k: v["line_movement"] for k, v in snapshot.items() if v.get("line_movement") is not None}


def get_market_divergence(date: str = None, force_refresh: bool = False) -> dict:
    """{(away_team_full_name, home_team_full_name): divergence} — Pinnacle's movement since open
    minus DraftKings' movement since open. Thin wrapper over get_market_snapshot; positive means
    the sharp book has moved toward home MORE than the retail book has — a rough proxy for
    "sharp money is on home, public hasn't followed," since OpticOdds has no actual bet-count/
    handle data (see PUBLIC_BOOK's docstring)."""
    snapshot = get_market_snapshot(date, force_refresh)
    return {k: v["market_divergence"] for k, v in snapshot.items() if v.get("market_divergence") is not None}


def get_consensus_odds(date: str = None, force_refresh: bool = False) -> dict:
    """{(away_team_full_name, home_team_full_name): {"consensus_prob": .., "book_median_prob": ..,
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
    """{(away_team_full_name, home_team_full_name): diff} — average devigged home prob across
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
    raw = {f"{away}|||{home}": v for (away, home), v in odds_by_matchup.items()}
    with open(_cache_path(date), "w") as f:
        json.dump(raw, f)


def _get_active_fixture_ids(date: str) -> list:
    """Fixture ids for unplayed MLB games on the given US-local calendar date."""
    headers = {"X-Api-Key": OPTICODDS_API_KEY}
    # Games on a given US-local calendar date can start anywhere from
    # mid-afternoon to nearly midnight local, which crosses into the next
    # UTC day for evening/West-coast games — pad the window on both sides.
    start_after = date
    start_before = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1, hours=12)).strftime("%Y-%m-%d")
    try:
        fixtures_resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures/active", params={
            "league": "mlb", "start_date_after": start_after, "start_date_before": start_before,
        }, headers=headers, timeout=15)
        fixtures_resp.raise_for_status()
        fixtures = fixtures_resp.json().get("data", [])
    except requests.exceptions.RequestException:
        return []
    return [f["id"] for f in fixtures if f.get("status") == "unplayed"]


def get_moneyline_odds(date: str = None, force_refresh: bool = False) -> dict:
    """
    Returns { (away_team_full_name, home_team_full_name): {"home": american_odds,
    "away": american_odds, "bookmaker": title} } for the given date (defaults
    to today, 'YYYY-MM-DD'). Empty dict if no key is configured or the
    request fails — callers should treat that as "no live odds available"
    rather than an error.
    """
    if not OPTICODDS_API_KEY:
        return {}

    date = date or datetime.now().strftime("%Y-%m-%d")

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
                "sportsbook": PREFERRED_SPORTSBOOKS,
                "is_main": "true",
                "fixture_id": batch,
            }, headers=headers, timeout=20)
            odds_resp.raise_for_status()
            fixtures_with_odds.extend(odds_resp.json().get("data", []))
        except requests.exceptions.RequestException:
            continue

    odds_by_matchup = {}
    for fixture in fixtures_with_odds:
        home_team = fixture.get("home_team_display")
        away_team = fixture.get("away_team_display")
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
                odds_by_matchup[(away_team, home_team)] = {
                    "home": prices[home_team],
                    "away": prices[away_team],
                    "bookmaker": book,
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
    (consensus) across CONSENSUS_BOOKS (see PLAYER_PROP_MARKETS' docstring on why the line
    itself, not the over/under price, is the signal). Keyed by normalize_player_name(pitcher full
    name) — callers must normalize their own lookup key the same way (see normalize_player_name's
    docstring on why: OpticOdds uses unaccented ASCII names, MLB Stats API doesn't).
    Uses /fixtures/odds/historical (via _fetch_player_prop_lines) rather than the live
    /fixtures/odds endpoint, since that's what exposes points cleanly per book — same choice
    already made for get_market_snapshot.
    """
    if not OPTICODDS_API_KEY:
        return {}
    date = date or datetime.now().strftime("%Y-%m-%d")
    cache_path = os.path.join(CACHE_DIR, f"pitcher_market_lines_{date}.json")
    if not force_refresh and os.path.exists(cache_path):
        age_min = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_min < _CACHE_MAX_AGE_MIN:
            with open(cache_path) as f:
                return json.load(f)

    end_date = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1, hours=12)).strftime("%Y-%m-%d")
    try:
        fixture_map = _fetch_fixture_map(date, end_date, statuses=("unplayed", "live", "completed"))
    except requests.exceptions.RequestException:
        return {}

    lines_by_pitcher = {}
    try:
        fixtures_resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures/active", params={
            "league": "mlb", "start_date_after": date, "start_date_before": end_date,
        }, headers={"X-Api-Key": OPTICODDS_API_KEY}, timeout=15)
        fixtures_resp.raise_for_status()
        for f in fixtures_resp.json().get("data", []):
            game_date = f["start_date"][:10]
            home_abbr = f.get("home_competitors", [{}])[0].get("abbreviation")
            away_abbr = f.get("away_competitors", [{}])[0].get("abbreviation")
            fixture_id = fixture_map.get((game_date, home_abbr, away_abbr)) or f.get("id")
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
    date = date or datetime.now().strftime("%Y-%m-%d")
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
