"""Immediate serving-feature audit (2026-09-06, heavy-fav skew): z-score every frozen live
feature value against its training-build distribution. A feature consistently far outside
its training distribution (wrong scale, wrong sign, collapsed variance) is the skew culprit
-- catchable TODAY, without waiting for the odds backfill."""
import json
import sys

import numpy as np
import pandas as pd

import model_e

FEED = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\ACTSL~1.DES\AppData\Local\Temp\claude\C--Users-actsl-DESKTOP-5CTNC21-OneDrive-Documents-Desktop-mlb-predictor\1526a1fa-20df-4322-a22b-68bd03e256ae\scratchpad\today7.json"

t = json.load(open(FEED))
vecs = []
for g in t.get("games", []):
    b = g.get("model_e_bet")
    if b and b.get("features"):
        vecs.append({"game": f"{g['away_team_abbr']}@{g['home_team_abbr']}", "side_home": bool(b.get("side_is_home")),
                     "type": b.get("type"), **b["features"]})
if not vecs:
    print("no frozen feature vectors on the feed yet")
    sys.exit(0)
v = pd.DataFrame(vecs)
print(f"bets with frozen feature vectors: {len(v)}  ({t.get('date')})")

df = pd.read_parquet("data_cache/training_dataset.parquet").drop_duplicates("game_pk")
hist = df[df["game_date"].astype(str) < "2026-08-19"]

mkt_cols = [c for c in model_e.MODEL_E_FEATURE_COLUMNS if c not in model_e.MODEL_E_BASEBALL_COLUMNS]
bb_cols = model_e.MODEL_E_BASEBALL_COLUMNS
print(f"\n{'feature':<32}{'build mean':>11}{'build std':>10}{'live values (z-scores)':>40}")
for group, cols in (("MARKET", mkt_cols), ("BASEBALL", bb_cols)):
    print(f"--- {group} ---")
    for c in cols:
        h = hist[c].dropna()
        if not len(h) or c not in v.columns:
            print(f"{c:<32}  (no data)")
            continue
        mu, sd = h.mean(), h.std()
        lv = v[c]
        zs = [(x - mu) / sd if (x is not None and pd.notna(x) and sd > 0) else None for x in lv]
        ztxt = " ".join("nan" if z is None else f"{z:+.1f}" for z in zs)
        mean_z = np.nanmean([z for z in zs if z is not None]) if any(z is not None for z in zs) else float("nan")
        flag = "  <<< " if (not np.isnan(mean_z) and abs(mean_z) > 1.5) else ""
        print(f"{c:<32}{mu:>11.4f}{sd:>10.4f}   [{ztxt}]{flag}")
print("\nper-bet games:", ", ".join(v['game']))
print("z = (live value - training mean) / training std; a feature whose z's are consistently |>2| or one-signed across bets is suspect. Small slate -- catches gross mismatches, not subtle drifts.")
