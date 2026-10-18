"""PHASE 2 step 4: re-evaluate the Phase 1 findings on the CORRECTED population, and quantify
what the contaminated rows alone were contributing. Also writes the lane-level metrics CSV
(avg odds + win rate + ROI +-2se where the lane records picks).

Populations:
  ELIGIBLE  settled, winner known, and NO ineligibility flag (the corrected basis)
  CONTAM    settled rows removed by the two NEW guards only (synthetic | poststart), net of rows
            an old flag already excluded -- i.e. exactly what the fix changed
Phase 1's "clean" population is reproduced for reconciliation (it lacked the 17 unparseable-
timestamp rows the strict guard now rejects, and the 1 vigged 'Polymarket' row).
"""
import math
import pandas as pd
import tennis_log as T

log = pd.read_parquet(T.LOG_PATH)


def f(c):
    return log[c].fillna(False).astype(bool) if c in log.columns else pd.Series(False, index=log.index)


def dec(a):
    a = float(a)
    return 1.0 + (a / 100.0 if a > 0 else 100.0 / -a)


settled = log["settled"].fillna(False).astype(bool) & log["p1_won"].notna()
oldbad = f("surface_bad") | f("inplay_suspect") | f("resolve_bad") | f("void")
newbad = f("price_synthetic") | f("price_poststart")
ELIG = settled & ~oldbad & ~newbad
CONTAM = settled & ~oldbad & newbad
print("settled %d | eligible %d | removed by the NEW guards alone %d | removed by old flags %d"
      % (settled.sum(), ELIG.sum(), CONTAM.sum(), (settled & oldbad).sum()))


def prep(df):
    df = df.copy()
    df["d1"] = [dec(a) for a in df["p1_odds"]]
    df["d2"] = [dec(a) for a in df["p2_odds"]]
    df["mk1"] = [(1 / a) / (1 / a + 1 / b) for a, b in zip(df["d1"], df["d2"])]
    df["y"] = df["p1_won"].astype(bool).astype(int)
    df["fav1"] = df["mk1"] >= 0.5
    df["lg"] = df["league"].astype(str)
    df["gender"] = ["W" if ("wta" in x or "itf_women" in x) else "M" for x in df["lg"]]
    return df


E, C = prep(log[ELIG]), prep(log[CONTAM])


def favstat(df, lab):
    if not len(df):
        return
    rr = [((r["d1"] if r["fav1"] else r["d2"]), (r["y"] == 1) == r["fav1"]) for _, r in df.iterrows()]
    n = len(rr)
    act = sum(w for _, w in rr) / n
    need = sum(1 / d for d, _ in rr) / n
    mk = df.apply(lambda r: max(r["mk1"], 1 - r["mk1"]), axis=1).mean()
    roi = sum((d - 1) if w else -1 for d, w in rr) / n
    print("   %-34s n=%-5d need %5.1f%%  mkt %5.1f%%  ACTUAL %5.1f%%  ROI %+7.2f%%"
          % (lab, n, 100 * need, 100 * mk, 100 * act, 100 * roi))


print("")
print("A. BLIND FAVOURITES -- corrected vs what the guards removed")
favstat(E, "ELIGIBLE (corrected)")
favstat(C, "CONTAMINATED (the removed rows)")
for g in ("M", "W"):
    favstat(E[E["gender"] == g], "eligible, gender %s" % g)
for lo, hi, lab in ((-150, -100, "-100..-150"), (-200, -150.001, "-151..-200")):
    m = E.apply(lambda r: lo <= (r["p1_odds"] if r["fav1"] else r["p2_odds"]) <= hi, axis=1)
    favstat(E[m], "eligible, fav %s" % lab)

print("")
print("B. WOMEN'S DOGS (the Phase 1 headroom claim)")
for df, lab in ((E, "ELIGIBLE"), (C, "CONTAM")):
    g = df[df["gender"] == "W"]
    if not len(g):
        continue
    rr = [((r["d2"] if r["fav1"] else r["d1"]), (r["y"] == 1) != r["fav1"]) for _, r in g.iterrows()]
    n = len(rr)
    roi = sum((d - 1) if w else -1 for d, w in rr) / n
    print("   %-10s n=%-5d win %5.1f%%  ROI %+7.2f%%" % (lab, n, 100 * sum(w for _, w in rr) / n, 100 * roi))

print("")
print("C. MODEL-SELECTED FAVOURITES 4pt+ (the anti-predictive finding), eligible rows only")
for h in ("model_c", "mc_c75", "mc2", "mc6", "model_a"):
    c, rc = h + "_p1", h + "_recon"
    m = E[c].notna()
    if rc in E.columns:
        m &= ~E[rc].fillna(False).astype(bool)
    g = E[m]
    rr = []
    for _, r in g.iterrows():
        hp = r[c] if r["fav1"] else 1 - r[c]
        mp = max(r["mk1"], 1 - r["mk1"])
        if hp - mp < 0.04:
            continue
        d = r["d1"] if r["fav1"] else r["d2"]
        rr.append((d, (r["y"] == 1) == r["fav1"], hp, mp))
    if len(rr) < 15:
        print("   %-9s n=%d (too few)" % (h, len(rr)))
        continue
    n = len(rr)
    print("   %-9s n=%-4d head %5.1f%%  mkt %5.1f%%  ACTUAL %5.1f%%  ROI %+7.2f%%"
          % (h, n, 100 * sum(x[2] for x in rr) / n, 100 * sum(x[3] for x in rr) / n,
             100 * sum(x[1] for x in rr) / n, 100 * sum(((x[0] - 1) if x[1] else -1) for x in rr) / n))

print("")
print("D. AUC ON IDENTICAL ELIGIBLE ROWS (market-free heads vs market)")


def auc(ps, ys):
    pairs = sorted(zip(ps, ys))
    npos = sum(ys)
    nneg = len(ys) - npos
    if not npos or not nneg:
        return float("nan")
    s_, i = 0.0, 0
    vals = [p for p, _ in pairs]
    rk = {}
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[j + 1] == vals[i]:
            j += 1
        for k in range(i, j + 1):
            rk[k] = (i + j) / 2.0 + 1
        i = j + 1
    for k, (_, y) in enumerate(pairs):
        if y:
            s_ += rk[k]
    return (s_ - npos * (npos + 1) / 2) / (npos * nneg)


for h in ("mc2", "mc6", "model_c", "model_a", "model_g2", "mc_c75"):
    c, rc = h + "_p1", h + "_recon"
    m = E[c].notna()
    if rc in E.columns:
        m &= ~E[rc].fillna(False).astype(bool)
    g = E[m]
    if len(g) < 100:
        continue
    print("   %-9s n=%-5d AUC %.4f | market %.4f" % (h, len(g), auc(list(g[c]), list(g["y"])), auc(list(g["mk1"]), list(g["y"]))))

# ---------------------------------------------------------------- lane metrics CSV
rec = T.get_ab25_record()
rows = []
for k, v in rec["study"].items():
    if not isinstance(v, dict):
        continue
    n, w = v.get("n") or 0, (v.get("wins") or 0)
    picks = [p for p in (v.get("picks") or []) if p.get("settled")]
    odds = [p["odds"] for p in picks if p.get("odds") is not None]
    avgd = (sum(dec(o) for o in odds) / len(odds)) if odds else None
    roi = (v.get("roi_pct") or 0) / 100 if n else None
    se = (math.sqrt(max((w / n) * (1 - w / n), 1e-9)) * (avgd or 2.0) / math.sqrt(n)) if n else None
    rows.append({"lane": k, "n": n, "wins": w, "win_rate": round(w / n, 4) if n else None,
                 "staked_usd": v.get("staked_usd"), "profit_usd": v.get("profit_usd"),
                 "roi_pct": v.get("roi_pct"), "pending": v.get("pending"),
                 "avg_decimal_odds": round(avgd, 3) if avgd else None,
                 "roi_2se_pct": round(200 * se, 2) if se else None,
                 "n_picks_recorded": len(picks)})
pd.DataFrame(rows).sort_values("n", ascending=False).to_csv("data_cache/phase2_lane_metrics.csv", index=False)
print("")
print("lane metrics CSV written: data_cache/phase2_lane_metrics.csv (%d lanes)" % len(rows))
