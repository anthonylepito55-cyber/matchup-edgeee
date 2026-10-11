"""TEST 2 (2026-10-10, user "try both"): give Model P a CAREER-PEAK feature.

The Brengle/Sharma miss exposed a structural hole. Astra Sharma is a former WTA ~#80; our rank
proxy reads her at 1170 because it is built from recent results only. EVERY Model P input is
recent-form (d_m_won, d_form_win, d_vs_band, d_lrank, d_sutr) -- a player's peak level is
invisible, so an ex-top-100 rebuilding at ITF level looks identical to a career journeywoman.

The archive already holds the data: `rival_rank` is the opponent's ranking at the time of each
match, so mirroring it over 615k rows gives a per-player ranking HISTORY. From that, as of each
match date and using only matches strictly BEFORE it (no leakage):

   cur   = the player's most recent known ranking
   peak  = the best (lowest) ranking they have ever held
   fall  = log(cur) - log(peak), how far they have dropped from their own best

Two new features, dog minus favourite:
   d_lpeak = log(peak_dog) - log(peak_fav)   -- who has the higher ceiling
   d_fall  = fall_dog - fall_fav             -- who is further below their own ceiling

Same strict walk-forward as production (base C/D already fit on years < Y; P refit per test
year on earlier years only; standardisation from the training years alone). Reported against
the identical baseline so the comparison is like-for-like -- added features must EARN the slot.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize

BASE = ["d_vs_band", "g_C", "g_gray", "g_Dma", "d_form_win", "d_m_perf", "d_m_won",
        "d_sutr", "d_lrank", "is_chall", "is_itf"]
BAND = {"M": 3.0, "W": 3.5}
EV_FAV, EV_DOG = 0.03, 0.05
YRS = (2024, 2025, 2026)


# ---- 1. per-player ranking history out of the archive --------------------------------
def rank_history():
    A = pd.read_parquet("data_cache/tennisratio/all_match_logs.parquet",
                        columns=["date", "rival_slugname", "rival_rank"])
    A["date"] = pd.to_datetime(A["date"], errors="coerce")
    A["rank"] = pd.to_numeric(A["rival_rank"], errors="coerce")
    A = A[A.date.notna() & A["rank"].between(1, 2000) & A.rival_slugname.notna()]
    A = A.rename(columns={"rival_slugname": "slug"})[["slug", "date", "rank"]]
    # one ranking per player per day, then the as-of-date running values
    A = A.groupby(["slug", "date"], as_index=False)["rank"].min().sort_values(["slug", "date"])
    g = A.groupby("slug", sort=False)
    # SHIFTED so a match's own day never contributes to its own feature
    A["cur"] = g["rank"].shift(1)
    A["peak"] = g["rank"].apply(lambda s: s.shift(1).cummin()).reset_index(level=0, drop=True)
    print(f"ranking history: {len(A)} player-days, {A.slug.nunique()} players, "
          f"{A.date.min().date()}..{A.date.max().date()}", flush=True)
    return A[A.cur.notna()][["slug", "date", "cur", "peak"]]


def attach(D, H):
    """merge_asof each side onto its last ranking row STRICTLY before the match date."""
    D = D.sort_values("date").reset_index(drop=True)
    H = H.sort_values("date")
    out = {}
    for side, col in (("dog", "player_slug"), ("fav", "rival_slugname")):
        L = D[["date", col]].rename(columns={col: "slug"}).sort_values("date")
        M = pd.merge_asof(L, H, on="date", by="slug", allow_exact_matches=False)
        out[f"cur_{side}"] = M["cur"].values
        out[f"peak_{side}"] = M["peak"].values
    for k, v in out.items():
        D[k] = v
    lg = lambda s: np.log(np.clip(s.astype(float), 1, 2000))
    D["d_lpeak"] = lg(D.peak_dog) - lg(D.peak_fav)
    D["d_fall"] = (lg(D.cur_dog) - lg(D.peak_dog)) - (lg(D.cur_fav) - lg(D.peak_fav))
    return D


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


def walk_forward(D, feats, label):
    out, wts = [], {}
    for G in ("M", "W"):
        S = D[(D.G == G) & (D.player_odd <= BAND[G])].copy()
        for yr in YRS:
            tr, te = S[S.yr < yr], S[S.yr == yr].copy()
            if len(tr) < 400 or not len(te):
                continue
            mu, sd = tr[feats].mean(), tr[feats].std().replace(0, 1)
            Xtr = ((tr[feats] - mu) / sd).fillna(0).values
            Xte = ((te[feats] - mu) / sd).fillna(0).values
            w = fit_offset(Xtr, tr.won.values.astype(float), tr.off.values)
            z = te.off.values + w[0] + Xte @ w[1:]
            te["p_dog"] = 1 / (1 + np.exp(-z))
            out.append(te)
            if yr == 2026:
                wts[G] = dict(zip(feats, np.round(w[1:], 3)))
    O = pd.concat(out)
    O["p_fav"] = 1 - O.p_dog
    O["fav_ev"] = O.p_fav * O.rival_odd - 1
    O["dog_ev"] = O.p_dog * O.player_odd - 1
    O["fav_won"] = ~O.won.astype(bool)
    print(f"\n[{label}] 2026 weights:")
    for G in ("M", "W"):
        if G in wts:
            print(f"   {G}: " + "  ".join(f"{k} {v:+.3f}" for k, v in wts[G].items()))
    return O


def score(O, label):
    print(f"\n{'=' * 80}\n{label}\n{'=' * 80}")
    F = O[(O.rival_odd >= 1.5) & (O.rival_odd <= 2.0) & (O.fav_ev >= EV_FAV)]
    Dg = O[O.dog_ev >= EV_DOG]
    for G, gl in (("M", "MEN"), ("W", "WOMEN")):
        f, d = F[F.G == G], Dg[Dg.G == G]
        print(f"   {gl:6s} Ⓟ FAV  {rep(f.fav_won.values, f.rival_odd.values)}")
        print(f"   {gl:6s} Ⓟ DOG  {rep(d.won.values, d.player_odd.values)}")
        for y in YRS:
            dy = d[d.yr == y]
            print(f"            dog {y}  {rep(dy.won.values, dy.player_odd.values, floor=20)}")
    return F, Dg


D = pd.read_parquet("data_cache/_model_p250_rows.parquet")
D["won"] = D["won"].astype(bool)
D["date"] = pd.to_datetime(D["date"])
H = rank_history()
D = attach(D, H)
cov = D[["d_lpeak", "d_fall"]].notna().all(axis=1).mean()
print(f"\nP rows: {len(D)} | peak features present on {100 * cov:.1f}%", flush=True)
print(D[["cur_dog", "peak_dog", "cur_fav", "peak_fav", "d_lpeak", "d_fall"]].describe().round(2))

O0 = walk_forward(D, BASE, "baseline 11 feats")
score(O0, "BASELINE -- production's 11 features")
for extra in (["d_lpeak"], ["d_fall"], ["d_lpeak", "d_fall"]):
    O1 = walk_forward(D, BASE + extra, "+" + "+".join(extra))
    score(O1, f"WITH {' + '.join(extra)}")
