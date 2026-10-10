"""STAGE 2: DOES AN ESTIMATED UE CARRY THE EDGE? (2026-10-09, user "anyway to get an unforced
errors number for every single game?")

_ue_proxy_build.py showed the stat line predicts UE/set to MAE 2.4 (vs 3.2 for guessing the
mean, R^2 ~.40) and names the lower-error player correctly 69.7% of the time, 78.3% when the
estimated gap is big. This decides whether it belongs on a card: re-run the women's LOW-ERROR
DOG gate on the FULL universe -- every priced match, not just the hand-charted few percent --
using the as-of estimated-UE profiles from _ue_proxy_profiles.py, against the real-UE result
(+11.1%, n=361, positive 2024/25/26).

WHY THIS DOESN'T exec _tennis_model_c_build.py LIKE THE OTHER STUDIES: that prep builds the
whole Model C feature set (52-week rolling windows, season blocks, H2H cumulations) and needs
more memory than this box has free -- it was OOM-killed twice at the H2H stage (exit 137,
2026-10-10). All this study needs is the prep's UNIVERSE, so the universe definition is
reproduced here from the same source columns and nothing else:
    won  = result == "Win"                         (_tennis_model_c_build.py line 30)
    two-sided: the rival's own row must exist       (line 130, the mirror inner-join)
    one row per match: player_slug < rival_slugname (line 131)
    mkt  = (1/player_odd) / (1/player_odd + 1/rival_odd), both odds > 1.005  (lines 133-135)
Keeping that identical is what makes these numbers comparable with the real-UE backtest, which
ran off the same universe. Note it keeps the lexicographically-first player as "player", so
filtering mkt < 0.5 selects the ~half of matches where that player is the dog -- exactly as the
real-UE backtest did, and independent of who is favoured.
"""
import sys

import numpy as np
import pandas as pd

import tennis_ue as U

GAP = 2.264        # the women's median real-UE gap the live lane uses
KEEP = ["date", "player_slug", "rival_slugname", "player_odd", "rival_odd", "result",
        "surface", "tournament_level"]

prof = pd.read_parquet("data_cache/_ue_hat_profiles.parquet").set_index(["d", "key"])["ue_hat5"]
print(f"as-of estimated-UE profiles loaded: {len(prof)} player-dates", flush=True)

df = pd.read_parquet("data_cache/tennisratio/all_match_logs.parquet", columns=KEEP)
df["date"] = pd.to_datetime(df["date"])
df["won"] = (df["result"] == "Win").astype(int)
for c in ("player_odd", "rival_odd"):
    df[c] = pd.to_numeric(df[c], errors="coerce")
df["rival_slugname"] = df["rival_slugname"].astype(str)
# two-sided: the rival must have their own row for this match (the prep's mirror inner-join)
side = df[["player_slug", "rival_slugname", "date"]].copy()
side["_m"] = 1
mirror = side.rename(columns={"player_slug": "rival_slugname", "rival_slugname": "player_slug"})
df = df.merge(mirror, on=["player_slug", "rival_slugname", "date"], how="inner")
del side, mirror
m = df[df["player_slug"].astype(str) < df["rival_slugname"]].copy()
m = m.drop_duplicates(["player_slug", "rival_slugname", "date"]).reset_index(drop=True)
del df
ip1 = 1 / m["player_odd"].where(m["player_odd"] > 1.005)
ip2 = 1 / m["rival_odd"].where(m["rival_odd"] > 1.005)
m["mkt"] = ip1 / (ip1 + ip2)
print(f"two-sided, one row per match: {len(m)}", flush=True)

GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
B = m[(m.date.dt.year >= 2024) & m.mkt.notna() & (m.mkt < 0.5)
      & (m.player_odd > 1) & (m.rival_odd > 1)].copy()
del m
B["G"] = B.player_slug.astype(str).map(GM)
B = B[B.G.isin(["M", "W"])]
B["k"] = B.player_slug.astype(str).map(U.norm)
B["ok"] = B.rival_slugname.astype(str).map(U.norm)
B["dn"] = B.date.dt.normalize()
B["ue_dog"] = [prof.get((d, k), np.nan) for d, k in zip(B.dn, B.k)]
B["ue_fav"] = [prof.get((d, k), np.nan) for d, k in zip(B.dn, B.ok)]
B["dam"] = (B.player_odd - 1) * 100
B["lv"] = B["tournament_level"].astype(str).str.lower()
S = B.dropna(subset=["ue_dog", "ue_fav"]).copy()
S["gap"] = S.ue_fav - S.ue_dog          # + = the DOG is estimated to make fewer errors
print(f"\n2024-26 dog rows: {len(B)} | with an estimated UE for BOTH players: {len(S)} "
      f"({100 * len(S) / len(B):.0f}%; men {int((S.G == 'M').sum())}, women {int((S.G == 'W').sum())})",
      flush=True)
print("  the REAL-UE backtest could only use rows where both players were hand-charted")


def rep(s):
    n = len(s)
    if n < 30:
        return f"n={n} (thin)"
    w = s.won.astype(bool)
    return (f"{int(w.sum())}-{n - int(w.sum())} hit {100 * w.mean():4.1f}% "
            f"vs mkt {100 * s.mkt.mean():4.1f}% | ROI "
            f"{100 * np.where(w, s.player_odd - 1, -1).mean():+6.1f}% (n={n})")


print("\n=== WOMEN: the LOW-ERROR DOG gate on ESTIMATED UE ===")
W = S[(S.G == "W") & S.dam.between(100, 250)]
print(f"  every women's dog +100..+250 with profiles: {rep(W)}")
for lo, hi, lab in ((GAP, 99, f">= {GAP}"), (1.0, GAP, "1.0-2.26"),
                    (3.5, 99, ">= 3.5"), (5.0, 99, ">= 5.0"), (-99, 0, "dog WORSE")):
    print(f"    gap {lab:9s}: {rep(W[(W.gap >= lo) & (W.gap < hi)])}")
print("  by year (gap >= 2.26):")
for Y in (2024, 2025, 2026):
    print(f"    {Y}: {rep(W[(W.gap >= GAP) & (W.date.dt.year == Y)])}")
WG = W[W.gap >= GAP]
print("  by level (gap >= 2.26):")
for lv, g in WG.groupby(WG.lv):
    print(f"    {lv:14s}: {rep(g)}")

print("\n=== MEN (real UE showed no edge; does the estimate?) ===")
M = S[(S.G == "M") & S.dam.between(100, 250)]
print(f"  every men's dog +100..+250 with profiles: {rep(M)}")
print(f"    gap >= {GAP}: {rep(M[M.gap >= GAP])}")
for Y in (2024, 2025, 2026):
    print(f"    {Y}: {rep(M[(M.gap >= GAP) & (M.date.dt.year == Y)])}")

print("\n=== is the estimated gap monotone, or is it noise? ===")
for G, lab in (("W", "women"), ("M", "men")):
    T = S[(S.G == G) & S.dam.between(100, 250)].copy()
    if len(T) < 200:
        continue
    T["q"] = pd.qcut(T.gap, 5, labels=False, duplicates="drop")
    print(f"  {lab} dogs by estimated-gap quintile (Q1 = dog makes MORE errors):")
    for q, g in T.groupby("q"):
        print(f"    Q{int(q) + 1}: {rep(g)}")
print("\nDONE")
sys.stdout.flush()
