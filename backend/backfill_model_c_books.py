"""
backfill_model_c_books.py

Model C needs historical LowVig + Betcris prices to train on. Four of its six books
(FanDuel/Pinnacle/Circa Sports/Kalshi) are already present in historical_market_probs.parquet
from Model B's existing backfill -- only LowVig and Betcris are genuinely new. Both fit in one
combined panel request (well under OpticOdds' 5-book/request cap), so this augments the EXISTING
historical_market_probs.parquet with 4 new columns (market_home_prob_lowvig/_open,
market_home_prob_betcris/_open) rather than building a separate file or re-fetching the 4 books
that are already cached.

Resumable: skips any game_pk that already has a non-null market_home_prob_lowvig, so an
interruption doesn't lose completed work. Uses the same doubleheader-safe fixture resolution
(_resolve_doubleheader_overrides) already fixed for the other backfill scripts.

Run directly: python backfill_model_c_books.py
"""
import os
import time

import pandas as pd

from data_collection import CACHE_DIR
from build_training_data import TRAINING_CACHE
from odds_fetcher import (
    devig_home_prob, _fetch_fixture_map, _fetch_panel_odds, HISTORICAL_RATE_LIMIT_SLEEP,
    _resolve_doubleheader_overrides,
)

ODDS_CACHE = os.path.join(CACHE_DIR, "historical_market_probs.parquet")
CHECKPOINT_EVERY = 25
MODEL_C_NEW_BOOKS = ["LowVig", "Betcris"]


def main():
    if not os.path.exists(ODDS_CACHE):
        print(f"No {ODDS_CACHE} — run backfill_historical_odds.py first.")
        return

    odds_df = pd.read_parquet(ODDS_CACHE)
    for col in ("market_home_prob_lowvig", "market_home_prob_lowvig_open",
                "market_home_prob_betcris", "market_home_prob_betcris_open"):
        if col not in odds_df.columns:
            odds_df[col] = None

    games = pd.read_parquet(TRAINING_CACHE)[["game_date", "home_team", "away_team", "game_pk"]].drop_duplicates(subset=["game_pk"])
    games = games.dropna(subset=["game_pk"])
    games = games.merge(odds_df[["game_pk"]], on="game_pk", how="inner")  # only games we already have SOME market data for

    remaining_pks = set(odds_df.loc[odds_df["market_home_prob_lowvig"].isna(), "game_pk"])
    remaining = games[games["game_pk"].isin(remaining_pks)].reset_index(drop=True)
    print(f"{len(odds_df)} games in historical_market_probs.parquet, {len(remaining)} still need LowVig/Betcris.\n")
    if remaining.empty:
        print("Nothing to do.")
        return

    start_date = remaining["game_date"].min()
    end_date = (pd.Timestamp(remaining["game_date"].max()) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"Fetching OpticOdds fixture list for {start_date}..{end_date}...")
    fixture_map = _fetch_fixture_map(start_date, end_date)
    print(f"Found {len(fixture_map)} indexed fixtures.\n")

    doubleheader_overrides = _resolve_doubleheader_overrides(remaining)
    if doubleheader_overrides:
        print(f"Resolved {len(doubleheader_overrides)} doubleheader game(s) to their correct fixture id.\n")

    odds_df = odds_df.set_index("game_pk", drop=False)
    matched = 0
    print(f"Pulling LowVig+Betcris (1 combined request/game, rate-limited, ~{HISTORICAL_RATE_LIMIT_SLEEP}s/request)...")
    for i, (_, row) in enumerate(remaining.iterrows()):
        if i % CHECKPOINT_EVERY == 0:
            print(f"  ...{i}/{len(remaining)} ({matched} matched so far)")
            odds_df.to_parquet(ODDS_CACHE)
        fixture_id = doubleheader_overrides.get(row["game_pk"]) or fixture_map.get(
            (row["game_date"], row["home_team"], row["away_team"])
        )
        pk = row["game_pk"]
        if fixture_id is not None:
            panel = _fetch_panel_odds(fixture_id, MODEL_C_NEW_BOOKS)
            time.sleep(HISTORICAL_RATE_LIMIT_SLEEP)
            found_any = False
            for book, key in (("LowVig", "lowvig"), ("Betcris", "betcris")):
                if book in panel:
                    odds_df.loc[pk, f"market_home_prob_{key}"] = devig_home_prob(panel[book].get("home"), panel[book].get("away"))
                    found_any = True
                if book in panel and "home_open" in panel[book] and "away_open" in panel[book]:
                    odds_df.loc[pk, f"market_home_prob_{key}_open"] = devig_home_prob(
                        panel[book]["home_open"], panel[book]["away_open"]
                    )
            if found_any:
                matched += 1

    odds_df.reset_index(drop=True).to_parquet(ODDS_CACHE)
    print(f"\nDone. {matched}/{len(remaining)} newly matched at least one of LowVig/Betcris -> {ODDS_CACHE}")


if __name__ == "__main__":
    main()
