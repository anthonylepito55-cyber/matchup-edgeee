"""HOW OFTEN DOES THE DOG WITH THE BETTER LAST-5 HOLD% AND BREAK% WIN? (2026-10-11, user ask)

The card now shows last-5-on-surface SGW (hold%) and RGW (break%). This tests the obvious
question: when the market DOG is better than the favourite on BOTH over their last 5 on that
court, how often does the dog win, and does it beat the price?

Method, with the traps from today's session deliberately avoided:
  * **mirror guard** -- `tennis_archive.load(priced_only=True, require_mirror=True)`, because
    selecting rows by their own price on a one-sided archive manufactures an edge
  * **no leakage** -- the L5 window for a match uses only that player's EARLIER matches on that
    surface (`.shift(1)` before the rolling sum)
  * **last 5 CHARTED** -- rows without a parsed game line are dropped before the window is
    built, so the stat is always defined (the card shows last-5-played, which can be statless)
  * SGW and RGW are built from the game SUMS over the window, exactly as the card does
  * reported with a standard error, per gender, per year, against the all-dogs baseline, since
    a pooled multi-year number mislead me once already today
"""
import numpy as np
import pandas as pd

import tennis_archive as TA

COLS = ["surface", "service_games_won", "return_games_won", "tournament_level"]
MINW = 3          # need at least 3 charted matches in the window, same floor as the card


def frac(s):
    p = s.astype(str).str.extract(r"^(\d+)/(\d+)$")
    return pd.to_numeric(p[0], errors="coerce"), pd.to_numeric(p[1], errors="coerce")


df = TA.load(columns=COLS, priced_only=True, require_mirror=True, verbose=True)
df["surf"] = df["surface"].astype(str).str.title().replace({"I.Hard": "Hard", "Carpet": "Hard"})
df["sg_w"], df["sg_a"] = frac(df["service_games_won"])
df["rg_w"], df["rg_a"] = frac(df["return_games_won"])
df["won"] = df["result"].eq("Win").astype(int)
df = df[df.sg_a.notna() & df.rg_a.notna() & df.sg_a.gt(0) & df.rg_a.gt(0)].copy()
df = df.sort_values(["player_slug", "surf", "date"], kind="stable").reset_index(drop=True)
print(f"charted, priced, mirrored rows: {len(df)}")

g = df.groupby(["player_slug", "surf"], sort=False)
for c in ("sg_w", "sg_a", "rg_w", "rg_a"):
    # shift(1) first so a match never sees itself, then sum the previous 5
    df["p_" + c] = (g[c].shift(1).groupby([df.player_slug, df.surf])
                    .rolling(5, min_periods=MINW).sum().reset_index(level=[0, 1], drop=True))
df["l5_sgw"] = 100 * df.p_sg_w / df.p_sg_a.replace(0, np.nan)
df["l5_rgw"] = 100 * df.p_rg_w / df.p_rg_a.replace(0, np.nan)
have = df[df.l5_sgw.notna() & df.l5_rgw.notna()].copy()
print(f"rows with a usable L5 hold% and break%: {len(have)}")

# pair each match: the row is one side, the mirror gives the opponent's L5
key = ["date", "player_slug", "rival_slugname"]
opp = have[["date", "player_slug", "rival_slugname", "l5_sgw", "l5_rgw"]].rename(
    columns={"player_slug": "rival_slugname", "rival_slugname": "player_slug",
             "l5_sgw": "o_sgw", "l5_rgw": "o_rgw"})
M = have.merge(opp, on=key, how="inner")
print(f"matches where BOTH sides have an L5: {len(M)}")

GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
M["G"] = M.player_slug.astype(str).map(GM)
i1 = 1 / M.player_odd.where(M.player_odd > 1.005)
i2 = 1 / M.rival_odd.where(M.rival_odd > 1.005)
M["mkt"] = i1 / (i1 + i2)
M = M[M.mkt.notna()]
D = M[M.mkt < 0.5].copy()          # this row is the market DOG -> one row per match
D["yr"] = D.date.dt.year
D["better_sgw"] = D.l5_sgw > D.o_sgw
D["better_rgw"] = D.l5_rgw > D.o_rgw
D["both"] = D.better_sgw & D.better_rgw
D["neither"] = (~D.better_sgw) & (~D.better_rgw)
D["lvl"] = D.tournament_level.astype(str).str.lower()
print(f"\nDOG rows (one per match): {len(D)}   {D.date.min().date()}..{D.date.max().date()}")


def rep(s, lab, floor=60):
    n = len(s)
    if n < floor:
        print(f"   {lab:40s} n={n} (thin)")
        return
    w = s.won.astype(bool)
    pnl = np.where(w, s.player_odd - 1, -1.0)
    se = 100 * pnl.std(ddof=1) / np.sqrt(n)
    print(f"   {lab:40s} {int(w.sum())}-{n - int(w.sum())}  dog wins {100 * w.mean():4.1f}%  "
          f"mkt {100 * s.mkt.mean():4.1f}%  ROI {100 * pnl.mean():+6.1f}% ± {se:4.1f}  (n={n})")


print("\n" + "=" * 94)
print("BACKING THE DOG, SPLIT BY ITS LAST-5 HOLD% / BREAK% vs THE FAVOURITE'S")
print("=" * 94)
rep(D, "EVERY dog (the baseline)")
rep(D[D.both], "dog better on BOTH hold% and break%")
rep(D[D.better_sgw & ~D.better_rgw], "dog better on hold% only")
rep(D[~D.better_sgw & D.better_rgw], "dog better on break% only")
rep(D[D.neither], "dog worse on BOTH")

print("\n   by gender:")
for Gg, lab in (("M", "men"), ("W", "women")):
    S = D[D.G == Gg]
    rep(S, f"   {lab}: every dog")
    rep(S[S.both], f"   {lab}: better on BOTH")
    rep(S[S.neither], f"   {lab}: worse on BOTH")

print("\n   'better on both', by year:")
for y in sorted(D.yr.unique()):
    if y < 2022:
        continue
    rep(D[D.both & (D.yr == y)], f"      {y}")

print("\n   'better on both', by price band:")
for lo, hi in ((2.0, 2.5), (2.5, 3.5), (3.5, 5.0), (5.0, 99)):
    rep(D[D.both & D.player_odd.between(lo, hi)], f"      dog {lo:.1f}-{hi:.1f} dec")

print("\n   'better on both', by level and surface:")
for lab, msk in (("tour", ~D.lvl.str.contains("chall|itf|futures")),
                 ("challenger", D.lvl.str.contains("chall")),
                 ("ITF/futures", D.lvl.str.contains("itf|futures"))):
    rep(D[D.both & msk], f"      {lab}")
for sf in ("Hard", "Clay", "Grass"):
    rep(D[D.both & (D.surf == sf)], f"      {sf}")

print("\n   how big does the gap need to be? (both margins at least X points)")
for x in (0, 2, 5, 10, 15):
    s = D[(D.l5_sgw - D.o_sgw >= x) & (D.l5_rgw - D.o_rgw >= x)]
    rep(s, f"      both gaps >= {x}pt")
