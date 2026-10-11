"""THE SAME TEST ON -100..-200 FAVOURITES (2026-10-11, user: "-100 to -200 favorite").

Mirror of the dog study: one row per match from the FAVOURITE's side, priced 1.50-2.00 decimal,
split by whether the favourite is better than the dog on BOTH last-5 hold% and break% on that
surface.

Carries the same EDGE column (realised win rate minus the NO-VIG implied probability) so a
small-but-real edge is distinguishable from an exactly-priced one, and the same discipline:
mirror guard, `.shift(1)` before the window, last 5 CHARTED matches on that court.

Context for reading the result: everything measured today says the favourite side carries no
information -- all 13 model heads lose on favourites (-5.0% to -9.1% on n=487+), Model C's
favourite side is -5.0% +/- 2.5 on 711 matches, and 50 of 55 lane favourite-halves are
negative. So the interesting cell here is not "favourite better on both" (the common case) but
whether a favourite who is WORSE on both is a worthwhile fade -- i.e. whether the DOG in that
spot is the bet.
"""
import numpy as np
import pandas as pd

import tennis_archive as TA

MINW = 3
BAND = (1.5, 2.0)        # -200 .. -100


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
opp = have[key + ["l5_sgw", "l5_rgw", "player_odd"]].rename(
    columns={"player_slug": "rival_slugname", "rival_slugname": "player_slug",
             "l5_sgw": "o_sgw", "l5_rgw": "o_rgw", "player_odd": "dog_odd"})
M = have.merge(opp, on=key, how="inner")
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
M["G"] = M.player_slug.astype(str).map(GM)
i1 = 1 / M.player_odd.where(M.player_odd > 1.005)
i2 = 1 / M.rival_odd.where(M.rival_odd > 1.005)
M["mkt"] = i1 / (i1 + i2)
F = M[M.mkt.notna() & (M.mkt > 0.5) & M.player_odd.between(*BAND)].copy()
F["yr"] = F.date.dt.year
F["bs"] = F.l5_sgw > F.o_sgw
F["br"] = F.l5_rgw > F.o_rgw
F["both"] = F.bs & F.br
F["neither"] = (~F.bs) & (~F.br)
F["lvl"] = F.tournament_level.astype(str).str.lower()
print(f"\n-100..-200 FAVOURITES with both L5s: {len(F)}   "
      f"{F.date.min().date()}..{F.date.max().date()}")


def rep(s, lab, side="fav", floor=60):
    n = len(s)
    if n < floor:
        print(f"   {lab:40s} n={n} (thin)")
        return
    if side == "fav":
        w = s.won.astype(bool)
        odd = s.player_odd
        imp = 100 * s.mkt.mean()
    else:                                  # back the DOG in the same spots
        w = ~s.won.astype(bool)
        odd = s.dog_odd
        imp = 100 * (1 - s.mkt).mean()
    pnl = np.where(w, odd - 1, -1.0)
    hit = 100 * w.mean()
    se = 100 * pnl.std(ddof=1) / np.sqrt(n)
    print(f"   {lab:40s} {int(w.sum())}-{n - int(w.sum())}  wins {hit:4.1f}%  "
          f"no-vig {imp:4.1f}%  EDGE {hit - imp:+5.1f}pt  "
          f"ROI {100 * pnl.mean():+6.1f}% ± {se:4.1f}  (n={n})")


print("\n" + "=" * 100)
print("BACKING THE -100..-200 FAVOURITE")
print("=" * 100)
rep(F, "every -100..-200 favourite (baseline)")
rep(F[F.both], "fav better on BOTH L5 hold% and break%")
rep(F[F.bs & ~F.br], "fav better on hold% only")
rep(F[~F.bs & F.br], "fav better on break% only")
rep(F[F.neither], "fav WORSE on both (vulnerable)")

print("\n" + "=" * 100)
print("THE FADE: BACKING THE DOG IN THOSE SAME SPOTS")
print("=" * 100)
rep(F, "every spot -> back the dog", side="dog")
rep(F[F.neither], "fav worse on both -> back the dog", side="dog")
rep(F[F.both], "fav better on both -> back the dog", side="dog")

print("\n   favourite better on both, by gender / level / surface:")
for Gg, lab in (("M", "men"), ("W", "women")):
    rep(F[(F.G == Gg) & F.both], f"      {lab}")
for lab, msk in (("tour", ~F.lvl.str.contains("chall|itf|futures")),
                 ("challenger", F.lvl.str.contains("chall")),
                 ("ITF/futures", F.lvl.str.contains("itf|futures"))):
    rep(F[F.both & msk], f"      {lab}")
for sf in ("Hard", "Clay", "Grass"):
    rep(F[F.both & (F.surf == sf)], f"      {sf}")

print("\n   favourite better on both, by year:")
for y in sorted(x for x in F.yr.unique() if x >= 2021):
    rep(F[F.both & (F.yr == y)], f"      {y}")

print("\n   tightened by gap size (favourite ahead on both by X+):")
for x in (0, 5, 10, 15):
    rep(F[(F.l5_sgw - F.o_sgw >= x) & (F.l5_rgw - F.o_rgw >= x)], f"      both gaps >= {x}pt")
