"""WHY HAVE THESE PICKS NEVER SETTLED? (2026-10-14)

Found while ordering the Dog picks tab: unsettled picks were sitting in the log from 10-10,
10-11 and 10-12 and landing at the top of a chronological list. An unsettled row is counted as
"pending" by every lane that holds it, so a row that never settles is a bet that silently never
resolves -- it inflates pending counts forever and its outcome never reaches any record.

This has happened before: all 130 ITF rows had never settled until they were name+date matched
off TennisExplorer (project_itf_settlement_fix), so the first question is whether this is the
same gap reappearing or something new.

Reported:
  1. every unsettled row whose match started more than 18 hours ago, with its league and age
  2. the same counted BY LEAGUE and BY DAY, against the settled rows on those days -- a league
     that settles 95% and one that settles 0% are different problems
  3. whether the players resolve in the rating pool at all, because an unresolvable name is the
     signature of the earlier ITF failure
  4. whether a RESULT exists for the match in the archive the settler reads from, which
     separates "we never fetched it" from "we fetched it and could not match the names"
"""
import datetime as dt
import os

import numpy as np
import pandas as pd

import tennis_log

log = pd.read_parquet(tennis_log.LOG_PATH)
log["_st"] = pd.to_datetime(log["start_time_utc"], errors="coerce", utc=True)
log["_d"] = log["date"].astype(str).str[:10]
now = pd.Timestamp.now(tz="UTC")
age_h = (now - log["_st"]).dt.total_seconds() / 3600.0

uns = log["p1_won"].isna()
stale = uns & (age_h > 18)
BAR = "=" * 100
print(BAR)
print("STALE UNSETTLED ROWS -- match started more than 18h ago and still has no result")
print(BAR)
print("   total rows %d | unsettled %d | of those STALE %d"
      % (len(log), int(uns.sum()), int(stale.sum())))

cols = [c for c in ("_d", "league", "player_1", "player_2", "tournament", "score") if c in log.columns]
S = log[stale].copy()
S["age_h"] = age_h[stale].round(1)
if len(S):
    print()
    print("   %-11s %-16s %-26s %-26s %7s %6s" % ("date", "league", "player 1", "player 2", "age h", "score"))
    for _, r in S.sort_values("_st").iterrows():
        print("   %-11s %-16s %-26s %-26s %7.1f %6s"
              % (r["_d"], str(r.get("league"))[:16], str(r.get("player_1"))[:26],
                 str(r.get("player_2"))[:26], r["age_h"],
                 "yes" if isinstance(r.get("score"), str) and r.get("score") else "-"))

print("\n" + BAR)
print("BY LEAGUE -- settled vs stale, on the days that have any stale rows")
print(BAR)
days = sorted(S["_d"].unique()) if len(S) else []
sub = log[log["_d"].isin(days)]
print("   %-18s %8s %8s %8s %9s" % ("league", "rows", "settled", "stale", "settle %"))
for lg, g in sub.groupby(sub["league"].astype(str)):
    st_ = int(g["p1_won"].notna().sum())
    sl = int((g["p1_won"].isna() & ((now - pd.to_datetime(g["start_time_utc"], errors="coerce", utc=True))
                                    .dt.total_seconds() / 3600 > 18)).sum())
    print("   %-18s %8d %8d %8d %8.0f%%" % (lg, len(g), st_, sl, 100 * st_ / max(len(g), 1)))

print("\n" + BAR)
print("BY DAY")
print(BAR)
for d in days:
    g = log[log["_d"] == d]
    st_ = int(g["p1_won"].notna().sum())
    sl = int((g["p1_won"].isna() & (age_h[g.index] > 18)).sum())
    print("   %s  rows %3d  settled %3d  stale %3d  (%.0f%% settled)"
          % (d, len(g), st_, sl, 100 * st_ / max(len(g), 1)))

print("\n" + BAR)
print("3. DO THE NAMES RESOLVE? an unresolvable name was the cause last time")
print(BAR)
try:
    import tennis_context as tc
    for _, r in S.sort_values("_st").iterrows():
        a = tc.get_context(r.get("player_1"), r.get("surface"))
        b = tc.get_context(r.get("player_2"), r.get("surface"))
        print("   %-26s %-9s  %-26s %-9s  %s"
              % (str(r.get("player_1"))[:26], "ok" if a else "UNRESOLVED",
                 str(r.get("player_2"))[:26], "ok" if b else "UNRESOLVED", r["_d"]))
except Exception as e:                                             # noqa: BLE001
    print("   context unavailable: %s" % type(e).__name__)

print("\n" + BAR)
print("4. IS THERE A RESULT TO FIND? checking the archive the settler reads")
print(BAR)
CAND = ["data_cache/tennis_matches.parquet", "data_cache/_tr_matches.parquet",
        "data_cache/tennisexplorer_results.parquet", "data_cache/te_results.parquet",
        "data_cache/_itf_results.parquet"]
found = [p for p in CAND if os.path.exists(p)]
print("   result archives present: %s" % (", ".join(os.path.basename(p) for p in found) or "none of the expected names"))
for p in found[:3]:
    try:
        A = pd.read_parquet(p)
        dc = next((c for c in A.columns if "date" in c.lower()), None)
        if dc is None:
            continue
        A["_d"] = pd.to_datetime(A[dc], errors="coerce").dt.strftime("%Y-%m-%d")
        print("   %-34s rows %-8d covers %s .. %s   rows on the stale days: %d"
              % (os.path.basename(p), len(A), A["_d"].min(), A["_d"].max(),
                 int(A["_d"].isin(days).sum())))
    except Exception as e:                                         # noqa: BLE001
        print("   %-34s unreadable (%s)" % (os.path.basename(p), type(e).__name__))
print("\n" + BAR)
