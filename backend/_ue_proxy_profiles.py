"""STAGE 1 of the estimated-UE study (2026-10-09, user "anyway to get an unforced errors number
for every single game?"). Builds the as-of estimated-UE profile for every player and saves it,
then exits.

WHY A SEPARATE PROCESS: the first version did this and the universe build in one process and was
OOM-killed at 4.9GB (2026-10-10 06:25). It held the 615k-row archive plus its feature matrix and
then exec'd _tennis_model_c_build.py's prep, which loads the archive a SECOND time and builds its
own 52w-window / season / h2h frames. Splitting the two means the archive copy is handed back
before the universe build starts. This box has 7.7GB with ~3GB already held by the two uvicorns.

Output: data_cache/_ue_hat_profiles.parquet with (d, key, ue_hat5) -- the mean predicted UE/set
over each player's previous 5 matches, strictly prior, so it is safe to join onto a match on its
own date. Also saves the fitted proxy (pre-2024 charted matches only).
"""
import gc
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import tennis_ue_proxy as P

KEEP = ["date", "player_slug", "rival_slugname", "surface", "tournament_level", "score",
        "aces", "double_faults", "first_serve_accuracy", "first_serve_points",
        "second_serve_points", "return_1st_serve_points", "return_2nd_serve_points",
        "service_games_won", "return_games_won", "breakpoints_saved_count",
        "breakpoints_converted_count", "serve_pressure_all", "serve_pressure_won",
        "return_pressure_all", "return_pressure_won"]

print("loading archive (needed columns only)…", flush=True)
A = P.prep(pd.read_parquet("data_cache/tennisratio/all_match_logs.parquet", columns=KEEP))
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
A["G"] = A["player_slug"].astype(str).map(GM)

# ---- fit the proxy on charted matches BEFORE 2024 --------------------------------------
J = P.charted_truth(A)
J = J[J["d"] < "2024-01-01"]
mdl = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.06, random_state=0)
mdl.fit(P.build_feats(J, J["is_w"].values), J["ue_set"].values)
print(f"proxy fit on {len(J)} pre-2024 charted player-matches", flush=True)
del J
gc.collect()

# ---- predict UE/set for every archive row ----------------------------------------------
X = P.build_feats(A, (A["G"] == "W").astype(float).values)
ok = (X.notna().sum(axis=1) >= 18).values
A["ue_hat"] = np.nan
A.loc[ok, "ue_hat"] = mdl.predict(X[ok])
del X
gc.collect()
print(f"estimated UE on {int(ok.sum())} of {len(A)} player-matches ({100 * ok.mean():.1f}%)", flush=True)
cov = A.groupby("lvl")["ue_hat"].apply(lambda s: s.notna().mean())
print("  coverage by level: " + ", ".join(f"{k} {100 * v:.0f}%" for k, v in cov.items()), flush=True)

# ---- as-of profile: mean estimated UE/set over the previous 5 matches -------------------
A = A[["d", "key", "player_slug", "ue_hat"]].sort_values(["player_slug", "d"], kind="stable")
sh = A.groupby("player_slug", sort=False)["ue_hat"].shift(1)
A["ue_hat5"] = sh.groupby(A["player_slug"]).rolling(5, min_periods=5).mean() \
    .reset_index(level=0, drop=True)
out = A.dropna(subset=["ue_hat5"])[["d", "key", "ue_hat5"]].drop_duplicates(["d", "key"], keep="last")
out.to_parquet("data_cache/_ue_hat_profiles.parquet", index=False)
joblib.dump({"model": mdl, "feats": P.FEATS,
             "note": "UE/set from the archive stat line; fit on pre-2024 charted matches"},
            "model_artifacts/tennis_ue_proxy.joblib")
print(f"\nsaved data_cache/_ue_hat_profiles.parquet: {len(out)} player-dates")
print("saved model_artifacts/tennis_ue_proxy.joblib")
sys.stdout.flush()
