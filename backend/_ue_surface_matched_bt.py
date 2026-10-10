"""A SURFACE-MATCHED UNFORCED-ERROR GATE (2026-10-10, user "Run it").

The shipped gate compares `ue_set_5` -- errors per set over each player's last 5 charted
matches on ANY court. That blindness is what blocks every new data source: Roland Garros rows
(clay) shift a profile by +1.69 errors/set, 75% of the gate's own 2.264 threshold, so merging
them manufactured qualifying gaps out of surface mix and measurably hurt.

`tennis_ue.profile()` already computes `ue_100_surf10`: errors per 100 points over the last 10
charted matches ON THIS SURFACE (needs 3+ there). A gate on that cannot be contaminated by
surface mix, because both sides are measured on the court being played. If it holds up, the 380
Roland Garros matches already on disk become usable, and so do the Australian Open and Wimbledon.

The risk, stated before running: it is strictly thinner. Requiring 3+ charted matches per player
PER SURFACE will cut the sample hard, and the earlier detail study found that none of five
alternatives beat ue_set_5. So this may simply not have the rows.

Measured three ways:
  1. coverage -- how many rows can even be graded, against ue_set_5's
  2. the gate, on identical rows, surface-matched vs ue_set_5
  3. the same with the Roland Garros rows merged in, to see whether surface-matching actually
     makes the extra data safe (the whole point)
"""
import os
import sys

import numpy as np
import pandas as pd

BAND = (2.0, 3.5)


def universe():
    KEEP = ["date", "player_slug", "rival_slugname", "player_odd", "rival_odd", "result",
            "tournament_level", "surface"]
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
    B["surf"] = B.surface.astype(str).str.title().replace({"Carpet": "Hard", "I.Hard": "Hard"})
    return B[(B.G == "W") & B.lvl.isin(["wta", "grand slams"])]


def rep(s, floor=25):
    n = len(s)
    if n < floor:
        return f"n={n} (thin)"
    w = s.won.astype(bool)
    return (f"{int(w.sum())}-{n - int(w.sum())} hit {100 * w.mean():4.1f}% "
            f"vs mkt {100 * s.mkt.mean():4.1f}% | ROI "
            f"{100 * np.where(w, s.player_odd - 1, -1).mean():+6.1f}% (n={n})")


def score(B, with_slam):
    os.environ["UE_INCLUDE_SLAM"] = "1" if with_slam else "0"
    import importlib

    import tennis_ue as U
    importlib.reload(U)
    U.load(force=True)
    rows = []
    for r in B.itertuples():
        a = U.profile(r.player_slug, r.date, r.surf)
        b = U.profile(r.rival_slugname, r.date, r.surf)
        if not a or not b:
            continue
        rows.append({
            "won": bool(r.won), "player_odd": r.player_odd, "mkt": r.mkt,
            "surf": r.surf, "yr": r.date.year,
            # surface-matched: errors per 100 points on THIS court
            "sm_dog": a.get("ue_100_surf10"), "sm_fav": b.get("ue_100_surf10"),
            # the shipped metric, for the like-for-like comparison
            "st_dog": a.get("ue_set_5"), "st_fav": b.get("ue_set_5"),
        })
    D = pd.DataFrame(rows)
    D["sm_gap"] = D.sm_fav - D.sm_dog
    D["st_gap"] = D.st_fav - D.st_dog
    return D


B = universe()
print(f"women's WTA-tour/slam dogs +100..+250, 2024-26: {len(B)}", flush=True)

for with_slam in (False, True):
    tag = "WITH Roland Garros rows" if with_slam else "charting project only"
    D = score(B, with_slam)
    sm = D.dropna(subset=["sm_gap"])
    st = D.dropna(subset=["st_gap"])
    both = D.dropna(subset=["sm_gap", "st_gap"])
    print("\n" + "=" * 84)
    print(f"{tag.upper()}")
    print("=" * 84)
    print(f"1. COVERAGE  surface-matched gradeable: {len(sm)}   ue_set_5 gradeable: {len(st)}"
          f"   both: {len(both)}")
    if len(both) < 60:
        print("   -> too thin to compare; surface-matched needs 3+ charted matches PER SURFACE")
        continue
    thr_sm = both.sm_gap.median()
    thr_st = both.st_gap.median()
    print(f"\n2. THE GATE on the {len(both)} rows BOTH can grade "
          f"(median split: surface-matched {thr_sm:.2f} per 100pts, ue_set {thr_st:.2f} per set)")
    print(f"   surface-matched: {rep(both[both.sm_gap >= thr_sm])}")
    print(f"   ue_set_5       : {rep(both[both.st_gap >= thr_st])}")
    print(f"   all rows        : {rep(both)}")
    print("   surface-matched by court:")
    for sf in ("Hard", "Clay", "Grass"):
        s2 = both[(both.surf == sf) & (both.sm_gap >= thr_sm)]
        print(f"     {sf:6s}: {rep(s2, floor=15)}")
    print("   surface-matched by year:")
    for Y in (2024, 2025, 2026):
        print(f"     {Y}: {rep(both[(both.sm_gap >= thr_sm) & (both.yr == Y)], floor=15)}")
    print("   and at the shipped gate's own strictness (top third of the gap):")
    t3 = both.sm_gap.quantile(2 / 3)
    print(f"     surface-matched gap >= {t3:.2f}: {rep(both[both.sm_gap >= t3])}")
sys.stdout.flush()
