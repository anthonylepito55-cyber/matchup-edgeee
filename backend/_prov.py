"""Provenance: exactly what is LIVE and over what window (2026-10-10, user asks)."""
import numpy as np
import pandas as pd
import tennis_log as TL

L = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
L["date"] = pd.to_datetime(L["date"], errors="coerce")
S = L[(L.settled == True) & L.p1_won.notna()]
print("THE FROZEN LIVE LOG")
print(f"   rows total {len(L)}   settled {len(S)}")
print(f"   full span      {L.date.min().date()} .. {L.date.max().date()}")
print(f"   settled span   {S.date.min().date()} .. {S.date.max().date()}")
print(f"   settled by month: "
      f"{ {str(k): int(v) for k, v in S.groupby(S.date.dt.to_period('M')).size().items()} }")
print()
has_c = S[S.model_c_p1.notna()]
print(f"   settled WITH Model C logged: {len(has_c)}   "
      f"{has_c.date.min().date()} .. {has_c.date.max().date()}")
for col, lab in (("mc_c75_p1", "c75"), ("model_cma_p1", "gray"), ("model_d_p1", "D"),
                 ("model_p_prob", "P")):
    h = S[S[col].notna()] if col in S.columns else S.iloc[:0]
    if len(h):
        print(f"   settled WITH {lab:5s}: {len(h):4d}   "
              f"{h.date.min().date()} .. {h.date.max().date()}")
tr = TL.get_tennis_track_record() or {}
print(f"\n   track-record endpoint says: since {tr.get('since')}, settled {tr.get('settled')}")
print("   (that is a narrower subset -- the A/B comparison universe -- not the whole log)")
