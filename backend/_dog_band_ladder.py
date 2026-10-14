"""THE DOG PRICE-BAND LADDER, per gender, on LANE DISCIPLINE (2026-10-14).

User: "can u show +150 to + 200 how u showed +100 to 150" then "split men and women so i can see",
then "only mark positive cells pink gender specifc for mc2".

CORRECTED 2026-10-14: the first run of this script excluded only `surface_bad`. The lanes also
drop `resolve_bad` (card priced off the wrong human) and `inplay_suspect` (price captured
mid-match), and a `void` row scores as neither a win nor a loss. That is up to 76 rows on a
1,905-row log, and it showed up as the tab's own +250..+300 women cell reporting 18 settles where
this script said 20. Every exclusion the lanes apply is now applied here, so the pooled figures
and the lane figures describe the same games.

THE SAMPLE is forward + CORRECTED recon:
  * forward  = frozen pre-match rows from the live log (mc2_recon False), MC2 as it was quoted
  * recon    = _mc2_recon2.parquet, re-priced with as-of states and post-2026-10-09 surfaces
               (the OLD stored mc2_p1 is NOT used -- that is the state-contaminated number)
ITF men is excluded, matching the tab.

"N pt over market" is MC2's probability on the DOG minus the DE-VIGGED market probability on the
dog -- the same `_ov9` the lanes use, with the sign flipped to the dog's side. De-vigging splits
the book's margin across both sides, so a 3pt edge over the de-vigged line is less than a 3pt
edge over the offered price. That is why the ROI column, not the edge, decides anything here.

Run: ./venv/bin/python _dog_band_ladder.py
"""
import math

import numpy as np
import pandas as pd

import tennis_log

BANDS = [(100, 150), (150, 200), (200, 250), (250, 300)]
THRESH = (0.04, 0.06, 0.08, 0.10)
# every flag the lanes honour; a void row is not a settled bet either way
DROP = ("surface_bad", "resolve_bad", "inplay_suspect", "void")

log = pd.read_parquet(tennis_log.LOG_PATH)
bad = np.zeros(len(log), bool)
for c in DROP:
    if c in log.columns:
        f = log[c].fillna(False).astype(bool).to_numpy()
        print("   excluding %-16s %d rows" % (c, int(f.sum())))
        bad |= f
log = log[~bad].copy()

RC = (log["mc2_recon"].fillna(False).astype(bool).to_numpy()
      if "mc2_recon" in log.columns else np.zeros(len(log), bool))
fw = log[~RC & log["mc2_p1"].notna()].copy()
fw["_mc2"] = pd.to_numeric(fw["mc2_p1"], errors="coerce")
fw["_win"] = "forward"

# the recon rows carry the log index in "i", so the same exclusions apply by index
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

dod = np.where(fav1, D2, D1)                 # the DOG side of every row
dam = (dod - 1) * 100
wond = np.where(fav1, ~W1, W1)
pnl = np.where(wond, dod - 1, -1.0)
mkd = np.where(fav1, 1 - MK1, MK1)           # de-vigged market prob on the dog
over = np.where(fav1, 1 - M2, M2) - mkd      # MC2 minus the market, on the dog
BE = 1.0 / dod                               # break-even hit rate at the offered price


def row(m, lab, ind="   "):
    n = int(m.sum())
    if n == 0:
        return "%s%-26s n=0" % (ind, lab)
    w = int(wond[m].sum())
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
for lo, hi in BANDS:
    # FIRST-MATCH band assignment, exactly as the panel's bandOf does: a dog at +150
    # belongs to +100..+150 ONLY. Testing each band independently counted every
    # round-number price twice and inflated both bands it straddled.
    lower = np.zeros(len(dam), bool)
    for _l, _h in BANDS:
        if _l < lo:
            lower |= (dam >= _l) & (dam <= _h)
    B = (dam >= lo) & (dam <= hi) & ~lower & ~ITFM
    for g, gl in ((~ISW, "MEN"), (ISW, "WOMEN")):
        print(chr(10) + BAR)
        print("%s   +%d to +%d DOGS   (ITF men excluded, lane discipline)" % (gl, lo, hi))
        print(BAR)
        print(row(B & g, "BLIND (no model)"))
        print("")
        for th in THRESH:
            m = B & g & (over >= th)
            print(row(m, "MC2 %dpt+" % round(th * 100)))
            print(row(m & FWD, "   forward", ind="      "))
            print(row(m & ~FWD, "   corrected recon", ind="      "))

print(chr(10) + BAR)
print("READ: 'needs' is break-even at the offered price. A cell is only real if it beats 'needs'")
print("in BOTH windows -- strong forward and negative on the corrected recon is the shape of a")
print("cell found by scanning, not an edge.")
print(BAR)
