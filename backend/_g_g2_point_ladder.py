"""G AND G2 ON THE MC2 POINT LADDER, LAST 3 DAYS (2026-10-13, user: "go back the last 3 days and
check on g and g2 does the same we tested mc 2").

Same single axis MC2 and c75 were scored on:

    over = head(favourite) - market(favourite)

    over > 0        -> head likes the favourite MORE than the price  -> back the FAVOURITE
    over < 0        -> head likes the favourite LESS than the price  -> back the DOG
    head(fav) < 0.5 -> the head flips the match outright             -> the DOG FLIP cell

WINDOW: the last 3 logged days. That matters a lot here, because G only went live 2026-10-12
22:00Z and G2 2026-10-13 01:00Z -- so inside a 3-day window almost every row is a walk-forward
BACKFILL (model_g_recon / model_g2_recon), not a pick that was ever shown on a card. Backfills
are honest -- model trained only on earlier seasons, strictly-prior windows, result never read
while scoring -- but they are not a record. Both columns are printed for every cell and the
forward one is the only one that is a record.

The full sample is printed underneath each 3-day block, because 3 days of tennis is a few hundred
rows at best and the only way to tell whether the window is representative is to see both.
"""
import sys

import numpy as np
import pandas as pd

import tennis_log

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
HEADS = [("G", "model_g_p1", "model_g_recon"), ("G2", "model_g2_p1", "model_g2_recon")]

L = pd.read_parquet(tennis_log.LOG_PATH)
base = L[L["p1_odds"].notna() & L["p2_odds"].notna() & L["p1_won"].notna()
         & (L["settled"] == True)].copy()                          # noqa: E712
for c in ("surface_bad", "inplay_suspect"):
    if c in base.columns:
        base = base[~base[c].fillna(False).astype(bool)]
base["day"] = base["date"].astype(str).str[:10]
alldays = sorted(base["day"].unique())
win = alldays[-DAYS:]
print("log days available: %s .. %s   (%d days)" % (alldays[0], alldays[-1], len(alldays)))
print("3-day window: %s" % ", ".join(win))


def dec(a):
    a = float(a)
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


def prep(d):
    o1 = d["p1_odds"].map(dec).to_numpy()
    o2 = d["p2_odds"].map(dec).to_numpy()
    mk1 = (1 / o1) / ((1 / o1) + (1 / o2))
    won1 = d["p1_won"].astype(bool).to_numpy()
    fav1 = mk1 >= 0.5
    z = {}
    z["mkfav"] = np.where(fav1, mk1, 1 - mk1)
    z["fav1"] = fav1
    z["favodd"] = np.where(fav1, o1, o2)
    z["dogodd"] = np.where(fav1, o2, o1)
    z["favwon"] = np.where(fav1, won1, ~won1)
    z["favpnl"] = np.where(z["favwon"], z["favodd"] - 1, -1.0)
    z["dogpnl"] = np.where(~z["favwon"], z["dogodd"] - 1, -1.0)
    z["favam"] = -100.0 / (z["favodd"] - 1)
    z["dogam"] = (z["dogodd"] - 1) * 100
    z["gend"] = np.where(d["league"].astype(str).isin(["wta", "itf_women"]), "W", "M")
    return z


def report(tag, col, rflag, d):
    if col not in d.columns:
        print("   (%s: column absent)" % tag)
        return
    d = d[d[col].notna()].copy()
    if not len(d):
        print("   (%s: no scored rows in this window)" % tag)
        return
    z = prep(d)
    pv = d[col].astype(float).to_numpy()
    cfav = np.where(z["fav1"], pv, 1 - pv)
    over = cfav - z["mkfav"]
    rc = (d[rflag].fillna(False).astype(bool).to_numpy()
          if rflag in d.columns else np.zeros(len(d), bool))
    FWD = ~rc
    ca = 100 * z["favpnl"].mean()
    cf = 100 * z["favpnl"][FWD].mean() if FWD.sum() else float("nan")
    da = 100 * z["dogpnl"].mean()
    df_ = 100 * z["dogpnl"][FWD].mean() if FWD.sum() else float("nan")
    print("   rows %d  (forward %d, backfill %d)" % (len(d), int(FWD.sum()), int(rc.sum())))
    print("   chalk here: every fav %+.2f%% all / %+.2f%% fwd | every dog %+.2f%% all / %+.2f%% fwd"
          % (ca, cf, da, df_))

    def cl(m, side):
        n = int(m.sum())
        if not n:
            return None
        p = z["favpnl"][m] if side == "fav" else z["dogpnl"][m]
        w = int(z["favwon"][m].sum()) if side == "fav" else int((~z["favwon"][m]).sum())
        return {"n": n, "roi": 100 * p.mean(), "hit": 100.0 * w / n,
                "se": 100 * p.std() / np.sqrt(n) if n > 1 else float("nan")}

    def f(c):
        if not c:
            return "%-30s" % "        --"
        return "n=%-4d %+7.2f%% +/-%4.1f %3.0f%%hit" % (c["n"], c["roi"], c["se"], c["hit"])

    def two(lab, m, side):
        print("     %-24s %-32s %s" % (lab, f(cl(m, side)), f(cl(m & FWD, side))))

    print("     %-24s %-32s %s" % ("cell", "ALL rows", "FORWARD only"))
    print("   -- FAVOURITE: head over the market, back the fav --")
    for t in (0.0, 0.01, 0.02, 0.04, 0.06, 0.08):
        two("%.0fpt+ over" % (100 * t), over >= t, "fav")
    for lo, hi in ((0, 2), (2, 4), (4, 8), (8, 100)):
        two("  %d-%dpt band" % (lo, hi),
            (over >= lo / 100.0) & (over < hi / 100.0), "fav")
    fb = (z["favam"] <= -100) & (z["favam"] >= -250)
    two("  any over, -100..-250", (over >= 0) & fb, "fav")
    for g in ("M", "W"):
        two("  %s any over" % g, (over >= 0) & (z["gend"] == g), "fav")

    print("   -- DOG: head under the market on the fav, back the dog --")
    for t in (0.0, 0.01, 0.03, 0.05, 0.08, 0.10):
        two("%.0fpt+ under" % (100 * t), over <= -t, "dog")
    two("  1-3pt dead zone", (over <= -0.01) & (over > -0.03), "dog")
    db = (z["dogam"] >= 100) & (z["dogam"] <= 250)
    two("  3pt+ under, +100..+250", (over <= -0.03) & db, "dog")

    print("   -- DOG FLIP: head puts the dog past 50%% --")
    flip = cfav < 0.5
    two("flip, all", flip, "dog")
    for g in ("M", "W"):
        two("  %s" % g, flip & (z["gend"] == g), "dog")
    two("  flip, +100..+250", flip & db, "dog")
    q = pd.Series(100 * over)
    print("   margin distribution: median %+.1fpt | p25 %+.1f | p75 %+.1f | over on fav %.0f%%"
          % (q.median(), q.quantile(.25), q.quantile(.75), 100 * (over > 0).mean()))


BAR = "=" * 96
for tag, col, rflag in HEADS:
    print("\n" + BAR)
    print("%s -- LAST %d DAYS (%s)" % (tag, DAYS, ", ".join(win)))
    print(BAR)
    report(tag, col, rflag, base[base["day"].isin(win)])
    print("\n" + BAR)
    print("%s -- FULL SAMPLE, for context" % tag)
    print(BAR)
    report(tag, col, rflag, base)
