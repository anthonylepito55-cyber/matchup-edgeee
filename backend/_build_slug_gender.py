"""TRUE GENDER MAP (2026-10-08). Rebuilds data_cache/_slug_gender.parquet.

WHY: the archive's `tournament_level` column says only "futures" for every ITF event, so
any level-based gender rule (the one the old backtest rig and the MC2 feature build both
used) files EVERY women's ITF match as MEN -- 17,210 of 2026's rows, 31% of its men's
bucket -- while its "women" bucket ends up WTA-tour only (4,917 of 22,127 true women's
rows). Gender actually lives in the `tournament` NAME: ITF events are M15/M25... vs
W15/W25/W35/W40/W50/W60/W75/W80/W100.

METHOD: label from unambiguous sources (level wta -> W, level atp/challengers -> M,
tournament name ^m\d -> M, ^w\d -> W; 79% direct coverage), then propagate per player
slug by mode -- players do not switch tours -- which resolves grand slams, national team
and olympic rows too. Result: 100% coverage, 1,759 players.

Consumers: _marks_bt_correct.py, _tennis_gender_side_bt_v2.py, _mc_asof_bt.py.
KNOWN STILL-BROKEN CONSUMER: _mc2_stage1b_serve_return.py builds its `wom` training
feature with a regex that misses w40/w60/w80 + slams (102,925 of 290,361 women's rows
mislabeled). MC2 is display-only and every MC2 betting cell measured negative anyway,
but a future MC2 rebuild should use this map.
"""
import numpy as np
import pandas as pd

m = pd.read_parquet("data_cache/tennisratio/all_match_logs.parquet")
lv = m["tournament_level"].astype(str).str.lower()
tn = m["tournament"].astype(str).str.lower().str.strip()
g = pd.Series(np.where(lv == "wta", "W",
                       np.where(lv.isin(["atp", "challengers"]), "M", "?")), index=m.index)
g[(g == "?") & tn.str.match(r"^w\d")] = "W"
g[(g == "?") & tn.str.match(r"^m\d")] = "M"
print(f"direct coverage: {(g != '?').mean():.4f}")
known = g[g != "?"].groupby(m.loc[g != "?", "player_slug"]).agg(lambda s: s.mode().iat[0])
full = g.where(g != "?", m["player_slug"].map(known).fillna("?"))
print(f"after slug propagation: {(full != '?').mean():.4f}  {full.value_counts().to_dict()}")
known.to_frame("g").to_parquet("data_cache/_slug_gender.parquet")
print(f"saved data_cache/_slug_gender.parquet: {len(known)} players")
