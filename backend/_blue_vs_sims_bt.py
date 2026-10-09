"""Do the Monte Carlos veto the blue dog marks? (2026-10-09, user on Sun/Kachmazov: "every
Monte Carlo has alibek"). Joins the walk-forward dossier dog rows (2025-26) to the as-of
sim rows (2026, production simulate_match on as-of profiles) by date + both odds."""
import numpy as np
import pandas as pd

D = pd.read_parquet("data_cache/_season_2026_dossier_rows.parquet")
D = D[(D.yr == 2026) & D[["p_A", "p_B", "p_C", "pm_C"]].notna().all(axis=1)].copy()
S = pd.read_parquet("data_cache/_mc_asof_bt_rows.parquet").dropna(subset=["c75"])
S["d"] = pd.to_datetime(S.date).dt.normalize()
D["d"] = D.date.dt.normalize()
r2 = lambda x: np.round(x.astype(float), 2)
# orientation 1: sim row player = our dog
a = S.assign(k1=r2(S.oa), k2=r2(S.ob), sdog_c50=S.c50, sdog_c75=S.c75, sdog_srv=S.mc1_serve)
# orientation 2: sim row player = our favourite
b = S.assign(k1=r2(S.ob), k2=r2(S.oa), sdog_c50=1 - S.c50, sdog_c75=1 - S.c75, sdog_srv=1 - S.mc1_serve)
SS = pd.concat([a, b])[["d", "k1", "k2", "sdog_c50", "sdog_c75", "sdog_srv"]].drop_duplicates(["d", "k1", "k2"])
D["k1"], D["k2"] = r2(D.player_odd), r2(D.rival_odd)
J = D.merge(SS, on=["d", "k1", "k2"], how="inner")
print(f"2026 dog rows {len(D)} | joined to sims {len(J)}")
aS, bS, cS, gS = J.p_A >= .5, J.p_B >= .5, J.p_C >= .5, J.pm_C >= .5
gray4 = gS & ((J.pm_C - J.mkt) >= 0.04)
blue = (cS & gS & ((~aS & ~bS) | gray4)) | gray4
J["nsim_dog"] = (J.sdog_c50 >= .5).astype(int) + (J.sdog_c75 >= .5).astype(int) + (J.sdog_srv >= .5).astype(int)
band = J.dog_am.between(100, 250)


def rep(s):
    if len(s) < 30:
        return f"n={len(s)} (thin)"
    p = np.where(s.won, s.player_odd - 1, -1.0)
    return f"{int(s.won.sum())}-{int((~s.won).sum())} win {100*s.won.mean():4.1f}% vs mkt {100*s.mkt.mean():4.1f} ROI {100*p.mean():+6.1f}% (n={len(s)})"


for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    B = J[blue & band & (J.G == G)]
    print(f"\n{gl} blue dog marks, +100..+250, 2026: {rep(B)}")
    for k, lab in ((0, "0 of 3 sims on the dog (all sims on fav)"), (1, "1 of 3"), (2, "2 of 3"), (3, "all 3 sims on the dog")):
        print(f"   {lab:40s} {rep(B[B.nsim_dog == k])}")
    print(f"   + A and B both on the fav, all sims on fav  {rep(B[(B.nsim_dog == 0) & ~aS[B.index] & ~bS[B.index]])}")
