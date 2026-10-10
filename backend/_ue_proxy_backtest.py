"""DOES AN ESTIMATED UE CARRY THE EDGE? (2026-10-09, user "anyway to get an unforced errors
number for every single game?")

_ue_proxy_build.py showed the stat line predicts UE/set to MAE 2.4 (vs 3.2 for guessing the
mean, R^2 ~.40) and ranks the two players' error rates correctly 69.7% of the time, 78.3% when
the estimated gap is big. That is the easy half. This is the half that decides whether an
estimated UE is worth putting on a card:

build an as-of ESTIMATED-UE profile for every player in the archive (mean predicted UE/set over
their previous 5 matches), then re-run the women's LOW-ERROR DOG gate on the FULL universe --
every priced match, not just the charted few percent -- and compare with the real-UE result
(+11.1%, n=361, positive 2024/25/26).

Guards:
  * the proxy is refit on charted matches BEFORE 2024, so nothing in the 2024-26 test years
    trained it;
  * closing odds, true gender, one row per match (the two defects fixed 2026-10-08);
  * a player needs 5 prior matches with a usable stat line to get a profile.

Known bias, reported either way: the charted training set is ~92% tour-level, so predictions on
futures are an extrapolation -- which is why the backtest is also split by level.
"""
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import tennis_ue as U
import tennis_ue_proxy as P

GAP = 2.264        # the women's median real-UE gap the live lane uses

print("loading archive…", flush=True)
A = P.prep(pd.read_parquet("data_cache/tennisratio/all_match_logs.parquet"))
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
A["G"] = A["player_slug"].astype(str).map(GM)

# ---- refit the proxy on charted matches BEFORE 2024 ------------------------------------
J = P.charted_truth(A)
J = J[J["d"] < "2024-01-01"]
mdl = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.06, random_state=0)
mdl.fit(P.build_feats(J, J["is_w"].values), J["ue_set"].values)
print(f"proxy refit on {len(J)} pre-2024 charted player-matches")

# ---- predict UE/set for EVERY archive row ----------------------------------------------
XA = P.build_feats(A, (A["G"] == "W").astype(float).values)
ok = XA.notna().sum(axis=1) >= 18
A["ue_hat"] = np.nan
A.loc[ok, "ue_hat"] = mdl.predict(XA[ok])
print(f"estimated UE on {int(ok.sum())} of {len(A)} archive player-matches ({100 * ok.mean():.1f}%)")
cov = A.groupby("lvl")["ue_hat"].apply(lambda s: s.notna().mean())
print("  coverage by level: " + ", ".join(f"{k} {100 * v:.0f}%" for k, v in cov.items()))

# ---- as-of profile: mean estimated UE/set over the previous 5 matches -------------------
A = A.sort_values(["player_slug", "d"], kind="stable")
sh = A.groupby("player_slug", sort=False)["ue_hat"].shift(1)
A["ue_hat5"] = sh.groupby(A["player_slug"]).rolling(5, min_periods=5).mean() \
    .reset_index(level=0, drop=True)
prof = A.dropna(subset=["ue_hat5"]).set_index(["d", "key"])["ue_hat5"]
prof = prof[~prof.index.duplicated()]
print(f"as-of estimated-UE profiles: {len(prof)} player-dates")

# ---- the betting universe (same construction as the real-UE backtest) ------------------
ns = {}
src = open("_tennis_model_c_build.py", encoding="utf-8").read()
exec(compile(src.split("from sklearn.linear_model")[0], "_c_prep", "exec"), ns)
m = ns["m"]
B = m[(m.date.dt.year >= 2024) & m.mkt.notna() & (m.mkt < 0.5)
      & (m.player_odd > 1) & (m.rival_odd > 1)].copy()
B["G"] = B.player_slug.astype(str).map(GM)
B = B[B.G.isin(["M", "W"])].drop_duplicates(["date", "player_slug", "rival_slugname"])
B["k"] = B.player_slug.astype(str).map(U.norm)
B["ok"] = B.rival_slugname.astype(str).map(U.norm)
B["dn"] = B.date.dt.normalize()
B["ue_dog"] = [prof.get((d, k), np.nan) for d, k in zip(B.dn, B.k)]
B["ue_fav"] = [prof.get((d, k), np.nan) for d, k in zip(B.dn, B.ok)]
B["dam"] = (B.player_odd - 1) * 100
B["lv"] = B["tournament_level"].astype(str).str.lower() if "tournament_level" in B.columns else "?"
S = B.dropna(subset=["ue_dog", "ue_fav"]).copy()
S["gap"] = S.ue_fav - S.ue_dog          # + = the DOG is estimated to make fewer errors
print(f"\npriced 2024-26 dog rows with an estimated UE for BOTH players: {len(S)} "
      f"(men {int((S.G == 'M').sum())}, women {int((S.G == 'W').sum())})")
print("  for contrast, the REAL-UE backtest could only use rows where both players were charted")


def rep(s):
    n = len(s)
    if n < 30:
        return f"n={n} (thin)"
    w = s.won.astype(bool)
    return (f"{int(w.sum())}-{n - int(w.sum())} hit {100 * w.mean():4.1f}% "
            f"vs mkt {100 * s.mkt.mean():4.1f}% | ROI "
            f"{100 * np.where(w, s.player_odd - 1, -1).mean():+6.1f}% (n={n})")


print("\n=== WOMEN: the LOW-ERROR DOG gate on ESTIMATED UE ===")
W = S[(S.G == "W") & S.dam.between(100, 250)]
print(f"  every women's dog +100..+250 with profiles: {rep(W)}")
for lo, hi, lab in ((GAP, 99, f">= {GAP}"), (1.0, GAP, "1.0-2.26"),
                    (3.5, 99, ">= 3.5"), (5.0, 99, ">= 5.0"), (-99, 0, "dog WORSE")):
    print(f"    gap {lab:9s}: {rep(W[(W.gap >= lo) & (W.gap < hi)])}")
print("  by year (gap >= 2.26):")
for Y in (2024, 2025, 2026):
    print(f"    {Y}: {rep(W[(W.gap >= GAP) & (W.date.dt.year == Y)])}")
print("  by level (gap >= 2.26):")
WG = W[W.gap >= GAP]
for lv, g in WG.groupby(WG.lv):
    print(f"    {lv:14s}: {rep(g)}")

print("\n=== MEN (real UE showed no edge; does the estimate?) ===")
M = S[(S.G == "M") & S.dam.between(100, 250)]
print(f"  every men's dog +100..+250 with profiles: {rep(M)}")
print(f"    gap >= {GAP}: {rep(M[M.gap >= GAP])}")
for Y in (2024, 2025, 2026):
    print(f"    {Y}: {rep(M[(M.gap >= GAP) & (M.date.dt.year == Y)])}")

print("\n=== is the estimated gap monotone, or is it noise? ===")
for G, lab in (("W", "women"), ("M", "men")):
    T = S[(S.G == G) & S.dam.between(100, 250)].copy()
    if len(T) < 200:
        continue
    T["q"] = pd.qcut(T.gap, 5, labels=False, duplicates="drop")
    print(f"  {lab} dogs by estimated-gap quintile (Q1 = dog makes MORE errors):")
    for q, g in T.groupby("q"):
        print(f"    Q{int(q) + 1}: {rep(g)}")
joblib.dump({"model": mdl, "gap": GAP, "feats": P.FEATS,
             "note": "UE/set from the archive stat line; pre-2024 charted fit; as-of 5-match profile"},
            "model_artifacts/tennis_ue_proxy.joblib")
print("\nsaved model_artifacts/tennis_ue_proxy.joblib")
sys.stdout.flush()
