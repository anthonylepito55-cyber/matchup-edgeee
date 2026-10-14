"""IS THE BROWN MC2 FAV BAND MARKING SUB-VIG EDGES? (2026-10-13)

The Duckworth card (Draxl vs Duckworth, Jinan Challenger) had MC2 3.3pt over the de-vigged market
ON A FAVOURITE at -154 -- inside the brown 2-8pt favourite band. But break-even at -154 is 60.6%
and MC2 said 60.0%, so the mark pointed at a -1.0% EV bet. He lost in straight sets.

The question is whether that is a one-off or whether the band systematically marks favourites
whose edge is smaller than the price demands. The band is defined against the DE-VIGGED market,
and challenger vig runs 7.0pt median, so a 2-3pt de-vigged edge there is routinely sub-vig.

Measured on the frozen live log: of the favourites the 2-8pt band marks, what share actually
clear break-even at the price offered, and what did each half return?
"""
import numpy as np
import pandas as pd

import tennis_log

log = pd.read_parquet(tennis_log.LOG_PATH)
log = log[log["p1_won"].notna()].copy()
for c in ("resolve_bad", "surface_bad", "inplay_suspect"):
    if c in log.columns:
        log = log[~log[c].fillna(False).astype(bool).to_numpy()]
log["_o1"] = pd.to_numeric(log["p1_odds"], errors="coerce")
log["_o2"] = pd.to_numeric(log["p2_odds"], errors="coerce")
log = log[log["_o1"].notna() & log["_o2"].notna()].reset_index(drop=True)

dc = lambda o: np.where(o > 0, 1 + o / 100.0, 1 + 100.0 / np.abs(o))
D1, D2 = dc(log["_o1"].to_numpy(float)), dc(log["_o2"].to_numpy(float))
I1, I2 = 1 / D1, 1 / D2
MKD1 = I1 / (I1 + I2)
VIG = (I1 + I2 - 1) * 100
W1 = log["p1_won"].astype(bool).to_numpy()
MEN = ~log["league"].astype(str).str.contains("wta|itf_women", case=False, na=False).to_numpy()

BAR = "=" * 96
for nm, col in (("MC2", "mc2_p1"), ("MC3", "mc3_p1"), ("MC5", "mc5_p1")):
    if col not in log.columns:
        continue
    p1 = pd.to_numeric(log[col], errors="coerce").to_numpy(float)
    ok = ~np.isnan(p1)
    fav1 = MKD1 >= 0.5
    # the head's probability ON THE MARKET FAVOURITE, and the favourite's own price
    pfav = np.where(fav1, p1, 1 - p1)
    mfav = np.where(fav1, MKD1, 1 - MKD1)
    dfav = np.where(fav1, D1, D2)
    wfav = np.where(fav1, W1, ~W1)
    be = 1 / dfav                                   # break-even at the real price
    marg = (pfav - mfav) * 100                      # what the board shows
    clears = (pfav - be) * 100                      # what actually matters
    pnl = np.where(wfav, dfav - 1, -1.0)

    band = ok & (marg >= 2.0) & (marg < 8.0)        # the brown 2-8pt favourite band
    print("\n" + BAR)
    print("%s -- the brown 2-8pt FAVOURITE band on the frozen log" % nm)
    print(BAR)
    n = int(band.sum())
    if n < 10:
        print("   n=%d, too few to read" % n)
        continue
    sub = band & (clears < 0)
    cle = band & (clears >= 0)
    print("   band total            n=%-5d ROI %+7.2f%%  hit %5.1f%%  median vig %4.1fpt"
          % (n, 100 * pnl[band].mean(), 100 * wfav[band].mean(), np.median(VIG[band])))
    print("   of those, SUB-VIG     n=%-5d ROI %+7.2f%%  hit %5.1f%%   (%.0f%% of the band)"
          % (int(sub.sum()), 100 * pnl[sub].mean() if sub.sum() else float("nan"),
             100 * wfav[sub].mean() if sub.sum() else float("nan"), 100 * sub.sum() / n))
    print("   of those, CLEARS B/E  n=%-5d ROI %+7.2f%%  hit %5.1f%%"
          % (int(cle.sum()), 100 * pnl[cle].mean() if cle.sum() else float("nan"),
             100 * wfav[cle].mean() if cle.sum() else float("nan")))
    for glab, gq in (("men", MEN), ("women", ~MEN)):
        for slab, sq in (("sub-vig", sub), ("clears", cle)):
            q = gq & sq
            if q.sum() >= 8:
                print("      %-6s %-8s n=%-4d ROI %+7.2f%%"
                      % (glab, slab, int(q.sum()), 100 * pnl[q].mean()))

print("\n" + BAR)
print("THE SAME CUT ACROSS EVERY FAVOURITE MARK, not just the 2-8pt band")
print(BAR)
p1 = pd.to_numeric(log["mc2_p1"], errors="coerce").to_numpy(float)
ok = ~np.isnan(p1)
fav1 = MKD1 >= 0.5
pfav = np.where(fav1, p1, 1 - p1)
mfav = np.where(fav1, MKD1, 1 - MKD1)
dfav = np.where(fav1, D1, D2)
wfav = np.where(fav1, W1, ~W1)
clears = (pfav - 1 / dfav) * 100
pnl = np.where(wfav, dfav - 1, -1.0)
print("   %-22s %7s %10s %8s" % ("MC2 vs BREAK-EVEN", "n", "ROI", "hit"))
for lo, hi, lab in ((-100, -2, "more than 2pt short"), (-2, 0, "0-2pt short"),
                    (0, 2, "clears by 0-2pt"), (2, 100, "clears by 2pt+")):
    q = ok & (clears >= lo) & (clears < hi)
    if q.sum() < 10:
        continue
    print("   %-22s %7d %+9.2f%% %7.1f%%" % (lab, int(q.sum()), 100 * pnl[q].mean(),
                                             100 * wfav[q].mean()))
print("\n   READ: if the 'clears' halves are the only positive ones, the band should be defined")
print("   against the PRICE rather than the de-vigged market.")
