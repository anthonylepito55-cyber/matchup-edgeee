"""RE-TEST THE RULES ON THE CORRECTED-SURFACE RECON (2026-10-14).

Companion to _mc2_recon_rebuild.py, which re-priced every MC2 recon row with an as-of state and
the surface the log holds after the 2026-10-09 wrong-court fix.

Two questions, and they are the only two that matter:
  1. HOW MUCH did the corrected surfaces move MC2's number? If barely at all, every recon-based
     conclusion in this session stands as stated.
  2. DO THE VERDICTS CHANGE? Specifically:
        the FAVOURITE rule -- MC2 4pt+/6pt+/8pt+ over the market on a fav at -100..-150, which
            looked like -21.80% on the old recon and killed the yellow mark
        the PINK DOG rule -- MC2 3pt+/6pt+ over the market on a dog at +100..+150, which looked
            like +2.94% on the old recon and prompted me to revise pink's expectation down to
            ~+10% from its +22% forward figure

Old and new are reported side by side on IDENTICAL rows, so any change is the surface correction
and nothing else. Rows flagged surface_bad are excluded throughout, exactly as in the original
scans, so this is a like-for-like re-test rather than a different sample.
"""
import math

import numpy as np
import pandas as pd

R = pd.read_parquet("data_cache/_mc2_recon2.parquet")
R = R[R["new"].notna() & R["p1_won"].notna()].copy()
R = R[~R["surface_bad"].fillna(False).astype(bool)]
R["_o1"] = pd.to_numeric(R["p1_odds"], errors="coerce")
R["_o2"] = pd.to_numeric(R["p2_odds"], errors="coerce")
R = R[R._o1.notna() & R._o2.notna()].reset_index(drop=True)
print("comparable recon rows (re-priced, settled, surface ok): %d" % len(R))

dc = lambda o: np.where(o > 0, 1 + o / 100.0, 1 + 100.0 / np.abs(o))
D1, D2 = dc(R._o1.to_numpy(float)), dc(R._o2.to_numpy(float))
I1, I2 = 1 / D1, 1 / D2
MK1 = I1 / (I1 + I2)
W1 = R.p1_won.astype(bool).to_numpy()
fav1 = MK1 >= 0.5
ITFM = (R.league.astype(str).str.lower() == "itf_men").to_numpy()
OLD, NEW = R["old"].to_numpy(float), R["new"].to_numpy(float)

BAR = "=" * 108
print("\n" + BAR)
print("1. HOW MUCH DID THE CORRECTED SURFACES MOVE MC2?")
print(BAR)
d = np.abs(NEW - OLD) * 100
print("   |new - old|: median %.2fpt  p75 %.2fpt  p90 %.2fpt  max %.2fpt"
      % (np.median(d), np.percentile(d, 75), np.percentile(d, 90), d.max()))
print("   share moving >1pt %.0f%%   >2pt %.0f%%   >4pt %.0f%%"
      % (100 * (d > 1).mean(), 100 * (d > 2).mean(), 100 * (d > 4).mean()))
print("   mean signed change: %+.2fpt (positive = new reads p1 higher)" % np.mean((NEW - OLD) * 100))

# favourite side
fod = np.where(fav1, D1, D2)
fam = np.where(fod >= 2, (fod - 1) * 100, -100.0 / np.maximum(fod - 1, 1e-9))
wonf = np.where(fav1, W1, ~W1)
pnlf = np.where(wonf, fod - 1, -1.0)
mkf = np.where(fav1, MK1, 1 - MK1)
# dog side
dod = np.where(fav1, D2, D1)
dam = (dod - 1) * 100
wond = np.where(fav1, ~W1, W1)
pnld = np.where(wond, dod - 1, -1.0)
mkd = np.where(fav1, 1 - MK1, MK1)


def rep(m, pnl, won, lab, ind="      "):
    n = int(m.sum())
    if n == 0:
        return "%s%-22s n=0" % (ind, lab)
    w = int(won[m].sum())
    roi = 100 * pnl[m].mean()
    r = roi / 100
    t = None
    if w:
        g = (r * n + (n - w)) / w
        v = (w * g * g + (n - w)) / n - r * r
        if v > 0:
            t = r / (math.sqrt(v) / math.sqrt(n))
    return ("%s%-22s n=%-4d %7s  hit %5.1f%%  ROI %+7.2f%%  $%+8.2f%s"
            % (ind, lab, n, "%d-%d" % (w, n - w), 100 * w / n, roi, 25 * pnl[m].sum(),
               "  t %5.2f" % t if t is not None else ""))


print("\n" + BAR)
print("2a. THE FAVOURITE RULE -- fav -100..-150, MC2 over the de-vigged market")
print("    old = the recon that killed the yellow mark; new = corrected surfaces, same rows")
print(BAR)
FB = (fam <= -100) & (fam >= -150)
print("   baseline, every fav in band:")
print(rep(FB, pnlf, wonf, "(model-free)"))
for th in (0.04, 0.06, 0.08):
    o_over = np.where(fav1, OLD, 1 - OLD) - mkf
    n_over = np.where(fav1, NEW, 1 - NEW) - mkf
    print("   %dpt+ over market" % round(th * 100))
    print(rep(FB & (o_over >= th), pnlf, wonf, "OLD surfaces"))
    print(rep(FB & (n_over >= th), pnlf, wonf, "NEW surfaces"))
    both = FB & (o_over >= th) & (n_over >= th)
    only_n = FB & (n_over >= th) & ~(o_over >= th)
    only_o = FB & (o_over >= th) & ~(n_over >= th)
    print("         membership: in both %d | NEW only %d | OLD only %d"
          % (int(both.sum()), int(only_n.sum()), int(only_o.sum())))

print("\n" + BAR)
print("2b. THE PINK DOG RULE -- dog +100..+150 (no ITF men), MC2 over the market")
print(BAR)
DB = (dam >= 100) & (dam <= 150) & ~ITFM
print("   baseline, every dog in band:")
print(rep(DB, pnld, wond, "(model-free)"))
for th in (0.03, 0.06):
    o_over = np.where(fav1, 1 - OLD, OLD) - mkd
    n_over = np.where(fav1, 1 - NEW, NEW) - mkd
    print("   %dpt+ over market" % round(th * 100))
    print(rep(DB & (o_over >= th), pnld, wond, "OLD surfaces"))
    print(rep(DB & (n_over >= th), pnld, wond, "NEW surfaces"))
    both = DB & (o_over >= th) & (n_over >= th)
    only_n = DB & (n_over >= th) & ~(o_over >= th)
    only_o = DB & (o_over >= th) & ~(n_over >= th)
    print("         membership: in both %d | NEW only %d | OLD only %d"
          % (int(both.sum()), int(only_n.sum()), int(only_o.sum())))

print("\n" + BAR)
print("READ: if the NEW lines sit close to the OLD ones, the surface contamination did not")
print("drive the recon verdicts and they stand. If the favourite rule's NEW line turns")
print("positive, the yellow mark deserves reconsidering. If the dog rule's NEW line rises,")
print("pink's expectation is higher than the ~+10% I revised it to.")
print(BAR)
