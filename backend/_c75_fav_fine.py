"""C75 OVER THE MARKET ON THE FAVOURITE -> BACK THE FAVOURITE, cut finely (2026-10-13).

The user's read: if c75 is over the market on the favourite, the bet is the FAVOURITE. So this
drops the fade framing entirely and scores only that bet, sliced every way that could hide a
usable cell inside a ladder that is negative overall:

  * fine exclusive bands from 0pt up, 1 point at a time, so a small-margin cell is not buried
    under the deep margins that dominate the nested ladder
  * against chalk on the same rows, which is the only honest bar (every favourite is -7.0%)
  * price band, gender, and level
  * the one cross-check that matters: is the FAVOURITE itself short or long at each margin? A
    big claimed edge on a short price is a different animal from one on a near-coin-flip.

MC2's favourite side turned out to be an inverted U -- best at 3-4pt, negative past 10pt -- so
the hypothesis here is that c75 has the same shape and the nested ladder was averaging a decent
small-margin cell together with a catastrophic deep one.
"""
import numpy as np
import pandas as pd

import tennis_log

COL, RECON = "mc_c75_p1", "mc_c_recon"
L = pd.read_parquet(tennis_log.LOG_PATH)
d = L[L[COL].notna() & L["p1_odds"].notna() & L["p2_odds"].notna()
      & L["p1_won"].notna() & (L["settled"] == True)].copy()      # noqa: E712
for c in ("surface_bad", "inplay_suspect"):
    if c in d.columns:
        d = d[~d[c].fillna(False).astype(bool)]
rc = (d[RECON].fillna(False).astype(bool).to_numpy()
      if RECON in d.columns else np.zeros(len(d), bool))
FWD = ~rc


def dec(a):
    a = float(a)
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


d1, d2 = d["p1_odds"].map(dec).to_numpy(), d["p2_odds"].map(dec).to_numpy()
mk1 = (1 / d1) / ((1 / d1) + (1 / d2))
pv = d[COL].astype(float).to_numpy()
won1 = d["p1_won"].astype(bool).to_numpy()
gend = np.where(d["league"].astype(str).isin(["wta", "itf_women"]), "W", "M")
lvl = np.where(d["league"].astype(str).str.startswith("itf"), "itf",
               np.where(d["league"].astype(str).str.contains("challenger"), "chall", "tour"))
fav1 = mk1 >= 0.5
mkfav = np.where(fav1, mk1, 1 - mk1)
cfav = np.where(fav1, pv, 1 - pv)
over = cfav - mkfav
favodd = np.where(fav1, d1, d2)
favwon = np.where(fav1, won1, ~won1)
favpnl = np.where(favwon, favodd - 1, -1.0)
favam = -100.0 / (favodd - 1)

CHALK_A = 100 * favpnl.mean()
CHALK_F = 100 * favpnl[FWD].mean()


def cl(m):
    n = int(m.sum())
    if not n:
        return None
    p = favpnl[m]
    return {"n": n, "w": int(favwon[m].sum()), "roi": 100 * p.mean(),
            "se": 100 * p.std() / np.sqrt(n) if n > 1 else float("nan"),
            "am": favam[m].mean()}


def f(c, chalk):
    if not c:
        return "%-40s" % "        --"
    return ("n=%-4d %+7.2f%% +/-%4.1f %3.0f%%hit  vs chalk %+6.1fpt  avg%+5.0f"
            % (c["n"], c["roi"], c["se"], 100 * c["w"] / c["n"], c["roi"] - chalk, c["am"]))


def two(lab, m):
    print("   %-24s %-52s %s" % (lab, f(cl(m), CHALK_A), f(cl(m & FWD), CHALK_F)))


BAR = "=" * 118
print("rows %d (forward %d).  CHALK: back every favourite = %+.2f%% all / %+.2f%% forward"
      % (len(d), int(FWD.sum()), CHALK_A, CHALK_F))
print("\n" + BAR)
print("BACK THE FAVOURITE when c75 is over the market -- FINE EXCLUSIVE BANDS (1pt wide)")
print(BAR)
print("   %-24s %-52s %s" % ("band", "ALL rows", "FORWARD only"))
edges = [0, 1, 2, 3, 4, 5, 6, 8, 10, 15, 100]
for lo, hi in zip(edges[:-1], edges[1:]):
    two("%d-%dpt over" % (lo, hi), (over >= lo / 100.0) & (over < hi / 100.0))

print("\n" + BAR)
print("THE SMALL-MARGIN CELL -- cumulative from 0, capped, to find where it turns")
print(BAR)
for hi in (2, 3, 4, 5, 6, 8):
    two("0 to %dpt over" % hi, (over >= 0.0) & (over < hi / 100.0))

print("\n   the best-looking cap, broken out:")
BEST = (over >= 0.0) & (over < 0.04)
two("0-4pt over, all", BEST)
for g in ("M", "W"):
    two("  %s" % g, BEST & (gend == g))
for lv in ("tour", "chall", "itf"):
    two("  %s" % lv, BEST & (lvl == lv))
print("   by the favourite's own price:")
for lo, hi in ((-150, 0), (-250, -150), (-400, -250), (-100000, -400)):
    two("  fav %d..%d" % (lo, hi), BEST & (favam > lo) & (favam <= hi))
print("   inside the -100..-250 mark band:")
band = (favam <= -100) & (favam >= -250)
two("  0-4pt over, in band", BEST & band)
two("  -- every band fav --", band)

print("\n" + BAR)
print("WHY THE DEEP END COLLAPSES -- what the favourite's price looks like at each margin")
print(BAR)
for lo, hi in zip(edges[:-1], edges[1:]):
    m = (over >= lo / 100.0) & (over < hi / 100.0)
    if not m.sum():
        continue
    print("   %-14s n=%-4d avg fav price %+6.0f   market gives it %4.1f%%   c75 says %4.1f%%"
          % ("%d-%dpt" % (lo, hi), int(m.sum()), favam[m].mean(),
             100 * mkfav[m].mean(), 100 * cfav[m].mean()))

print("\n" + BAR)
print("FOR COMPARISON -- the same fine bands on the DOG side of those matches")
print(BAR)
dogodd = np.where(fav1, d2, d1)
dogpnl = np.where(~favwon, dogodd - 1, -1.0)
CH_D = 100 * dogpnl.mean()
for lo, hi in zip(edges[:-1], edges[1:]):
    m = (over >= lo / 100.0) & (over < hi / 100.0)
    n = int(m.sum())
    if not n:
        continue
    nf = int((m & FWD).sum())
    print("   %-14s dog: all %+7.2f%%/%-4d   forward %s"
          % ("%d-%dpt" % (lo, hi), 100 * dogpnl[m].mean(), n,
             ("%+7.2f%%/%d" % (100 * dogpnl[m & FWD].mean(), nf)) if nf else "--"))
print("   (every dog on these rows: %+.2f%%)" % CH_D)
