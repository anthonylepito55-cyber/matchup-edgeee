"""MC v2 in G's two cells, on the LIVE log (2026-10-13, user: "What's the live roi when mc2
favorites someone over the market and flips a dog").

Same two reads G and G2 are tracked on, applied to MC v2's frozen probability:
  FAV-OVER  -- mc2 rates the market FAVOURITE above the price the market set on it -> back the fav
  DOG-FLIP  -- mc2 puts the market UNDERDOG past 50%, picking it outright       -> back the dog

Frozen log only, per the forward-tests-only rule:
  * mc2_recon rows are DROPPED. Those are walk-forward backfills onto games that predate the
    model -- honest, but not picks that were ever shown, so they are not a record.
  * surface_bad and inplay_suspect rows are dropped, as every lane does.
  * one bet per match at the frozen closing price, flat 1u, so ROI is comparable to the lanes.

Baselines on the SAME rows are printed beside each cell, because a cell that merely reproduces
what backing every favourite (or every dog) would have done is not a finding -- that is exactly
how G's fav-over turned out to be worse than arbitrary chalk.
"""
import numpy as np
import pandas as pd

import tennis_log

L = pd.read_parquet(tennis_log.LOG_PATH)
print("log rows: %d" % len(L))
if "mc2_p1" not in L.columns:
    raise SystemExit("no mc2_p1 column")

d = L[L["mc2_p1"].notna() & L["p1_odds"].notna() & L["p2_odds"].notna()
      & L["p1_won"].notna() & (L["settled"] == True)].copy()   # noqa: E712
print("settled rows with a frozen mc2: %d" % len(d))
for c in ("mc2_recon", "surface_bad", "inplay_suspect"):
    if c in d.columns:
        bad = d[c].fillna(False).astype(bool)
        print("   dropping %-16s %d" % (c, int(bad.sum())))
        d = d[~bad]
print("forward, clean rows: %d" % len(d))
if not len(d):
    raise SystemExit("nothing to score")


def dec(a):
    a = float(a)
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


d1, d2 = d["p1_odds"].map(dec), d["p2_odds"].map(dec)
mk = (1 / d1) / ((1 / d1) + (1 / d2))
d["fav1"] = mk >= 0.5
d["mkfav"] = np.where(d["fav1"], mk, 1 - mk)
d["mc2fav"] = np.where(d["fav1"], d["mc2_p1"].astype(float), 1 - d["mc2_p1"].astype(float))
d["favodd"] = np.where(d["fav1"], d1, d2)
d["dogodd"] = np.where(d["fav1"], d2, d1)
d["favwon"] = np.where(d["fav1"], d["p1_won"].astype(bool), ~d["p1_won"].astype(bool))
d["G"] = np.where(d["league"].astype(str).isin(["wta", "itf_women"]), "W", "M")
d["over"] = d["mc2fav"] - d["mkfav"]

d["favpnl"] = np.where(d["favwon"], d["favodd"] - 1, -1.0)
d["dogpnl"] = np.where(~d["favwon"], d["dogodd"] - 1, -1.0)


def line(lab, sub, pnlcol, hitcol):
    if not len(sub):
        return "   %-34s (none)" % lab
    p = sub[pnlcol]
    se = 100 * p.std() / np.sqrt(len(p)) if len(p) > 1 else float("nan")
    w = int(sub[hitcol].sum())
    dc = float(sub["favodd" if pnlcol == "favpnl" else "dogodd"].mean())
    am = (dc - 1) * 100 if dc >= 2 else -100 / (dc - 1)      # decimal -> American
    return ("   %-34s n=%-4d %5d-%-4d roi %+7.2f%% +/-%4.1f   avg price %+.0f"
            % (lab, len(sub), w, len(sub) - w, 100 * p.mean(), se, am))


print("\n" + "=" * 86)
print("MC2 FAV-OVER  -- mc2 above the market on the favourite, back the favourite")
print("=" * 86)
fo = d[d["over"] > 0]
print(line("all", fo, "favpnl", "favwon"))
for g in ("M", "W"):
    print(line("  %s" % g, fo[fo.G == g], "favpnl", "favwon"))
print("   %-34s" % "-- baseline on the same rows --")
print(line("every favourite (all rows)", d, "favpnl", "favwon"))
for g in ("M", "W"):
    print(line("  every favourite, %s" % g, d[d.G == g], "favpnl", "favwon"))
print("   %-34s" % "-- by margin over the market --")
for lo, hi in ((0, 0.02), (0.02, 0.04), (0.04, 0.08), (0.08, 1.0)):
    print(line("  %.0f-%.0f pt over" % (100 * lo, 100 * hi),
               fo[(fo["over"] > lo) & (fo["over"] <= hi)], "favpnl", "favwon"))
print(line("  4pt+ over (G2's gate)", fo[fo["over"] >= 0.04], "favpnl", "favwon"))

print("\n" + "=" * 86)
print("MC2 DOG-FLIP  -- mc2 puts the underdog past 50%, back the dog")
print("=" * 86)
df_ = d[d["mc2fav"] < 0.5]
df_ = df_.assign(dogwon=~df_["favwon"])
d_all = d.assign(dogwon=~d["favwon"])
print(line("all", df_, "dogpnl", "dogwon"))
for g in ("M", "W"):
    print(line("  %s" % g, df_[df_.G == g], "dogpnl", "dogwon"))
print("   %-34s" % "-- baseline on the same rows --")
print(line("every dog (all rows)", d_all, "dogpnl", "dogwon"))
for g in ("M", "W"):
    print(line("  every dog, %s" % g, d_all[d_all.G == g], "dogpnl", "dogwon"))
print("   %-34s" % "-- by how far past 50% --")
for lo, hi in ((0, 0.02), (0.02, 0.05), (0.05, 1.0)):
    q = df_[(0.5 - df_["mc2fav"] > lo) & (0.5 - df_["mc2fav"] <= hi)]
    print(line("  flips %.0f-%.0f pt past" % (100 * lo, 100 * hi), q, "dogpnl", "dogwon"))
print("   %-34s" % "-- by the dog's price --")
for lo, hi in ((100, 150), (150, 200), (200, 300), (300, 100000)):
    am = (df_["dogodd"] - 1) * 100
    print(line("  dog +%d..+%d" % (lo, hi), df_[(am >= lo) & (am < hi)], "dogpnl", "dogwon"))

print("\nnote: both cells are the SAME two reads G and G2 are tracked on, so these are directly")
print("comparable to the g_/g2_ lanes. Dates covered: %s .. %s"
      % (str(d["date"].min())[:10], str(d["date"].max())[:10]))
