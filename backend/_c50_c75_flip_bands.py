"""c50 AND c75 DOG FLIPS, BY GENDER x PRICE BAND (2026-10-14).

User: "okay what about c50 c75 flips".

A FLIP is the head putting the MARKET DOG past 50% and picking it outright:
    c50 flip   mc_c_p1   on the dog >= 0.50      (the Model-C-anchored MC)
    c75 flip   mc_c75_p1 on the dog >= 0.50
    BOTH       c50 and c75 both flip -- the cc75 family's condition

Computed straight from the frozen log rather than read off the lanes, so the bands and the
gender split can be cut freely and the three heads are directly comparable on identical rows.

RECON: the family carries ONE flag, mc_c_recon, and mc_c75_p1 has no flag of its own. Rows the
flag marks are excluded for both heads -- the conservative reading, since the alternative is to
treat c75's backfilled rows as frozen. The run prints how many rows that removes.

Bands are FIRST-MATCH so the edges do not overlap: a dog at exactly +150 belongs to +100..+150
only. Full lane discipline (surface_bad / resolve_bad / inplay_suspect / void), ITF men excluded
to match the dog tab.

Run on EC2: ./venv/bin/python _c50_c75_flip_bands.py
"""
import math

import numpy as np
import pandas as pd

import tennis_log

BANDS = [("+100..+150", 100, 150), ("+150..+200", 150, 200),
         ("+200..+250", 200, 250), ("+250..+300", 250, 300)]
DROP = ("surface_bad", "resolve_bad", "inplay_suspect", "void")

log = pd.read_parquet(tennis_log.LOG_PATH)
n0 = len(log)
bad = np.zeros(len(log), bool)
for c in DROP:
    if c in log.columns:
        bad |= log[c].fillna(False).astype(bool).to_numpy()
log = log[~bad]
log = log[log["p1_won"].notna()]
log = log[log["p1_odds"].notna() & log["p2_odds"].notna()]
log = log[log["mc_c_p1"].notna() & log["mc_c75_p1"].notna()].reset_index(drop=True)

rc = (log["mc_c_recon"].fillna(False).astype(bool).to_numpy()
      if "mc_c_recon" in log.columns else np.zeros(len(log), bool))
print("rows with both heads, settled, priced: %d   (of %d log rows)" % (len(log), n0))
print("   flagged mc_c_recon and therefore EXCLUDED: %d" % int(rc.sum()))
log = log[~rc].reset_index(drop=True)
d = log["date"].astype(str).str[:10]
print("   frozen rows used: %d   %s .. %s  (%d days)" % (len(log), d.min(), d.max(), d.nunique()))

o1 = pd.to_numeric(log["p1_odds"], errors="coerce").to_numpy(float)
o2 = pd.to_numeric(log["p2_odds"], errors="coerce").to_numpy(float)
dc = lambda o: np.where(o > 0, 1 + o / 100.0, 1 + 100.0 / np.abs(o))
D1, D2 = dc(o1), dc(o2)
mk1 = (1 / D1) / ((1 / D1) + (1 / D2))
dog1 = mk1 < 0.5
dam = np.where(dog1, o1, o2)
dec = np.where(dog1, D1, D2)
W1 = log["p1_won"].astype(bool).to_numpy()
won = np.where(dog1, W1, ~W1)
pnl = np.where(won, dec - 1.0, -1.0)
lg = log["league"].astype(str).str.lower()
isw = (lg.str.contains("wta") | lg.str.contains("itf_women")).to_numpy()
itfm = (lg == "itf_men").to_numpy()

c50 = pd.to_numeric(log["mc_c_p1"], errors="coerce").to_numpy(float)
c75 = pd.to_numeric(log["mc_c75_p1"], errors="coerce").to_numpy(float)
c50_dog = np.where(dog1, c50, 1 - c50)          # the head's probability ON THE DOG
c75_dog = np.where(dog1, c75, 1 - c75)
F50, F75 = c50_dog >= 0.5, c75_dog >= 0.5
CELLS = [("c50 FLIP", F50), ("c75 FLIP", F75),
         ("BOTH FLIP (c50 & c75)", F50 & F75),
         ("c75 flips, c50 does NOT", F75 & ~F50),
         ("c50 flips, c75 does NOT", F50 & ~F75)]


def rep(m, lab, ind="      "):
    n = int(m.sum())
    if n == 0:
        return "%s%-26s n=0" % (ind, lab)
    w = int(won[m].sum())
    r = pnl[m].mean()
    t = ""
    if w:
        g = ((r * n) + (n - w)) / w
        v = (w * g * g + (n - w)) / n - r * r
        if v > 0:
            t = "  t %5.2f" % (r / (math.sqrt(v) / math.sqrt(n)))
    return ("%s%-26s n=%-4d %6s  hit %5.1f%%  ROI %+7.2f%%  $%+8.2f%s"
            % (ind, lab, n, "%d-%d" % (w, n - w), 100 * w / n, 100 * r, 25 * pnl[m].sum(), t))


BAR = "=" * 100
base = ~itfm
print("\n" + BAR)
print("BLIND BASELINES (no model), the comparator for everything below")
print(BAR)
print(rep(base & ~isw, "MEN dogs, all prices", ind="   "))
print(rep(base & isw, "WOMEN dogs, all prices", ind="   "))

for cname, cmask in CELLS:
    print("\n" + BAR)
    print(cname)
    print(BAR)
    for g, gl in ((~isw, "MEN"), (isw, "WOMEN")):
        print(rep(base & g & cmask, "%s  ALL PRICES" % gl, ind="   "))
        lower = np.zeros(len(dam), bool)
        for lab, lo, hi in BANDS:
            b = (dam >= lo) & (dam <= hi) & ~lower
            lower |= (dam >= lo) & (dam <= hi)
            print(rep(base & g & cmask & b, "%s  %s" % (gl, lab)))

print("\n" + BAR)
print("READ: a flip is the head picking the dog OUTRIGHT, so these are not threshold cells --")
print("there is no margin to tune. The band split is the only free parameter.")
print(BAR)
