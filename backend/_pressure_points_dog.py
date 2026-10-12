"""PRESSURE POINTS WON ON SERVE **AND** RETURN -- WHAT IS THE ROI? (2026-10-11, user ask with a
TennisRatio Compare-Players screenshot: Bondar 58.8%/44.0% vs Pohankova 61.4%/49.1%).

These are the two dials TennisRatio shows on every comparison, and the archive carries the raw
counts behind them: `serve_pressure_won / serve_pressure_all` and
`return_pressure_won / return_pressure_all`. Note the coverage limit up front -- those columns
are populated on about 30% of archive rows, against ~97% for double faults and ~52% for the
serve lines, so this is a thinner universe than the hold/break work.

The question is the same shape as the L5 hold/break study: back the player who is better on
BOTH dials. Tested on the dog, on the favourite, and (because the hold/break version inverted)
on the FADE of each.

Mirrored to what the screenshot actually shows -- "This Season / All Levels / <surface>" -- so
the window is season-to-date ON THAT SURFACE, not a rolling 52 weeks.

Discipline as everywhere else: `tennis_archive.load(priced_only=True, require_mirror=True)`,
`.shift(1)` before the cumulative sums so a match never sees its own pressure points, EDGE
against the NO-VIG line, and per-year / per-gender splits.
"""
import numpy as np
import pandas as pd

import tennis_archive as TA

MIN_PTS = 40          # pressure points in the window before the rate is trusted


df = TA.load(columns=["surface", "serve_pressure_all", "serve_pressure_won",
                      "return_pressure_all", "return_pressure_won", "tournament_level"],
             priced_only=True, require_mirror=True, verbose=False)
df["surf"] = df["surface"].astype(str).str.title().replace({"I.Hard": "Hard", "Carpet": "Hard"})
for c in ("serve_pressure_all", "serve_pressure_won",
          "return_pressure_all", "return_pressure_won"):
    df[c] = pd.to_numeric(df[c], errors="coerce")
df["won"] = df["result"].eq("Win").astype(int)
have_raw = df[["serve_pressure_all", "return_pressure_all"]].notna().all(axis=1)
print("priced+mirrored rows: %d | with pressure-point counts: %d (%.0f%%)"
      % (len(df), int(have_raw.sum()), 100 * have_raw.mean()))
df = df[have_raw].copy()
df["yr"] = df["date"].dt.year
df = df.sort_values(["player_slug", "surf", "yr", "date"], kind="stable").reset_index(drop=True)

# season-to-date ON THIS SURFACE, strictly before the match -- what the screenshot shows
g = df.groupby(["player_slug", "surf", "yr"], sort=False)
for c in ("serve_pressure_all", "serve_pressure_won",
          "return_pressure_all", "return_pressure_won"):
    df["p_" + c] = g[c].cumsum() - df[c]        # cumulative EXCLUDING this match
df["sp"] = 100 * df.p_serve_pressure_won / df.p_serve_pressure_all.replace(0, np.nan)
df["rp"] = 100 * df.p_return_pressure_won / df.p_return_pressure_all.replace(0, np.nan)
ok = (df.p_serve_pressure_all >= MIN_PTS) & (df.p_return_pressure_all >= MIN_PTS)
have = df[ok & df.sp.notna() & df.rp.notna()].copy()
print("rows with a usable season-to-date pressure profile (>=%d pts each side): %d"
      % (MIN_PTS, len(have)))

key = ["date", "player_slug", "rival_slugname"]
opp = have[key + ["sp", "rp"]].rename(columns={
    "player_slug": "rival_slugname", "rival_slugname": "player_slug",
    "sp": "o_sp", "rp": "o_rp"})
M = have.merge(opp, on=key, how="inner")
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
M["G"] = M.player_slug.astype(str).map(GM)
i1 = 1 / M.player_odd.where(M.player_odd > 1.005)
i2 = 1 / M.rival_odd.where(M.rival_odd > 1.005)
M["mkt"] = i1 / (i1 + i2)
M = M[M.mkt.notna()].copy()
M["dog"] = M.mkt < 0.5
M["lvl"] = M.tournament_level.astype(str).str.lower()
M["better_sp"] = M.sp > M.o_sp
M["better_rp"] = M.rp > M.o_rp
M["both"] = M.better_sp & M.better_rp
M["neither"] = (~M.better_sp) & (~M.better_rp)
print("matches with BOTH players profiled: %d   %s..%s\n"
      % (len(M), M.date.min().date(), M.date.max().date()))


def rep(s, lab, floor=150):
    n = len(s)
    if n < floor:
        print("   %-46s n=%d (thin)" % (lab, n))
        return
    w = s.won.astype(bool)
    pnl = np.where(w, s.player_odd - 1, -1.0)
    hit, imp = 100 * w.mean(), 100 * s.mkt.mean()
    se = 100 * pnl.std(ddof=1) / np.sqrt(n)
    print("   %-46s wins %4.1f%%  no-vig %4.1f%%  EDGE %+5.1fpt  ROI %+6.1f%% ± %4.1f  (n=%d)"
          % (lab, hit, imp, hit - imp, 100 * pnl.mean(), se, n))


D = M[M.dog]
F = M[~M.dog]
print("=" * 112)
print("BACK THE DOG, by its pressure-point profile vs the favourite's")
print("=" * 112)
rep(D, "every dog (baseline)")
rep(D[D.both], "** dog better on BOTH serve+return pressure **")
rep(D[D.better_sp & ~D.better_rp], "   dog better on SERVE pressure only")
rep(D[~D.better_sp & D.better_rp], "   dog better on RETURN pressure only")
rep(D[D.neither], "   dog worse on BOTH (the fade of the fav)")

print("\n" + "=" * 112)
print("BACK THE FAVOURITE, same split")
print("=" * 112)
rep(F, "every favourite (baseline)")
rep(F[F.both], "** fav better on BOTH **")
rep(F[F.neither], "   fav worse on BOTH")

print("\n" + "=" * 112)
print("THE QUALIFYING CELL, SPLIT (dog better on both)")
print("=" * 112)
S = D[D.both]
print("   by gender:")
for Gg, nm in (("M", "men"), ("W", "women")):
    rep(S[S.G == Gg], "      %s" % nm)
print("   by year:")
for y in sorted(v for v in S.yr.unique() if v >= 2022):
    rep(S[S.yr == y], "      %d" % y, floor=80)
print("   by price:")
for lo, hi, nm in ((2.0, 3.0, "+100..+200"), (3.0, 5.0, "+200..+400"), (1.0, 2.0, "under +100")):
    rep(S[S.player_odd.between(lo, hi)], "      %s" % nm)
print("   by level:")
for nm, msk in (("tour", ~S.lvl.str.contains("chall|itf|futures")),
                ("challenger", S.lvl.str.contains("chall")),
                ("ITF", S.lvl.str.contains("itf|futures"))):
    rep(S[msk], "      %s" % nm)
print("   how big does the double edge need to be?")
for x in (0, 2, 5, 10):
    rep(D[(D.sp - D.o_sp >= x) & (D.rp - D.o_rp >= x)], "      both gaps >= %dpt" % x)
