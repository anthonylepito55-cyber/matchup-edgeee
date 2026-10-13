"""Merge an already-computed G2 recon fill into the log (2026-10-12).

Split out from _model_g2_recon.py so the expensive part -- rebuilding both as-of windows for
every logged row -- never has to run twice. The recon writes
data_cache/_model_g2_recon_fill.parquet; this applies it, and only into rows where model_g2_p1
is still null, so a genuine frozen value can never be overwritten.
"""
import sys

import numpy as np
import pandas as pd

LOGP = sys.argv[1] if len(sys.argv) > 1 else "data_cache/tennis_prediction_log.parquet"
fill = pd.read_parquet("data_cache/_model_g2_recon_fill.parquet")
print("fill rows: %d" % len(fill), flush=True)
L = pd.read_parquet(LOGP)
for c in ("model_g2_p1", "model_g2ma_p1"):
    if c not in L.columns:
        L[c] = np.nan
if "model_g2_recon" not in L.columns:
    L["model_g2_recon"] = False
L["_d"] = L["date"].astype(str).str[:10]
idx = {(x.date, x.player_1, x.player_2): (x.model_g2_p1, x.model_g2ma_p1)
       for x in fill.itertuples()}
n = 0
for i in L.index:
    if pd.notna(L.at[i, "model_g2_p1"]):
        continue
    v = idx.get((L.at[i, "_d"], L.at[i, "player_1"], L.at[i, "player_2"]))
    if v is None:
        continue
    L.at[i, "model_g2_p1"], L.at[i, "model_g2ma_p1"] = v
    L.at[i, "model_g2_recon"] = True
    n += 1
L.drop(columns=["_d"]).to_parquet(LOGP)
s = L[L["p1_won"].notna()]
print("applied %d rows | settled G2 coverage now %d/%d = %.1f%%"
      % (n, s["model_g2_p1"].notna().sum(), len(s), 100 * s["model_g2_p1"].notna().mean()),
      flush=True)
