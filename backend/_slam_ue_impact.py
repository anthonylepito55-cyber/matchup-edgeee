"""WHAT DID THE ROLAND GARROS DATA BUY? (2026-10-10)

tennis_slam_ue.py pulled real unforced errors from rolandgarros.com women's singles 2024-26 --
the one free, permitted source that actually publishes the field. This measures whether it was
worth it, on three questions, in increasing order of importance:

  1. COVERAGE   how many of the 195 players blocking 2026 WTA-tour dog matches now have a
                profile, and how many more of those matches have BOTH players profiled
                (baseline: 435 of 937).
  2. THE EDGE   does the LOW-ERROR DOG gate still pay on the WIDER sample? This is the one that
                decides it. More coverage is only good if the edge survives -- adding matches
                can just as easily dilute it, and a bigger losing lane is worse than a small
                winning one. Baseline to beat: +10.8% (n=276) on WTA tour.
  3. HONESTY    how much of any change comes from slam matches themselves rather than from
                newly-profiled players' WTA matches, since the first is a narrow win and the
                second is the leverage that justified the work.
"""
import sys

import numpy as np
import pandas as pd

import tennis_ue as U

GAP = 2.264
BAND = (2.0, 3.5)


def universe():
    KEEP = ["date", "player_slug", "rival_slugname", "player_odd", "rival_odd", "result",
            "tournament_level", "tournament"]
    df = pd.read_parquet("data_cache/tennisratio/all_match_logs.parquet", columns=KEEP)
    df["date"] = pd.to_datetime(df["date"])
    df["won"] = (df["result"] == "Win").astype(int)
    for c in ("player_odd", "rival_odd"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["rival_slugname"] = df["rival_slugname"].astype(str)
    side = df[["player_slug", "rival_slugname", "date"]].copy()
    mir = side.rename(columns={"player_slug": "rival_slugname", "rival_slugname": "player_slug"})
    df = df.merge(mir, on=["player_slug", "rival_slugname", "date"], how="inner")
    m = df[df["player_slug"].astype(str) < df["rival_slugname"]].drop_duplicates(
        ["player_slug", "rival_slugname", "date"])
    i1 = 1 / m["player_odd"].where(m["player_odd"] > 1.005)
    i2 = 1 / m["rival_odd"].where(m["rival_odd"] > 1.005)
    m["mkt"] = i1 / (i1 + i2)
    GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
    B = m[(m.date.dt.year >= 2024) & m.mkt.notna() & (m.mkt < 0.5)
          & m.player_odd.between(*BAND)].copy()
    B["G"] = B.player_slug.astype(str).map(GM)
    B["lvl"] = B.tournament_level.astype(str).str.lower()
    return B[(B.G == "W") & B.lvl.isin(["wta", "grand slams"])]


def rep(s):
    n = len(s)
    if n < 25:
        return f"n={n} (thin)"
    w = s.won.astype(bool)
    return (f"{int(w.sum())}-{n - int(w.sum())} hit {100 * w.mean():4.1f}% "
            f"vs mkt {100 * s.mkt.mean():4.1f}% | ROI "
            f"{100 * np.where(w, s.player_odd - 1, -1).mean():+6.1f}% (n={n})")


W = universe()
print(f"women's WTA-tour/slam dogs +100..+250, 2024-26: {len(W)}", flush=True)
D = U.load(force=True)
print(f"charted player-matches after the merge: {len(D)}")
if "src" in D.columns:
    print(f"  by source: {D.src.value_counts().to_dict()}")

rows = []
for r in W.itertuples():
    a = U.profile(r.player_slug, r.date)
    b = U.profile(r.rival_slugname, r.date)
    if not a or not b or a.get("ue_set_5") is None or b.get("ue_set_5") is None:
        continue
    rows.append({"won": bool(r.won), "odd": r.player_odd, "mkt": r.mkt, "lvl": r.lvl,
                 "yr": r.date.year, "gap": b["ue_set_5"] - a["ue_set_5"]})
R = pd.DataFrame(rows)
R.rename(columns={"odd": "player_odd"}, inplace=True)
print(f"\n1. COVERAGE")
print(f"   both players profiled: {len(R)} of {len(W)} ({100 * len(R) / len(W):.0f}%)")
print(f"   baseline before the slam data was 435 of 937 on the 2026 slice")
y26 = R[R.yr == 2026]
print(f"   2026 alone: {len(y26)} gradeable")

try:
    wl = pd.read_csv("data_cache/mcp/manual_ue_worklist.csv")
    miss = list(wl.player.astype(str))
    now = sum(1 for p in miss if U.profile(p))
    print(f"   of the {len(miss)} previously-missing players, {now} now have a profile")
except Exception as e:  # noqa: BLE001
    print(f"   (worklist check skipped: {e})")

print(f"\n2. THE EDGE on the wider sample  (baseline to beat: +10.8%, n=276 on WTA tour)")
G = R[R.gap >= GAP]
print(f"   gate (gap >= {GAP}):            {rep(G)}")
print(f"   every gradeable dog in band:   {rep(R)}")
for lv in ("wta", "grand slams"):
    s = G[G.lvl == lv]
    if len(s) >= 25:
        print(f"   {lv:14s}              {rep(s)}")
print("   by year:")
for Y in (2024, 2025, 2026):
    s = G[G.yr == Y]
    if len(s) >= 20:
        print(f"     {Y}: {rep(s)}")

print(f"\n3. WHERE THE NEW ROWS CAME FROM")
print(f"   slam matches in the gate:  {len(G[G.lvl == 'grand slams'])}")
print(f"   WTA-tour matches in the gate: {len(G[G.lvl == 'wta'])}")
print("   (the second is the leverage -- newly-profiled players' tour matches, not slam games)")
sys.stdout.flush()
