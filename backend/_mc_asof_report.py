"""Report every sim cell from the as-of backtest rows (2026-10-08).
Reads data_cache/_mc_asof_bt_rows.parquet (written by _mc_asof_bt.py).
Cells: green bait (3-sim proxy) x c75-flip gate, c75/c50/serve-MC dogs and
favorite bands, all split by TRUE gender.
"""
import sys

import numpy as np
import pandas as pd

D = pd.read_parquet("data_cache/_mc_asof_bt_rows.parquet")
D = D[D[["mc1_serve", "c50", "c75"]].notna().all(axis=1)].copy()
print(f"as-of simulated matches: {len(D)}  ({int(D['isW'].sum())} women, "
      f"{len(D) - int(D['isW'].sum())} men)\n")

fav1 = (D["mkt"] >= 0.5).values
mkt_fav = np.where(fav1, D["mkt"], 1 - D["mkt"])
disc = np.where(D["isW"], 0.04, 0.06)
simfav = {c: np.where(fav1, D[c], 1 - D[c]) for c in ("mc1_serve", "c50", "c75")}
G = np.vstack([mkt_fav - simfav[c] for c in simfav])
green = (G >= disc).all(axis=0)
flip75 = simfav["c75"] < 0.5
dog_od = np.where(fav1, D["ob"], D["oa"])
fav_od = np.where(fav1, D["oa"], D["ob"])
dog_won = np.where(fav1, ~D["won"].astype(bool), D["won"].astype(bool))
band = (dog_od >= 2.0) & (dog_od <= 3.0)
W = D["isW"].values


def rep(label, mask, od, won, floor=25):
    k = int(mask.sum())
    if k < floor:
        print(f"  {label:38s} n={k} (thin)")
        return
    o, w = od[mask], won[mask]
    pnl = np.where(w, o - 1.0, -1.0)
    print(f"  {label:38s} {int(w.sum())}-{int((~w).sum())}  win {100*w.mean():.1f}%  "
          f"ROI {100*pnl.mean():+.1f}%  (n={k})")


print("=== GREEN BAIT CELL x MC GATE (bet the dog, +100..+200) ===")
for gl, gm in (("MEN", ~W), ("WOMEN", W)):
    print(f"-- {gl} --")
    rep("green cell (all)", green & band & gm, dog_od, dog_won)
    rep("green + c75 FLIPS  [the gate]", green & band & gm & flip75, dog_od, dog_won)
    rep("green + c75 no flip [NO BET]", green & band & gm & ~flip75, dog_od, dog_won)
    rep("control: band dogs, no signal", band & gm & ~green, dog_od, dog_won)
    rep("control: out-of-band +200/+400", green & gm & (dog_od > 3.0) & (dog_od <= 5.0), dog_od, dog_won)
print("-- COMBINED --")
rep("green + c75 FLIPS", green & band & flip75, dog_od, dog_won)
rep("green + c75 no flip", green & band & ~flip75, dog_od, dog_won)

print("\n=== EACH SIM: DOG SIDE ===")
for col in ("c75", "c50", "mc1_serve"):
    pick_dog = simfav[col] < 0.5
    for gl, gm in (("MEN", ~W), ("WOMEN", W)):
        rep(f"{col:10s} {gl:5s} dog +100..+200", pick_dog & band & gm, dog_od, dog_won)

print("\n=== EACH SIM: FAVORITE SIDE BY BAND ===")
BANDS = (("-100..-150", 1.667, 2.0), ("-150..-200", 1.5, 1.667),
         ("-200..-250", 1.4, 1.5), ("-250..-300", 1.333, 1.4))
fav_won = np.where(fav1, D["won"].astype(bool), ~D["won"].astype(bool))
for col in ("c75", "c50", "mc1_serve"):
    pick_fav = simfav[col] >= 0.5
    for gl, gm in (("MEN", ~W), ("WOMEN", W)):
        for lab, lo, hi in BANDS:
            rep(f"{col:10s} {gl:5s} fav {lab}",
                pick_fav & gm & (fav_od >= lo) & (fav_od <= hi), fav_od, fav_won)
