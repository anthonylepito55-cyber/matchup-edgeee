"""OPPONENT-QUALITY, RANK-FREE (2026-10-08 follow-up): the rank version of the
better-competition test could be an artifact -- rival_rank is missing/stale at ITF
level. This repeats it with the measure Model D v4 actually uses: each opponent judged
by THEIR OWN prior any-surface last-10 win rate (no ranks at all), averaged over a
player's last 10 matches, computed strictly as-of.
"""
import numpy as np
import pandas as pd

import tennis_model_a as T

m = T._parse(pd.read_parquet(T.LOGS_PARQUET))
m["date"] = pd.to_datetime(m["date"]).dt.normalize()
m = m.sort_values(["player_slug", "date"], kind="stable").reset_index(drop=True)
# each row: the player's own prior L10 win rate (shifted -> as-of)
g = m.groupby("player_slug", sort=False)["won"]
m["own_l10"] = g.apply(lambda s: s.shift(1).rolling(10, min_periods=4).mean()).reset_index(level=0, drop=True)
# publish it as "the opponent's strength" for the rival's row
opp = m[["date", "player_slug", "own_l10"]].rename(
    columns={"player_slug": "rival_slugname", "own_l10": "opp_strength"})
opp["rival_slugname"] = opp["rival_slugname"].astype(str)
opp = opp.drop_duplicates(["date", "rival_slugname"])
m["rival_slugname"] = m["rival_slugname"].astype(str)
m = m.merge(opp, on=["date", "rival_slugname"], how="left")
# a player's recent SCHEDULE strength = mean opp_strength over their last 10, as-of
g2 = m.groupby("player_slug", sort=False)["opp_strength"]
m["sched"] = g2.apply(lambda s: s.shift(1).rolling(10, min_periods=5).mean()).reset_index(level=0, drop=True)
m["sched_n"] = g2.apply(lambda s: s.shift(1).rolling(10, min_periods=5).count()).reset_index(level=0, drop=True)
print(f"rows with as-of rank-free schedule strength: {int(m['sched'].notna().sum())} / {len(m)}", flush=True)

GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
m["gen"] = m["player_slug"].astype(str).map(GM).fillna("?")
side = m[["date", "player_slug", "rival_slugname", "player_odd", "rival_odd", "won",
          "sched", "sched_n", "gen"]]
riv = side[["date", "player_slug", "sched", "sched_n"]].rename(
    columns={"player_slug": "rival_slugname", "sched": "sched_r", "sched_n": "sched_rn"})
riv = riv.drop_duplicates(["date", "rival_slugname"])
D = side.merge(riv, on=["date", "rival_slugname"], how="inner")
D = D[D["player_slug"].astype(str) < D["rival_slugname"]]
D = D[D["sched"].notna() & D["sched_r"].notna() & (D["sched_n"] >= 6) & (D["sched_rn"] >= 6)]
D = D[D["player_odd"].notna() & D["rival_odd"].notna() & (D["player_odd"] > 1)
      & (D["rival_odd"] > 1) & (D["gen"] != "?")]
D["year"] = D["date"].dt.year
D = D[D["year"] >= 2024]
print(f"matches usable: {len(D)}", flush=True)

i1, i2 = 1.0 / D["player_odd"], 1.0 / D["rival_odd"]
D["mkt"] = i1 / (i1 + i2)
tough_p = (D["sched"] > D["sched_r"]).values          # HIGHER opponent win rate = tougher
gap = np.abs(D["sched"].values - D["sched_r"].values)
t_od = np.where(tough_p, D["player_odd"], D["rival_odd"])
t_won = np.where(tough_p, D["won"].astype(bool), ~D["won"].astype(bool))
t_mkt = np.where(tough_p, D["mkt"], 1 - D["mkt"])
t_dog = t_mkt < 0.5
W = (D["gen"] == "W").values


def rep(label, mask, od=None, won=None, floor=40):
    od = t_od if od is None else od
    won = t_won if won is None else won
    k = int(mask.sum())
    if k < floor:
        print(f"  {label:44s} n={k} (thin)")
        return
    o, w = od[mask], won[mask]
    pnl = np.where(w, o - 1.0, -1.0)
    print(f"  {label:44s} {int(w.sum())}-{int((~w).sum())}  win {100*w.mean():.1f}%  "
          f"ROI {100*pnl.mean():+.1f}%  (n={k})")


print("\n=== BACK THE TOUGHER-SCHEDULE PLAYER (rank-free measure) ===")
for gl, gm in (("MEN", ~W), ("WOMEN", W)):
    print(f"-- {gl} --")
    rep("as the UNDERDOG", gm & t_dog)
    rep("  dog +100..+200", gm & t_dog & (t_od >= 2.0) & (t_od <= 3.0))
    rep("  dog +200..+400", gm & t_dog & (t_od > 3.0) & (t_od <= 5.0))
    rep("as the FAVORITE", gm & ~t_dog)
    rep("  fav -100..-200", gm & ~t_dog & (t_od >= 1.5) & (t_od <= 2.0))
    rep("  fav -200..-400", gm & ~t_dog & (t_od >= 1.25) & (t_od < 1.5))
print("-- biggest schedule gaps only (top decile), both genders --")
cut = np.quantile(gap, 0.9)
rep(f"dog, gap >= {cut:.3f}", t_dog & (gap >= cut))
rep(f"fav, gap >= {cut:.3f}", ~t_dog & (gap >= cut))
print("-- control: back the WEAKER-schedule side --")
w_od = np.where(tough_p, D["rival_odd"], D["player_odd"])
w_won = np.where(tough_p, ~D["won"].astype(bool), D["won"].astype(bool))
rep("weaker side as dog", ~t_dog, w_od, w_won)
rep("weaker side as fav", t_dog, w_od, w_won)
