"""HOW DO WALKOVERS AND RETIREMENTS SHOW UP? (2026-10-12, user: "make sure u see if any
walkovers to not count them")

TennisRatio's archive barely labels them -- 53 rows in 615k have a non-numeric score (WO, BYE,
DEF, empty) and the strings "ret" and "retired" appear zero times. So they have to be detected
from the SHAPE of the match rather than a flag:

  * the winner never reached a winning set count (2 in a best-of-3, 3 in a best-of-5), which is
    what a retirement looks like -- "6-2 2-1" and the match stops;
  * the match is far too short to have produced a usable stat line at all.

Both matter for a last-10 block, which is the point: a hold% built on three service games is not
a hold%, and a win over someone who pulled out is not a win over them. This quantifies each
class so the exclusion rule is based on the data instead of a guess, and checks what the excluded
rows do to the stat line they would otherwise contribute.
"""
import numpy as np
import pandas as pd

P = "data_cache/tennisratio/all_match_logs.parquet"
d = pd.read_parquet(P)
d["date"] = pd.to_datetime(d["date"], errors="coerce")
d["won"] = (d["result"] == "Win").astype(int)
for col, pre in (("service_games_won", "sg"), ("return_games_won", "rg")):
    parts = d[col].astype(str).str.extract(r"^(\d+)/(\d+)$")
    d[pre + "_w"] = pd.to_numeric(parts[0], errors="coerce")
    d[pre + "_a"] = pd.to_numeric(parts[1], errors="coerce")
s = d["score"].astype(str)

# ---- parse the score into per-set game pairs ----
sets = s.str.findall(r"(\d+)-(\d+)")
d["nsets"] = sets.map(len)
def setswon(pairs):
    a = b = 0
    for x, y in pairs:
        x, y = int(x), int(y)
        if x > y:
            a += 1
        elif y > x:
            b += 1
    return a, b
sw = sets.map(setswon)
d["sets_for"] = [x[0] for x in sw]
d["sets_ag"] = [x[1] for x in sw]
d["games"] = sets.map(lambda ps: sum(int(x) + int(y) for x, y in ps))
d["bo5"] = (d["sets_for"] + d["sets_ag"]) >= 4
need = np.where(d["bo5"], 3, 2)

# the winner of a COMPLETED match must have reached the winning set count
win_sets = np.where(d["won"] == 1, d["sets_for"], d["sets_ag"])
d["incomplete"] = (win_sets < need) & (d["nsets"] > 0)
d["noscore"] = d["nsets"] == 0

print("rows: %d" % len(d))
print("no parseable score at all (WO / BYE / DEF / empty): %5d  (%.3f%%)"
      % (d["noscore"].sum(), 100 * d["noscore"].mean()))
print("winner never reached a winning set count (retirement): %5d  (%.3f%%)"
      % (d["incomplete"].sum(), 100 * d["incomplete"].mean()))
print("either: %d (%.3f%%)" % ((d.noscore | d.incomplete).sum(), 100 * (d.noscore | d.incomplete).mean()))
print()
print("games played, by class:")
for lab, m in (("completed", ~d.noscore & ~d.incomplete), ("retirement", d.incomplete),
               ("no score", d.noscore)):
    sub = d[m]
    print("   %-11s n=%-7d median games %5.1f   p10 %4.1f   service games p50 %4.1f"
          % (lab, len(sub), sub["games"].median(), sub["games"].quantile(0.10),
             sub["sg_a"].median()))

print("\nwhat a retirement does to the stat line it would contribute:")
for lab, m in (("completed", ~d.noscore & ~d.incomplete), ("retirement", d.incomplete)):
    sub = d[m]
    hold = 100 * sub["sg_w"].sum() / sub["sg_a"].sum()
    print("   %-11s hold%% %.1f  1st-serve-pts %.1f  rows with usable stats %.0f%%"
          % (lab, hold, sub["first_serve_points"].astype(float).mean(),
             100 * sub["sg_a"].notna().mean()))

print("\nretirements by year (the window only looks back 365 days, so recency matters):")
print(d[d.incomplete].groupby(d["date"].dt.year).size().tail(8).to_string())

print("\nSHORTEST completed matches -- is there a floor below which the stats are noise?")
q = d[~d.noscore & ~d.incomplete]
print(q["sg_a"].describe(percentiles=[0.01, 0.05, 0.1, 0.5]).to_string())
print("\nsample retirement scores:")
print(d.loc[d.incomplete, "score"].astype(str).head(12).tolist())
