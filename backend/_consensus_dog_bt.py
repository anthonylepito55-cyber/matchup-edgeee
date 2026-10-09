"""CONSENSUS ON A +100..+200 PLAYER (2026-10-09, user: "what's the roi when more mcs and
models land on one person from +100-+200"). Count how many heads back the plus-money
player, then ROI of backing that player at +100..+200.
  BACKTEST 2026: 9 heads -- A, B, C, gray(C-MA), D, D-MA (walk-forward) + c50, c75,
                 serve-MC (as-of sims). Joined like _blue_vs_sims_bt.py.
  LIVE (frozen log 09-28..): 12 heads -- the 9 + cUTR-MC, MC2, Model X."""
import numpy as np
import pandas as pd

def roi(won, dec):
    return np.where(won, dec - 1, -1.0)

def rep(won, dec, floor=30):
    n = len(won)
    if n < floor:
        return f"n={n} (thin)"
    w = int(np.sum(won))
    return f"{w}-{n-w}  win {100*w/n:4.1f}%  ROI {100*roi(won, dec).mean():+6.1f}%  (n={n})"

# ---------------- BACKTEST 2026 ----------------
D = pd.read_parquet("data_cache/_season_2026_dossier_rows.parquet")
D = D[(D.yr == 2026)].copy()
S = pd.read_parquet("data_cache/_mc_asof_bt_rows.parquet").dropna(subset=["c75"])
S["d"] = pd.to_datetime(S.date).dt.normalize()
D["d"] = D.date.dt.normalize()
r2 = lambda x: np.round(x.astype(float), 2)
a = S.assign(k1=r2(S.oa), k2=r2(S.ob), s50=S.c50, s75=S.c75, ssv=S.mc1_serve)
b = S.assign(k1=r2(S.ob), k2=r2(S.oa), s50=1 - S.c50, s75=1 - S.c75, ssv=1 - S.mc1_serve)
SS = pd.concat([a, b])[["d", "k1", "k2", "s50", "s75", "ssv"]].drop_duplicates(["d", "k1", "k2"])
D["k1"], D["k2"] = r2(D.player_odd), r2(D.rival_odd)
J = D.merge(SS, on=["d", "k1", "k2"], how="inner")
H = ["p_A", "p_B", "p_C", "pm_C", "p_D", "pm_D", "s50", "s75", "ssv"]
J = J[J[H].notna().all(axis=1) & J.dog_am.between(100, 200)]
J["n"] = sum((J[h] >= 0.5).astype(int) for h in H)
print("=== BACKTEST 2026: +100..+200 player, by how many of 9 heads back them ===")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    T = J[J.G == G]
    print(f"\n{gl}: every +100..+200 player   {rep(T.won.values, T.player_odd.values)}")
    for lo, hi, lab in ((0, 0, "0 of 9"), (1, 2, "1-2"), (3, 4, "3-4"), (5, 6, "5-6"), (7, 8, "7-8"), (9, 9, "all 9")):
        s = T[T.n.between(lo, hi)]
        print(f"   {lab:8s} {rep(s.won.values, s.player_odd.values)}")
    m = T[T.n.between(5, 9)]
    print(f"   majority (5+) {rep(m.won.values, m.player_odd.values)}")

# ---------------- LIVE ----------------
L = pd.read_parquet("data_cache/_ec2_log_now.parquet")
L = L[L.p1_won.notna() & L.p1_odds.notna() & L.p2_odds.notna()].copy()
LH = ["model_a_p1", "model_b_p1", "model_c_p1", "model_cma_p1", "model_d_p1", "model_dma_p1",
      "mc_c_p1", "mc_c75_p1", "mc_p1", "mc_cutr_p1", "mc2_p1", "model_x_p1"]
LH = [h for h in LH if h in L.columns]
L = L[L[LH].notna().all(axis=1)]
rows = []
for r in L.itertuples():
    for side in (1, 2):
        od = float(r.p1_odds if side == 1 else r.p2_odds)
        if not (100 <= od <= 200):
            continue
        dec = 1 + od / 100
        n = sum(int((float(getattr(r, h)) >= 0.5) == (side == 1)) for h in LH)
        lg = str(r.league)
        rows.append({"G": "W" if ("wta" in lg or "itf_women" in lg) else "M", "n": n,
                     "won": bool(r.p1_won) == (side == 1), "dec": dec})
R = pd.DataFrame(rows)
print(f"\n=== LIVE frozen log ({L.date.astype(str).min()[:10]}..{L.date.astype(str).max()[:10]}): "
      f"+100..+200 player, by how many of {len(LH)} heads back them ===")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    T = R[R.G == G]
    print(f"\n{gl}: every +100..+200 player   {rep(T.won.values, T.dec.values, 15)}")
    for lo, hi, lab in ((0, 1, "0-1"), (2, 3, "2-3"), (4, 5, "4-5"), (6, 7, "6-7"), (8, 9, "8-9"), (10, 12, "10-12")):
        s = T[T.n.between(lo, hi)]
        print(f"   {lab:8s} {rep(s.won.values, s.dec.values, 15)}")

# ================= FAVOURITES -100..-200 (user follow-up) =================
J2 = D.merge(SS, on=["d", "k1", "k2"], how="inner")
J2 = J2[J2[H].notna().all(axis=1)].copy()
J2["fav_am"] = np.where(J2.rival_odd >= 2, (J2.rival_odd - 1) * 100, -100 / (J2.rival_odd - 1))
J2 = J2[J2.fav_am.between(-200, -100)]
J2["nf"] = sum((J2[h] < 0.5).astype(int) for h in H)          # heads backing the favourite
J2["fwon"] = ~J2.won.astype(bool)
print("\n\n=== BACKTEST 2026: -100..-200 FAVOURITE, by how many of 9 heads back them ===")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    T = J2[J2.G == G]
    print(f"\n{gl}: every -100..-200 favourite   {rep(T.fwon.values, T.rival_odd.values)}")
    for lo, hi, lab in ((0, 2, "0-2"), (3, 4, "3-4"), (5, 6, "5-6"), (7, 8, "7-8"), (9, 9, "all 9")):
        s = T[T.nf.between(lo, hi)]
        print(f"   {lab:8s} {rep(s.fwon.values, s.rival_odd.values)}")
rows = []
for r in L.itertuples():
    for side in (1, 2):
        od = float(r.p1_odds if side == 1 else r.p2_odds)
        if not (-200 <= od <= -100):
            continue
        n = sum(int((float(getattr(r, h)) >= 0.5) == (side == 1)) for h in LH)
        lg = str(r.league)
        rows.append({"G": "W" if ("wta" in lg or "itf_women" in lg) else "M", "n": n,
                     "won": bool(r.p1_won) == (side == 1), "dec": 1 + 100 / abs(od)})
R = pd.DataFrame(rows)
print(f"\n=== LIVE: -100..-200 favourite, by how many of {len(LH)} heads back them ===")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    T = R[R.G == G]
    print(f"\n{gl}: every -100..-200 favourite   {rep(T.won.values, T.dec.values, 15)}")
    for lo, hi, lab in ((0, 5, "0-5"), (6, 7, "6-7"), (8, 9, "8-9"), (10, 11, "10-11"), (12, 12, "all 12")):
        s = T[T.n.between(lo, hi)]
        print(f"   {lab:8s} {rep(s.won.values, s.dec.values, 15)}")
