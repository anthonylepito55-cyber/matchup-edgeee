"""
backfill_player_props.py

One-off backfill: pulls OpticOdds' Player Strikeouts/Outs/Earned Runs/Hits Allowed lines for
every game in data_cache/game_logs_{season}.parquet and caches each side's posted lines to
data_cache/historical_player_prop_lines.parquet, one row per game_pk with home_*/away_*-prefixed
columns. Feeds: the strikeout model's market_strikeout_line/market_outs_line/market_er_line/
market_hits_allowed_line (this pitcher's own posted lines tonight), and the win-prob model's
market_outs_line_diff/market_er_line_diff/market_hits_allowed_line_diff — see features.py.

game_logs_{season}.parquet (built by build_training_data.fetch_season_schedule_with_pitchers)
has home_pitcher_id/away_pitcher_id, not names — OpticOdds' player props are name-keyed (same
"names are unambiguous within a slate" reasoning get_strikeout_prop_lines already documents), so
this resolves each id to a name via data_collection.get_pitcher_info (MLB Stats API, free,
heavily cached already from this session's many pitcher-hand/name lookups — not the OpticOdds
rate limit).

Only 1 request/game — odds_fetcher._fetch_player_prop_lines fetches all 4 markets across all 5
CONSENSUS_BOOKS in a single combined call (OpticOdds accepts a list for both `market` and
`sportsbook` in the same request) and averages whichever books have data per pitcher/market,
a true multi-book consensus rather than a single-book-with-fallback value. Rate-limited like
backfill_historical_odds.py (~10 req/15s). Resumable: checkpoints every 25 games, skips game_pks
already cached on a re-run.

Run directly:
    python backfill_player_props.py
"""

import os
import time
import pandas as pd
from dotenv import load_dotenv

from data_collection import CACHE_DIR, get_pitcher_info
from odds_fetcher import _fetch_fixture_map, _fetch_player_prop_lines, normalize_player_name, HISTORICAL_RATE_LIMIT_SLEEP

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
OPTICODDS_API_KEY = os.environ.get("OPTICODDS_API_KEY")

OUTPUT_PATH = os.path.join(CACHE_DIR, "historical_player_prop_lines.parquet")
CHECKPOINT_EVERY = 25

_LINE_KEY_BY_MARKET = {
    "Player Strikeouts": "strikeout_line", "Player Outs": "outs_line",
    "Player Earned Runs": "er_line", "Player Hits Allowed": "hits_allowed_line",
}

# Column present in the cache only once this schema version is written — same versioned-schema-
# detection pattern as backfill_historical_odds.py.
_SCHEMA_MARKER_COLUMN = "home_outs_line"


def _empty_fields() -> dict:
    fields = {"home_pitcher_name": None, "away_pitcher_name": None}
    for side in ("home", "away"):
        for key in _LINE_KEY_BY_MARKET.values():
            fields[f"{side}_{key}"] = None
    return fields


def _load_existing() -> dict:
    """{game_pk: dict of home_*/away_* line fields} — see _save for the exact keys."""
    if not os.path.exists(OUTPUT_PATH):
        return {}
    df = pd.read_parquet(OUTPUT_PATH)
    if _SCHEMA_MARKER_COLUMN not in df.columns:
        return {}
    cols = [c for c in df.columns if c != "game_pk"]
    return {row["game_pk"]: {c: row[c] for c in cols} for _, row in df.iterrows()}


def _save(results: dict):
    df = pd.DataFrame([{"game_pk": pk, **fields} for pk, fields in results.items()])
    df.to_parquet(OUTPUT_PATH)


def _load_games() -> pd.DataFrame:
    """Every game across the cached game_logs_{season}.parquet files, with pitcher ids resolved
    to names — the join key OpticOdds' player-prop entries use."""
    frames = []
    for fname in sorted(os.listdir(CACHE_DIR)):
        if fname.startswith("game_logs_") and fname.endswith(".parquet"):
            frames.append(pd.read_parquet(os.path.join(CACHE_DIR, fname)))
    if not frames:
        raise FileNotFoundError(
            "No data_cache/game_logs_*.parquet found — run build_training_data.py first."
        )
    games = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["game_pk"])
    games = games.dropna(subset=["game_pk", "home_pitcher_id", "away_pitcher_id"])

    pitcher_ids = pd.unique(pd.concat([games["home_pitcher_id"], games["away_pitcher_id"]]))
    print(f"Resolving names for {len(pitcher_ids)} unique pitcher ids (cached MLB Stats API calls)...")
    name_by_id = {}
    for i, pid in enumerate(pitcher_ids):
        if i % 100 == 0:
            print(f"  ...{i}/{len(pitcher_ids)}")
        name_by_id[pid] = get_pitcher_info(int(pid)).get("name")

    games["home_pitcher_name"] = games["home_pitcher_id"].map(name_by_id)
    games["away_pitcher_name"] = games["away_pitcher_id"].map(name_by_id)
    return games.dropna(subset=["home_pitcher_name", "away_pitcher_name"])


def _fetch_game_fields(fixture_id: str, home_pitcher_name: str, away_pitcher_name: str) -> dict:
    fields = _empty_fields()
    fields["home_pitcher_name"] = home_pitcher_name
    fields["away_pitcher_name"] = away_pitcher_name

    # _fetch_player_prop_lines' keys are already normalize_player_name()'d (OpticOdds uses
    # unaccented ASCII names, e.g. "Carlos Rodon" vs. MLB Stats API's "Carlos Rodón") — caught
    # directly via a live smoke test where Rodón's lines came back all-None despite Peralta
    # (unaccented) matching fine in the same fixture. Normalize our own keys the same way.
    home_key = normalize_player_name(home_pitcher_name)
    away_key = normalize_player_name(away_pitcher_name)

    by_market = _fetch_player_prop_lines(fixture_id)
    time.sleep(HISTORICAL_RATE_LIMIT_SLEEP)

    for market, key in _LINE_KEY_BY_MARKET.items():
        lines = by_market.get(market, {})
        if home_key in lines:
            fields[f"home_{key}"] = lines[home_key]
        if away_key in lines:
            fields[f"away_{key}"] = lines[away_key]

    return fields


def main():
    if not OPTICODDS_API_KEY:
        print("No OPTICODDS_API_KEY configured — set it in backend/.env")
        return

    games = _load_games()
    print(f"{len(games)} unique games with resolved starter names.")

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

    print(f"Pulling player-prop lines (1 request/game, rate-limited, ~{HISTORICAL_RATE_LIMIT_SLEEP}s/request)...")
    matched = 0
    for i, (_, row) in enumerate(remaining.iterrows()):
        if i % CHECKPOINT_EVERY == 0:
            print(f"  ...{i}/{len(remaining)} ({matched} matched so far)")
            _save(results)
        fixture_id = fixture_map.get((row["game_date"], row["home_team"], row["away_team"]))
        if fixture_id is None:
            results[row["game_pk"]] = _empty_fields()
            continue
        fields = _fetch_game_fields(fixture_id, row["home_pitcher_name"], row["away_pitcher_name"])
        results[row["game_pk"]] = fields
        if fields["home_strikeout_line"] is not None or fields["away_strikeout_line"] is not None:
            matched += 1

    _save(results)
    print(f"\nDone. {matched}/{len(remaining)} newly matched. {len(results)} total cached -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
