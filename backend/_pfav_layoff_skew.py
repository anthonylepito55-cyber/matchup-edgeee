"""THE LAST MECHANICAL EXPLANATION: does Ⓟ FAV pick the rows where the TRAINED feature and
the SERVED feature are furthest apart? (2026-10-10, user "Dig into it")

Where the investigation stands:
  * STATS CLEAN. No leakage in the 52w / last-10 / seasonal windows. The backtest anchors the
    52w window at the player's previous match, the live path at the match date -- different,
    but the bias is +0.001 on m_won across 605k rows, i.e. noise.
  * PRICES CLEAN. Same 307 games: archive -5.3%, live -5.6%.
  * RETIREMENTS PRESENT in the archive (1.01% of matches have <=1 completed set; favourites in
    them go 50.0% / -18.9%), so no survivorship inflation.
  * ONE-SIDED BACKFILL is real and severe in recent data (18.5% of rows in the live window,
    favourites 86.1% / +39.5%) but it CANNOT touch Model C/P -- that universe is 100% mirrored
    because the C build needs the opponent's row to form its diff features.
  * BASELINES AGREE: archive mirrored favourites in band 58.0% hit / -6.5% (n=53,430) vs live
    55.8% / -8.1% (n=534). Within noise.
So the gap is not the data level -- it is that P's favourite SELECTION lift (+9 to +13 points of
hit rate over baseline, every year) does not transfer.

The one mechanism left: the window skew is unbiased ON AVERAGE but grows with layoff (180d+
rows: mean |diff| 0.066, 19.4% differ by over 10 points). A stale or thin opponent profile is
exactly what makes C rate a dog badly and P call the favourite underpriced. If P's favourite
picks concentrate on long-layoff opponents, then the features it was FITTED on and the features
it is SERVED are materially different precisely where it bets.

Measured: attach each side's days-since-previous-match-on-surface, then split the Ⓟ FAV cell.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize

FEATS = ["d_vs_band", "g_C", "g_gray", "g_Dma", "d_form_win", "d_m_perf", "d_m_won",
         "d_sutr", "d_lrank", "is_chall", "is_itf"]
BAND = {"M": 3.0, "W": 3.5}
EV_FAV = 0.03
YRS = (2024, 2025, 2026)
AR = "data_cache/tennisratio/all_match_logs.parquet"


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


def rep(won, d, floor=40):
    n = len(won)
    if n < floor:
        return f"n={n} (thin)"
    won = np.asarray(won, dtype=bool)
    w = int(won.sum())
    return (f"{w}-{n - w}  hit {100 * w / n:4.1f}%  "
            f"ROI {100 * np.where(won, np.asarray(d, float) - 1, -1).mean():+6.1f}%  (n={n})")


# ---- days since each player's previous match on this surface ---------------------------
A = pd.read_parquet(AR, columns=["date", "player_slug", "surface"])
A["date"] = pd.to_datetime(A["date"], errors="coerce")
A["surface"] = A["surface"].astype(str).str.title()
A["player_slug"] = A["player_slug"].astype(str)
A = A[A.date.notna()].drop_duplicates(["player_slug", "surface", "date"])
A = A.sort_values(["player_slug", "surface", "date"], kind="stable")
A["prev"] = A.groupby(["player_slug", "surface"], sort=False)["date"].shift(1)
A["layoff"] = (A["date"] - A["prev"]).dt.days
LAY = A[["player_slug", "surface", "date", "layoff"]]
print(f"layoff table: {len(LAY)} player-surface-days, median {LAY.layoff.median():.0f}d")

D = pd.read_parquet("data_cache/_model_p250_rows.parquet")
D["won"] = D["won"].astype(bool)
D["date"] = pd.to_datetime(D["date"])
for c in ("player_slug", "rival_slugname"):
    D[c] = D[c].astype(str)
# the P rows carry no surface column; take it from the archive row itself
SUR = pd.read_parquet(AR, columns=["date", "player_slug", "rival_slugname", "surface"])
SUR["date"] = pd.to_datetime(SUR["date"], errors="coerce")
SUR["surface"] = SUR["surface"].astype(str).str.title()
for c in ("player_slug", "rival_slugname"):
    SUR[c] = SUR[c].astype(str)
SUR = SUR.drop_duplicates(["date", "player_slug", "rival_slugname"])
D = D.merge(SUR, on=["date", "player_slug", "rival_slugname"], how="left")
print(f"P rows with a surface attached: {100 * D.surface.notna().mean():.1f}%")

D = D.merge(LAY.rename(columns={"layoff": "lay_dog"}),
            on=["player_slug", "surface", "date"], how="left")
D = D.merge(LAY.rename(columns={"player_slug": "rival_slugname", "layoff": "lay_fav"}),
            on=["rival_slugname", "surface", "date"], how="left")
print(f"   dog layoff present {100 * D.lay_dog.notna().mean():.1f}%  "
      f"fav layoff present {100 * D.lay_fav.notna().mean():.1f}%")

out = []
for G in ("M", "W"):
    S = D[(D.G == G) & (D.player_odd <= BAND[G])].copy()
    for yr in YRS:
        tr, te = S[S.yr < yr], S[S.yr == yr].copy()
        if len(tr) < 400 or not len(te):
            continue
        mu, sd = tr[FEATS].mean(), tr[FEATS].std().replace(0, 1)
        w = fit_offset(((tr[FEATS] - mu) / sd).fillna(0).values,
                       tr.won.values.astype(float), tr.off.values)
        z = te.off.values + w[0] + ((te[FEATS] - mu) / sd).fillna(0).values @ w[1:]
        te["p_dog"] = 1 / (1 + np.exp(-z))
        out.append(te)
O = pd.concat(out)
O["p_fav"] = 1 - O.p_dog
O["fav_ev"] = O.p_fav * O.rival_odd - 1
O["fav_won"] = ~O.won.astype(bool)
O["lay_max"] = O[["lay_dog", "lay_fav"]].max(axis=1)

U = O[(O.rival_odd >= 1.5) & (O.rival_odd <= 2.0)].copy()
F = U[U.fav_ev >= EV_FAV]
print("\n" + "=" * 90)
print("DOES Ⓟ FAV CONCENTRATE ON STALE PROFILES?")
print("=" * 90)
print(f"   layoff (the longer of the two players), in-band universe vs P's fav picks:")
for lab, s in (("universe", U), ("Ⓟ FAV picks", F)):
    q = s.lay_max.dropna()
    print(f"      {lab:14s} median {q.median():5.0f}d   p75 {q.quantile(.75):5.0f}d   "
          f"p90 {q.quantile(.90):5.0f}d   share >60d {100 * (q > 60).mean():5.1f}%   "
          f"share >180d {100 * (q > 180).mean():4.1f}%")
print("\n   the Ⓟ FAV cell split by how stale the staler profile is:")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    S = F[F.G == G]
    print(f"      {gl}  all {rep(S.fav_won.values, S.rival_odd.values)}")
    for lo, hi in ((0, 14), (14, 60), (60, 180), (180, 1e9)):
        s = S[(S.lay_max >= lo) & (S.lay_max < hi)]
        lab = f"{lo}-{hi:.0f}d" if hi < 1e9 else "180d+"
        print(f"            {lab:9s} {rep(s.fav_won.values, s.rival_odd.values, floor=25)}")

print("\n" + "=" * 90)
print("AND THE HONEST COMPARISON: Ⓟ FAV's lift over the baseline, per year, same rows")
print("=" * 90)
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    for y in YRS:
        u = U[(U.G == G) & (U.yr == y)]
        f = u[u.fav_ev >= EV_FAV]
        if len(u) < 100:
            continue
        bh = 100 * u.fav_won.mean()
        fh = 100 * f.fav_won.mean()
        print(f"   {gl:6s} {y}  baseline {bh:4.1f}% hit / "
              f"{100 * np.where(u.fav_won, u.rival_odd - 1, -1).mean():+5.1f}% (n={len(u)})"
              f"   ->  P's picks {fh:4.1f}% / "
              f"{100 * np.where(f.fav_won, f.rival_odd - 1, -1).mean():+5.1f}% (n={len(f)})"
              f"   LIFT {fh - bh:+4.1f} pts")
