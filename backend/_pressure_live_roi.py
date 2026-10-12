"""THE PRESSURE-POINT CELL ON THE LIVE LOG (2026-10-11, user: "The roi live of the pressure
points stuff").

The archive said fully priced (dog better on both dials -8.9%, fav better on both -7.1%, every
split negative). This is the forward test of the same cell.

The frozen log already carries the two pressure diffs as FROZEN pre-match features --
`c_sp_diff_p1` (serve-pressure, p1 minus p2) and `c_rp_diff_p1` (return-pressure) -- so no
recomputation and no as-of reconstruction is needed: these are the exact numbers the card had
at first serve. Both > 0 means player_1 is ahead on both dials, which is what TennisRatio's two
Compare-Players circles show.

Run on EC2 against the authoritative log. The stale LOCAL copy inverted a sign earlier today,
so every live number is computed here.
"""
import numpy as np
import pandas as pd

LOG = "data_cache/tennis_prediction_log.parquet"


def dec(a):
    a = float(a)
    return 1.0 + a / 100.0 if a > 0 else 1.0 + 100.0 / abs(a)


d = pd.read_parquet(LOG)
d["date"] = pd.to_datetime(d["date"], errors="coerce")
S = d[(d["settled"] == True) & d.p1_won.notna()                   # noqa: E712
      & d.p1_odds.notna() & d.p2_odds.notna()].copy()
for c in ("surface_bad", "inplay_suspect"):
    if c in S.columns:
        S = S[~S[c].fillna(False).astype(bool)]
print("settled, priced, clean rows: %d" % len(S))
for c in ("c_sp_diff_p1", "c_rp_diff_p1"):
    print("   %-16s present on %d (%.0f%%)" % (c, S[c].notna().sum(),
                                               100 * S[c].notna().mean()))
S = S[S.c_sp_diff_p1.notna() & S.c_rp_diff_p1.notna()].copy()
S["d1"], S["d2"] = S.p1_odds.map(dec), S.p2_odds.map(dec)
i1, i2 = 1 / S.d1, 1 / S.d2
S["mkt1"] = i1 / (i1 + i2)
S["dog1"] = S.mkt1 < 0.5
lg = S.league.astype(str)
S["G"] = np.where(lg.str.contains("wta") | lg.str.contains("itf_women"), "W", "M")
S["lvl"] = np.where(lg.str.contains("itf"), "ITF",
                    np.where(lg.str.contains("chall"), "challenger", "tour"))
print("rows with both pressure diffs: %d   %s..%s\n"
      % (len(S), str(S.date.min())[:10], str(S.date.max())[:10]))


def rep(rows, side_is_p1, lab, floor=10):
    n = len(rows)
    if n < floor:
        print("   %-46s n=%d (too thin)" % (lab, n))
        return
    s = np.asarray(side_is_p1, dtype=bool)
    won = np.where(s, rows.p1_won.astype(bool), ~rows.p1_won.astype(bool))
    odds = np.where(s, rows.d1, rows.d2)
    imp = np.where(s, rows.mkt1, 1 - rows.mkt1)
    pnl = np.where(won, odds - 1, -1.0)
    se = 100 * pnl.std(ddof=1) / np.sqrt(n)
    print("   %-46s %d-%d  wins %4.1f%%  no-vig %4.1f%%  EDGE %+5.1fpt  ROI %+6.1f%% ± %4.1f  (n=%d)"
          % (lab, int(won.sum()), n - int(won.sum()), 100 * won.mean(), 100 * imp.mean(),
             100 * (won.mean() - imp.mean()), 100 * pnl.mean(), se, n))


# orient the two dials to the DOG
sgn = np.where(S.dog1, 1.0, -1.0)
S["dog_sp"] = sgn * S.c_sp_diff_p1.astype(float)
S["dog_rp"] = sgn * S.c_rp_diff_p1.astype(float)
S["dog_both"] = (S.dog_sp > 0) & (S.dog_rp > 0)
S["fav_both"] = (S.dog_sp < 0) & (S.dog_rp < 0)

print("=" * 112)
print("LIVE -- BACK THE DOG, by its pressure profile   (archive said -8.9%)")
print("=" * 112)
rep(S, S.dog1, "every dog (baseline)")
rep(S[S.dog_both], S[S.dog_both].dog1, "** dog better on BOTH dials **")
rep(S[(S.dog_sp > 0) & (S.dog_rp <= 0)], S[(S.dog_sp > 0) & (S.dog_rp <= 0)].dog1,
    "   dog better on SERVE pressure only")
rep(S[(S.dog_sp <= 0) & (S.dog_rp > 0)], S[(S.dog_sp <= 0) & (S.dog_rp > 0)].dog1,
    "   dog better on RETURN pressure only")
rep(S[S.fav_both], S[S.fav_both].dog1, "   dog worse on BOTH (fade the fav)")

print("\n" + "=" * 112)
print("LIVE -- BACK THE FAVOURITE, same split   (archive said -7.1%)")
print("=" * 112)
rep(S, ~S.dog1, "every favourite (baseline)")
rep(S[S.fav_both], ~S[S.fav_both].dog1, "** fav better on BOTH **")
rep(S[S.dog_both], ~S[S.dog_both].dog1, "   fav worse on BOTH")

print("\n" + "=" * 112)
print("THE DOG-BETTER-ON-BOTH CELL, SPLIT")
print("=" * 112)
Q = S[S.dog_both]
for Gg, nm in (("M", "men"), ("W", "women")):
    rep(Q[Q.G == Gg], Q[Q.G == Gg].dog1, "      %s" % nm)
for lv in ("tour", "challenger", "ITF"):
    rep(Q[Q.lvl == lv], Q[Q.lvl == lv].dog1, "      %s" % lv)
dogdec = np.where(Q.dog1, Q.d1, Q.d2)
for lo, hi, nm in ((2.0, 3.0, "+100..+200"), (3.0, 99, "+200 and longer"),
                   (1.0, 2.0, "under +100")):
    m = (dogdec >= lo) & (dogdec < hi)
    rep(Q[m], Q[m].dog1, "      %s" % nm)
print("   tightened:")
for x in (0, 2, 5):
    m = (Q.dog_sp >= x) & (Q.dog_rp >= x)
    rep(Q[m], Q[m].dog1, "      both gaps >= %dpt" % x)
