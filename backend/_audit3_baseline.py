"""PHASE 1 AUDIT, part 3: the BASELINE REPORT.

Per head: discrimination (hit%, AUC), sharpness/accuracy (Brier, logloss), CALIBRATION (decile
table + Cox slope/intercept on the logit), and the market on the SAME rows -- a head can only be
judged against the price it has to beat.

CLEAN population (used for every number unless stated): drops the rows part 1/2 showed are not
valid pre-match bets -- surface_bad, resolve_bad, void, inplay_suspect, overround<=1.0000
(de-vigged/synthetic price), and price logged after the start.
FORWARD only: a head's as-of RECONSTRUCTION rows are excluded from its own numbers, because the
rule/state was built after those matches.
"""
import math
import pandas as pd
import tennis_log as T

HEADS = ["model_a", "model_b", "model_c", "model_d", "model_cma", "mc_c", "mc_c75",
         "model_g", "model_g2", "model_x", "mc2", "mc3", "mc5", "mc6"]

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
print("rows %d -> clean settled %d (dropped %d)" % (len(log), CLEAN.sum(), len(log) - CLEAN.sum()))

base = log[CLEAN].copy()
base["mk1"] = [(1 / dec(a)) / ((1 / dec(a)) + (1 / dec(b))) for a, b in zip(base["p1_odds"], base["p2_odds"])]
base["y"] = base["p1_won"].astype(bool).astype(int)
base["d1"] = [dec(a) for a in base["p1_odds"]]
base["d2"] = [dec(a) for a in base["p2_odds"]]
base["fav1"] = base["mk1"] >= 0.5
base["favodds"] = [r["p1_odds"] if r["fav1"] else r["p2_odds"] for _, r in base.iterrows()]
base["dogodds"] = [r["p2_odds"] if r["fav1"] else r["p1_odds"] for _, r in base.iterrows()]
base["lg"] = base["league"].astype(str)
base["gender"] = ["W" if ("wta" in x or "itf_women" in x) else "M" for x in base["lg"]]
base["tour"] = ["TOUR" if x in ("atp", "wta") else ("CHALL" if x == "atp_challenger" else "ITF") for x in base["lg"]]
base["surf"] = base["surface"].astype(str)
base["wk"] = pd.to_datetime(base["date"].astype(str).str[:10]).dt.to_period("W").apply(lambda p: str(p.start_time)[5:10])


def auc(ps, ys):
    pairs = sorted(zip(ps, ys))
    npos = sum(ys)
    nneg = len(ys) - npos
    if not npos or not nneg:
        return float("nan")
    rank, i, s = {}, 0, 0.0
    # average ranks for ties
    vals = [p for p, _ in pairs]
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[j + 1] == vals[i]:
            j += 1
        r = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            rank[k] = r
        i = j + 1
    for k, (_, y) in enumerate(pairs):
        if y == 1:
            s += rank[k]
    return (s - npos * (npos + 1) / 2.0) / (npos * nneg)


def metrics(ps, ys):
    n = len(ps)
    ps = [min(max(p, 1e-6), 1 - 1e-6) for p in ps]
    hit = sum((p > 0.5) == (y == 1) for p, y in zip(ps, ys)) / n
    br = sum((p - y) ** 2 for p, y in zip(ps, ys)) / n
    ll = -sum(y * math.log(p) + (1 - y) * math.log(1 - p) for p, y in zip(ps, ys)) / n
    return hit, br, ll, auc(ps, ys)


def cox(ps, ys):
    """logistic recalibration: y ~ a + b*logit(p). b<1 = overconfident, a!=0 = biased."""
    x = [math.log(min(max(p, 1e-6), 1 - 1e-6) / (1 - min(max(p, 1e-6), 1 - 1e-6))) for p in ps]
    a, b = 0.0, 1.0
    for _ in range(60):
        g = [1 / (1 + math.exp(-(a + b * xi))) for xi in x]
        g0 = sum(gi - yi for gi, yi in zip(g, ys))
        g1 = sum((gi - yi) * xi for gi, yi, xi in zip(g, ys, x))
        h00 = sum(gi * (1 - gi) for gi in g) + 1e-9
        h01 = sum(gi * (1 - gi) * xi for gi, xi in zip(g, x))
        h11 = sum(gi * (1 - gi) * xi * xi for gi, xi in zip(g, x)) + 1e-9
        det = h00 * h11 - h01 * h01
        if abs(det) < 1e-12:
            break
        da = (h11 * g0 - h01 * g1) / det
        db = (h00 * g1 - h01 * g0) / det
        a -= da
        b -= db
        if abs(da) + abs(db) < 1e-10:
            break
    return a, b


def col(h):
    return h + "_p1"


def rc(h):
    return h + "_recon"


print("")
print("=" * 108)
print("A. ACCURACY AND CALIBRATION, forward rows, clean population")
print("=" * 108)
print("   %-10s %6s %7s %8s %8s %7s | %-28s | %s"
      % ("head", "n", "hit%", "Brier", "logloss", "AUC", "market on the same rows", "calib slope/intercept"))
summary = {}
for h in HEADS:
    c = col(h)
    if c not in base.columns:
        continue
    m = base[c].notna() & ~flag(rc(h)).reindex(base.index).fillna(False)
    g = base[m]
    if len(g) < 60:
        print("   %-10s n=%d  (too few forward rows to report)" % (h, len(g)))
        continue
    ps, ys = list(g[c].astype(float)), list(g["y"])
    hit, br, ll, au = metrics(ps, ys)
    mh, mb, ml, ma = metrics(list(g["mk1"]), ys)
    a, b = cox(ps, ys)
    summary[h] = dict(n=len(g), hit=hit, br=br, ll=ll, auc=au, mbr=mb, mauc=ma, slope=b, inter=a)
    print("   %-10s %6d %7.1f %8.4f %8.4f %7.4f | hit %5.1f Brier %.4f AUC %.4f | slope %5.2f  int %+5.2f"
          % (h, len(g), 100 * hit, br, ll, au, 100 * mh, mb, ma, b, a))
print("")
print("   slope < 1.00 = OVERCONFIDENT (probabilities too extreme); > 1.00 = underconfident.")
print("   Brier/AUC worse than the market column means the head does not out-predict the price.")

print("")
print("=" * 108)
print("B. CALIBRATION DECILES -- predicted vs actual (the 80%-should-win-80% test)")
print("=" * 108)
for h in ("mc6", "mc2", "model_c", "model_a"):
    c = col(h)
    if c not in base.columns:
        continue
    m = base[c].notna() & ~flag(rc(h)).reindex(base.index).fillna(False)
    g = base[m]
    if len(g) < 100:
        continue
    print("   %s (n=%d)   market shown for the same rows" % (h.upper(), len(g)))
    print("      %-12s %6s %9s %9s %9s %9s" % ("bucket", "n", "pred", "ACTUAL", "gap", "mkt pred"))
    for lo in [i / 10 for i in range(10)]:
        hi = lo + 0.1
        b2 = g[(g[c] >= lo) & (g[c] < hi)] if hi < 1 else g[(g[c] >= lo) & (g[c] <= 1.0)]
        if len(b2) < 15:
            continue
        pr, ac, mp = b2[c].mean(), b2["y"].mean(), b2["mk1"].mean()
        print("      %.1f-%.1f      %6d %8.1f%% %8.1f%% %+8.1fpt %8.1f%%"
              % (lo, hi, len(b2), 100 * pr, 100 * ac, 100 * (pr - ac), 100 * mp))
    print("")

print("=" * 108)
print("C. WHY FAVOURITE BETS LOSE -- is it the winner pick or the price?")
print("=" * 108)
print("   For the FAVOURITE side only. 'need' = win rate required to break even at that price.")
print("   %-14s %6s %8s %8s %8s %9s %9s" % ("segment", "n", "need%", "ACTUAL%", "mktpred%", "ROI", "edge vs need"))


def fav_rows(sel):
    out = []
    for _, r in sel.iterrows():
        fav1 = r["fav1"]
        d = r["d1"] if fav1 else r["d2"]
        won = (r["y"] == 1) if fav1 else (r["y"] == 0)
        out.append(dict(d=d, won=won, need=1.0 / d, mk=max(r["mk1"], 1 - r["mk1"]),
                        odds=r["favodds"], lg=r["lg"], gender=r["gender"], tour=r["tour"],
                        surf=r["surf"], wk=r["wk"]))
    return out


def fav_line(lab, rr):
    if len(rr) < 20:
        return
    n = len(rr)
    act = sum(x["won"] for x in rr) / n
    need = sum(x["need"] for x in rr) / n
    mk = sum(x["mk"] for x in rr) / n
    roi = sum((x["d"] - 1) if x["won"] else -1.0 for x in rr) / n
    print("   %-14s %6d %7.1f%% %7.1f%% %7.1f%% %+8.2f%% %+8.1fpt"
          % (lab, n, 100 * need, 100 * act, 100 * mk, 100 * roi, 100 * (act - need)))


allf = fav_rows(base)
fav_line("ALL favourites", allf)
for g_ in ("M", "W"):
    fav_line("gender " + g_, [x for x in allf if x["gender"] == g_])
for t in ("TOUR", "CHALL", "ITF"):
    fav_line("tour " + t, [x for x in allf if x["tour"] == t])
for lgv in sorted(base["lg"].unique()):
    fav_line("league " + lgv[:8], [x for x in allf if x["lg"] == lgv])
for sv in sorted(base["surf"].unique()):
    fav_line("surface " + sv[:7], [x for x in allf if x["surf"] == sv])
for lo, hi, lab in ((-150, -100, "-100..-150"), (-200, -150.001, "-151..-200"), (-300, -200.001, "-201..-300"),
                    (-500, -300.001, "-301..-500"), (-1e9, -500.001, "below -500")):
    fav_line(lab, [x for x in allf if lo <= x["odds"] <= hi])
for wk in sorted(base["wk"].unique()):
    fav_line("week " + wk, [x for x in allf if x["wk"] == wk])

print("")
print("   DECOMPOSITION -- favourites the HEAD rates above the de-vigged market:")
print("   %-22s %6s %8s %8s %8s %8s %9s" % ("head / selection", "n", "head%", "mkt%", "ACTUAL%", "need%", "ROI"))
for h in ("mc6", "mc2", "model_c", "model_a", "mc_c75"):
    c = col(h)
    if c not in base.columns:
        continue
    m = base[c].notna() & ~flag(rc(h)).reindex(base.index).fillna(False)
    g = base[m]
    for lab, cond in (("over market", lambda hp, mp: hp > mp), ("over by 4pt+", lambda hp, mp: hp - mp >= 0.04)):
        rr, hp_, mp_ = [], [], []
        for _, r in g.iterrows():
            fav1 = r["fav1"]
            hp = r[c] if fav1 else 1 - r[c]
            mp = max(r["mk1"], 1 - r["mk1"])
            if not cond(hp, mp):
                continue
            d = r["d1"] if fav1 else r["d2"]
            won = (r["y"] == 1) if fav1 else (r["y"] == 0)
            rr.append(dict(d=d, won=won, need=1 / d))
            hp_.append(hp)
            mp_.append(mp)
        if len(rr) < 20:
            continue
        n = len(rr)
        print("   %-22s %6d %7.1f%% %7.1f%% %7.1f%% %7.1f%% %+8.2f%%"
              % ("%s %s" % (h, lab), n, 100 * sum(hp_) / n, 100 * sum(mp_) / n,
                 100 * sum(x["won"] for x in rr) / n, 100 * sum(x["need"] for x in rr) / n,
                 100 * sum((x["d"] - 1) if x["won"] else -1.0 for x in rr) / n))
