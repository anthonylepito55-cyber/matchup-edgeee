"""DOES MC3's ACCURACY TURN INTO MONEY? (2026-10-13, user: "yes run the roi measurement").

Every number produced for MC3 today was AUC, Brier or the mean gap to the market. None of those
pay. A head can be better calibrated and still never produce a bettable edge, or produce one
only in price bands nobody plays. This is the measurement that was missing.

    MC2 recipe   data_cache/_mc2_features.parquet   binary Elo, career serve/return
    MC3 recipe   data_cache/_mc3_features.parquet   per-surface S/R (KS=20) + margin Elo (1.5)

Both built today from the same archive by the nightly job, so the comparison is paired on
identical matches at identical prices.

HOW THE BET IS PRICED, because this is the easy thing to get wrong:
  * the EDGE is measured against `imp`, the DE-VIGGED market probability (i1/(i1+i2))
  * the PAYOUT is at `odd_a` / `odd_b`, the RAW decimal odds the book actually offered
Using the de-vigged number for both would silently hand every strategy the bookmaker's margin
and make any model look profitable -- the exact error that made the eleven duplicate rows worth
removing this morning.

Flat 1 unit, one bet per match, on whichever side the head rates above the de-vigged price by
at least the threshold. Reported by threshold, by side, by price band and by year, with BET
COUNTS alongside -- a head that returns the same ROI on ten times the volume is the better head,
and one that only profits on 40 bets out of 120,000 has found nothing usable.

READ THIS AS ARCHIVE EVIDENCE ONLY. Archive ROI has misled this project repeatedly: six
favourite cells passed a backtest and failed forward, and Tier 3's calibration looked like the
day's best finding until the live log disagreed. Treat a positive number here as a reason to
watch the forward lanes, never as a reason to bet.
"""
import gc
import os

import numpy as np
import pandas as pd

from _mc2_shrink_sweep import live_blend

MC2F = "data_cache/_mc2_features.parquet"
MC3F = "data_cache/_mc3_features.parquet"
for p in (MC2F, MC3F):
    if not os.path.exists(p):
        raise SystemExit("missing %s" % p)

COLS = ["date", "year", "a", "b", "p_elo", "pa_pt", "pb_pt", "nS_a", "nS_b",
        "imp", "won", "surf", "score", "odd_a", "odd_b"]
A = pd.read_parquet(MC2F, columns=COLS)
B = pd.read_parquet(MC3F, columns=COLS)
A["_k"] = list(zip(A["date"], A["a"], A["b"]))
B["_k"] = list(zip(B["date"], B["a"], B["b"]))
common = set(A["_k"]) & set(B["_k"])
A = A[A["_k"].isin(common)].drop_duplicates("_k").set_index("_k").sort_index()
B = B[B["_k"].isin(common)].drop_duplicates("_k").set_index("_k").sort_index()
A, B = A.align(B, join="inner", axis=0)
ok = (A["imp"].notna() & A["won"].notna() & A["odd_a"].notna() & A["odd_b"].notna()
      & A["pa_pt"].notna() & A["p_elo"].notna()
      & B["pa_pt"].notna() & B["p_elo"].notna()
      & (A["nS_a"] >= 4) & (A["nS_b"] >= 4)
      & (B["nS_a"] >= 4) & (B["nS_b"] >= 4)
      & (A["odd_a"] > 1.005) & (A["odd_b"] > 1.005)).to_numpy()
A, B = A[ok], B[ok]
print("paired, priced rows: %d  (%s .. %s)"
      % (len(A), str(A["date"].min())[:10], str(A["date"].max())[:10]))


def sets_won(s):
    if not isinstance(s, str) or not s.strip():
        return 0
    x = y = 0
    for tok in s.split():
        t = tok.split("(")[0]
        if "-" not in t:
            continue
        u, _, v = t.partition("-")
        try:
            u, v = int(u), int(v)
        except ValueError:
            continue
        if u > v:
            x += 1
        elif v > u:
            y += 1
    return max(x, y)


bo5 = np.array([sets_won(s) >= 3 for s in A["score"]])
IMP = A["imp"].to_numpy(dtype=float)
OA = A["odd_a"].to_numpy(dtype=float)
OB = A["odd_b"].to_numpy(dtype=float)
WON = A["won"].to_numpy(dtype=float).astype(bool)
YR = A["year"].to_numpy()
# American price of each side, for the band splits
am = lambda d: np.where(d >= 2, (d - 1) * 100, -100 / (d - 1))
AMA, AMB = am(OA), am(OB)
print("best-of-five rows: %d" % int(bo5.sum()))

P = {}
# live_blend scores best-of-THREE for both heads. That is fine for a PAIRED comparison -- the
# format treatment is a constant across MC2 and MC3, so it cannot favour either -- and
# best-of-five is a fraction of a percent of the archive. It does mean these are not the exact
# numbers the live heads would quote on a slam.
for tag, F in (("MC2", A), ("MC3", B)):
    P[tag], _ = live_blend(F)
    print("   scored %s" % tag)
    gc.collect()


def strategy(p, thr):
    """-> (mask of bets, pnl, took_side_a). Edge vs the DE-VIGGED price, paid at RAW odds."""
    ea = p - IMP
    eb = (1 - p) - (1 - IMP)
    side_a = ea >= eb
    edge = np.where(side_a, ea, eb)
    m = edge >= thr
    odd = np.where(side_a, OA, OB)
    hit = np.where(side_a, WON, ~WON)
    pnl = np.where(hit, odd - 1.0, -1.0)
    return m, pnl, side_a


def row(tag, m, pnl):
    n = int(m.sum())
    if not n:
        return "%-5s      --" % tag
    r = 100 * pnl[m].mean()
    se = 100 * pnl[m].std() / np.sqrt(n)
    return "%-5s n=%-6d roi %+7.2f%% +/-%4.1f" % (tag, n, r, se)


BAR = "=" * 92
print("\n" + BAR)
print("FLAT 1u ON THE HEAD'S EDGE -- by minimum edge over the de-vigged price")
print(BAR)
for thr in (0.0, 0.01, 0.02, 0.04, 0.06, 0.08, 0.10):
    print("   edge >= %.0fpt" % (100 * thr))
    for tag in ("MC2", "MC3"):
        m, pnl, _ = strategy(P[tag], thr)
        print("      " + row(tag, m, pnl))

print("\n" + BAR)
print("SPLIT BY SIDE at a 2pt edge -- every live record says the two behave differently")
print(BAR)
for thr in (0.02, 0.04):
    print("   edge >= %.0fpt" % (100 * thr))
    for tag in ("MC2", "MC3"):
        m, pnl, sa = strategy(P[tag], thr)
        took = np.where(sa, OA, OB)
        dog = took >= 2.0
        print("      %s  %s" % (tag, row("dog", m & dog, pnl).strip()))
        print("      %s  %s" % (tag, row("fav", m & ~dog, pnl).strip()))

print("\n" + BAR)
print("THE BANDS ACTUALLY PLAYED -- dogs +100..+250, favourites -100..-250")
print(BAR)
for thr in (0.02, 0.04):
    print("   edge >= %.0fpt" % (100 * thr))
    for tag in ("MC2", "MC3"):
        m, pnl, sa = strategy(P[tag], thr)
        tam = np.where(sa, AMA, AMB)
        db = (tam >= 100) & (tam <= 250)
        fb = (tam <= -100) & (tam >= -250)
        print("      %s  %s" % (tag, row("dog band", m & db, pnl).strip()))
        print("      %s  %s" % (tag, row("fav band", m & fb, pnl).strip()))

print("\n" + BAR)
print("BY YEAR at a 2pt edge -- a strategy that only works in one year has not worked")
print(BAR)
for y in (2024, 2025, 2026):
    print("   %d" % y)
    for tag in ("MC2", "MC3"):
        m, pnl, _ = strategy(P[tag], 0.02)
        print("      " + row(tag, m & (YR == y), pnl))

print("\n" + BAR)
print("HEAD TO HEAD -- rows where they pick DIFFERENT sides at a 2pt edge")
print(BAR)
m2, pnl2, sa2 = strategy(P["MC2"], 0.02)
m3, pnl3, sa3 = strategy(P["MC3"], 0.02)
dis = m2 & m3 & (sa2 != sa3)
print("   both bet, opposite sides: n=%d" % int(dis.sum()))
if dis.sum():
    print("      " + row("MC2", dis, pnl2))
    print("      " + row("MC3", dis, pnl3))
print("\n   baselines on all paired rows:")
print("      back every favourite  roi %+7.2f%%"
      % (100 * np.where(np.where(IMP >= 0.5, WON, ~WON),
                        np.where(IMP >= 0.5, OA, OB) - 1, -1.0).mean()))
print("      back every underdog   roi %+7.2f%%"
      % (100 * np.where(np.where(IMP >= 0.5, ~WON, WON),
                        np.where(IMP >= 0.5, OB, OA) - 1, -1.0).mean()))
