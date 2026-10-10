"""WHAT IS THE ROI WHEN MODEL P FULLY FLIPS A DOG? (2026-10-10, user ask)

"Fully flips" = P puts the market DOG above 50%, i.e. it says the market has the wrong
favourite. P is an offset model on the price, so a flip is P overriding the market's choice of
favourite outright rather than just finding a few points of value.

This matters because a flip means very different things at different prices. The shipped gate is
EV >= 5%, i.e. pP >= 1.05 / decimal_odds:
    at +100 (dec 2.0) EV>=5% already requires pP >= 0.525  -- so the gate is ALREADY a flip
    at +250 (dec 3.5) EV>=5% only requires pP >= 0.30      -- no flip needed
So the two cells coincide at short prices and diverge badly at long ones, and the interesting
question is whether the flip adds anything the EV gate does not already capture.

Exact same walk-forward harness as _model_p250_build.py: per gender, fit on years < Y with the
offset logistic (lam=2.0, features standardised on the training years only), score year Y out of
sample. 2024, 2025 and 2026 are each tested only on earlier years.
"""
import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize

FEATS = ["d_vs_band", "g_C", "g_gray", "g_Dma", "d_form_win", "d_m_perf", "d_m_won",
         "d_sutr", "d_lrank", "is_chall", "is_itf"]


def fit_offset(X, y, off, lam=2.0):
    n, k = X.shape
    Xb = np.column_stack([np.ones(n), X])

    def f(w):
        z = off + Xb @ w
        ll = np.sum(y * z - np.logaddexp(0, z))
        pen = 0.5 * lam * np.sum(w[1:] ** 2)
        p = 1 / (1 + np.exp(-z))
        g = -(Xb.T @ (y - p))
        g[1:] += lam * w[1:]
        return -ll + pen, g
    return minimize(f, np.zeros(k + 1), jac=True, method="L-BFGS-B").x


D = pd.read_parquet("data_cache/_model_p250_rows.parquet")
D = D[D[["p_C", "pm_C", "pm_D"]].notna().all(axis=1)].copy()
print(f"P universe (+100..+250 dogs): {len(D)} | by year {D.groupby('yr').size().to_dict()}",
      flush=True)

OUT = []
for G in ("M", "W"):
    S = D[D.G == G].copy()
    for yr in (2024, 2025, 2026):
        tr, te = S[S.yr < yr].copy(), S[S.yr == yr].copy()
        if len(tr) < 500 or len(te) < 50:
            continue
        mu, sd = tr[FEATS].mean(), tr[FEATS].std().replace(0, 1)
        Xtr = ((tr[FEATS] - mu) / sd).fillna(0).values
        Xte = ((te[FEATS] - mu) / sd).fillna(0).values
        w = fit_offset(Xtr, tr.won.values.astype(float), tr.off.values)
        te["pP"] = 1 / (1 + np.exp(-(te.off.values + w[0] + Xte @ w[1:])))
        te["ev"] = te.pP * te.player_odd - 1
        te["G"] = G
        OUT.append(te)
P = pd.concat(OUT, ignore_index=True)
P["flip"] = P.pP > 0.50
P["bet"] = P.ev >= 0.05
P["dam"] = (P.player_odd - 1) * 100
P["u"] = np.where(P.won.astype(bool), P.player_odd - 1, -1.0)


def rep(s, floor=30):
    n = len(s)
    if n < floor:
        return f"n={n} (thin)"
    w = int(s.won.astype(bool).sum())
    return (f"{w}-{n - w} win {100 * w / n:4.1f}% vs mkt {100 * s.mkt.mean():4.1f}% | "
            f"ROI {100 * s.u.mean():+6.1f}% (n={n}, {s.u.sum():+.1f}u)")


print("\n" + "=" * 86)
print("MODEL P FULLY FLIPS THE DOG  (pP > 50%: P says the market has the wrong favourite)")
print("=" * 86)
for G, gl in (("W", "WOMEN"), ("M", "MEN")):
    T = P[P.G == G]
    print(f"\n--- {gl} ---")
    print(f"  every +100..+250 dog     {rep(T)}")
    print(f"  P FLIPS (pP > 50%)       {rep(T[T.flip])}")
    print(f"  the shipped EV>=5% gate  {rep(T[T.bet])}")
    print(f"  FLIP and EV>=5%          {rep(T[T.flip & T.bet])}")
    print(f"  FLIP but EV < 5%         {rep(T[T.flip & ~T.bet])}")
    print(f"  EV>=5% but NO flip       {rep(T[~T.flip & T.bet])}")
    print("  flip, by year:")
    for Y in (2024, 2025, 2026):
        print(f"    {Y}: {rep(T[T.flip & (T.yr == Y)], floor=15)}")
    print("  flip, by how far P goes past 50%:")
    for lo, hi, lab in ((0.50, 0.55, "50-55%"), (0.55, 0.60, "55-60%"), (0.60, 1.01, "60%+")):
        print(f"    pP {lab:8s}: {rep(T[(T.pP >= lo) & (T.pP < hi)], floor=15)}")
    print("  flip, by price (a flip at +250 is a far bigger disagreement than at +100):")
    for lo, hi in ((100, 150), (150, 200), (200, 250)):
        print(f"    +{lo}..+{hi}: {rep(T[T.flip & T.dam.between(lo, hi)], floor=15)}")
print("\n=== how often does a flip even happen? ===")
for G in ("W", "M"):
    T = P[P.G == G]
    print(f"  {G}: {100 * T.flip.mean():.1f}% of dogs flipped "
          f"({int(T.flip.sum())} of {len(T)}) | EV>=5% fires on {100 * T.bet.mean():.1f}%")
sys.stdout.flush()
