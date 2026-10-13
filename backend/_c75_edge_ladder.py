"""MODEL C75 PUT THROUGH THE EXACT MC2 TREATMENT (2026-10-13, user: "yk how we tested the point
stuff for mc2 on dogs and favorites -- i want u to test model c75 that same way").

One axis, the same one MC2 was scored on: how far c75 sits from the market's own de-vigged
number ON THE MARKET FAVOURITE.

    over = c75(favourite) - market(favourite)

    over > 0  ->  c75 likes the favourite MORE than the price does   -> back the FAVOURITE
    over < 0  ->  c75 likes the favourite LESS than the price does   -> back the DOG
    c75(fav) < 0.5  ->  c75 outright flips the match                 -> the DOG FLIP cell

Every cell MC2 was asked for, reproduced: the positive ladder on favourites, the negative ladder
on dogs, the at-the-market seam, the price bands the marks are restricted to (-100..-250 favs,
+100..+250 dogs), the dead zone, the flip, and the gender split.

Two columns throughout, because that split is what broke MC2's favourite band:
  ALL      every settled row c75 priced -- forward picks and mc_c_recon walk-forward backfills
  FORWARD  only rows c75 was genuinely frozen on pre-match
A cell whose two columns disagree is an artefact of one of them.

c75 is not a fresh head: c75_dog_100plus is the single best lane on the live leaderboard
(+18.6%, t=1.9), so the dog side here should confirm something already known, and the
favourite side is the open question.
"""
import numpy as np
import pandas as pd

import tennis_log

COL, RECON = "mc_c75_p1", "mc_c_recon"

L = pd.read_parquet(tennis_log.LOG_PATH)
if COL not in L.columns:
    raise SystemExit("no %s column" % COL)
d = L[L[COL].notna() & L["p1_odds"].notna() & L["p2_odds"].notna()
      & L["p1_won"].notna() & (L["settled"] == True)].copy()      # noqa: E712
for c in ("surface_bad", "inplay_suspect"):
    if c in d.columns:
        bad = d[c].fillna(False).astype(bool)
        print("dropping %-16s %d" % (c, int(bad.sum())))
        d = d[~bad]
rc = (d[RECON].fillna(False).astype(bool).to_numpy()
      if RECON in d.columns else np.zeros(len(d), bool))
print("settled clean rows with a c75: %d   (forward %d, backfill %d)   %s .. %s"
      % (len(d), int((~rc).sum()), int(rc.sum()),
         str(d["date"].min())[:10], str(d["date"].max())[:10]))


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

favodd = np.where(fav1, d1, d2)
dogodd = np.where(fav1, d2, d1)
favwon = np.where(fav1, won1, ~won1)
favpnl = np.where(favwon, favodd - 1, -1.0)
dogpnl = np.where(~favwon, dogodd - 1, -1.0)
favam = -100.0 / (favodd - 1)
dogam = (dogodd - 1) * 100

FWD = ~rc


def cell(m, side):
    n = int(m.sum())
    if not n:
        return None
    p = favpnl[m] if side == "fav" else dogpnl[m]
    w = int(favwon[m].sum()) if side == "fav" else int((~favwon[m]).sum())
    return {"n": n, "w": w, "roi": 100 * p.mean(),
            "se": 100 * p.std() / np.sqrt(n) if n > 1 else float("nan")}


def f(c):
    if not c:
        return "%-26s" % "        --"
    return "n=%-4d %+7.2f%% +/-%4.1f %3.0f%%hit" % (c["n"], c["roi"], c["se"],
                                                    100 * c["w"] / c["n"])


def two(lab, m, side):
    return "   %-26s %-28s %s" % (lab, f(cell(m, side)), f(cell(m & FWD, side)))


HDR = "   %-26s %-28s %s" % ("cell", "ALL rows", "FORWARD only")
BAR = "=" * 92

# ----------------------------------------------------------------- favourites
print("\n" + BAR)
print("C75 ON THE FAVOURITE -- back the market favourite when c75 is N points OVER the market")
print(BAR)
print(HDR)
for t in (0.0, 0.005, 0.01, 0.015, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10):
    print(two("%.1fpt+ over" % (100 * t), over >= t, "fav"))
print(two("-- every favourite --", np.ones(len(d), bool), "fav"))

print("\n   exclusive bands (not nested), so one good slice cannot carry the ladder:")
for lo, hi in ((0.0, 0.02), (0.02, 0.04), (0.04, 0.06), (0.06, 0.08), (0.08, 1.0)):
    print(two("  %.0f-%.0fpt over" % (100 * lo, 100 * hi),
              (over >= lo) & (over < hi), "fav"))

print("\n   the at-the-market seam (MC2's strongest unmarked cell was here):")
for lab, m in (("exactly at mkt +/-0.5pt", np.abs(over) < 0.005),
               ("within 1pt either way", np.abs(over) < 0.01),
               ("at mkt or over, any amt", over >= 0.0)):
    print(two("  " + lab, m, "fav"))

print("\n   restricted to the -100..-250 favourite band the marks use:")
band_f = (favam <= -100) & (favam >= -250)
for t in (0.0, 0.01, 0.02, 0.03, 0.04, 0.06, 0.08):
    print(two("  %.0fpt+ over, in band" % (100 * t), (over >= t) & band_f, "fav"))
print(two("  -- every fav in band --", band_f, "fav"))

print("\n   gender split on the favourite:")
for g in ("M", "W"):
    for t in (0.0, 0.02, 0.04, 0.08):
        print(two("  %s %.0fpt+ over" % (g, 100 * t), (over >= t) & (gend == g), "fav"))
    print(two("  %s every favourite" % g, gend == g, "fav"))

# ----------------------------------------------------------------------- dogs
print("\n" + BAR)
print("C75 ON THE DOG -- back the market underdog when c75 is N points BELOW the market on the fav")
print(BAR)
print(HDR)
for t in (0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12):
    print(two("%.0fpt+ under (take dog)" % (100 * t), over <= -t, "dog"))
print(two("-- every dog --", np.ones(len(d), bool), "dog"))

print("\n   exclusive bands:")
for lo, hi in ((0.0, 0.01), (0.01, 0.03), (0.03, 0.05), (0.05, 0.08), (0.08, 0.12), (0.12, 1.0)):
    print(two("  %.0f-%.0fpt under" % (100 * lo, 100 * hi),
              (over <= -lo) & (over > -hi), "dog"))

print("\n   the dead zone MC2 has (1-3pt under was -17% there):")
print(two("  1-3pt under", (over <= -0.01) & (over > -0.03), "dog"))
print(two("  3pt+ under", over <= -0.03, "dog"))
print(two("  agreement, under 1pt", np.abs(over) < 0.01, "dog"))

print("\n   THE DOG FLIP -- c75 puts the market dog outright past 50%:")
flip = cfav < 0.5
print(two("  flip, all", flip, "dog"))
for g in ("M", "W"):
    print(two("  flip, %s" % g, flip & (gend == g), "dog"))
for lo, hi in ((0.0, 0.02), (0.02, 0.05), (0.05, 1.0)):
    print(two("  flips %.0f-%.0fpt past 50" % (100 * lo, 100 * hi),
              flip & (0.5 - cfav > lo) & (0.5 - cfav <= hi), "dog"))

print("\n   restricted to the +100..+250 dog band the marks use:")
band_d = (dogam >= 100) & (dogam <= 250)
for t in (0.0, 0.01, 0.03, 0.05, 0.08, 0.10):
    print(two("  %.0fpt+ under, in band" % (100 * t), (over <= -t) & band_d, "dog"))
print(two("  flip, in band", flip & band_d, "dog"))
print(two("  -- every dog in band --", band_d, "dog"))

print("\n   price extent at a 3pt+ under gate (where the band stops working):")
for lo, hi in ((0, 100), (100, 150), (150, 200), (200, 250), (250, 300), (300, 1e9)):
    print(two("  dog +%d..+%d" % (lo, hi),
              (over <= -0.03) & (dogam >= lo) & (dogam < hi), "dog"))

print("\n   gender split on the dog:")
for g in ("M", "W"):
    for t in (0.0, 0.03, 0.05, 0.08):
        print(two("  %s %.0fpt+ under" % (g, 100 * t), (over <= -t) & (gend == g), "dog"))
    print(two("  %s every dog" % g, gend == g, "dog"))

print("\n   where c75's margin actually lands:")
q = pd.Series(100 * over)
print("   median %+.1fpt | p10 %+.1f | p25 %+.1f | p75 %+.1f | p90 %+.1f | over on fav %.0f%%"
      % (q.median(), q.quantile(.1), q.quantile(.25), q.quantile(.75), q.quantile(.9),
         100 * (over > 0).mean()))
print("   (cell reads n, ROI +/- 1se, hit rate)")
