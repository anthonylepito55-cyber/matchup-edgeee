"""WHERE DOES THE UNFORCED-ERROR EDGE ACTUALLY LIVE? (2026-10-10, user: "im literally finding
more unforced error stats on dropshotft that arent popping up on my model")

The user is right that other sites show unforced errors for matches we are blank on. Dropshot
covers ATP/WTA tour only and licenses Goalserve, so Goalserve very likely does carry UE at tour
level, where official stats crews exist. Our charted coverage of WTA tour is only 21%, so a
licensed tour feed could take that slice towards 100%.

Whether that is worth buying depends entirely on one thing: IS THE +11.1% EDGE A TOUR-LEVEL
EDGE? The shipped lane (women's dog +100..+250, UE/set gap >= 2.264) was measured across every
charted match without splitting by level. Two warning signs say it might not be tour:
  * the detail study (which required MORE charting per player, i.e. the most-charted top-level
    regulars) found NO edge at all on that subsample;
  * the 2026 season work found TOUR is the premium level for dogs generally, so a tour-only
    version of this could equally be where it is strongest.
Only the split settles it. If the edge is in WTA-tour matches, a licensed tour feed is worth
pricing. If it sits at W-level/ITF, tour data buys nothing and we stop.

Same construction as every other study: closing odds, true gender, one row per match.
"""
import re
import sys
import unicodedata

import numpy as np
import pandas as pd

import tennis_ue as U

GAP = 2.264
ARCH = "data_cache/tennisratio/all_match_logs.parquet"


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


KEEP = ["date", "player_slug", "rival_slugname", "player_odd", "rival_odd", "result",
        "tournament_level", "tournament"]
df = pd.read_parquet(ARCH, columns=KEEP)
df["date"] = pd.to_datetime(df["date"])
df["won"] = (df["result"] == "Win").astype(int)
for c in ("player_odd", "rival_odd"):
    df[c] = pd.to_numeric(df[c], errors="coerce")
df["rival_slugname"] = df["rival_slugname"].astype(str)
side = df[["player_slug", "rival_slugname", "date"]].copy()
mir = side.rename(columns={"player_slug": "rival_slugname", "rival_slugname": "player_slug"})
df = df.merge(mir, on=["player_slug", "rival_slugname", "date"], how="inner")
m = df[df["player_slug"].astype(str) < df["rival_slugname"]].copy()
m = m.drop_duplicates(["player_slug", "rival_slugname", "date"])
i1, i2 = 1 / m["player_odd"].where(m["player_odd"] > 1.005), 1 / m["rival_odd"].where(m["rival_odd"] > 1.005)
m["mkt"] = i1 / (i1 + i2)
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
B = m[(m.date.dt.year >= 2024) & m.mkt.notna() & (m.mkt < 0.5)
      & m.player_odd.between(2.0, 3.5)].copy()
B["G"] = B.player_slug.astype(str).map(GM)
B = B[B.G == "W"].copy()
B["lvl"] = B["tournament_level"].astype(str).str.lower()
print(f"women's dogs +100..+250, 2024-26: {len(B)}", flush=True)

U.load()
rows = []
for r in B.itertuples():
    a = U.profile(r.player_slug, r.date)
    b = U.profile(r.rival_slugname, r.date)
    if not a or not b:
        continue
    da, db = a.get("ue_set_5"), b.get("ue_set_5")
    if da is None or db is None:
        continue
    rows.append({"won": bool(r.won), "odd": r.player_odd, "mkt": r.mkt, "lvl": r.lvl,
                 "yr": r.date.year, "gap": db - da, "tourn": r.tournament,
                 "dog_n": a.get("n_5"), "fav_n": b.get("n_5")})
D = pd.DataFrame(rows)
print(f"both players charted: {len(D)}")


def rep(s):
    n = len(s)
    if n < 25:
        return f"n={n} (thin)"
    w = s.won.astype(bool)
    return (f"{int(w.sum())}-{n - int(w.sum())} hit {100 * w.mean():4.1f}% "
            f"vs mkt {100 * s.mkt.mean():4.1f}% | ROI "
            f"{100 * np.where(w, s.odd - 1, -1).mean():+6.1f}% (n={n})")


G = D[D.gap >= GAP]
print(f"\nTHE SHIPPED LANE (gap >= {GAP}): {rep(G)}")
print(f"  every charted women's dog in band:  {rep(D)}")
print("\n=== THE SPLIT THAT DECIDES IT: by tournament level ===")
for lv, g in G.groupby("lvl"):
    print(f"  {lv:14s} {rep(g)}")
print("\n  (for reference, all charted dogs by level, no UE gate)")
for lv, g in D.groupby("lvl"):
    print(f"  {lv:14s} {rep(g)}")
print("\n=== and by year within each level ===")
for lv in G.lvl.unique():
    s = G[G.lvl == lv]
    if len(s) < 40:
        continue
    yr = " | ".join(f"{Y}: {rep(s[s.yr == Y])}" for Y in (2024, 2025, 2026))
    print(f"  {lv}\n     {yr}")
print("\n=== how charted are the players in the winning cells? ===")
print(f"  median prior charted matches, dog {D.dog_n.median():.0f} / fav {D.fav_n.median():.0f}")
for lv, g in G.groupby("lvl"):
    if len(g) >= 25:
        print(f"  {lv:14s} dog n={g.dog_n.median():.0f} fav n={g.fav_n.median():.0f}")
sys.stdout.flush()
