"""DO THE YELLOW/GOLD FAVOURITES HOLD UP? (2026-10-14)

User: "and do the favorites hold up?" -- the same audit the dogs just had, on the same basis:
FORWARD decides, gender-specific, lane discipline, and NON-OVERLAPPING bands.

The favourite mark is a WOMENS favourite at -100..-200 that MC2 rates 4pt+ above the de-vigged
market: yellow at -100..-150, gold at -150..-200. The men's lane is a control and is not marked.

THREE THINGS THIS CHECKS, in the order they can kill it:
  1. THE BAND-BOUNDARY BUG. favBandOf uses FIRST MATCH, so a favourite at exactly -150 belongs to
     -100..-150 only. The scan that produced the shipped +22.31% / +23.50% split tested each band
     independently, which is what inflated the dogs' +250..+300 cell and flipped its sign. Round
     numbers are even more common on the favourite side, so this is the first suspect.
  2. FORWARD vs POOLED. The shipped figure (+22.85% on 51, t 2.16) is forward + corrected recon.
     The dogs are now gated on FORWARD ALONE, so the favourite has to be judged the same way.
  3. GENDER. The women's cell is the take; the men's is the control that justifies it. Both are
     reported at every rung so the split keeps being tested rather than assumed.

Lane discipline throughout: surface_bad / resolve_bad / inplay_suspect / void excluded. ITF men is
NOT excluded here -- that gate is a dog-side decision and the favourite lane never applied it; the
run reports what dropping it would do rather than silently assuming either way.

Run on EC2: ./venv/bin/python _fav_band_ladder.py
"""
import math

import numpy as np
import pandas as pd

import tennis_log

# favBandOf's own bands, in its own order -- first match wins, so -150 lands in the FIRST
FAV_BANDS = [("-100..-150", -150.0, -100.0), ("-150..-200", -200.0, -150.0),
             ("-200..-250", -250.0, -200.0), ("-250..-400", -400.0, -250.0)]
THRESH = (0.02, 0.03, 0.04, 0.06, 0.08, 0.10)
DROP = ("surface_bad", "resolve_bad", "inplay_suspect", "void")

log = pd.read_parquet(tennis_log.LOG_PATH)
bad = np.zeros(len(log), bool)
for c in DROP:
    if c in log.columns:
        bad |= log[c].fillna(False).astype(bool).to_numpy()
log = log[~bad].copy()

RC = (log["mc2_recon"].fillna(False).astype(bool).to_numpy()
      if "mc2_recon" in log.columns else np.zeros(len(log), bool))
fw = log[~RC & log["mc2_p1"].notna()].copy()
fw["_mc2"] = pd.to_numeric(fw["mc2_p1"], errors="coerce")
fw["_win"] = "forward"

rc = pd.read_parquet("data_cache/_mc2_recon2.parquet")
rc = rc[rc["new"].notna()].copy()
rc = rc[rc["i"].isin(set(log.index))]
rc["_mc2"] = pd.to_numeric(rc["new"], errors="coerce")
rc["_win"] = "recon"

keep = ["league", "p1_odds", "p2_odds", "p1_won", "_mc2", "_win"]
R = pd.concat([fw[keep], rc[keep]], ignore_index=True)
R = R[R["p1_won"].notna()]
R["_o1"] = pd.to_numeric(R["p1_odds"], errors="coerce")
R["_o2"] = pd.to_numeric(R["p2_odds"], errors="coerce")
R = R[R._o1.notna() & R._o2.notna() & R._mc2.notna()].reset_index(drop=True)
print("rows: %d  (forward %d, corrected recon %d)"
      % (len(R), int((R._win == "forward").sum()), int((R._win == "recon").sum())))

dc = lambda o: np.where(o > 0, 1 + o / 100.0, 1 + 100.0 / np.abs(o))
D1, D2 = dc(R._o1.to_numpy(float)), dc(R._o2.to_numpy(float))
I1, I2 = 1 / D1, 1 / D2
MK1 = I1 / (I1 + I2)
W1 = R.p1_won.astype(bool).to_numpy()
fav1 = MK1 >= 0.5
LG = R.league.astype(str).str.lower()
ITFM = (LG == "itf_men").to_numpy()
ISW = (LG.str.contains("wta") | LG.str.contains("itf_women")).to_numpy()
FWD = (R._win == "forward").to_numpy()
M2 = R._mc2.to_numpy(float)

# the FAVOURITE side of every row
fod = np.where(fav1, D1, D2)
fam = np.where(fod >= 2, (fod - 1) * 100, -100.0 / np.maximum(fod - 1, 1e-9))
wonf = np.where(fav1, W1, ~W1)
pnl = np.where(wonf, fod - 1, -1.0)
mkf = np.where(fav1, MK1, 1 - MK1)              # de-vigged market prob on the favourite
over = np.where(fav1, M2, 1 - M2) - mkf         # MC2 minus market, ON THE FAVOURITE
BE = 1.0 / fod


def band_mask(lo, hi, idx):
    """First-match assignment, exactly as favBandOf does."""
    m = (fam >= lo) & (fam <= hi)
    for k, (_, l2, h2) in enumerate(FAV_BANDS):
        if k < idx:
            m &= ~((fam >= l2) & (fam <= h2))
    return m


def row(m, lab, ind="   "):
    n = int(m.sum())
    if n == 0:
        return "%s%-26s n=0" % (ind, lab)
    w = int(wonf[m].sum())
    r = pnl[m].mean()
    t = ""
    if w:
        g = ((r * n) + (n - w)) / w
        v = (w * g * g + (n - w)) / n - r * r
        if v > 0:
            t = "  t %5.2f" % (r / (math.sqrt(v) / math.sqrt(n)))
    return ("%s%-26s n=%-4d %7s  hit %5.1f%%  needs %5.1f%%  ROI %+7.2f%%  $%+8.2f%s"
            % (ind, lab, n, "%d-%d" % (w, n - w), 100 * w / n, 100 * BE[m].mean(),
               100 * r, 25 * pnl[m].sum(), t))


BAR = "=" * 112
WHOLE = band_mask(-400.0, -100.0, 0)            # the combined -100..-200 range

print(chr(10) + BAR)
print("0. DOES THE BAND BOUNDARY MATTER HERE? favourites priced exactly -150")
print(BAR)
at150 = (np.abs(fam + 150.0) < 0.5)
print("   rows at exactly -150: %d  (women %d, men %d)"
      % (int(at150.sum()), int((at150 & ISW).sum()), int((at150 & ~ISW).sum())))
print("   of those, MC2 4pt+ over on the favourite: %d women, %d men"
      % (int((at150 & ISW & (over >= 0.04)).sum()), int((at150 & ~ISW & (over >= 0.04)).sum())))

for idx, (lab, lo, hi) in enumerate(FAV_BANDS + [("-100..-400 COMBINED", -400.0, -100.0)]):
    B = band_mask(lo, hi, idx) if idx < len(FAV_BANDS) else WHOLE
    for g, gl in ((ISW, "WOMEN"), (~ISW, "MEN")):
        print(chr(10) + BAR)
        print("%s   %s FAVOURITES   (lane discipline, one band per pick)" % (gl, lab))
        print(BAR)
        print(row(B & g, "BLIND (no model)"))
        print("")
        for th in THRESH:
            m = B & g & (over >= th)
            print(row(m, "MC2 %dpt+" % round(th * 100)))
            print(row(m & FWD, "   FORWARD", ind="      "))
            print(row(m & ~FWD, "   corrected recon", ind="      "))

print(chr(10) + BAR)
print("WHAT ITF MEN WOULD DO (the dog tab excludes it; the favourite lane does not)")
print(BAR)
m4 = WHOLE & ISW & (over >= 0.04)
print(row(m4, "women 4pt+, as is"))
print(row(m4 & ~ITFM, "women 4pt+, no ITF men"))
print(row(m4 & FWD, "   forward, as is"))
print(BAR)
