"""ADJUDICATION (2026-10-10): the walk-forward says an extreme g_C favourite is the BEST
favourite cell (men +19.3%, women +36.4%). The frozen live log said the opposite. Run the
SAME split on the live log, in the same universe the backtest used, and see which holds.

Universe matched to the backtest: market dog decimal 2.0-3.5, favourite decimal 1.5-2.0.
g_C is measured the way Model P measures it -- logit(C on the dog) - logit(no-vig market on
the dog) -- but from the LIVE logged model_c_p1, which is what the board actually fires on.
"""
import numpy as np
import pandas as pd

L = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
L["date"] = pd.to_datetime(L["date"], errors="coerce")


def dec(o):
    o = pd.to_numeric(o, errors="coerce").astype(float)
    return np.where(o > 0, 1 + o / 100.0, 1 + 100.0 / -o)


def lg(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


L["d1"], L["d2"] = dec(L.p1_odds), dec(L.p2_odds)
i1, i2 = 1 / L.d1, 1 / L.d2
L["mk1"] = i1 / (i1 + i2)
L["W"] = L.league.astype(str).str.lower().str.contains("women|wta")

S = L[(L.settled == True) & L.p1_won.notna() & L.model_c_p1.notna() & L.mk1.notna()].copy()
S["dog1"] = S.mk1 < 0.5
S["dog_dec"] = np.where(S.dog1, S.d1, S.d2)
S["fav_dec"] = np.where(S.dog1, S.d2, S.d1)
S["mk_dog"] = np.where(S.dog1, S.mk1, 1 - S.mk1)
S["c_dog"] = np.where(S.dog1, S.model_c_p1, 1 - S.model_c_p1)
S["g_C"] = lg(S.c_dog) - lg(S.mk_dog)
S["fav_won"] = np.where(S.dog1, S.p1_won == 0, S.p1_won == 1)

U = S[(S.dog_dec >= 2.0) & (S.dog_dec <= 3.5) & (S.fav_dec >= 1.5) & (S.fav_dec <= 2.0)].copy()
print(f"live log, universe matched to the backtest: {len(U)} settled "
      f"(men {int((~U.W).sum())}, women {int(U.W.sum())})")
print(f"date range {U.date.min().date()}..{U.date.max().date()}\n")


def rep(s, floor=10):
    n = len(s)
    if n < floor:
        return f"n={n} (thin)"
    w = s.fav_won.astype(bool)
    return (f"{int(w.sum())}-{n - int(w.sum())}  hit {100 * w.mean():4.1f}%  "
            f"ROI {100 * np.where(w, s.fav_dec - 1, -1).mean():+6.1f}%  (n={n})")


for G, lab in ((False, "MEN"), (True, "WOMEN")):
    T = U[U.W == G]
    print(f"=== {lab}: backing the favourite, live, split by g_C ===")
    print(f"   all favourites in universe   {rep(T)}")
    for lo, hi in ((-9.9, -1.2), (-1.2, -0.8), (-0.8, -0.4), (-0.4, 0.0), (0.0, 9.9)):
        s = T[(T.g_C >= lo) & (T.g_C < hi)]
        l = (f"g_C below {hi:+.1f}" if lo < -9 else
             f"g_C {hi:+.1f} and up" if hi > 9 else f"g_C {lo:+.1f}..{hi:+.1f}")
        print(f"      {l:22s} {rep(s)}")
    print()
print("=== POOLED (both genders), the cell the backtest calls best ===")
for thr in (-1.2, -1.0, -0.8):
    print(f"   g_C <= {thr:+.1f}  {rep(U[U.g_C <= thr])}")
    print(f"   g_C >  {thr:+.1f}  {rep(U[U.g_C > thr])}")

print("\n=== is LIVE C shifted vs the clean recipe? distribution of g_C ===")
print("   live   ", " ".join(f"{q}%={U.g_C.quantile(q / 100):+.2f}" for q in (10, 25, 50, 75, 90)))
B = pd.read_parquet("data_cache/_model_p250_rows.parquet", columns=["g_C", "G", "yr", "rival_odd"])
B = B[(B.rival_odd >= 1.5) & (B.rival_odd <= 2.0)]
print("   backtest", " ".join(f"{q}%={B.g_C.quantile(q / 100):+.2f}" for q in (10, 25, 50, 75, 90)))
print(f"   live mean {U.g_C.mean():+.3f} vs backtest mean {B.g_C.mean():+.3f}"
      f"   ->  live C sits {U.g_C.mean() - B.g_C.mean():+.3f} logits on the DOG")
print(f"   share of rows with g_C <= -1.2:  live {100 * (U.g_C <= -1.2).mean():.1f}%"
      f"   backtest {100 * (B.g_C <= -1.2).mean():.1f}%")
