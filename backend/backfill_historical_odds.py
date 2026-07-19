"""
backfill_historical_odds.py

One-off backfill: pulls OpticOdds opening AND closing moneyline lines for
every game in training_dataset.parquet and caches per-book devigged home
probabilities to data_cache/historical_market_probs.parquet. Feeds: the
strikeout model's team_market_win_prob (closing-line game-script/blowout
proxy), and the win-prob model's line_movement_diff (Pinnacle),
market_divergence_diff (Pinnacle vs. DraftKings movement — a reverse-line-
movement proxy), prediction_market_diff (Kalshi/Polymarket (USA) current
price vs. Pinnacle's), consensus_prob_diff (average current price across
CONSENSUS_BOOKS), and book_disagreement (spread across CONSENSUS_BOOKS) —
see features.py.

Only 3 requests/game: one 5-book CONSENSUS_BOOKS panel (Pinnacle, DraftKings,
FanDuel, BetMGM, Circa Sports — open+close each, OpticOdds' hard cap on
sportsbooks/request) via odds_fetcher._fetch_panel_odds, one 2-book
PREDICTION_MARKET_BOOKS panel (current price only — see PREDICTION_MARKET_BOOKS'
docstring on the confirmed opening-price artifact for these books), and one more
5-book CONSENSUS_BOOKS panel for Team Total/Total Runs (odds_fetcher._fetch_totals_panel) —
feeds team_total_diff/market_total_runs (see features.py).

Reuses the exact fixture-matching approach already validated in
clv_backtest.py (Task #6) rather than reinventing it, since team-abbreviation
mismatches between data sources have been a real, previously-hit bug here
(see data_collection.py's ARI/WSN/CHW/OAK fix).

Rate-limited like clv_backtest.py (~10 req/15s on the historical-odds
endpoint) — a full multi-season backfill still takes a couple hours at 2
requests/game. Resumable: writes progress every 25 games and skips
game_pks already in the cache on a re-run, so an interruption doesn't lose
completed work.

Run directly:
    python backfill_historical_odds.py
"""

import os
import time
import statistics
import requests
import pandas as pd
from dotenv import load_dotenv

from data_collection import CACHE_DIR
from build_training_data import TRAINING_CACHE
from odds_fetcher import (
    devig_home_prob, _fetch_fixture_map, _fetch_panel_odds, _fetch_totals_panel, HISTORICAL_RATE_LIMIT_SLEEP,
    CLOSING_BOOK, PUBLIC_BOOK, CONSENSUS_BOOKS, PREDICTION_MARKET_BOOKS,
)

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
OPTICODDS_API_KEY = os.environ.get("OPTICODDS_API_KEY")

OUTPUT_PATH = os.path.join(CACHE_DIR, "historical_market_probs.parquet")
CHECKPOINT_EVERY = 25

# Column present in the cache only once this schema version is written — used to force a
# full re-fetch of any cache built before the team-total/total-runs columns existed, same
# versioned-schema-detection pattern used when opening lines were added.
_SCHEMA_MARKER_COLUMN = "market_total_runs"


def _load_existing() -> dict:
    """{game_pk: dict of per-book devigged home probs} — see _save for the exact keys."""
    if not os.path.exists(OUTPUT_PATH):
        return {}
    df = pd.read_parquet(OUTPUT_PATH)
    if _SCHEMA_MARKER_COLUMN not in df.columns:
        return {}  # old-schema cache from before the market expansion — force a full re-fetch
    cols = [c for c in df.columns if c != "game_pk"]
    return {row["game_pk"]: {c: row[c] for c in cols} for _, row in df.iterrows()}


def _save(results: dict):
    df = pd.DataFrame([{"game_pk": pk, **fields} for pk, fields in results.items()])
    df.to_parquet(OUTPUT_PATH)


def _empty_fields() -> dict:
    return {
        "market_home_prob": None, "market_home_prob_open": None,
        "market_home_prob_dk": None, "market_home_prob_dk_open": None,
        "market_home_prob_kalshi": None, "market_home_prob_polymarket": None,
        "market_home_prob_consensus": None, "market_home_prob_book_disagreement": None,
        "market_home_prob_movement_agreement": None,
        "market_home_prob_median": None, "market_home_prob_std": None, "market_home_prob_favor_diff": None,
        "market_team_total_home": None, "market_team_total_away": None, "market_total_runs": None,
    }


def _fetch_game_fields(fixture_id: str) -> dict:
    """One game's worth of per-book devigged home probs — 2 rate-limited requests (a 5-book
    CONSENSUS_BOOKS panel + a 2-book PREDICTION_MARKET_BOOKS panel), down from one request per
    book — see odds_fetcher._fetch_panel_odds."""
    fields = _empty_fields()

    panel = _fetch_panel_odds(fixture_id, CONSENSUS_BOOKS)
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

    if CLOSING_BOOK in panel:
        fields["market_home_prob"] = devig_home_prob(panel[CLOSING_BOOK].get("home"), panel[CLOSING_BOOK].get("away"))
        if "home_open" in panel[CLOSING_BOOK] and "away_open" in panel[CLOSING_BOOK]:
            fields["market_home_prob_open"] = devig_home_prob(
                panel[CLOSING_BOOK]["home_open"], panel[CLOSING_BOOK]["away_open"]
            )
    if PUBLIC_BOOK in panel:
        fields["market_home_prob_dk"] = devig_home_prob(panel[PUBLIC_BOOK].get("home"), panel[PUBLIC_BOOK].get("away"))
        if "home_open" in panel[PUBLIC_BOOK] and "away_open" in panel[PUBLIC_BOOK]:
            fields["market_home_prob_dk_open"] = devig_home_prob(
                panel[PUBLIC_BOOK]["home_open"], panel[PUBLIC_BOOK]["away_open"]
            )
    if probs_now:
        fields["market_home_prob_consensus"] = sum(probs_now.values()) / len(probs_now)
        fields["market_home_prob_median"] = statistics.median(probs_now.values())
        favor_home = sum(1 for p in probs_now.values() if p > 0.5)
        favor_away = sum(1 for p in probs_now.values() if p < 0.5)
        fields["market_home_prob_favor_diff"] = (favor_home - favor_away) / len(probs_now)
    if len(probs_now) >= 2:
        fields["market_home_prob_book_disagreement"] = max(probs_now.values()) - min(probs_now.values())
        fields["market_home_prob_std"] = statistics.pstdev(probs_now.values())

    # Signed fraction of CONSENSUS_BOOKS that moved the same direction since open — see
    # odds_fetcher.get_market_snapshot's identical computation for the live-serving path.
    book_movements = {book: probs_now[book] - probs_open[book] for book in probs_now if book in probs_open}
    if book_movements:
        toward_home = sum(1 for m in book_movements.values() if m > 0)
        toward_away = sum(1 for m in book_movements.values() if m < 0)
        fields["market_home_prob_movement_agreement"] = (toward_home - toward_away) / len(book_movements)

    # Prediction markets: current price only, per PREDICTION_MARKET_BOOKS' docstring —
    # their opening-price snapshot is a confirmed artifact, never trusted.
    pred_panel = _fetch_panel_odds(fixture_id, PREDICTION_MARKET_BOOKS)
    time.sleep(HISTORICAL_RATE_LIMIT_SLEEP)
    pred_key_by_book = {"Kalshi": "market_home_prob_kalshi", "Polymarket (USA)": "market_home_prob_polymarket"}
    for book, o in pred_panel.items():
        p = devig_home_prob(o.get("home"), o.get("away"))
        if p is not None and book in pred_key_by_book:
            fields[pred_key_by_book[book]] = p

    # Team Total (each team's own projected runs) + Total Runs (game total), averaged across
    # whichever CONSENSUS_BOOKS members have each field — see odds_fetcher.get_market_snapshot's
    # identical computation for the live-serving path.
    totals_panel = _fetch_totals_panel(fixture_id, CONSENSUS_BOOKS)
    time.sleep(HISTORICAL_RATE_LIMIT_SLEEP)
    home_totals = [o["home_team_total"] for o in totals_panel.values() if "home_team_total" in o]
    away_totals = [o["away_team_total"] for o in totals_panel.values() if "away_team_total" in o]
    game_totals = [o["total_runs"] for o in totals_panel.values() if "total_runs" in o]
    if home_totals:
        fields["market_team_total_home"] = sum(home_totals) / len(home_totals)
    if away_totals:
        fields["market_team_total_away"] = sum(away_totals) / len(away_totals)
    if game_totals:
        fields["market_total_runs"] = sum(game_totals) / len(game_totals)

    return fields


def main():
    if not OPTICODDS_API_KEY:
        print("No OPTICODDS_API_KEY configured — set it in backend/.env")
        return

    df = pd.read_parquet(TRAINING_CACHE)
    games = df[["game_date", "home_team", "away_team", "game_pk"]].drop_duplicates(subset=["game_pk"])
    games = games.dropna(subset=["game_pk"])
    print(f"{len(games)} unique games in training set.")

    results = _load_existing()
    print(f"{len(results)} already cached from a prior run — skipping those.")
    remaining = games[~games["game_pk"].isin(results.keys())]
    print(f"{len(remaining)} left to fetch.\n")
    if remaining.empty:
        print("Nothing to do.")
        return

    start_date = remaining["game_date"].min()
    end_date = (pd.Timestamp(remaining["game_date"].max()) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"Fetching OpticOdds fixture list for {start_date}..{end_date}...")
    fixture_map = _fetch_fixture_map(start_date, end_date)
    print(f"Found {len(fixture_map)} indexed fixtures.\n")

    print(f"Pulling odds across {len(CONSENSUS_BOOKS) + len(PREDICTION_MARKET_BOOKS)} books/game "
          f"in 3 panel requests (rate-limited, ~{HISTORICAL_RATE_LIMIT_SLEEP}s/request)...")
    matched = 0
    for i, (_, row) in enumerate(remaining.iterrows()):
        if i % CHECKPOINT_EVERY == 0:
            print(f"  ...{i}/{len(remaining)} ({matched} matched so far)")
            _save(results)
        fixture_id = fixture_map.get((row["game_date"], row["home_team"], row["away_team"]))
        if fixture_id is None:
            results[row["game_pk"]] = _empty_fields()
            continue
        fields = _fetch_game_fields(fixture_id)
        results[row["game_pk"]] = fields
        if fields["market_home_prob"] is not None:
            matched += 1

    _save(results)
    print(f"\nDone. {matched}/{len(remaining)} newly matched. {len(results)} total cached -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
