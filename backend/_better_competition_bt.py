"""BETTER-COMPETITION BACKTEST (2026-10-08, user: "backtest whether the person that
plays better competition wins as an underdog or a favorite, roi after").

DEFINITION (as-of, no leakage): for each player/match, the MEDIAN RANK OF THEIR LAST 10
OPPONENTS *before* this match (the same `oppq` the live model computes in
tennis_model_a._profile). Lower median rank = tougher recent schedule. The player with
the lower median is "the one who plays better competition"; the gap is how much tougher.

Then: back that player, split by whether they are the market DOG or the FAVORITE, by
gender (true gender from the slug map), by price band, and by how big the schedule gap
is. Flat 1u at the archive's own closing odds. 2024-26.
"""
import numpy as np
import pandas as pd

import tennis_model_a as T

m = T._parse(pd.read_parquet(T.LOGS_PARQUET))
m["date"] = pd.to_datetime(m["date"]).dt.normalize()
m = m.sort_values(["player_slug", "date"], kind="stable").reset_index(drop=True)

# as-of median rank of the last 10 opponents, STRICTLY before this match
g = m.groupby("player_slug", sort=False)["rival_rank"]
m["oppq"] = g.apply(lambda s: s.shift(1).rolling(10, min_periods=4).median()).reset_index(level=0, drop=True)
cnt = g.apply(lambda s: s.shift(1).rolling(10, min_periods=4).count()).reset_index(level=0, drop=True)
m["oppq_n"] = cnt

GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
m["gen"] = m["player_slug"].astype(str).map(GM).fillna("?")

# one row per match: keep the lexicographically-first side, join the rival's oppq
side = m[["date", "player_slug", "rival_slugname", "player_odd", "rival_odd", "won",
          "oppq", "oppq_n", "gen", "tournament_level"]].copy()
side["rival_slugname"] = side["rival_slugname"].astype(str)
riv = side[["date", "player_slug", "oppq", "oppq_n"]].rename(
    columns={"player_slug": "rival_slugname", "oppq": "oppq_r", "oppq_n": "oppq_rn"})
riv = riv.drop_duplicates(["date", "rival_slugname"])
D = side.merge(riv, on=["date", "rival_slugname"], how="inner")
D = D[(D["player_slug"].astype(str) < D["rival_slugname"])]
D = D[D["oppq"].notna() & D["oppq_r"].notna() & (D["oppq_n"] >= 6) & (D["oppq_rn"] >= 6)]
D = D[D["player_odd"].notna() & D["rival_odd"].notna()
      & (D["player_odd"] > 1) & (D["rival_odd"] > 1) & (D["gen"] != "?")]
D["year"] = D["date"].dt.year
D = D[D["year"] >= 2024]
print(f"matches with as-of schedule quality for BOTH players: {len(D)}", flush=True)

i1, i2 = 1.0 / D["player_odd"], 1.0 / D["rival_odd"]
D["mkt"] = i1 / (i1 + i2)                      # no-vig prob for the row's player
# "tougher schedule" side = lower median opponent rank
tough_is_p = (D["oppq"] < D["oppq_r"]).values
gap = np.abs(D["oppq"].values - D["oppq_r"].values)
t_odds = np.where(tough_is_p, D["player_odd"], D["rival_odd"])
t_won = np.where(tough_is_p, D["won"].astype(bool), ~D["won"].astype(bool))
t_mkt = np.where(tough_is_p, D["mkt"], 1 - D["mkt"])
t_is_dog = t_mkt < 0.5
W = (D["gen"] == "W").values


def rep(label, mask, floor=40):
    k = int(mask.sum())
    if k < floor:
        print(f"  {label:44s} n={k} (thin)")
        return
    o, w = t_odds[mask], t_won[mask]
    pnl = np.where(w, o - 1.0, -1.0)
    print(f"  {label:44s} {int(w.sum())}-{int((~w).sum())}  win {100*w.mean():.1f}%  "
          f"ROI {100*pnl.mean():+.1f}%  (n={k})")


print("\n=== BACK THE TOUGHER-SCHEDULE PLAYER ===")
for gl, gm in (("MEN", ~W), ("WOMEN", W)):
    print(f"-- {gl} --")
    rep("as the UNDERDOG (all dog prices)", gm & t_is_dog)
    rep("  dog +100..+200", gm & t_is_dog & (t_odds >= 2.0) & (t_odds <= 3.0))
    rep("  dog +200..+400", gm & t_is_dog & (t_odds > 3.0) & (t_odds <= 5.0))
    rep("as the FAVORITE (all fav prices)", gm & ~t_is_dog)
    rep("  fav -100..-200", gm & ~t_is_dog & (t_odds >= 1.5) & (t_odds <= 2.0))
    rep("  fav -200..-400", gm & ~t_is_dog & (t_odds >= 1.25) & (t_odds < 1.5))
print("-- gap size (both genders, dog side) --")
for lo, hi, lab in ((0, 25, "gap <25 ranks"), (25, 75, "gap 25-75"),
                    (75, 150, "gap 75-150"), (150, 1e9, "gap 150+")):
    rep(f"dog, {lab}", t_is_dog & (gap >= lo) & (gap < hi))
print("-- gap size (both genders, favorite side) --")
for lo, hi, lab in ((0, 25, "gap <25 ranks"), (25, 75, "gap 25-75"),
                    (75, 150, "gap 75-150"), (150, 1e9, "gap 150+")):
    rep(f"fav, {lab}", ~t_is_dog & (gap >= lo) & (gap < hi))
print("\n-- control: back the WEAKER-schedule player --")
for gl, gm in (("MEN", ~W), ("WOMEN", W)):
    o = np.where(tough_is_p, D["rival_odd"], D["player_odd"])
    w = np.where(tough_is_p, ~D["won"].astype(bool), D["won"].astype(bool))
    for lab, mask in ((f"{gl}: weaker-schedule side as dog", gm & ~t_is_dog),
                      (f"{gl}: weaker-schedule side as fav", gm & t_is_dog)):
        k = int(mask.sum())
        if k < 40:
            continue
        pnl = np.where(w[mask], o[mask] - 1.0, -1.0)
        print(f"  {lab:44s} {int(w[mask].sum())}-{int((~w[mask]).sum())}  "
              f"win {100*w[mask].mean():.1f}%  ROI {100*pnl.mean():+.1f}%  (n={k})")
print("\n-- by year (dog side, both genders) --")
for y in (2024, 2025, 2026):
    rep(f"dog, {y}", t_is_dog & (D["year"] == y).values)
