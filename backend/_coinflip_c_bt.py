"""COIN-FLIP C + CHALLENGER CHECK (2026-10-08, user on Sun vs Kachmazov: "all signs point to
alibek why is sun the person highlighted"). Model C had Sun at 50.01% -- the C-ALONE and
TIER-1 marks fired on a 0.01pt margin. Does a barely-over-50 C still carry the edge, and do
these dog marks hold at men's challengers? Rows: walk-forward 2025-26 dog rows from
_season_2026_dossier.py (one per match, true gender, closing odds)."""
import numpy as np
import pandas as pd

D = pd.read_parquet("data_cache/_season_2026_dossier_rows.parquet")
D = D[D[["p_A", "p_B", "p_C", "pm_C"]].notna().all(axis=1)].copy()
aS, bS, cS, gS = D.p_A >= .5, D.p_B >= .5, D.p_C >= .5, D.pm_C >= .5
alone = ~aS & ~bS
gray4 = gS & ((D.pm_C - D.mkt) >= 0.04)
D["calone"] = alone & cS & gS
D["tier1"] = cS & gS & (alone | gray4)
D["gray4"] = gray4
D["cmarg"] = D.p_C - 0.5
D["band"] = D.dog_am.between(100, 250)
D["chall"] = D.level.eq("challenger")


def rep(s):
    if len(s) < 40:
        return f"n={len(s)} (thin)"
    p = np.where(s.won, s.player_odd - 1, -1.0)
    return f"{int(s.won.sum())}-{int((~s.won).sum())}  win {100*s.won.mean():4.1f}% vs mkt {100*s.mkt.mean():4.1f}  ROI {100*p.mean():+6.1f}%  (n={len(s)})"


for cell in ("calone", "tier1", "gray4"):
    print(f"\n=== {cell.upper()} (dog +100..+250) ===")
    for G, gl in (("M", "MEN"), ("W", "WOMEN")):
        S = D[D[cell] & D.band & (D.G == G)]
        print(f"  {gl} all                      {rep(S)}")
        if cell != "gray4":
            print(f"  {gl} C margin < 2pt (coin flip) {rep(S[S.cmarg < 0.02])}")
            print(f"  {gl} C margin >= 2pt            {rep(S[S.cmarg >= 0.02])}")
        print(f"  {gl} challenger               {rep(S[S.chall])}")
        print(f"  {gl} not challenger           {rep(S[~S.chall])}")
        for y in (2025, 2026):
            print(f"    {y}: all {rep(S[S.yr == y])} | challenger {rep(S[S.chall & (S.yr == y)])}")

print("\n=== SUN-SHAPED: men, challenger, +100..+250, C margin < 2pt, gray 4pt+ ===")
S = D[(D.G == "M") & D.chall & D.band & (D.cmarg.between(0, 0.02)) & gray4]
print(f"  {rep(S)}")
print("  ...and A + B both on the favourite (C-ALONE shape):")
print(f"  {rep(S[alone.loc[S.index]])}")
