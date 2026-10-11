"""How fast does each source have a finished match? (2026-10-10, user: "were we able to scrape
a site that gives recent games faster than tennis ratio?")

Compares, per day, three things for the matches on our own board:
  * SETTLED in the frozen log -- Polymarket Gamma (scores + settlement) and, for ITF,
    TennisExplorer via tennis_itf_settle.py
  * PRESENT in the TennisRatio archive at all (the result landed)
  * WITH A STAT LINE in the archive (serve/return/BP -- what Models C and D need)
The third is the one that matters: a result is cheap, a stat line is not.
"""
import numpy as np
import pandas as pd
import tennis_model_a as MA

MA._load()
K = ["date", "player_slug", "rival_slugname"]
A = pd.read_parquet("data_cache/tennisratio/all_match_logs.parquet",
                    columns=K + ["result", "service_games_won", "serve_pressure_all"])
A["date"] = pd.to_datetime(A["date"], errors="coerce")
for c in ("player_slug", "rival_slugname"):
    A[c] = A[c].astype(str)
A["has_stats"] = A.service_games_won.astype(str).str.match(r"^\d+/\d+$").fillna(False)
A["has_press"] = pd.to_numeric(A.serve_pressure_all, errors="coerce").notna()
idx = {}
for d, p, r, st, pr in zip(A.date.values, A.player_slug.values, A.rival_slugname.values,
                           A.has_stats.values, A.has_press.values):
    idx[(d, p)] = (st, pr)

L = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
L["date"] = pd.to_datetime(L["date"], errors="coerce")
L = L[L.date >= L.date.max() - pd.Timedelta(days=9)]
print(f"{'date':12s} {'logged':>7s} {'settled (PM/TE)':>16s} {'in archive':>11s} "
      f"{'+ stat line':>12s} {'+ pressure':>11s}")
for d, g in L.groupby(L.date.dt.date):
    n = len(g)
    sett = int((g.settled == True).sum())
    inar = st = pr = 0
    dd = np.datetime64(pd.Timestamp(d))
    for r in g.itertuples():
        s1 = MA.resolve(str(r.player_1))
        if not s1:
            continue
        hit = idx.get((dd, s1))
        if hit is None:
            continue
        inar += 1
        st += int(bool(hit[0]))
        pr += int(bool(hit[1]))
    f = lambda x: f"{x:4d} ({100 * x / max(n, 1):3.0f}%)"
    print(f"{str(d):12s} {n:7d} {f(sett):>16s} {f(inar):>11s} {f(st):>12s} {f(pr):>11s}")
print("\n  settled = we know who won and the set scores (Polymarket same-day; TennisExplorer")
print("  next-day for ITF). in archive = TennisRatio has the row at all. stat line = the")
print("  serve/return/BP numbers Models C and D are built on. pressure = the c_sp/c_rp family.")
