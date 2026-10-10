"""IS THE UNFORCED-ERROR EDGE A HARD-COURT EDGE? (2026-10-10)

Surfaced by the user asking whether the Roland Garros data at least added players. Splitting
that comparison by surface showed something more important than the answer: the gate's results
differ enormously by court, and the shipped lane has never been split that way.

Self-contained on purpose. The previous attempt imported _slam_ue_clay_only to reuse its
universe loader, which executed that script's whole body -- loading the slam rows and leaving
UE_INCLUDE_SLAM=1 -- so the numbers printed under "clean data" were actually the contaminated
ones. Nothing is imported here except tennis_ue, and the slam rows are explicitly excluded.
"""
import os
import sys

os.environ["UE_INCLUDE_SLAM"] = "0"

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import tennis_ue as U  # noqa: E402

GAP = 2.264

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
      & m.player_odd.between(2.0, 3.5)].copy()
B["G"] = B.player_slug.astype(str).map(GM)
B["lvl"] = B.tournament_level.astype(str).str.lower()
B["surf"] = B.surface.astype(str).str.title().replace({"Carpet": "Hard", "I.Hard": "Hard"})
B = B[(B.G == "W") & B.lvl.isin(["wta", "grand slams"])]

d = U.load(force=True)
assert "manual" not in set(d.get("src", pd.Series(dtype=str))), "slam rows leaked in"
print(f"charted rows in use: {len(d)} (sources: {d.src.value_counts().to_dict()})")
print(f"women's WTA-tour/slam dogs +100..+250, 2024-26: {len(B)}", flush=True)

rows = []
for r in B.itertuples():
    a = U.profile(r.player_slug, r.date)
    b = U.profile(r.rival_slugname, r.date)
    if not a or not b or a.get("ue_set_5") is None or b.get("ue_set_5") is None:
        continue
    rows.append({"won": bool(r.won), "player_odd": r.player_odd, "mkt": r.mkt,
                 "surf": r.surf, "yr": r.date.year, "gap": b["ue_set_5"] - a["ue_set_5"]})
R = pd.DataFrame(rows)
G = R[R.gap >= GAP]


def rep(s):
    n = len(s)
    if n < 20:
        return f"n={n} (thin)"
    w = s.won.astype(bool)
    return (f"{int(w.sum())}-{n - int(w.sum())} hit {100 * w.mean():4.1f}% "
            f"vs mkt {100 * s.mkt.mean():4.1f}% | ROI "
            f"{100 * np.where(w, s.player_odd - 1, -1).mean():+6.1f}% (n={n})")


print(f"\ngradeable: {len(R)} | gate fires on {len(G)}")
print("\n=== THE SHIPPED LANE, SPLIT BY SURFACE (clean data) ===")
print(f"  ALL surfaces : {rep(G)}")
for sf in ("Hard", "Clay", "Grass"):
    print(f"  {sf:12s}: {rep(G[G.surf == sf])}")
print("\n  ungated baseline, for contrast:")
for sf in ("Hard", "Clay", "Grass"):
    print(f"  {sf:12s}: {rep(R[R.surf == sf])}")
print("\n=== BY YEAR WITHIN SURFACE ===")
for sf in ("Hard", "Clay", "Grass"):
    print(f"  {sf}:")
    for Y in (2024, 2025, 2026):
        print(f"    {Y}: {rep(G[(G.surf == sf) & (G.yr == Y)])}")
sys.stdout.flush()
