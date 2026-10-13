"""THE MIRROR OF C75'S FAVOURITE FADE (2026-10-13).

The favourite ladder came back monotone NEGATIVE: the further c75 sits over the market on a
favourite, the worse that favourite does (-8.5% at any margin, -21% at 8pt+, against -7.0%
chalk). That is a fade gradient, and the bettable form of a fade is the other side of the same
match, so this scores it directly:

    back the DOG whenever c75 is N points OVER the market on the FAVOURITE

which is the same shape MC2's "-4 to -12 from the favourite" test had, just with c75's sign.
Reported against every dog on the same rows, which is the bar that matters -- the dog baseline
in this window is itself positive (+2.3% forward), so a fade cell has to clear that, not zero.

Also here: the dog flip crossed with price and gender, since the flip was the one cell that came
out positive in both samples and for both genders, and the overlap with the c75 lanes already
running, so a new mark would not just re-bet something already marked.
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
fav1 = mk1 >= 0.5
mkfav = np.where(fav1, mk1, 1 - mk1)
cfav = np.where(fav1, pv, 1 - pv)
over = cfav - mkfav
dogodd = np.where(fav1, d2, d1)
favwon = np.where(fav1, won1, ~won1)
dogpnl = np.where(~favwon, dogodd - 1, -1.0)
dogam = (dogodd - 1) * 100
dogwon = ~favwon


def cl(m):
    n = int(m.sum())
    if not n:
        return None
    p = dogpnl[m]
    return {"n": n, "w": int(dogwon[m].sum()), "roi": 100 * p.mean(),
            "se": 100 * p.std() / np.sqrt(n) if n > 1 else float("nan"),
            "am": dogam[m].mean()}


def f(c):
    if not c:
        return "%-34s" % "        --"
    return ("n=%-4d %+7.2f%% +/-%4.1f %3.0f%%hit avg%+5.0f"
            % (c["n"], c["roi"], c["se"], 100 * c["w"] / c["n"], c["am"]))


def two(lab, m):
    print("   %-26s %-36s %s" % (lab, f(cl(m)), f(cl(m & FWD))))


BAR = "=" * 100
print("rows %d (forward %d)" % (len(d), int(FWD.sum())))
print("\n" + BAR)
print("FADE THE FAVOURITE c75 LIKES -- back the DOG when c75 is Npt OVER the market on the fav")
print(BAR)
print("   %-26s %-36s %s" % ("cell", "ALL rows", "FORWARD only"))
for t in (0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12):
    two("%.0fpt+ over -> take dog" % (100 * t), over >= t)
two("-- every dog, same rows --", np.ones(len(d), bool))

print("\n   in the +100..+250 dog band:")
band = (dogam >= 100) & (dogam <= 250)
for t in (0.0, 0.02, 0.04, 0.06, 0.08):
    two("  %.0fpt+ over, band" % (100 * t), (over >= t) & band)
two("  -- every band dog --", band)

print("\n   by gender, 4pt+ over on the fav -> take the dog:")
for g in ("M", "W"):
    for t in (0.0, 0.04, 0.08):
        two("  %s %.0fpt+ over" % (g, 100 * t), (over >= t) & (gend == g))
    two("  %s every dog" % g, gend == g)

print("\n   price extent, 4pt+ over on the fav -> take the dog:")
for lo, hi in ((0, 100), (100, 150), (150, 200), (200, 250), (250, 300), (300, 1e9)):
    two("  dog +%d..+%d" % (lo, hi), (over >= 0.04) & (dogam >= lo) & (dogam < hi))

print("\n" + BAR)
print("THE DOG FLIP crossed with price and gender (the cell that held in both samples)")
print(BAR)
print("   %-26s %-36s %s" % ("cell", "ALL rows", "FORWARD only"))
flip = cfav < 0.5
two("flip, all", flip)
for lo, hi in ((0, 100), (100, 150), (150, 200), (200, 250), (250, 300), (300, 1e9)):
    two("  dog +%d..+%d" % (lo, hi), flip & (dogam >= lo) & (dogam < hi))
for g in ("M", "W"):
    two("  %s flip" % g, flip & (gend == g))
    two("  %s flip, +100..+250" % g, flip & (gend == g) & band)

print("\n" + BAR)
print("OVERLAP with the c75 lanes already live -- is any of this already being bet?")
print(BAR)
try:
    rec = tennis_log.get_ab25_record()
    st = rec.get("study") or {}
    for k in sorted(st):
        if "c75" in k or "c_75" in k:
            v = st[k] or {}
            print("   %-28s n=%-4s roi=%-9s pending=%s"
                  % (k, v.get("n"), v.get("roi_pct"), v.get("pending")))
except Exception as e:                                             # noqa: BLE001
    print("   (lane read failed: %s)" % e)
