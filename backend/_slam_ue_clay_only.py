"""DOES THE ROLAND GARROS DATA WORK IF WE ONLY USE IT ON CLAY? (2026-10-10, user: "it could
stay the same roi but did it add more players to the list?")

It did add players: 35 of the 195 that were blocking 2026 WTA-tour dog matches, worth 70 extra
gate-eligible matches. The problem was that those 70 lost (-9.6%, and -49.5% on the 2026 subset).

But the diagnosed cause was a SURFACE MISMATCH, not bad players: RG is clay, clay averages +1.69
unforced errors per set more than the charting population, and the gate's whole threshold is
2.264 -- so a part-clay profile applied to a HARD-court match can clear the bar on surface mix
alone.

That suggests an obvious fix rather than throwing the data away: use it only where the profile
and the match agree on surface. So this scores the gate three ways on CLAY matches only --
without the RG rows, with them, and on the rows they add -- and does the same for hard courts as
a control. If the mismatch theory is right, clay should be fine or better with RG included, and
hard should be where the damage sits.

Also reports, for each, how many distinct players and matches the data adds, since the question
is explicitly whether the extra coverage is usable rather than merely larger.
"""
import os
import sys

import numpy as np
import pandas as pd

GAP = 2.264


def load_universe():
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
    return B[(B.G == "W") & B.lvl.isin(["wta", "grand slams"])]


def score(B, include_slam):
    os.environ["UE_INCLUDE_SLAM"] = "1" if include_slam else "0"
    import importlib

    import tennis_ue as U
    importlib.reload(U)
    U.load(force=True)
    rows = []
    for r in B.itertuples():
        a = U.profile(r.player_slug, r.date)
        b = U.profile(r.rival_slugname, r.date)
        if not a or not b or a.get("ue_set_5") is None or b.get("ue_set_5") is None:
            continue
        rows.append({"won": bool(r.won), "player_odd": r.player_odd, "mkt": r.mkt,
                     "surf": r.surf, "yr": r.date.year,
                     "gap": b["ue_set_5"] - a["ue_set_5"],
                     "k": (r.date, str(r.player_slug), str(r.rival_slugname)),
                     "p1": str(r.player_slug), "p2": str(r.rival_slugname)})
    return pd.DataFrame(rows)


def rep(s):
    n = len(s)
    if n < 20:
        return f"n={n} (thin)"
    w = s.won.astype(bool)
    return (f"{int(w.sum())}-{n - int(w.sum())} hit {100 * w.mean():4.1f}% | ROI "
            f"{100 * np.where(w, s.player_odd - 1, -1).mean():+6.1f}% (n={n})")


B = load_universe()
print(f"women's WTA-tour/slam dogs +100..+250, 2024-26: {len(B)}")
print(f"  by surface: {B.surf.value_counts().to_dict()}\n", flush=True)

OFF = score(B, False)
ON = score(B, True)
new_keys = set(map(tuple, ON.k)) - set(map(tuple, OFF.k))
print(f"gradeable without RG: {len(OFF)}   with RG: {len(ON)}   added: {len(new_keys)}")
pl_off = set(OFF.p1) | set(OFF.p2)
pl_on = set(ON.p1) | set(ON.p2)
print(f"distinct players appearing: {len(pl_off)} -> {len(pl_on)}  (+{len(pl_on - pl_off)})\n")

for surf in ("Clay", "Hard"):
    print(f"=== {surf.upper()} matches ===")
    o, n = OFF[OFF.surf == surf], ON[ON.surf == surf]
    print(f"  gate WITHOUT RG : {rep(o[o.gap >= GAP])}")
    print(f"  gate WITH RG    : {rep(n[n.gap >= GAP])}")
    addl = n[n.k.map(lambda x: tuple(x) in new_keys) & (n.gap >= GAP)]
    print(f"  only the ADDED rows: {rep(addl)}")
    print()
print("READ: if the surface-mismatch theory holds, CLAY should survive with RG included and")
print("HARD is where the damage is. If both sag, the added players are not usable either way.")
sys.stdout.flush()
