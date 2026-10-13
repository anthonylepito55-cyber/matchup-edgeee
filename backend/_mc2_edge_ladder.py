"""MC2 "any points over the market" -- the full edge ladder, live (2026-10-13).

The previous answer split MC2 into two cells (over the market on the FAVOURITE, or flipping the
DOG). This drops that distinction: back whichever side MC2 rates above the market's own implied
probability, by any margin, and then tighten the margin step by step. Split dog/favourite and
by gender, because every live record in this project says the two sides behave differently.

Frozen log, forward picks only: mc2_recon backfills dropped, surface_bad and inplay_suspect
dropped, one bet per match at the frozen closing price, flat 1u.

Baselines on the same rows are printed, since "back the side with an edge" has to beat "back a
side at random" before the edge means anything.
"""
import numpy as np
import pandas as pd

import tennis_log

L = pd.read_parquet(tennis_log.LOG_PATH)
d = L[(L["settled"] == True) & L["p1_won"].notna() & L["mc2_p1"].notna()   # noqa: E712
      & L["p1_odds"].notna() & L["p2_odds"].notna()].copy()
for c in ("mc2_recon", "surface_bad", "inplay_suspect"):
    if c in d.columns:
        d = d[~d[c].fillna(False).astype(bool)]
print("forward settled rows with a frozen mc2: %d  (%s .. %s)"
      % (len(d), str(d["date"].min())[:10], str(d["date"].max())[:10]))


def dec(a):
    a = float(a)
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


d1, d2 = d["p1_odds"].map(dec).to_numpy(), d["p2_odds"].map(dec).to_numpy()
mk1 = (1 / d1) / ((1 / d1) + (1 / d2))
p1 = d["mc2_p1"].astype(float).to_numpy()
won1 = d["p1_won"].astype(bool).to_numpy()
gend = np.where(d["league"].astype(str).isin(["wta", "itf_women"]), "W", "M")

# the side MC2 is over the market on, and by how much. Only one side can be over, since both
# probabilities and both implieds sum to 1 after de-vig.
edge1, edge2 = p1 - mk1, (1 - p1) - (1 - mk1)
take1 = edge1 > 0
edge = np.where(take1, edge1, edge2)
odd = np.where(take1, d1, d2)
hit = np.where(take1, won1, ~won1)
pnl = np.where(hit, odd - 1, -1.0)
isdog = odd >= 2.0


def row(lab, m):
    n = int(m.sum())
    if not n:
        return "   %-28s (none)" % lab
    p, w = pnl[m], int(hit[m].sum())
    se = 100 * p.std() / np.sqrt(n) if n > 1 else float("nan")
    dc = float(odd[m].mean())
    am = (dc - 1) * 100 if dc >= 2 else -100 / (dc - 1)
    return ("   %-28s n=%-4d %4d-%-4d roi %+7.2f%% +/-%4.1f  avg %+5.0f  %3.0f%% dogs"
            % (lab, n, w, n - w, 100 * p.mean(), se, am, 100 * isdog[m].mean()))


print("\n" + "=" * 90)
print("MC2 EDGE LADDER -- back whichever side MC2 is over the market on")
print("=" * 90)
for t in (0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.08, 0.10, 0.15):
    print(row("%.0fpt+ over" % (100 * t), edge > t))

print("\nsplit by the side taken, at a few thresholds:")
for t in (0.0, 0.04, 0.08):
    print("  %.0fpt+ over" % (100 * t))
    print(row("  on a DOG", (edge > t) & isdog))
    print(row("  on a FAVOURITE", (edge > t) & ~isdog))

print("\nby gender, any margin:")
for g in ("M", "W"):
    print(row("  %s" % g, (edge > 0) & (gend == g)))
    print(row("    %s dog" % g, (edge > 0) & (gend == g) & isdog))
    print(row("    %s fav" % g, (edge > 0) & (gend == g) & ~isdog))

print("\n" + "=" * 90)
print("BASELINES on the same %d rows" % len(d))
print("=" * 90)
dogpnl = np.where(~won1 if True else won1, 0, 0)  # placeholder, replaced below
favo = np.where(mk1 >= 0.5, d1, d2)
dogo = np.where(mk1 >= 0.5, d2, d1)
favw = np.where(mk1 >= 0.5, won1, ~won1)
fp = np.where(favw, favo - 1, -1.0)
dp = np.where(~favw, dogo - 1, -1.0)
print("   %-28s n=%-4d %4d-%-4d roi %+7.2f%%"
      % ("every favourite", len(d), int(favw.sum()), len(d) - int(favw.sum()), 100 * fp.mean()))
print("   %-28s n=%-4d %4d-%-4d roi %+7.2f%%"
      % ("every dog", len(d), len(d) - int(favw.sum()), int(favw.sum()), 100 * dp.mean()))

print("\nwhere MC2's edge actually lands (distribution of the margin it claims):")
q = pd.Series(100 * edge)
print("   median %.1fpt | p75 %.1f | p90 %.1f | max %.1f | share on a dog %.0f%%"
      % (q.median(), q.quantile(.75), q.quantile(.9), q.max(), 100 * isdog.mean()))
