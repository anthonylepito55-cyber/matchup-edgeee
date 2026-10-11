"""A MEN'S LOW-ERROR DOG? (2026-10-11, user: "for low error dog is there any for men like we
have for women?")

The women's lane (`lowerr_dog_w`) is built on real unforced errors from the Match Charting
Project, and that road is closed for men twice over: the archive work found no men's UE edge,
and UE exists on 1.8% of our logged matches anyway (10 men's settled rows -- see
project_ue_live_coverage).

But there is a second error statistic, and it is the one that fits the men's game. The DOUBLE
FAULT is a pure unforced error, it is the only one recorded for essentially every match
(**97% of 615k archive rows**, including challengers and ITF where charting is 0%), and it sits
on the serve -- which is where men's matches are decided (hold% predicts 55.4% of men's matches,
break% an inverted 47.8%). If a men's analogue exists, this is where it should be.

Tested as the mirror of the women's lane: back the market DOG when the dog's pre-match
double-fault rate is LOWER than the favourite's.

Discipline, same as every other study here:
  * mirror guard -- `priced_only=True, require_mirror=True`, since selecting rows by their own
    price on a one-sided archive manufactures an edge
  * `.shift(1)` before the rolling window, so a match never sees its own double faults
  * rate = double faults per SERVICE GAME (the denominator matters: a 5-set match has more
    chances to fault than a 2-set one)
  * EDGE measured against the NO-VIG implied probability, per year, per level, per band
"""
import numpy as np
import pandas as pd

import tennis_archive as TA

WIN = 20          # matches in the look-back
MINW = 5


def frac(s):
    p = s.astype(str).str.extract(r"^(\d+)/(\d+)$")
    return pd.to_numeric(p[0], errors="coerce"), pd.to_numeric(p[1], errors="coerce")


df = TA.load(columns=["surface", "service_games_won", "double_faults", "aces",
                      "tournament_level"],
             priced_only=True, require_mirror=True, verbose=False)
df["surf"] = df["surface"].astype(str).str.title().replace({"I.Hard": "Hard", "Carpet": "Hard"})
df["sg_w"], df["sg_all"] = frac(df["service_games_won"])
df["dfs"] = pd.to_numeric(df["double_faults"], errors="coerce")
df["won"] = df["result"].eq("Win").astype(int)
df = df[df.dfs.notna() & df.sg_all.notna() & df.sg_all.gt(0)].copy()
df = df.sort_values(["player_slug", "date"], kind="stable").reset_index(drop=True)
print("charted, priced, mirrored rows with double faults: %d" % len(df))

# career-to-date DF per service game, strictly before each match
g = df.groupby("player_slug", sort=False)
for c in ("dfs", "sg_all"):
    df["p_" + c] = (g[c].shift(1).groupby(df.player_slug)
                    .rolling(WIN, min_periods=MINW).sum().reset_index(level=0, drop=True))
df["df_rate"] = df.p_dfs / df.p_sg_all.replace(0, np.nan)
have = df[df.df_rate.notna()].copy()
print("rows with a usable pre-match DF rate: %d" % len(have))

key = ["date", "player_slug", "rival_slugname"]
opp = have[key + ["df_rate"]].rename(columns={
    "player_slug": "rival_slugname", "rival_slugname": "player_slug", "df_rate": "o_df"})
M = have.merge(opp, on=key, how="inner")
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
M["G"] = M.player_slug.astype(str).map(GM)
i1 = 1 / M.player_odd.where(M.player_odd > 1.005)
i2 = 1 / M.rival_odd.where(M.rival_odd > 1.005)
M["mkt"] = i1 / (i1 + i2)
D = M[M.mkt.notna() & (M.mkt < 0.5)].copy()          # this row is the market DOG
D["yr"] = D.date.dt.year
D["lvl"] = D.tournament_level.astype(str).str.lower()
D["gap"] = D.o_df - D.df_rate                        # positive = the DOG faults LESS
print("DOG rows with both DF rates: %d   %s..%s\n"
      % (len(D), D.date.min().date(), D.date.max().date()))


def rep(s, lab, floor=150):
    n = len(s)
    if n < floor:
        print("   %-46s n=%d (thin)" % (lab, n))
        return
    w = s.won.astype(bool)
    pnl = np.where(w, s.player_odd - 1, -1.0)
    hit, imp = 100 * w.mean(), 100 * s.mkt.mean()
    se = 100 * pnl.std(ddof=1) / np.sqrt(n)
    print("   %-46s dog wins %4.1f%%  no-vig %4.1f%%  EDGE %+5.1fpt  ROI %+6.1f%% +/- %4.1f  (n=%d)"
          % (lab, hit, imp, hit - imp, 100 * pnl.mean(), se, n))


for Gg, lab in (("M", "MEN"), ("W", "WOMEN")):
    S = D[D.G == Gg]
    print("=" * 112)
    print("%s -- back the dog when the DOG double-faults LESS than the favourite" % lab)
    print("=" * 112)
    rep(S, "every dog (baseline)")
    rep(S[S.gap > 0], "dog faults less")
    rep(S[S.gap <= 0], "dog faults MORE (control)")
    med = S[S.gap > 0].gap.median()
    rep(S[S.gap > med], "dog faults less, gap above median")
    print("   by price band (dog faults less):")
    for lo, hi, nm in ((2.0, 3.0, "+100..+200"), (2.0, 3.5, "+100..+250"),
                       (3.0, 5.0, "+200..+400"), (1.5, 2.0, "under +100")):
        rep(S[(S.gap > 0) & S.player_odd.between(lo, hi)], "      %s" % nm)
    print("   by level (dog faults less):")
    for nm, msk in (("tour", ~S.lvl.str.contains("chall|itf|futures")),
                    ("challenger", S.lvl.str.contains("chall")),
                    ("ITF/futures", S.lvl.str.contains("itf|futures"))):
        rep(S[(S.gap > 0) & msk], "      %s" % nm)
    print("   by surface (dog faults less):")
    for sf in ("Hard", "Clay", "Grass"):
        rep(S[(S.gap > 0) & (S.surf == sf)], "      %s" % sf)
    print("   by year (dog faults less):")
    for y in sorted(v for v in S.yr.unique() if v >= 2021):
        rep(S[(S.gap > 0) & (S.yr == y)], "      %d" % y, floor=100)
    print()

print("=" * 112)
print("MEN -- the best-looking combinations, to see if anything survives stacking")
print("=" * 112)
S = D[D.G == "M"]
tour = ~S.lvl.str.contains("chall|itf|futures")
med = S[S.gap > 0].gap.median()
rep(S[(S.gap > 0) & tour & S.player_odd.between(2.0, 3.5)], "   tour + +100..+250")
rep(S[(S.gap > 0) & tour & (S.surf == "Hard")], "   tour + hard")
rep(S[(S.gap > 0) & (S.gap > med) & S.player_odd.between(2.0, 3.5)], "   big gap + +100..+250")
rep(S[(S.gap > 0) & (S.gap > med) & tour], "   big gap + tour")
rep(S[(S.gap > 0) & (S.gap > med) & tour & (S.surf == "Hard")], "   big gap + tour + hard")
