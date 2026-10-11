"""TEST 1 (2026-10-10, user "try both"): gate the Ⓟ FAV mark on g_C.

Brengle vs Sharma, 10-10: P put +16.1% EV on the -141 favourite and she lost 3-6 2-6. The
per-feature decomposition showed ONE driver -- g_C = logit(C) - logit(market) on the dog, at
-0.524, more than twice the next term, with C at 80.0% against a no-vig market of 55.3%. The
rank gap was 7th of 11 by weight and pushed the OTHER way.

Hypothesis: P's favourite picks are good when the favourite edge comes from the PRICE, and bad
when it is just an extreme raw-C disagreement. If so, excluding very negative g_C (C hating the
dog) should lift the fav cell without touching the dog cell.

Method: exactly the production recipe, strict walk-forward. The base C/D probabilities in
_model_p250_rows.parquet were themselves fit on years < Y (two-level walk-forward from
_model_p250_build.py), and Model P for year Y is fit only on P-rows from years < Y with the
standardisation taken from the training years alone. The favourite rule is production's:
favourite decimal 1.5-2.0 and fav_ev >= 3%.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize

FEATS = ["d_vs_band", "g_C", "g_gray", "g_Dma", "d_form_win", "d_m_perf", "d_m_won",
         "d_sutr", "d_lrank", "is_chall", "is_itf"]
BAND = {"M": 3.0, "W": 3.5}
EV_FAV, EV_DOG = 0.03, 0.05
YRS = (2024, 2025, 2026)


def fit_offset(X, y, off, lam=2.0):
    n, k = X.shape
    Xb = np.column_stack([np.ones(n), X])

    def f(w):
        z = off + Xb @ w
        ll = np.sum(y * z - np.logaddexp(0, z))
        p = 1 / (1 + np.exp(-z))
        g = -(Xb.T @ (y - p))
        g[1:] += lam * w[1:]
        return -ll + 0.5 * lam * np.sum(w[1:] ** 2), g
    return minimize(f, np.zeros(k + 1), jac=True, method="L-BFGS-B").x


def rep(won, dec, floor=40):
    n = len(won)
    if n < floor:
        return f"n={n} (thin)"
    w = int(np.sum(won))
    return (f"{w}-{n - w}  hit {100 * w / n:4.1f}%  "
            f"ROI {100 * np.where(won, dec - 1, -1.0).mean():+6.1f}%  (n={n})")


def walk_forward(D):
    """Production recipe, per gender, per test year. Returns the out-of-sample rows."""
    out = []
    for G in ("M", "W"):
        S = D[(D.G == G) & (D.player_odd <= BAND[G])].copy()
        for yr in YRS:
            tr, te = S[S.yr < yr], S[S.yr == yr].copy()
            if len(tr) < 400 or not len(te):
                continue
            mu, sd = tr[FEATS].mean(), tr[FEATS].std().replace(0, 1)
            Xtr = ((tr[FEATS] - mu) / sd).fillna(0).values
            Xte = ((te[FEATS] - mu) / sd).fillna(0).values
            w = fit_offset(Xtr, tr.won.values.astype(float), tr.off.values)
            z = te.off.values + w[0] + Xte @ w[1:]
            te["p_dog"] = 1 / (1 + np.exp(-z))
            out.append(te)
    O = pd.concat(out)
    O["p_fav"] = 1 - O.p_dog
    O["fav_ev"] = O.p_fav * O.rival_odd - 1
    O["dog_ev"] = O.p_dog * O.player_odd - 1
    O["fav_won"] = ~O.won.astype(bool)
    return O


D = pd.read_parquet("data_cache/_model_p250_rows.parquet")
D["won"] = D["won"].astype(bool)
print(f"P universe: {len(D)} rows | {D.groupby(['G', 'yr']).size().to_dict()}", flush=True)
O = walk_forward(D)
print(f"out-of-sample rows: {len(O)}", flush=True)

# the production Ⓟ FAV universe
F = O[(O.rival_odd >= 1.5) & (O.rival_odd <= 2.0) & (O.fav_ev >= EV_FAV)].copy()
print(f"\n⒅ FAV universe (fav 1.5-2.0 dec, fav_ev>={EV_FAV}): {len(F)}")

for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    S = F[F.G == G]
    print(f"\n{'=' * 78}\n{gl}  --  Ⓟ FAV picks, out of sample\n{'=' * 78}")
    print(f"   BASELINE (what ships today)          {rep(S.fav_won.values, S.rival_odd.values)}")
    print(f"\n   split by g_C (C's disagreement with the market, DOG side --")
    print(f"   very negative = C hates the dog / loves the favourite; Brengle was -1.178):")
    for lo, hi in ((-9.9, -1.2), (-1.2, -0.8), (-0.8, -0.4), (-0.4, 0.0), (0.0, 9.9)):
        s = S[(S.g_C >= lo) & (S.g_C < hi)]
        lab = (f"g_C below {hi:+.1f}" if lo < -9 else
               f"g_C {hi:+.1f} and up" if hi > 9 else f"g_C {lo:+.1f}..{hi:+.1f}")
        print(f"      {lab:24s} {rep(s.fav_won.values, s.rival_odd.values, floor=25)}")
    print(f"\n   THE GATE -- drop the extreme-C favourites:")
    for thr in (-1.4, -1.2, -1.0, -0.8, -0.6):
        k, d = S[S.g_C > thr], S[S.g_C <= thr]
        print(f"      keep g_C > {thr:+.1f}   {rep(k.fav_won.values, k.rival_odd.values)}"
              f"   | dropped {len(d)}: {rep(d.fav_won.values, d.rival_odd.values, floor=25)}")
    print(f"\n   per year at the best-looking gate, to check it is not one year:")
    for thr in (-1.2, -1.0, -0.8):
        line = "   ".join(
            f"{y} {rep(S[(S.g_C > thr) & (S.yr == y)].fav_won.values, S[(S.g_C > thr) & (S.yr == y)].rival_odd.values, floor=15)}"
            for y in YRS)
        print(f"      g_C > {thr:+.1f}: {line}")

# does the gate damage the DOG side (the lane that actually earns)?
Dg = O[O.dog_ev >= EV_DOG].copy()
print(f"\n{'=' * 78}\nSANITY -- the Ⓟ DOG cell must not be harmed by the same gate\n{'=' * 78}")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    S = Dg[Dg.G == G]
    print(f"   {gl:6s} all P dog bets    {rep(S.won.values, S.player_odd.values)}")
    for thr in (-1.2, -1.0, -0.8):
        k = S[S.g_C > thr]
        print(f"          g_C > {thr:+.1f}       {rep(k.won.values, k.player_odd.values)}")
