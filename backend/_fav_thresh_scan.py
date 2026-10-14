"""FAVOURITES -100..-150: DOES ANY CELL HOLD ACROSS ALL OUR DAYS? (2026-10-14)

User: "what about -100 to 150" / "no im talking about favorites".

The earlier scan of this band was forward-weighted, and the MC2 rule that looked best there
(+40.52% on 18 over 6 days) collapsed to -21.80% on 32 over the 14 earlier days. So the question
worth asking now is not "which cell looks best" but "which cell, if any, is positive in BOTH
windows" -- a cell that only works in the recent week is a cell that found a good week.

Every head, favourites priced -100..-150, at the 4pt+ over-market threshold and at "clears the
real price", split FORWARD vs RECON. Recon is a walk-forward replay rather than a frozen pick, and
for MC2 the two are known to diverge because the live rating state went unrebuilt for days -- so
they are never pooled without the split being shown first.

A cell is only interesting if it is positive in both columns AND beats the band baseline in both.
The baseline is printed first because the band is structurally negative: every favourite at
-100..-150 is -9.69% over 261 bets and 31 days, needing 56.7% and hitting 51.0%.
"""
import math

import numpy as np
import pandas as pd

import tennis_log

HEADS = [("MC2", "mc2_p1", "mc2_recon"), ("MC3", "mc3_p1", "mc3_recon"),
         ("MC5", "mc5_p1", "mc5_recon"), ("Model C", "model_c_p1", None),
         ("c75", "mc_c75_p1", None), ("gray (C-MA)", "model_cma_p1", None),
         ("Model D", "model_d_p1", None), ("D-MA", "model_dma_p1", None),
         ("Model G", "model_g_p1", "model_g_recon"),
         ("Model G2", "model_g2_p1", "model_g2_recon"),
         ("Model X", "model_x_p1", "model_x_recon"),
         ("Model A", "model_a_p1", None), ("Model B", "model_b_p1", None)]

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
dts = log["date"].astype(str).str[:10].to_numpy()

fod = np.where(fav1, D1, D2)
fam = np.where(fod >= 2, (fod - 1) * 100, -100.0 / np.maximum(fod - 1, 1e-9))
wonf = np.where(fav1, W1, ~W1)
pnl = np.where(wonf, fod - 1, -1.0)
mkf = np.where(fav1, MK1, 1 - MK1)
be = 1.0 / fod
BAND = (fam <= -100) & (fam >= -150)
import sys
THRESH = float(sys.argv[1]) if len(sys.argv) > 1 else 0.04


def rep(m, lab, ind="      "):
    n = int(m.sum())
    if n == 0:
        return "%s%-26s n=0" % (ind, lab)
    w = int(wonf[m].sum())
    roi = 100 * pnl[m].mean()
    prof = 25 * pnl[m].sum()
    r = roi / 100
    t = None
    if w:
        g = (r * n + (n - w)) / w
        v = (w * g * g + (n - w)) / n - r * r
        if v > 0:
            t = r / (math.sqrt(v) / math.sqrt(n))
    nd = len(set(dts[m]))
    return ("%s%-26s n=%-4d %7s  hit %5.1f%%  ROI %+7.2f%%  $%+8.2f%s %2dd"
            % (ind, lab, n, "%d-%d" % (w, n - w), 100 * w / n, roi, prof,
               "  t %5.2f" % t if t is not None else "        ", nd))


BAR = "=" * 118
print(BAR)
print("THE BAND ITSELF -- favourites priced -100..-150, no model")
print(BAR)
print(rep(BAND, "every fav -100..-150", "   "))
print(rep(BAND & ~WOM, "   men", "   "))
print(rep(BAND & WOM, "   women", "   "))

print("\n" + BAR)
print("EVERY HEAD, %dpt+ OVER THE MARKET ON THE FAVOURITE" % round(THRESH*100) + " -- forward vs the earlier days")
print(BAR)
both_pos = []
for lab, col, rc in HEADS:
    if col not in log.columns:
        continue
    p = pd.to_numeric(log[col], errors="coerce").to_numpy(float)
    have = ~np.isnan(p)
    RC = (log[rc].fillna(False).astype(bool).to_numpy()
          if (rc and rc in log.columns) else np.zeros(len(log), bool))
    pf = np.where(fav1, p, 1 - p)
    over = pf - mkf
    base = BAND & have
    if base.sum() < 25:
        continue
    m4 = base & (over >= THRESH)
    f, r = m4 & ~RC, m4 & RC
    if int(f.sum()) < 5 and int(r.sum()) < 5:
        continue
    print("   %s" % lab)
    print(rep(f, "%dpt+ forward" % round(THRESH*100)))
    print(rep(r, "%dpt+ recon" % round(THRESH*100)))
    print(rep(m4, "%dpt+ pooled (flagged)" % round(THRESH*100)))
    fr = 100 * pnl[f].mean() if f.sum() else None
    rr = 100 * pnl[r].mean() if r.sum() else None
    if fr is not None and rr is not None and fr > 0 and rr > 0:
        both_pos.append((lab, "%dpt+" % round(THRESH*100), int(f.sum()), fr, int(r.sum()), rr,
                         100 * pnl[m4].mean(), int(m4.sum())))
    mev = base & (pf >= be)
    fe, re_ = mev & ~RC, mev & RC
    print(rep(fe, "clears price, forward"))
    print(rep(re_, "clears price, recon"))
    fe2 = 100 * pnl[fe].mean() if fe.sum() else None
    re2 = 100 * pnl[re_].mean() if re_.sum() else None
    if fe2 is not None and re2 is not None and fe2 > 0 and re2 > 0:
        both_pos.append((lab, "clears price", int(fe.sum()), fe2, int(re_.sum()), re2,
                         100 * pnl[mev].mean(), int(mev.sum())))
    print()

print(BAR)
print("POSITIVE IN BOTH WINDOWS -- the only thing that would justify a favourite mark")
print(BAR)
if not both_pos:
    print("   NONE. Not one head x rule in this band is positive both forward and on the")
    print("   earlier days. Every favourite cell that looks good does so in one window only.")
else:
    print("   %-14s %-14s %18s %18s %16s" % ("head", "rule", "forward", "recon", "pooled"))
    for lab, rule, nf, rf, nr, rr, pr, npl in sorted(both_pos, key=lambda x: -x[6]):
        print("   %-14s %-14s  n=%-4d %+7.2f%%  n=%-4d %+7.2f%%   n=%-4d %+7.2f%%"
              % (lab, rule, nf, rf, nr, rr, npl, pr))
print("\n" + BAR)
