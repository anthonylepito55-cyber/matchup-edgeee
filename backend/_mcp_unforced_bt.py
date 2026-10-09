"""REAL UNFORCED ERRORS backtest (2026-10-09). Profiles from tennis_ue.py (Tennis Abstract
Match Charting Project, as-of, last 5 / last 10 / surface). Universe: every 2024-26 match in
our odds archive (closing odds, true gender, one row per match from the dog's side) where
BOTH players have >= 3 charted matches in the prior 2 years. For each metric: does the
player who is better on it win more than the price says, as a dog and as a favourite?
Opponent quality of the charted matches comes from the archive's rival_rank where the
charted match is in the archive."""
import numpy as np
import pandas as pd

import tennis_ue as U

C = U.load()
print(f"charted player-matches: {len(C)} | players {C.key.nunique()} | latest charted match {C.date.max():%Y-%m-%d}")
print("charted player-matches by year (2022+):", C[C.date.dt.year >= 2022].date.dt.year.value_counts().sort_index().to_dict())

ns = {}
src = open("_tennis_model_c_build.py", encoding="utf-8").read()
exec(compile(src.split("from sklearn.linear_model")[0], "_c_prep", "exec"), ns)
m = ns["m"]
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()

# opponent quality of each player's charted matches (rank of the opponent at match time)
rk = m[["date", "player_slug", "rival_slugname", "rival_rank"]].copy()
rk["k"], rk["ok"] = rk.player_slug.astype(str).map(U.norm), rk.rival_slugname.astype(str).map(U.norm)
rk = rk.dropna(subset=["rival_rank"]).drop_duplicates(["date", "k", "ok"]).set_index(["date", "k", "ok"])["rival_rank"]
C["opp_rank"] = [rk.get((d, k, o), np.nan) for d, k, o in zip(C.date.dt.normalize(), C.key, C.okey)]
print(f"charted matches with an opponent rank from the archive: {int(C.opp_rank.notna().sum())} / {len(C)}")

A = m[(m.date.dt.year >= 2024) & m.mkt.notna() & (m.mkt < 0.5) & (m.player_odd > 1) & (m.rival_odd > 1)].copy()
A["G"] = A.player_slug.astype(str).map(GM)
A = A[A.G.isin(["M", "W"])].drop_duplicates(["date", "player_slug", "rival_slugname"])
by = U._CACHE["by"]
opp_by = {k: g for k, g in C.groupby("key")}
rows = []
for r in A.itertuples():
    pd_ = U.profile(r.player_slug, r.date, r.surface)
    pf_ = U.profile(r.rival_slugname, r.date, r.surface)
    if not pd_ or not pf_:
        continue
    def oq(slug):
        g = opp_by.get(U.norm(slug))
        g = g[(g.date < r.date)].tail(10) if g is not None else None
        return float(np.nanmean(g.opp_rank)) if g is not None and g.opp_rank.notna().any() else np.nan
    rows.append({"G": r.G, "yr": r.date.year, "won": bool(r.won), "mkt": r.mkt, "dog_odd": r.player_odd, "fav_odd": r.rival_odd,
                 **{f"d_{k}": v for k, v in pd_.items() if not isinstance(v, str)},
                 **{f"f_{k}": v for k, v in pf_.items() if not isinstance(v, str)},
                 "d_oq": oq(r.player_slug), "f_oq": oq(r.rival_slugname)})
D = pd.DataFrame(rows)
D.to_parquet("data_cache/_mcp_ue_rows.parquet")
D["dam"] = (D.dog_odd - 1) * 100
print(f"\narchive matches 2024-26 with UE profiles for BOTH players: {len(D)} (men {int((D.G == 'M').sum())}, women {int((D.G == 'W').sum())})")


def rep(s, side, f=40):
    n = len(s)
    if n < f:
        return f"n={n} (thin)"
    w = s.won.astype(bool) if side == "dog" else ~s.won.astype(bool)
    o = s.dog_odd if side == "dog" else s.fav_odd
    imp = s.mkt if side == "dog" else 1 - s.mkt
    return f"{int(w.sum())}-{n-int(w.sum())} win {100*w.mean():4.1f}% vs {100*imp.mean():4.1f}% ROI {100*np.where(w, o-1, -1).mean():+6.1f}% (n={n})"


# metric, label, sign (+1 = higher is better for the player)
MET = [("ue_match_5", "UEs per match, last 5", -1), ("ue_match_10", "UEs per match, last 10", -1),
       ("ue_set_5", "UEs per set, last 5", -1), ("ue_set_10", "UEs per set, last 10", -1),
       ("ue_100_5", "UEs per 100 pts, last 5", -1), ("ue_100_10", "UEs per 100 pts, last 10", -1),
       ("ue_100_surf10", "UEs per 100 pts, same surface (last 10)", -1),
       ("wue_10", "winners / UEs ratio, last 10", +1),
       ("fh_100_10", "forehand UEs per 100 pts, last 10", -1), ("bh_100_10", "backhand UEs per 100 pts, last 10", -1),
       ("pts_10", "points per match (duration), last 10", +1), ("oq", "avg opponent rank of charted matches (lower = tougher)", -1)]
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    T = D[D.G == G]
    if len(T) < 40:
        continue
    print(f"\n==================== {gl} ({len(T)} matches) ====================")
    print(f"   every dog: {rep(T, 'dog')}")
    for k, lab, sg in MET:
        d, f = T[f"d_{k}"], T[f"f_{k}"]
        ok = d.notna() & f.notna()
        S = T[ok]
        if len(S) < 40:
            print(f"   {lab:44s} thin (n={len(S)})")
            continue
        gap = sg * (d[ok] - f[ok])            # + = DOG better on this metric
        q = gap.abs().quantile(.5)
        print(f"   {lab}")
        print(f"      DOG better            back DOG {rep(S[gap > 0], 'dog')} | who's better wins {100*np.mean(np.where(gap > 0, S.won, ~S.won.astype(bool))):.1f}%")
        print(f"      DOG better (big gap)  back DOG {rep(S[gap > q], 'dog')} | +100..+250: {rep(S[(gap > q) & S.dam.between(100, 250)], 'dog')}")
        print(f"      FAV better (big gap)  back FAV {rep(S[gap < -q], 'fav')}")
