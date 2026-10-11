"""THE DOG SIDE OF THE GAP-SIZE QUESTION (2026-10-11, user: "for dogs as well")

The favourite study found a monotone INVERSION: backing the dog against a -100..-200 favourite
got better the bigger that favourite's L5 hold/break advantage was (>=20pt: +9.9pt edge).
This runs the mirror on the DOG side -- back the DOG when the DOG is the one ahead on both
last-5 hold% and break%, tightened the same way -- plus the +100..+200 band the board bets.

Same discipline throughout: mirror guard, `.shift(1)` before the rolling window, last 5
CHARTED matches on that court, EDGE measured against the NO-VIG implied probability.
"""
import numpy as np
import pandas as pd

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
opp = have[key + ["l5_sgw", "l5_rgw"]].rename(
    columns={"player_slug": "rival_slugname", "rival_slugname": "player_slug",
             "l5_sgw": "o_sgw", "l5_rgw": "o_rgw"})
M = have.merge(opp, on=key, how="inner")
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
M["G"] = M.player_slug.astype(str).map(GM)
i1 = 1 / M.player_odd.where(M.player_odd > 1.005)
i2 = 1 / M.rival_odd.where(M.rival_odd > 1.005)
M["mkt"] = i1 / (i1 + i2)
D = M[M.mkt.notna() & (M.mkt < 0.5)].copy()      # this row is the market DOG
D["yr"] = D.date.dt.year
D["gs"] = D.l5_sgw - D.o_sgw
D["gr"] = D.l5_rgw - D.o_rgw
D["lvl"] = D.tournament_level.astype(str).str.lower()


def rep(s, lab, floor=40):
    n = len(s)
    if n < floor:
        print(f"   {lab:42s} n={n} (thin)")
        return
    w = s.won.astype(bool)
    pnl = np.where(w, s.player_odd - 1, -1.0)
    hit = 100 * w.mean()
    imp = 100 * s.mkt.mean()
    se = 100 * pnl.std(ddof=1) / np.sqrt(n)
    print(f"   {lab:42s} {int(w.sum())}-{n - int(w.sum())}  dog wins {hit:4.1f}%  "
          f"no-vig {imp:4.1f}%  EDGE {hit - imp:+5.1f}pt  "
          f"ROI {100 * pnl.mean():+6.1f}% ± {se:4.1f}  (n={n})")


for lab, S in (("ALL PRICES", D), ("+100..+200 ONLY", D[D.player_odd.between(2.0, 3.0)])):
    print("\n" + "=" * 104)
    print(f"BACK THE DOG when the DOG is ahead on both L5 hold% and break% -- {lab}")
    print("=" * 104)
    rep(S, "every dog (baseline)")
    for x in (0, 5, 10, 12, 15, 18, 20):
        rep(S[(S.gs >= x) & (S.gr >= x)], f"   dog ahead on both by >= {x}pt")
    sel = S[(S.gs >= 15) & (S.gr >= 15)]
    print("   the 15pt+ cell, by year / gender / level:")
    for y in sorted(v for v in sel.yr.unique() if v >= 2022):
        rep(sel[sel.yr == y], f"      {y}", floor=20)
    for Gg, gl in (("M", "men"), ("W", "women")):
        rep(sel[sel.G == Gg], f"      {gl}", floor=25)
    for ll, msk in (("tour", ~sel.lvl.str.contains("chall|itf|futures")),
                    ("challenger", sel.lvl.str.contains("chall")),
                    ("ITF/futures", sel.lvl.str.contains("itf|futures"))):
        rep(sel[msk], f"      {ll}", floor=25)
    if len(sel):
        yrs = max((sel.date.max() - sel.date.min()).days / 365.25, 1)
        print(f"   total 15pt+ spots: {len(sel)}  (~{len(sel) / yrs:.0f}/yr)")
