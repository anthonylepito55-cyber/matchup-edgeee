"""PHASE 1 AUDIT, part 4: the dog side of the decomposition, duplicated signals, contradictions,
and whether RECALIBRATION rescues the favourite selection.

Same clean forward population as part 3.
"""
import math
import pandas as pd
import tennis_log as T

HEADS = ["model_a", "model_b", "model_c", "model_d", "mc_c75", "model_g", "model_g2",
         "model_x", "mc2", "mc3", "mc5", "mc6"]

log = pd.read_parquet(T.LOG_PATH)


def flag(col):
    return log[col].fillna(False).astype(bool) if col in log.columns else pd.Series(False, index=log.index)


def dec(a):
    a = float(a)
    return 1.0 + (a / 100.0 if a > 0 else 100.0 / -a)


log["ovr"] = [1 / dec(a) + 1 / dec(b) for a, b in zip(log["p1_odds"], log["p2_odds"])]
_st = pd.to_datetime(log["start_time_utc"], errors="coerce", utc=True)
_lg = pd.to_datetime(log["logged_at"], errors="coerce", utc=True)
CLEAN = (~flag("surface_bad") & ~flag("resolve_bad") & ~flag("void") & ~flag("inplay_suspect")
         & (log["ovr"] > 1.0001) & ~((_lg > _st) & _st.notna() & _lg.notna())
         & log["settled"].fillna(False).astype(bool) & log["p1_won"].notna())
base = log[CLEAN].copy()
base["mk1"] = [(1 / dec(a)) / ((1 / dec(a)) + (1 / dec(b))) for a, b in zip(base["p1_odds"], base["p2_odds"])]
base["y"] = base["p1_won"].astype(bool).astype(int)
base["d1"] = [dec(a) for a in base["p1_odds"]]
base["d2"] = [dec(a) for a in base["p2_odds"]]
base["fav1"] = base["mk1"] >= 0.5
base["lg"] = base["league"].astype(str)
base["gender"] = ["W" if ("wta" in x or "itf_women" in x) else "M" for x in base["lg"]]

print("clean forward population: %d settled rows" % len(base))

# ---------------------------------------------------------------- 1. the DOG side decomposition
print("")
print("=" * 104)
print("1. THE DOG SIDE -- same decomposition as the favourites")
print("=" * 104)
print("   %-14s %6s %8s %8s %8s %9s" % ("segment", "n", "need%", "ACTUAL%", "mktpred%", "ROI"))


def dog_line(lab, sel):
    rr = []
    for _, r in sel.iterrows():
        dog1 = not r["fav1"]
        d = r["d1"] if dog1 else r["d2"]
        won = (r["y"] == 1) if dog1 else (r["y"] == 0)
        rr.append(dict(d=d, won=won, need=1 / d, mk=min(r["mk1"], 1 - r["mk1"])))
    if len(rr) < 20:
        return
    n = len(rr)
    print("   %-14s %6d %7.1f%% %7.1f%% %7.1f%% %+8.2f%%"
          % (lab, n, 100 * sum(x["need"] for x in rr) / n, 100 * sum(x["won"] for x in rr) / n,
             100 * sum(x["mk"] for x in rr) / n, 100 * sum((x["d"] - 1) if x["won"] else -1 for x in rr) / n))


dog_line("ALL dogs", base)
for g_ in ("M", "W"):
    dog_line("gender " + g_, base[base["gender"] == g_])
for lo, hi, lab in ((100, 150, "+100..+150"), (150.001, 200, "+151..+200"), (200.001, 300, "+201..+300"),
                    (300.001, 1e9, "above +300")):
    m = []
    for _, r in base.iterrows():
        do = r["p2_odds"] if r["fav1"] else r["p1_odds"]
        m.append(lo <= do <= hi)
    dog_line(lab, base[pd.Series(m, index=base.index)])

# ---------------------------------------------------------------- 2. duplicated signals
print("")
print("=" * 104)
print("2. DUPLICATED SIGNALS -- correlation of head probabilities (forward rows where both exist)")
print("=" * 104)
cols = [h + "_p1" for h in HEADS if h + "_p1" in base.columns]
sub = base[cols + ["mk1"]].astype(float)
cor = sub.corr()
names = [c[:-3] for c in cols] + ["market"]
print("   %-9s" % "" + "".join("%9s" % n[:8] for n in names))
for i, c in enumerate(cols + ["mk1"]):
    row = cor.loc[c]
    print("   %-9s" % names[i][:9] + "".join("%9.2f" % row[cc] for cc in cols + ["mk1"]))
print("")
print("   pairs correlated above 0.93 (effectively one signal):")
for i in range(len(cols)):
    for j in range(i + 1, len(cols)):
        v = cor.iloc[i, j]
        if v > 0.93:
            print("      %-10s ~ %-10s %.3f" % (names[i], names[j], v))

# ---------------------------------------------------------------- 3. contradictory predictions
print("")
print("=" * 104)
print("3. CONTRADICTIONS -- how often two live heads pick OPPOSITE winners on one card")
print("=" * 104)
pairs = [("mc2", "mc6"), ("mc2", "model_c"), ("model_c", "model_d"), ("model_a", "model_c"),
         ("mc6", "model_c"), ("mc6", "mc_c75"), ("model_g2", "mc6")]
for a, b in pairs:
    ca, cb = a + "_p1", b + "_p1"
    if ca not in base.columns or cb not in base.columns:
        continue
    g = base[base[ca].notna() & base[cb].notna()]
    opp = ((g[ca] > 0.5) & (g[cb] < 0.5)) | ((g[ca] < 0.5) & (g[cb] > 0.5))
    print("   %-10s vs %-10s n=%-5d opposite winners %5.1f%%" % (a, b, len(g), 100 * opp.mean()))

# ---------------------------------------------------------------- 4. recalibration test
print("")
print("=" * 104)
print("4. DOES RECALIBRATION RESCUE THE FAVOURITE SELECTION?")
print("=" * 104)
print("   Each head recalibrated on the FIRST HALF of its forward rows (Cox slope/intercept),")
print("   selection re-run on the SECOND HALF only -- an honest split, no reuse.")


def cox_fit(ps, ys):
    x = [math.log(min(max(p, 1e-6), 1 - 1e-6) / (1 - min(max(p, 1e-6), 1 - 1e-6))) for p in ps]
    a, b = 0.0, 1.0
    for _ in range(80):
        g = [1 / (1 + math.exp(-(a + b * xi))) for xi in x]
        g0 = sum(gi - yi for gi, yi in zip(g, ys))
        g1 = sum((gi - yi) * xi for gi, yi, xi in zip(g, ys, x))
        h00 = sum(gi * (1 - gi) for gi in g) + 1e-9
        h01 = sum(gi * (1 - gi) * xi for gi, xi in zip(g, x))
        h11 = sum(gi * (1 - gi) * xi * xi for gi, xi in zip(g, x)) + 1e-9
        det = h00 * h11 - h01 * h01
        if abs(det) < 1e-12:
            break
        a -= (h11 * g0 - h01 * g1) / det
        b -= (h00 * g1 - h01 * g0) / det
    return a, b


def recal(p, a, b):
    z = math.log(min(max(p, 1e-6), 1 - 1e-6) / (1 - min(max(p, 1e-6), 1 - 1e-6)))
    return 1 / (1 + math.exp(-(a + b * z)))


for h in ("model_c", "mc_c75", "model_a", "mc2"):
    c = h + "_p1"
    rcol = h + "_recon"
    m = base[c].notna() & ~flag(rcol).reindex(base.index).fillna(False)
    g = base[m].sort_values("date")
    if len(g) < 300:
        print("   %-9s too few rows (%d)" % (h, len(g)))
        continue
    half = len(g) // 2
    tr, te = g.iloc[:half], g.iloc[half:]
    a, b = cox_fit(list(tr[c]), list(tr["y"]))

    def favsel(df, use_recal):
        rr = []
        for _, r in df.iterrows():
            p1 = recal(r[c], a, b) if use_recal else r[c]
            fav1 = r["fav1"]
            hp = p1 if fav1 else 1 - p1
            mp = max(r["mk1"], 1 - r["mk1"])
            if hp - mp < 0.04:
                continue
            d = r["d1"] if fav1 else r["d2"]
            won = (r["y"] == 1) if fav1 else (r["y"] == 0)
            rr.append(((d - 1) if won else -1.0, won, 1 / d, hp, mp))
        return rr

    for lab, use in (("raw 4pt+", False), ("recal 4pt+", True)):
        rr = favsel(te, use)
        n = len(rr)
        if n < 8:
            print("   %-9s %-11s n=%d (selection nearly empty after recalibration)" % (h, lab, n))
            continue
        print("   %-9s %-11s n=%-4d head %5.1f%% mkt %5.1f%% ACTUAL %5.1f%% need %5.1f%% ROI %+7.2f%%  (slope %.2f int %.2f)"
              % (h, lab, n, 100 * sum(x[3] for x in rr) / n, 100 * sum(x[4] for x in rr) / n,
                 100 * sum(x[1] for x in rr) / n, 100 * sum(x[2] for x in rr) / n,
                 100 * sum(x[0] for x in rr) / n, b, a))

# ---------------------------------------------------------------- 5. post-match fields as inputs?
print("")
print("=" * 104)
print("5. POST-MATCH COLUMNS -- confirm nothing consumes them as a feature")
print("=" * 104)
post = ["ue_p1", "ue_fh_p1", "ue_set5_diff_p1", "df_p1", "aces_p1", "sgames_p1", "win_p1", "score"]
print("   post-match columns on the log: %s" % ", ".join(c for c in post if c in log.columns))
print("   (grep check runs locally -- see the report)")
