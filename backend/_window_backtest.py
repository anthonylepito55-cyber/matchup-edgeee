"""BACKTEST THE WINDOW LADDER: L3 vs L5 vs L10 (2026-10-11, user: "what about backteststing last
3").

The live test said L3 does not improve on L5 and the effect saturates by five matches -- but it
rested on n=117 over five weeks, which is not enough to separate "saturated" from "unlucky".
This runs the identical cell on the archive, where the sample is ~100x larger.

Identical definition to the live test so the two are comparable:
  * one row per match, oriented to the market DOG
  * "better on BOTH" = ahead on hold% AND ahead on break% as SEPARATE conditions (never the
    sum -- those are different cells with different answers, which bit me earlier today)
  * the window is the previous K CHARTED matches on that surface, `.shift(1)` applied before
    the rolling sum so a match never sees itself
  * SGW/RGW rebuilt from the game SUMS over the window, exactly as the card builds them

Discipline carried over from the rest of this work: `tennis_archive.load(priced_only=True,
require_mirror=True)`, because selecting rows by their own price on a one-sided archive
manufactures an edge; EDGE measured against the NO-VIG implied probability so "priced exactly"
is distinguishable from "has an edge too small to clear the spread"; per-year and per-gender
splits, since a pooled multi-year number has misled me before.
"""
import numpy as np
import pandas as pd

import tennis_archive as TA

WINDOWS = (3, 5, 10)
MINW = 3          # same floor as the card: a window needs 3 charted matches


def frac(s):
    p = s.astype(str).str.extract(r"^(\d+)/(\d+)$")
    return pd.to_numeric(p[0], errors="coerce"), pd.to_numeric(p[1], errors="coerce")


df = TA.load(columns=["surface", "service_games_won", "return_games_won", "tournament_level"],
             priced_only=True, require_mirror=True, verbose=False)
df["surf"] = df["surface"].astype(str).str.title().replace({"I.Hard": "Hard", "Carpet": "Hard"})
df["sg_w"], df["sg_a"] = frac(df["service_games_won"])
df["rg_w"], df["rg_a"] = frac(df["return_games_won"])
df["won"] = df["result"].eq("Win").astype(int)
df = df[df.sg_a.notna() & df.rg_a.notna() & df.sg_a.gt(0) & df.rg_a.gt(0)].copy()
df = df.sort_values(["player_slug", "surf", "date"], kind="stable").reset_index(drop=True)
print("charted, priced, mirrored rows: %d" % len(df))

g = df.groupby(["player_slug", "surf"], sort=False)
for K in WINDOWS:
    for c in ("sg_w", "sg_a", "rg_w", "rg_a"):
        df["p%d_%s" % (K, c)] = (
            g[c].shift(1).groupby([df.player_slug, df.surf])
            .rolling(K, min_periods=MINW).sum().reset_index(level=[0, 1], drop=True))
    df["h%d" % K] = 100 * df["p%d_sg_w" % K] / df["p%d_sg_a" % K].replace(0, np.nan)
    df["r%d" % K] = 100 * df["p%d_rg_w" % K] / df["p%d_rg_a" % K].replace(0, np.nan)

cols = ["h%d" % K for K in WINDOWS] + ["r%d" % K for K in WINDOWS]
have = df[df[cols].notna().all(axis=1)].copy()      # same match set for every window
print("rows with ALL windows defined: %d" % len(have))

key = ["date", "player_slug", "rival_slugname"]
opp = have[key + cols].rename(columns={
    "player_slug": "rival_slugname", "rival_slugname": "player_slug",
    **{c: "o_" + c for c in cols}})
M = have.merge(opp, on=key, how="inner")
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
M["G"] = M.player_slug.astype(str).map(GM)
i1 = 1 / M.player_odd.where(M.player_odd > 1.005)
i2 = 1 / M.rival_odd.where(M.rival_odd > 1.005)
M["mkt"] = i1 / (i1 + i2)
D = M[M.mkt.notna() & (M.mkt < 0.5)].copy()         # this row is the market DOG
D["yr"] = D.date.dt.year
D["lvl"] = D.tournament_level.astype(str).str.lower()
for K in WINDOWS:                                    # the DOG's edge in each window
    D["dh%d" % K] = D["h%d" % K] - D["o_h%d" % K]
    D["dr%d" % K] = D["r%d" % K] - D["o_r%d" % K]
print("DOG rows (one per match): %d   %s..%s\n"
      % (len(D), D.date.min().date(), D.date.max().date()))


def rep(s, lab, floor=120):
    n = len(s)
    if n < floor:
        print("   %-44s n=%d (thin)" % (lab, n))
        return
    w = s.won.astype(bool)
    pnl = np.where(w, s.player_odd - 1, -1.0)
    hit, imp = 100 * w.mean(), 100 * s.mkt.mean()
    se = 100 * pnl.std(ddof=1) / np.sqrt(n)
    print("   %-44s dog wins %4.1f%%  no-vig %4.1f%%  EDGE %+5.1fpt  ROI %+6.1f%% +/- %4.1f  (n=%d)"
          % (lab, hit, imp, hit - imp, 100 * pnl.mean(), se, n))


def cells(S, tag):
    print("   %s" % tag)
    rep(S, "      every dog (baseline)")
    for K in WINDOWS:
        dh, dr = S["dh%d" % K], S["dr%d" % K]
        rep(S[(dh > 0) & (dr > 0)], "      L%-2d  DOG better on both" % K)
    for K in WINDOWS:
        dh, dr = S["dh%d" % K], S["dr%d" % K]
        rep(S[(dh < 0) & (dr < 0)], "      L%-2d  FAV better on both" % K)


print("=" * 110)
print("ARCHIVE BACKTEST -- back the market DOG, by window (same match set for every window)")
print("=" * 110)
cells(D, "ALL")
print()
for Gg, lab in (("M", "MEN"), ("W", "WOMEN")):
    cells(D[D.G == Gg], lab)
    print()

print("=" * 110)
print("MEN, the DOG-better-on-both cell per year -- is L3-vs-L5 stable?")
print("=" * 110)
Dm = D[D.G == "M"]
for K in WINDOWS:
    dh, dr = Dm["dh%d" % K], Dm["dr%d" % K]
    S = Dm[(dh > 0) & (dr > 0)]
    print("   L%d:" % K)
    for y in sorted(v for v in S.yr.unique() if v >= 2021):
        rep(S[S.yr == y], "      %d" % y, floor=60)

print("\n" + "=" * 110)
print("MEN, +100..+200 only (the band the board bets)")
print("=" * 110)
Db = Dm[Dm.player_odd.between(2.0, 3.0)]
rep(Db, "   every +100..+200 dog")
for K in WINDOWS:
    dh, dr = Db["dh%d" % K], Db["dr%d" % K]
    rep(Db[(dh > 0) & (dr > 0)], "   L%-2d  DOG better on both" % K)
    rep(Db[(dh < 0) & (dr < 0)], "   L%-2d  FAV better on both" % K)

print("\n" + "=" * 110)
print("MEN, where L3 and L5 DISAGREE on the dog leading")
print("=" * 110)
l3 = (Dm.dh3 > 0) & (Dm.dr3 > 0)
l5 = (Dm.dh5 > 0) & (Dm.dr5 > 0)
print("   dog leads on: L3 %d - L5 %d - both %d - L3 only %d - L5 only %d"
      % (int(l3.sum()), int(l5.sum()), int((l3 & l5).sum()),
         int((l3 & ~l5).sum()), int((l5 & ~l3).sum())))
rep(Dm[l3 & l5], "   both windows agree")
rep(Dm[l3 & ~l5], "   L3 only (hot last 3)")
rep(Dm[l5 & ~l3], "   L5 only (cooling)")

print("\n" + "=" * 110)
print("DOES THE SHORT WINDOW PREDICT? (all games, the leader's win rate vs the market)")
print("=" * 110)
A = M[M.mkt.notna()].copy()
for K in WINDOWS:
    dh = A["h%d" % K] - A["o_h%d" % K]
    dr = A["r%d" % K] - A["o_r%d" % K]
    sp = (dh + dr) > 0                   # ahead on the SUM, labelled as such
    f = A[(dh + dr) != 0]
    spf = sp[(dh + dr) != 0]
    hit = (spf == f.won.astype(bool)).mean()
    mkt = ((f.mkt > 0.5) == f.won.astype(bool)).mean()
    print("   L%-2d  leader (sum) wins %5.1f%%   market, same rows %5.1f%%   (n=%d)"
          % (K, 100 * hit, 100 * mkt, len(f)))
