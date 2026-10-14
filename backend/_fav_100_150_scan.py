"""ARE ANY CELLS POSITIVE ON FAVOURITES AT -100..-150? (2026-10-14)

User: "for favorites are any cells positive for -100 to 150 maybe mc2 4 pts above market or
something?"

THE PRIOR, stated first so the result is read against it. Every favourite cell in this project
has failed forward: 604 live favourite settles at -9.7% against 377 dog settles at +16.1%, all 13
heads negative on favourites (-5.0% to -9.1%), and six archive favourite cells have died forward
in a row. Today's brown favourite band was also found to be marking negative-EV bets.

WHY THIS BAND IS THE RIGHT ONE TO ASK ABOUT ANYWAY. -100..-150 is where a favourite needs only
50% to 60% to break even, so a head that is genuinely a couple of points better than the price has
the least to overcome. It is also the band the Ⓟ CLOSE cell already lives in.

THE MEASUREMENT. Every head, favourites priced -100..-150, laddered by how far the head sits
ABOVE the de-vigged market on the favourite. Two things are reported for each rung:
  * ROI at the REAL price, which is the only number that decides anything
  * whether the head's own probability clears BREAK-EVEN at that price -- the Bouzkova lesson:
    "+2.1pt over the de-vigged market" was still a -1.0% bet, because de-vigging splits the
    book's margin across both sides. A rung can be "over the market" and under the price.

Forward only (recon excluded), $25 flat, and the blind baseline for the same rows is printed so a
cell that merely matches chalk is not mistaken for an edge.
"""
import math

import numpy as np
import pandas as pd

import tennis_log

HEADS = [("MC2", "mc2_p1", "mc2_recon"), ("MC3", "mc3_p1", "mc3_recon"),
         ("MC5", "mc5_p1", "mc5_recon"), ("Model C", "model_c_p1", None),
         ("c75", "mc_c75_p1", None), ("Model D", "model_d_p1", None),
         ("D-MA", "model_dma_p1", None), ("Model G", "model_g_p1", "model_g_recon"),
         ("Model G2", "model_g2_p1", "model_g2_recon"), ("Model X", "model_x_p1", "model_x_recon"),
         ("gray (C-MA)", "model_cma_p1", None), ("Model A", "model_a_p1", None),
         ("Model B", "model_b_p1", None)]

log = pd.read_parquet(tennis_log.LOG_PATH)
log = log[log["p1_won"].notna()].copy()
for c in ("resolve_bad", "surface_bad", "inplay_suspect"):
    if c in log.columns:
        log = log[~log[c].fillna(False).astype(bool).to_numpy()]
log["_o1"] = pd.to_numeric(log["p1_odds"], errors="coerce")
log["_o2"] = pd.to_numeric(log["p2_odds"], errors="coerce")
log = log[log._o1.notna() & log._o2.notna()].reset_index(drop=True)

dc = lambda o: np.where(o > 0, 1 + o / 100.0, 1 + 100.0 / np.abs(o))
D1, D2 = dc(log._o1.to_numpy(float)), dc(log._o2.to_numpy(float))
I1, I2 = 1 / D1, 1 / D2
MK1 = I1 / (I1 + I2)
W1 = log.p1_won.astype(bool).to_numpy()
fav1 = MK1 >= 0.5
WOM = log.league.astype(str).str.contains("wta|itf_women", case=False, na=False).to_numpy()

fav_od = np.where(fav1, D1, D2)                    # the favourite's decimal
fav_am = np.where(fav_od >= 2, (fav_od - 1) * 100, -100.0 / np.maximum(fav_od - 1, 1e-9))
won_fav = np.where(fav1, W1, ~W1)
pnl_fav = np.where(won_fav, fav_od - 1, -1.0)
mkfav = np.where(fav1, MK1, 1 - MK1)
be_fav = 1.0 / fav_od                              # break-even at the real price
BAND = (fav_am <= -100) & (fav_am >= -150)

print("forward settled rows with a price: %d   favourites in -100..-150: %d"
      % (len(log), int(BAND.sum())))


def rep(mask, lab, indent="   "):
    n = int(mask.sum())
    if n == 0:
        return "%s%-30s n=0" % (indent, lab)
    w = int(won_fav[mask].sum())
    roi = 100 * pnl_fav[mask].mean()
    prof = 25 * pnl_fav[mask].sum()
    r = roi / 100
    t = None
    if w:
        g = (r * n + (n - w)) / w
        v = (w * g * g + (n - w)) / n - r * r
        if v > 0:
            t = r / (math.sqrt(v) / math.sqrt(n))
    return ("%s%-30s n=%-4d %7s  hit %5.1f%%  needs %5.1f%%  ROI %+7.2f%%  $%+8.2f%s"
            % (indent, lab, n, "%d-%d" % (w, n - w), 100 * w / n,
               100 * be_fav[mask].mean(), roi, prof,
               "  t %5.2f" % t if t is not None else ""))


BAR = "=" * 116
print("\n" + BAR)
print("BASELINE -- backing EVERY favourite at -100..-150, no model involved")
print(BAR)
print(rep(BAND, "every fav -100..-150"))
print(rep(BAND & ~WOM, "   men"))
print(rep(BAND & WOM, "   women"))

print("\n" + BAR)
print("EACH HEAD, laddered by points ABOVE the de-vigged market on the favourite")
print("   'needs' is the break-even at the real price -- a rung over the market can still be")
print("   under the price, which is the whole Bouzkova lesson.")
print(BAR)
RUNGS = [(0.0, 0.02, "0-2pt over"), (0.02, 0.04, "2-4pt"), (0.04, 0.06, "4-6pt"),
         (0.06, 0.08, "6-8pt"), (0.08, 1.0, "8pt+ over")]
summary = []
for lab, col, rc in HEADS:
    if col not in log.columns:
        continue
    p = pd.to_numeric(log[col], errors="coerce").to_numpy(float)
    ok = ~np.isnan(p)
    if rc and rc in log.columns:
        ok &= ~log[rc].fillna(False).astype(bool).to_numpy()
    pf = np.where(fav1, p, 1 - p)                  # head's prob ON THE FAVOURITE
    over = pf - mkfav
    base = BAND & ok
    if base.sum() < 20:
        continue
    print("   %s   (%d rows in band)" % (lab, int(base.sum())))
    print(rep(base & (over >= 0), "any margin over market", "      "))
    for lo, hi, rl in RUNGS:
        m = base & (over >= lo) & (over < hi)
        if m.sum() >= 8:
            print(rep(m, rl, "      "))
    # the version that must clear the actual price
    m4 = base & (over >= 0.04)
    mev = base & (pf >= be_fav)
    print(rep(m4, "4pt+ over market", "      "))
    print(rep(mev, "clears BREAK-EVEN (EV>=0)", "      "))
    m4ev = base & (over >= 0.04) & (pf >= be_fav)
    print(rep(m4ev, "4pt+ over AND clears price", "      "))
    for nm, mm in (("4pt+ over", m4), ("4pt+ & clears price", m4ev), ("clears price", mev)):
        n = int(mm.sum())
        if n >= 15:
            summary.append((100 * pnl_fav[mm].mean(), lab, nm, n))
    print()

print(BAR)
print("EVERY CELL x RULE WITH n>=15, RANKED -- is anything positive here at all?")
print(BAR)
for roi, lab, nm, n in sorted(summary, reverse=True):
    print("   %-14s %-22s n=%-4d ROI %+7.2f%%" % (lab, nm, n, roi))
pos = [x for x in summary if x[0] > 0]
print()
print("   positive cells at n>=15: %d of %d" % (len(pos), len(summary)))
print("\n" + BAR)
