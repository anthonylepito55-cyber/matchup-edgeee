"""
backfill_f5_odds.py -- historical FIRST-5-INNINGS moneyline prices ("1st Half Moneyline" on
OpticOdds) for every game in training_dataset.parquet, so the F5 model (model_f5.py) can be
backtested against its OWN market, not the full-game line. Verified live 2026-08-20 that the
historical endpoint serves this market with both clv (close) and olv (open) for settled 2026
games (DraftKings + FanDuel; Pinnacle requested too where present).

Output: data_cache/f5_market_probs.parquet, one row per game_pk:
    f5_market_home_prob        de-vigged home F5 win prob, average of books' CLOSE prices
    f5_market_home_prob_open   same from OPEN prices
    f5_books                   how many books priced it
    f5_<book>_home/away        raw american close prices per book (for realistic ROI later)

One request per game, HISTORICAL_RATE_LIMIT_SLEEP-paced like the other backfills; resumable
(skips cached game_pks, checkpoints every 25). ~6,700 games ~= 1h. 2024 will come back empty
(OpticOdds has no 2024 odds at all -- see project memory), same as the full-game backfill.
Run: python backfill_f5_odds.py
"""
import os
import time

import pandas as pd
import requests

from build_training_data import TRAINING_CACHE
from data_collection import CACHE_DIR
from odds_fetcher import (
    HISTORICAL_RATE_LIMIT_SLEEP, OPTICODDS_API_KEY, OPTICODDS_BASE_URL, _fetch_fixture_map,
    _resolve_doubleheader_overrides, devig_home_prob,
)

OUT_PATH = os.path.join(CACHE_DIR, "f5_market_probs.parquet")
F5_MARKET = "1st Half Moneyline"
F5_BOOKS = ["Pinnacle", "DraftKings", "FanDuel"]
CHECKPOINT_EVERY = 25


def fetch_f5(fixture_id: str) -> dict:
    out = {"f5_market_home_prob": None, "f5_market_home_prob_open": None, "f5_books": 0}
    try:
        resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures/odds/historical", params={
            "fixture_id": fixture_id, "sportsbook": F5_BOOKS, "market": F5_MARKET, "odds_format": "american",
        }, headers={"X-Api-Key": OPTICODDS_API_KEY}, timeout=25)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except requests.exceptions.RequestException:
        return out
    if not data:
        return out
    fx = data[0]
    home, away = fx.get("home_team_display"), fx.get("away_team_display")
    by_book = {}
    for o in fx.get("odds", []):
        b = o.get("sportsbook")
        side = "home" if o.get("name") == home else "away" if o.get("name") == away else None
        if not side:
            continue
        d = by_book.setdefault(b, {})
        if (o.get("clv") or {}).get("price") is not None:
            d[side] = o["clv"]["price"]
        if (o.get("olv") or {}).get("price") is not None:
            d[side + "_open"] = o["olv"]["price"]
    close_probs, open_probs = [], []
    for b, d in by_book.items():
        if "home" in d and "away" in d and d["home"] != d["away"]:
            p = devig_home_prob(d["home"], d["away"])
            if p is not None:
                close_probs.append(p)
                out[f"f5_{b.lower().replace(' ', '_')}_home"] = d["home"]
                out[f"f5_{b.lower().replace(' ', '_')}_away"] = d["away"]
        if "home_open" in d and "away_open" in d and d["home_open"] != d["away_open"]:
            p = devig_home_prob(d["home_open"], d["away_open"])
            if p is not None:
                open_probs.append(p)
    if close_probs:
        out["f5_market_home_prob"] = sum(close_probs) / len(close_probs)
        out["f5_books"] = len(close_probs)
    if open_probs:
        out["f5_market_home_prob_open"] = sum(open_probs) / len(open_probs)
    return out


def main():
    if not OPTICODDS_API_KEY:
        print("No OPTICODDS_API_KEY"); return
    games = pd.read_parquet(TRAINING_CACHE)[["game_date", "home_team", "away_team", "game_pk"]].drop_duplicates("game_pk").dropna(subset=["game_pk"])
    # 2024 has no odds upstream at all -- don't spend an hour confirming it again
    games = games[games["game_date"].astype(str) >= "2025-01-01"]
    results = {}
    if os.path.exists(OUT_PATH):
        old = pd.read_parquet(OUT_PATH)
        results = {int(r["game_pk"]): {c: r[c] for c in old.columns if c != "game_pk"} for _, r in old.iterrows()}
    remaining = games[~games["game_pk"].astype(int).isin(results.keys())]
    print(f"{len(games)} 2025+ games, {len(results)} cached, {len(remaining)} to fetch", flush=True)
    if remaining.empty:
        return
    fixture_map = _fetch_fixture_map(remaining["game_date"].min(),
                                     (pd.Timestamp(remaining["game_date"].max()) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    overrides = _resolve_doubleheader_overrides(remaining)
    matched = 0
    for i, (_, row) in enumerate(remaining.iterrows()):
        if i % CHECKPOINT_EVERY == 0:
            print(f"  ...{i}/{len(remaining)} ({matched} with F5 prices)", flush=True)
            pd.DataFrame([{"game_pk": pk, **f} for pk, f in results.items()]).to_parquet(OUT_PATH)
        fid = overrides.get(row["game_pk"]) or fixture_map.get((row["game_date"], row["home_team"], row["away_team"]))
        fields = fetch_f5(fid) if fid else {"f5_market_home_prob": None, "f5_market_home_prob_open": None, "f5_books": 0}
        time.sleep(HISTORICAL_RATE_LIMIT_SLEEP)
        results[int(row["game_pk"])] = fields
        if fields["f5_market_home_prob"] is not None:
            matched += 1
    pd.DataFrame([{"game_pk": pk, **f} for pk, f in results.items()]).to_parquet(OUT_PATH)
    print(f"done: {matched}/{len(remaining)} newly matched, {len(results)} cached -> {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
