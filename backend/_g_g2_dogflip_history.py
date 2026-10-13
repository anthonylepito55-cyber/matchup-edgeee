"""G and G2 DOG-FLIP across the whole logged history (2026-10-13, user: "what's the roi when g
and g2 dog flip go back on our results tab and see").

The forward lanes have 1 settle between them, so the only way to answer at any scale is the
results-tab data: every settled row in the log, with G and G2 read off their walk-forward
BACKFILL. Those rows were scored by a model trained only on seasons before each game, off
strictly-prior windows, and the result was never read while producing the probability -- but they
were never shown on a board either, so this is what the cell WOULD have done, not a record of
what it did. Both models' backfills were rescored with the current artifacts, so the two are
internally consistent and comparable to each other.

Reported by gender, by price band, and by DAY, because a single good or bad day inside ~1,500
rows is the main way a number like this lies.
"""
import numpy as np
import pandas as pd

import tennis_log

L = pd.read_parquet(tennis_log.LOG_PATH)
d = L[(L["settled"] == True) & L["p1_won"].notna()                      # noqa: E712
      & L["p1_odds"].notna() & L["p2_odds"].notna()].copy()
for c in ("surface_bad", "inplay_suspect"):
    if c in d.columns:
        d = d[~d[c].fillna(False).astype(bool)]
d["day"] = d["date"].astype(str).str[:10]
print("settled, clean rows: %d  (%s .. %s)" % (len(d), d["day"].min(), d["day"].max()))


def dec(a):
    a = float(a)
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


d1, d2 = d["p1_odds"].map(dec).to_numpy(), d["p2_odds"].map(dec).to_numpy()
mk1 = (1 / d1) / ((1 / d1) + (1 / d2))
won1 = d["p1_won"].astype(bool).to_numpy()
gend = np.where(d["league"].astype(str).isin(["wta", "itf_women"]), "W", "M")
fav1 = mk1 >= 0.5
dogodd = np.where(fav1, d2, d1)
dogwon = np.where(fav1, ~won1, won1)
dogpnl = np.where(dogwon, dogodd - 1, -1.0)
dogam = (dogodd - 1) * 100
lvl = np.where(d["league"].astype(str).str.startswith("itf"), "itf",
               np.where(d["league"].astype(str).str.contains("challenger"), "chall", "tour"))


def show(lab, m):
    n = int(m.sum())
    if not n:
        return "   %-30s (none)" % lab
    p = dogpnl[m]
    se = 100 * p.std() / np.sqrt(n) if n > 1 else float("nan")
    w = int(dogwon[m].sum())
    return ("   %-30s n=%-5d %4d-%-4d roi %+7.2f%% +/-%4.1f  hit %4.1f%%  avg %+5.0f"
            % (lab, n, w, n - w, 100 * p.mean(), se, 100 * w / n, dogam[m].mean()))


for tag, col in (("G", "model_g_p1"), ("G2", "model_g2_p1")):
    if col not in d.columns:
        print("\n%s: no column" % tag)
        continue
    pv = d[col].astype(float).to_numpy()
    have = d[col].notna().to_numpy()
    hfav = np.where(fav1, pv, 1 - pv)
    flip = have & (hfav < 0.5)
    print("\n" + "=" * 94)
    print("%s DOG-FLIP -- %s puts the market underdog past 50%%   (walk-forward backfill)" % (tag, tag))
    print("=" * 94)
    print(show("all", flip))
    for g in ("M", "W"):
        print(show("  %s" % g, flip & (gend == g)))
    print("   -- by the dog's price --")
    for lo, hi in ((0, 100), (100, 150), (150, 200), (200, 300), (300, 1e9)):
        print(show("  dog +%d..+%d" % (lo, hi), flip & (dogam >= lo) & (dogam < hi)))
    print("   -- by level --")
    for lv in ("tour", "chall", "itf"):
        print(show("  %s" % lv, flip & (lvl == lv)))
    print("   -- by how far past 50%% --")
    for lo, hi in ((0, 0.02), (0.02, 0.05), (0.05, 1.0)):
        print(show("  flips %.0f-%.0f pt" % (100 * lo, 100 * hi),
                   flip & (0.5 - hfav > lo) & (0.5 - hfav <= hi)))

# ---- stability: is any of it one day? ----
print("\n" + "=" * 94)
print("BY DAY -- the main way a 1,500-row number lies is one outlier day")
print("=" * 94)
rows = []
for day, sub in d.groupby("day"):
    i = d["day"].to_numpy() == day
    line = {"day": day, "rows": int(i.sum())}
    for tag, col in (("G", "model_g_p1"), ("G2", "model_g2_p1")):
        if col not in d.columns:
            continue
        pv = d[col].astype(float).to_numpy()
        hv = np.where(fav1, pv, 1 - pv)
        m = i & d[col].notna().to_numpy() & (hv < 0.5)
        line["%s n" % tag] = int(m.sum())
        line["%s roi" % tag] = round(100 * dogpnl[m].mean(), 1) if m.sum() else None
    rows.append(line)
t = pd.DataFrame(rows).set_index("day")
print(t.tail(16).to_string())

print("\n" + "=" * 94)
print("BASELINES on the same rows")
print("=" * 94)
print(show("every dog", np.ones(len(d), bool)))
for g in ("M", "W"):
    print(show("  every dog %s" % g, gend == g))
print("\nFORWARD lanes for contrast (frozen picks only, the actual record):")
st = tennis_log.get_ab25_record()["study"]
for k in ("g_dog_flip", "g2_dog_flip"):
    v = st.get(k) or {}
    print("   %-14s n=%-3s pending=%-3s roi=%s" % (k, v.get("n"), v.get("pending"), v.get("roi_pct")))
