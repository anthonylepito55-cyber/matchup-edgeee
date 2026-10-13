"""IS THE HEADS' DISAGREEMENT WITH THE PRICE WORTH FADING? (2026-10-13).

The ROI measurement found a monotone ANTI-signal over 120,877 rows: backing a head's own edge
returns -8.78% at any margin and -9.66% at 10pt+, so the further a head sits from the price the
worse it does. That is the same shape as the c75 favourite fade found this morning at 108 rows.
This asks the obvious next question at full scale: does taking the OTHER side pay?

THE TRAP THIS SCRIPT IS BUILT AROUND. At a wide threshold a head's edge is nearly always on the
DOG -- it took 82,440 dog bets against 23,058 favourite bets at 2pt -- so fading it mostly means
backing FAVOURITES, and backing every favourite blindly already returns -5.59%. A naive fade
number would therefore just rediscover "favourites lose less than dogs" and look like a finding.

So every fade cell is reported against TWO controls on the same side:
  complement  the same side backed on rows BELOW the threshold (within-sample, same universe)
  all rows    the same side backed everywhere
The fade is only interesting if it beats BOTH. If it matches them, the model contributed nothing
and the number is a price-band artefact.

Edge vs the de-vigged market, payout at the raw decimal odds, flat 1u, one bet per match --
same pricing as _mc2_vs_mc3_roi.py.

ARCHIVE EVIDENCE. Treat anything positive as a candidate for a forward lane, never as a bet.
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
        "imp", "won", "odd_a", "odd_b"]
A = pd.read_parquet(MC2F, columns=COLS)
B = pd.read_parquet(MC3F, columns=COLS)
for F in (A, B):
    F["_k"] = list(zip(F["date"], F["a"], F["b"]))
common = set(A["_k"]) & set(B["_k"])
A = A[A["_k"].isin(common)].drop_duplicates("_k").set_index("_k").sort_index()
B = B[B["_k"].isin(common)].drop_duplicates("_k").set_index("_k").sort_index()
A, B = A.align(B, join="inner", axis=0)
ok = (A["imp"].notna() & A["won"].notna() & A["odd_a"].notna() & A["odd_b"].notna()
      & A["pa_pt"].notna() & A["p_elo"].notna() & B["pa_pt"].notna() & B["p_elo"].notna()
      & (A["nS_a"] >= 4) & (A["nS_b"] >= 4) & (B["nS_a"] >= 4) & (B["nS_b"] >= 4)
      & (A["odd_a"] > 1.005) & (A["odd_b"] > 1.005)).to_numpy()
A, B = A[ok], B[ok]
IMP = A["imp"].to_numpy(dtype=float)
OA = A["odd_a"].to_numpy(dtype=float)
OB = A["odd_b"].to_numpy(dtype=float)
WON = A["won"].to_numpy(dtype=float).astype(bool)
YR = A["year"].to_numpy()
print("paired, priced rows: %d" % len(A))

P = {}
for tag, F in (("MC2", A), ("MC3", B)):
    P[tag], _ = live_blend(F)
    print("   scored %s" % tag)
    gc.collect()


def pnl_for(side_a):
    odd = np.where(side_a, OA, OB)
    hit = np.where(side_a, WON, ~WON)
    return np.where(hit, odd - 1.0, -1.0)


def edges(p):
    ea = p - IMP
    eb = (1 - p) - (1 - IMP)
    like_a = ea >= eb
    return like_a, np.where(like_a, ea, eb)


def fmt(lab, m, pnl):
    n = int(m.sum())
    if n < 50:
        return "   %-26s n=%-6d (too few)" % (lab, n)
    r = 100 * pnl[m].mean()
    se = 100 * pnl[m].std() / np.sqrt(n)
    return "   %-26s n=%-6d roi %+7.2f%% +/-%4.1f" % (lab, n, r, se)


BAR = "=" * 94
for tag in ("MC2", "MC3"):
    like_a, edge = edges(P[tag])
    fade_side = ~like_a                      # the side the head DISLIKES
    fpnl = pnl_for(fade_side)
    took_dec = np.where(fade_side, OA, OB)
    is_dog = took_dec >= 2.0
    print("\n" + BAR)
    print("%s -- FADE: back the side the head rates BELOW the de-vigged price" % tag)
    print(BAR)
    for thr in (0.0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20):
        m = edge >= thr
        comp = ~m                            # same side, below the threshold
        print(fmt("fade, edge >= %.0fpt" % (100 * thr), m, fpnl))
        print(fmt("  control: same side <thr", comp, fpnl))
        print("   %-26s %s"
              % ("  share of fades on a dog",
                 ("%.0f%%" % (100 * is_dog[m].mean())) if m.sum() else "--"))
    print("   %-26s %s" % ("all rows, same-side bet", ""))
    print(fmt("  fade side everywhere", np.ones(len(A), bool), fpnl))

print("\n" + BAR)
print("THE FADE SPLIT BY WHAT IT ENDS UP BACKING, at 8pt -- the price-band control")
print(BAR)
for tag in ("MC2", "MC3"):
    like_a, edge = edges(P[tag])
    fade_side = ~like_a
    fpnl = pnl_for(fade_side)
    took_dec = np.where(fade_side, OA, OB)
    is_dog = took_dec >= 2.0
    m = edge >= 0.08
    print("  %s" % tag)
    for lab, q in (("fade -> favourite", m & ~is_dog), ("fade -> dog", m & is_dog)):
        print(fmt("    " + lab, q, fpnl))
        print(fmt("    control <thr, same", (~m) & (~is_dog if "favourite" in lab else is_dog),
                  fpnl))

print("\n" + BAR)
print("BY YEAR at 8pt -- and the unconditional baselines for reference")
print(BAR)
for tag in ("MC2", "MC3"):
    like_a, edge = edges(P[tag])
    fpnl = pnl_for(~like_a)
    m = edge >= 0.08
    print("  %s" % tag)
    for y in (2024, 2025, 2026):
        print(fmt("    %d" % y, m & (YR == y), fpnl))

fav_a = IMP >= 0.5
print("\n  unconditional, all %d rows:" % len(A))
print(fmt("    back every favourite", np.ones(len(A), bool), pnl_for(fav_a)))
print(fmt("    back every underdog", np.ones(len(A), bool), pnl_for(~fav_a)))
