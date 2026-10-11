"""THE L5 HOLD/BREAK DOG, RESTRICTED TO +100..+200 (2026-10-11, user: "What about +100 to +200
dogs").

That is the band the board actually bets -- Model P's universe -- so it is the cut that matters.
The full-universe answer was 37.9% realised against 37.9% implied, i.e. fully priced; the
2.0-2.5 slice hinted at a small outperformance (42.9% realised vs 42.4% implied), so this
checks the exact band properly.

Adds one column the first pass lacked: **EDGE = realised win rate minus the NO-VIG implied
probability.** That isolates whether there is any edge at all BEFORE the vig is paid, which is
the only way to tell "priced exactly" apart from "has an edge too small to clear the spread".
Same discipline as before: mirror guard, shifted window, last 5 CHARTED on that surface.
"""
import numpy as np
import pandas as pd

import tennis_archive as TA

MINW = 3
BAND = (2.0, 3.0)        # +100 .. +200


def frac(s):
    p = s.astype(str).str.extract(r"^(\d+)/(\d+)$")
    return pd.to_numeric(p[0], errors="coerce"), pd.to_numeric(p[1], errors="coerce")


df = TA.load(columns=["surface", "service_games_won", "return_games_won", "tournament_level"],
             priced_only=True, require_mirror=True, verbose=True)
df["surf"] = df["surface"].astype(str).str.title().replace({"I.Hard": "Hard", "Carpet": "Hard"})
df["sg_w"], df["sg_a"] = frac(df["service_games_won"])
df["rg_w"], df["rg_a"] = frac(df["return_games_won"])
df["won"] = df["result"].eq("Win").astype(int)
df = df[df.sg_a.notna() & df.rg_a.notna() & df.sg_a.gt(0) & df.rg_a.gt(0)].copy()
df = df.sort_values(["player_slug", "surf", "date"], kind="stable").reset_index(drop=True)
g = df.groupby(["player_slug", "surf"], sort=False)
for c in ("sg_w", "sg_a", "rg_w", "rg_a"):
    df["p_" + c] = (g[c].shift(1).groupby([df.player_slug, df.surf])
                    .rolling(5, min_periods=MINW).sum().reset_index(level=[0, 1], drop=True))
df["l5_sgw"] = 100 * df.p_sg_w / df.p_sg_a.replace(0, np.nan)
df["l5_rgw"] = 100 * df.p_rg_w / df.p_rg_a.replace(0, np.nan)
have = df[df.l5_sgw.notna() & df.l5_rgw.notna()].copy()
key = ["date", "player_slug", "rival_slugname"]
opp = have[key + ["l5_sgw", "l5_rgw"]].rename(
    columns={"player_slug": "rival_slugname", "rival_slugname": "player_slug",
             "l5_sgw": "o_sgw", "l5_rgw": "o_rgw"})
M = have.merge(opp, on=key, how="inner")
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
M["G"] = M.player_slug.astype(str).map(GM)
i1 = 1 / M.player_odd.where(M.player_odd > 1.005)
i2 = 1 / M.rival_odd.where(M.rival_odd > 1.005)
M["mkt"] = i1 / (i1 + i2)
D = M[M.mkt.notna() & (M.mkt < 0.5) & M.player_odd.between(*BAND)].copy()
D["yr"] = D.date.dt.year
D["bs"] = D.l5_sgw > D.o_sgw
D["br"] = D.l5_rgw > D.o_rgw
D["both"] = D.bs & D.br
D["lvl"] = D.tournament_level.astype(str).str.lower()
print(f"\n+100..+200 dogs with both L5s: {len(D)}   "
      f"{D.date.min().date()}..{D.date.max().date()}")


def rep(s, lab, floor=60):
    n = len(s)
    if n < floor:
        print(f"   {lab:38s} n={n} (thin)")
        return
    w = s.won.astype(bool)
    pnl = np.where(w, s.player_odd - 1, -1.0)
    hit = 100 * w.mean()
    imp = 100 * s.mkt.mean()
    se = 100 * pnl.std(ddof=1) / np.sqrt(n)
    print(f"   {lab:38s} {int(w.sum())}-{n - int(w.sum())}  wins {hit:4.1f}%  "
          f"no-vig {imp:4.1f}%  EDGE {hit - imp:+5.1f}pt  ROI {100 * pnl.mean():+6.1f}% ± {se:4.1f}  (n={n})")


print("\n" + "=" * 100)
print("+100..+200 DOGS -- EDGE = realised win rate minus the NO-VIG implied probability")
print("=" * 100)
rep(D, "every +100..+200 dog (baseline)")
rep(D[D.both], "better on BOTH L5 hold% and break%")
rep(D[D.bs & ~D.br], "better on hold% only")
rep(D[~D.bs & D.br], "better on break% only")
rep(D[~D.bs & ~D.br], "worse on BOTH")

print("\n   BOTH, by gender:")
for Gg, lab in (("M", "men"), ("W", "women")):
    rep(D[(D.G == Gg)], f"      {lab}: baseline")
    rep(D[(D.G == Gg) & D.both], f"      {lab}: better on BOTH")

print("\n   BOTH, by year:")
for y in sorted(x for x in D.yr.unique() if x >= 2021):
    rep(D[D.both & (D.yr == y)], f"      {y}")

print("\n   BOTH, by level:")
for lab, msk in (("tour", ~D.lvl.str.contains("chall|itf|futures")),
                 ("challenger", D.lvl.str.contains("chall")),
                 ("ITF/futures", D.lvl.str.contains("itf|futures"))):
    rep(D[D.both & msk], f"      {lab}")

print("\n   BOTH, by surface:")
for sf in ("Hard", "Clay", "Grass"):
    rep(D[D.both & (D.surf == sf)], f"      {sf}")

print("\n   BOTH, tightened by gap size:")
for x in (0, 3, 6, 10):
    rep(D[(D.l5_sgw - D.o_sgw >= x) & (D.l5_rgw - D.o_rgw >= x)], f"      both gaps >= {x}pt")

print("\n   BOTH + the best-looking combinations:")
rep(D[D.both & (D.G == "M") & (D.surf == "Hard")], "      men, hard")
rep(D[D.both & (D.G == "W") & (D.surf == "Hard")], "      women, hard")
rep(D[D.both & (~D.lvl.str.contains("chall|itf|futures")) & (D.surf == "Hard")], "      tour, hard")
rep(D[D.both & D.player_odd.between(2.0, 2.5)], "      priced 2.0-2.5 only")
rep(D[D.both & D.player_odd.between(2.0, 2.3)], "      priced 2.0-2.3 only")
