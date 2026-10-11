"""DOES THE ONE-SIDED ARCHIVE CONTAMINATION LAND ON Ⓟ FAV'S PICKS? (2026-10-10)

Established so far:
  * stats are clean -- no leakage in the 52w / last-10 / seasonal windows, and the
    backtest-vs-live window difference is unbiased (+0.001 on m_won)
  * prices are clean -- same 307 games, archive -5.3% vs live -5.6%
  * but the archive is backfilled ONE-SIDEDLY in 2026 and those rows are winner-biased:
    one-sided favourites 86.1% hit / +39.5% over 2026-09-06..10-10 (n=144, 18.5% of rows),
    against 59.5% / -4.1% for properly mirrored rows

A one-sided row means the OPPONENT has no row for that match -- i.e. the opponent is the
poorly-tracked player. A poorly-tracked opponent has a thin profile, which is exactly the
shape that makes C rate the dog badly and P call the favourite underpriced. So P's favourite
picks may be CONCENTRATED in the contaminated rows, which would make its whole favourite edge
an ingestion artifact rather than a signal.

Test: attach has_mirror to the P universe, refit the production walk-forward, and split the
Ⓟ FAV cell by it. If the edge lives in the one-sided rows, that is the answer to five years
of favourite cells failing live.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize

FEATS = ["d_vs_band", "g_C", "g_gray", "g_Dma", "d_form_win", "d_m_perf", "d_m_won",
         "d_sutr", "d_lrank", "is_chall", "is_itf"]
BAND = {"M": 3.0, "W": 3.5}
EV_FAV, EV_DOG = 0.03, 0.05
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


# ---- which P rows are one-sided in the archive? ----------------------------------------
K = ["date", "player_slug", "rival_slugname"]
A = pd.read_parquet(AR, columns=K)
A["date"] = pd.to_datetime(A["date"], errors="coerce")
A["player_slug"] = A["player_slug"].astype(str)
A["rival_slugname"] = A["rival_slugname"].astype(str)
A = A[A.date.notna()].drop_duplicates(K)
mir = A.rename(columns={"player_slug": "rival_slugname", "rival_slugname": "player_slug"})
mir["has_mirror"] = True
del A

D = pd.read_parquet("data_cache/_model_p250_rows.parquet")
D["won"] = D["won"].astype(bool)
D["date"] = pd.to_datetime(D["date"])
D["player_slug"] = D["player_slug"].astype(str)
D["rival_slugname"] = D["rival_slugname"].astype(str)
D = D.merge(mir.drop_duplicates(K), on=K, how="left")
D["has_mirror"] = D["has_mirror"].fillna(False)
print(f"P universe {len(D)} rows | one-sided (opponent's row missing): "
      f"{100 * (~D.has_mirror).mean():.2f}%")
print("   by year: " + "  ".join(
    f"{y} {100 * (~D[D.yr == y].has_mirror).mean():.1f}%" for y in (2022, 2023, 2024, 2025, 2026)))

# ---- production walk-forward ------------------------------------------------------------
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
O["dog_ev"] = O.p_dog * O.player_odd - 1
O["fav_won"] = ~O.won.astype(bool)

F = O[(O.rival_odd >= 1.5) & (O.rival_odd <= 2.0) & (O.fav_ev >= EV_FAV)]
print("\n" + "=" * 90)
print("Ⓟ FAV PICKS, SPLIT BY WHETHER THE ARCHIVE HAS BOTH SIDES OF THE MATCH")
print("=" * 90)
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    S = F[F.G == G]
    print(f"\n   {gl}")
    print(f"      as backtested (everything)   {rep(S.fav_won.values, S.rival_odd.values)}")
    print(f"      MIRRORED rows only           {rep(S[S.has_mirror].fav_won.values, S[S.has_mirror].rival_odd.values)}")
    print(f"      one-sided rows only          {rep(S[~S.has_mirror].fav_won.values, S[~S.has_mirror].rival_odd.values, floor=15)}")
    print(f"      one-sided share of its picks {100 * (~S.has_mirror).mean():.1f}%"
          f"   (universe-wide {100 * (~O[O.G == G].has_mirror).mean():.1f}%)")
    for y in YRS:
        s = S[(S.yr == y) & S.has_mirror]
        print(f"         {y} mirrored only  {rep(s.fav_won.values, s.rival_odd.values, floor=20)}")

print("\n" + "=" * 90)
print("IS Ⓟ FAV OVER-SELECTING THE CONTAMINATED ROWS? (pick rate on each population)")
print("=" * 90)
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    U = O[(O.G == G) & (O.rival_odd >= 1.5) & (O.rival_odd <= 2.0)]
    for tag, m in (("mirrored", U.has_mirror), ("one-sided", ~U.has_mirror)):
        s = U[m]
        if not len(s):
            continue
        print(f"   {gl:6s} {tag:10s} P picks the favourite on "
              f"{100 * (s.fav_ev >= EV_FAV).mean():5.1f}% of them  (n={len(s)})")

print("\n" + "=" * 90)
print("SANITY -- the Ⓟ DOG cell under the same split (the lane that is working live)")
print("=" * 90)
Dg = O[O.dog_ev >= EV_DOG]
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    S = Dg[Dg.G == G]
    print(f"   {gl:6s} all {rep(S.won.values, S.player_odd.values)}")
    print(f"          mirrored {rep(S[S.has_mirror].won.values, S[S.has_mirror].player_odd.values)}")
    print(f"          one-sided {rep(S[~S.has_mirror].won.values, S[~S.has_mirror].player_odd.values, floor=15)}")
