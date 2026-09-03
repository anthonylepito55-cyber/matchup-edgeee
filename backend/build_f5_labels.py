"""
build_f5_labels.py -- first-5-innings outcome for every game in training_dataset.parquet,
from the MLB Stats API linescore (free, per-inning runs). Feeds the F5 model (see model_f5.py):
"1st Half Moneyline" on OpticOdds is the first-5-innings winner, a thinner market that prices
almost exactly what this app's features measure (the two starters), without the bullpen/late-
inning noise the full-game line carries.

Output: data_cache/f5_labels.parquet with one row per game_pk:
    f5_home_runs, f5_away_runs   runs through the end of the 5th inning
    f5_home_win                  1 home led after 5, 0 away led, None = tied after 5 (a push
                                 on a 2-way F5 line; excluded from the binary training label)
    innings_played               sanity: games shortened before 5 innings are dropped

Resumable: skips game_pks already cached. ~6,700 games, threaded; a few minutes.
Run: python build_f5_labels.py
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

from build_training_data import TRAINING_CACHE
from data_collection import CACHE_DIR

OUT_PATH = os.path.join(CACHE_DIR, "f5_labels.parquet")
MLB = "https://statsapi.mlb.com/api/v1"
WORKERS = 8


def fetch_one(game_pk: int) -> dict | None:
    for attempt in range(3):
        try:
            r = requests.get(f"{MLB}/game/{game_pk}/linescore", timeout=20)
            r.raise_for_status()
            innings = r.json().get("innings", [])
            break
        except requests.exceptions.RequestException:
            time.sleep(1.5 * (attempt + 1))
    else:
        return None
    if len(innings) < 5:
        return {"game_pk": game_pk, "f5_home_runs": None, "f5_away_runs": None, "f5_home_win": None,
                "innings_played": len(innings)}
    h = sum(int((i.get("home") or {}).get("runs") or 0) for i in innings[:5])
    a = sum(int((i.get("away") or {}).get("runs") or 0) for i in innings[:5])
    return {"game_pk": game_pk, "f5_home_runs": h, "f5_away_runs": a,
            "f5_home_win": (1 if h > a else 0) if h != a else None, "innings_played": len(innings)}


def main():
    pks = pd.read_parquet(TRAINING_CACHE)["game_pk"].dropna().astype(int).unique().tolist()
    done = pd.read_parquet(OUT_PATH) if os.path.exists(OUT_PATH) else pd.DataFrame()
    have = set(done["game_pk"].astype(int)) if len(done) else set()
    todo = [pk for pk in pks if pk not in have]
    print(f"{len(pks)} games in training set, {len(have)} cached, {len(todo)} to fetch", flush=True)
    rows, t0 = [], time.time()
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = {ex.submit(fetch_one, pk): pk for pk in todo}
        for i, f in enumerate(as_completed(futs), 1):
            res = f.result()
            if res:
                rows.append(res)
            if i % 500 == 0:
                print(f"  {i}/{len(todo)} ({time.time()-t0:.0f}s)", flush=True)
                pd.concat([done, pd.DataFrame(rows)], ignore_index=True).to_parquet(OUT_PATH)
    out = pd.concat([done, pd.DataFrame(rows)], ignore_index=True).drop_duplicates("game_pk")
    out.to_parquet(OUT_PATH)
    dec = out["f5_home_win"].notna().sum()
    print(f"done: {len(out)} rows, {dec} decided after 5, {int(out['f5_home_win'].isna().sum())} ties/short -> {OUT_PATH}")
    print("home F5 win rate (decided):", round(out["f5_home_win"].dropna().mean(), 4))


if __name__ == "__main__":
    main()
