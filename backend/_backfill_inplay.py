"""BACKFILL THE IN-PLAY SUSPECT FLAG (2026-10-11).

The guard added to log_predictions only marks rows logged from now on. Existing rows need the
same test applied retrospectively, otherwise every lane keeps scoring the contaminated ITF
prices the audit found (-102 -> -1223 and +105 -> -290).

Same rule: |frozen price - opening price| > 20 probability points = not a closing line.
Only decidable where an opener exists, so this is a partial clean-up by construction.
"""
import numpy as np
import pandas as pd

PATH = "data_cache/tennis_prediction_log.parquet"
DRIFT_MAX_PP = 20.0

d = pd.read_parquet(PATH)
if "inplay_suspect" not in d.columns:
    d["inplay_suspect"] = False


def ip(a):
    a = pd.to_numeric(a, errors="coerce")
    return np.where(a > 0, 100.0 / (a + 100.0), -a / (-a + 100.0))


has = d["open_p1_odds"].notna() & d["p1_odds"].notna()
drift = pd.Series(np.nan, index=d.index)
drift[has] = 100.0 * (ip(d.loc[has, "p1_odds"]) - ip(d.loc[has, "open_p1_odds"]))
flag = drift.abs() > DRIFT_MAX_PP
d["inplay_suspect"] = flag.fillna(False)

lg = d["league"].astype(str)
grp = np.where(lg.str.contains("itf"), "ITF",
               np.where(lg.str.contains("chall"), "challenger", "tour"))
print("rows %d | with an opener %d | flagged in-play suspect %d"
      % (len(d), int(has.sum()), int(d.inplay_suspect.sum())))
for g in ("ITF", "challenger", "tour"):
    m = grp == g
    print("   %-11s %4d rows, %3d with opener, %2d flagged"
          % (g, int(m.sum()), int((m & has).sum()), int((m & d.inplay_suspect).sum())))
if d.inplay_suspect.any():
    print("\n   flagged rows:")
    for r in d[d.inplay_suspect].itertuples():
        print("      %-46s open %s -> frozen %s   settled=%s"
              % (("%s v %s" % (r.player_1, r.player_2))[:46], r.open_p1_odds, r.p1_odds,
                 r.settled))
d.to_parquet(PATH, index=False)
print("\nwritten back to %s" % PATH)
