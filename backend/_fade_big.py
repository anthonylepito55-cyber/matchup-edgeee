"""FADE THE FAVOURITE WITH A BIG L5 ADVANTAGE? (2026-10-11)

The favourite study showed the gap size INVERTING: a -100..-200 favourite ahead on BOTH last-5
hold% and break% by 15+ points realised 52.4% against a no-vig 57.0% -- a -4.6pt edge and
-14.0% ROI. That is the same shape as this morning's finding that an extreme model edge on a
favourite is a fade, measured there on 711 matches.

So: back the DOG when the favourite's L5 advantage is large. Thin (n=374 at 15pt), so this
prints several thresholds with error bars and a per-year split, and it is a lead rather than a
result.
"""
import numpy as np
import pandas as pd
import pickle

import tennis_archive as TA

MINW = 3


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
F = M[M.mkt.notna() & (M.mkt > 0.5) & M.player_odd.between(1.5, 2.0)].copy()
F["yr"] = F.date.dt.year
F["gs"] = F.l5_sgw - F.o_sgw
F["gr"] = F.l5_rgw - F.o_rgw


def rep(s, lab, floor=40):
    n = len(s)
    if n < floor:
        print(f"   {lab:40s} n={n} (thin)")
        return
    w = ~s.won.astype(bool)                 # the DOG won
    pnl = np.where(w, s.dog_odd - 1, -1.0)
    hit = 100 * w.mean()
    imp = 100 * (1 - s.mkt).mean()
    se = 100 * pnl.std(ddof=1) / np.sqrt(n)
    print(f"   {lab:40s} {int(w.sum())}-{n - int(w.sum())}  dog wins {hit:4.1f}%  "
          f"no-vig {imp:4.1f}%  EDGE {hit - imp:+5.1f}pt  "
          f"ROI {100 * pnl.mean():+6.1f}% ± {se:4.1f}  (n={n})")


print("BACK THE DOG against a -100..-200 favourite, by how big the favourite's L5 edge is")
print("=" * 100)
rep(F, "every spot (baseline)")
for x in (5, 10, 12, 15, 18, 20):
    rep(F[(F.gs >= x) & (F.gr >= x)], f"   fav ahead on both by >= {x}pt")
print("\n   the 15pt+ cell, per year:")
sel = F[(F.gs >= 15) & (F.gr >= 15)]
for y in sorted(x for x in sel.yr.unique() if x >= 2018):
    rep(sel[sel.yr == y], f"      {y}", floor=15)
print("\n   the 15pt+ cell, by gender / level / surface:")
for Gg, lab in (("M", "men"), ("W", "women")):
    rep(sel[sel.G == Gg], f"      {lab}", floor=25)
lvl = sel.tournament_level.astype(str).str.lower()
for lab, msk in (("tour", ~lvl.str.contains("chall|itf|futures")),
                 ("challenger", lvl.str.contains("chall")),
                 ("ITF/futures", lvl.str.contains("itf|futures"))):
    rep(sel[msk], f"      {lab}", floor=25)
print(f"\n   total 15pt+ spots: {len(sel)} over {sel.date.min().date()}..{sel.date.max().date()}"
      f"  (~{len(sel) / max((sel.date.max() - sel.date.min()).days / 365.25, 1):.0f}/yr)")
