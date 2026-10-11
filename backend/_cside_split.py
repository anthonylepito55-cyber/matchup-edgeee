"""IS IT "MODEL C'S SIDE" THAT IS POSITIVE, OR SPECIFICALLY C-ON-THE-DOG? (2026-10-10)

The lane records point at the dog half every time -- tier_avoid dogs +19.1% against its favs
+0.9%, and every c75-dog variant positive while every favourite lane is flat or negative. This
measures it directly off the frozen log: back MODEL C'S SIDE on every match, split by whether
that side is the market dog or the market favourite, with error bars.
"""
import numpy as np
import pandas as pd

L = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
L["date"] = pd.to_datetime(L["date"], errors="coerce")


def dec(o):
    o = pd.to_numeric(o, errors="coerce").astype(float)
    return np.where(o > 0, 1 + o / 100.0, 1 + 100.0 / -o)


L["d1"], L["d2"] = dec(L.p1_odds), dec(L.p2_odds)
i1, i2 = 1 / L.d1, 1 / L.d2
L["mk1"] = i1 / (i1 + i2)
S = L[(L.settled == True) & L.p1_won.notna() & L.mk1.notna()
      & (L.d1 > 1.005) & (L.d2 > 1.005)].copy()
S["dog1"] = S.mk1 < 0.5
S["W"] = S.league.astype(str).str.lower().str.contains("women|wta")


def block(col, label):
    T = S[S[col].notna()].copy()
    if not len(T):
        print(f"\n{label}: no rows")
        return
    T["side1"] = T[col].astype(float) >= 0.5       # the model's side
    T["dec"] = np.where(T.side1, T.d1, T.d2)
    T["won"] = np.where(T.side1, T.p1_won == 1, T.p1_won == 0)
    T["on_dog"] = T.side1 == T.dog1
    print(f"\n{'=' * 78}\n{label}  (n={len(T)} settled)\n{'=' * 78}")

    def rep(s, lab, floor=20):
        n = len(s)
        if n < floor:
            print(f"   {lab:26s} n={n} (thin)")
            return
        w = s.won.astype(bool)
        pnl = np.where(w, s.dec - 1, -1.0)
        print(f"   {lab:26s} {int(w.sum())}-{n - int(w.sum())}  hit {100 * w.mean():5.1f}%  "
              f"ROI {100 * pnl.mean():+7.1f}% ± {100 * pnl.std(ddof=1) / np.sqrt(n):4.1f}  (n={n})")

    rep(T, "every match")
    rep(T[T.on_dog], "   when C is on the DOG")
    rep(T[~T.on_dog], "   when C is on the FAV")
    print()
    for g, lab in ((False, "men"), (True, "women")):
        rep(T[(T.W == g) & T.on_dog], f"   {lab}, on the dog")
        rep(T[(T.W == g) & (~T.on_dog)], f"   {lab}, on the fav")


block("model_c_p1", "MODEL C's side")
block("mc_c75_p1", "c75 (C-anchored Monte Carlo, 0.75 weight) side")
block("model_cma_p1", "GRAY (C market-aware) side")
block("model_d_p1", "MODEL D's side")
