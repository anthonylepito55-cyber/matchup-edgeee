"""P-75 and P-SETS backtests (2026-10-09, user: "back test p-75 and the other thing").

A) P-75: a match sim anchored 75% on Model P. simulate_match's anchor blends in PROBABILITY
   space (target = 0.75*anchor + 0.25*serve-sim, then small day-form noise); verified on
   the stored as-of sims that c75 == 0.75*C + 0.25*serve to 0.83pt mean error (97.7% same
   side of 50%). So P-75 = 0.75*P + 0.25*(as-of serve sim). 2026 (as-of sims exist).
   Compared on the SAME dogs: P's bets vs P-75's bets (EV >= 5%), by gender.

B) P-SETS: does P price the SET SCORE better than the market? For every best-of-3 match in
   P's out-of-sample universe (2024-26), turn a match prob into a set-score distribution
   (per-set prob s solved from m = s^2(3-2s); 2-0 = s^2, 2-1 = 2s^2(1-s), ...). Compare the
   P-anchored distribution with the market-anchored one on the REAL set scores (log loss),
   and check the +1.5 sets dog (dog wins at least one set) on P's bet matches. NOTE: the
   archive has no set-market PRICES, so this measures accuracy, not ROI; set ROI needs the
   live 🎲 Sets scanner's Polymarket prices.
"""
import numpy as np
import pandas as pd


def rep(won, dec, f=30):
    n = len(won)
    if n < f:
        return f"n={n} (thin)"
    w = int(np.sum(won))
    return f"{w}-{n-w} win {100*w/n:4.1f}% ROI {100*np.where(won, dec-1, -1).mean():+6.1f}% (n={n})"


O = pd.read_parquet("data_cache/_model_p250_oos.parquet")
R = pd.read_parquet("data_cache/_model_p250_rows.parquet")[["date", "player_slug", "rival_slugname", "rival_odd"]]
O = O.merge(R, on=["date", "player_slug", "rival_slugname"], how="left")
O = O[(O.G == "W") | (O.player_odd <= 3.0)].copy()

# ---------------- A) P-75 ----------------
S = pd.read_parquet("data_cache/_mc_asof_bt_rows.parquet").dropna(subset=["mc1_serve"])
S["d"] = pd.to_datetime(S.date).dt.normalize()
r2 = lambda x: np.round(x.astype(float), 2)
a = S.assign(k1=r2(S.oa), k2=r2(S.ob), srv=S.mc1_serve)
b = S.assign(k1=r2(S.ob), k2=r2(S.oa), srv=1 - S.mc1_serve)
SS = pd.concat([a, b])[["d", "k1", "k2", "srv"]].drop_duplicates(["d", "k1", "k2"])
A = O[O.yr == 2026].copy()
A["d"] = pd.to_datetime(A.date).dt.normalize()
A["k1"], A["k2"] = r2(A.player_odd), r2(A.rival_odd)
A = A.merge(SS, on=["d", "k1", "k2"], how="inner")
A["p75"] = 0.75 * A.pP + 0.25 * A.srv
A["p50"] = 0.50 * A.pP + 0.50 * A.srv
A["ev75"] = A.p75 * A.player_odd - 1
A["ev50"] = A.p50 * A.player_odd - 1
print(f"A) P-75 vs P, 2026 dogs in P's band joined to as-of serve sims: {len(A)}")
for G, gl in (("M", "MEN +100..+200"), ("W", "WOMEN +100..+250")):
    T = A[A.G == G]
    pb, b75, b50 = T.ev >= .05, T.ev75 >= .05, T.ev50 >= .05
    print(f"\n{gl}: every dog {rep(T.won.values, T.player_odd.values)}")
    print(f"   P bets (EV>=5%)             {rep(T[pb].won.values, T[pb].player_odd.values)}")
    print(f"   P-75 bets                   {rep(T[b75].won.values, T[b75].player_odd.values)}")
    print(f"   P-50 bets                   {rep(T[b50].won.values, T[b50].player_odd.values)}")
    print(f"   P bets that P-75 DROPS      {rep(T[pb & ~b75].won.values, T[pb & ~b75].player_odd.values)}")
    print(f"   P-75 bets that P doesn't    {rep(T[b75 & ~pb].won.values, T[b75 & ~pb].player_odd.values)}")
    ll = lambda p: -np.mean(np.where(T.won, np.log(np.clip(p, 1e-6, 1)), np.log(np.clip(1 - p, 1e-6, 1))))
    print(f"   log loss: market {ll(T.mkt):.4f} | P {ll(T.pP):.4f} | P-75 {ll(T.p75):.4f} | serve sim {ll(T.srv):.4f}")

# ---------------- B) P-SETS ----------------
ns = {}
src = open("_tennis_model_c_build.py", encoding="utf-8").read()
exec(compile(src.split("from sklearn.linear_model")[0], "_c_prep", "exec"), ns)
sc = ns["m"][["date", "player_slug", "rival_slugname", "score"]].drop_duplicates(["date", "player_slug", "rival_slugname"])
B = O.merge(sc, on=["date", "player_slug", "rival_slugname"], how="left")


def sets(score):
    try:
        w = l = 0
        for t in str(score).split():
            g = t.split("(")[0].split("-")
            x, y = int(g[0]), int(g[1])
            if x > y:
                w += 1
            elif y > x:
                l += 1
        return w, l
    except (ValueError, IndexError):
        return None


ss = B.score.map(sets)
B["sw"] = [x[0] if x else np.nan for x in ss]
B["sl"] = [x[1] if x else np.nan for x in ss]
B = B[B.sw.notna()].copy()
B = B[((B.sw == 2) & (B.sl <= 1)) | ((B.sl == 2) & (B.sw <= 1))]          # completed best-of-3
B = B[(B.sw == 2) == B.won.astype(bool)]                                 # orientation check
B["cls"] = np.select([(B.sw == 2) & (B.sl == 0), (B.sw == 2) & (B.sl == 1), (B.sw == 1) & (B.sl == 2)], [0, 1, 2], 3)


def s_from_m(m):
    m = np.clip(np.asarray(m, float), 1e-4, 1 - 1e-4)
    lo, hi = np.zeros_like(m), np.ones_like(m)
    for _ in range(50):
        mid = (lo + hi) / 2
        f = mid * mid * (3 - 2 * mid)
        lo = np.where(f < m, mid, lo)
        hi = np.where(f >= m, mid, hi)
    return (lo + hi) / 2


def dist(m):
    s = s_from_m(m)
    return np.column_stack([s * s, 2 * s * s * (1 - s), 2 * s * (1 - s) ** 2, (1 - s) ** 2])


print(f"\nB) SET SCORES, P's out-of-sample universe 2024-26, completed best-of-3 with a clean score: {len(B)}")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    T = B[B.G == G]
    y = T.cls.values.astype(int)
    for lab, m in (("market-anchored", T.mkt.values), ("P-anchored", T.pP.values)):
        Dm = dist(m)
        ll = -np.mean(np.log(np.clip(Dm[np.arange(len(y)), y], 1e-9, 1)))
        print(f"   {gl:5s} {lab:16s} set-score log loss {ll:.4f} | predicted dog wins >=1 set {100*(1-Dm[:,3]).mean():4.1f}% "
              f"| predicted dog 2-0 {100*Dm[:,0].mean():4.1f}%")
    print(f"   {gl:5s} ACTUAL: dog wins >=1 set {100*(y != 3).mean():4.1f}% | dog 2-0 {100*(y == 0).mean():4.1f}% | n={len(y)}")
    pb = T.ev.values >= .05
    yb = y[pb]
    Dm, Dp = dist(T.mkt.values[pb]), dist(T.pP.values[pb])
    print(f"   {gl:5s} on P's DOG BETS: dog wins >=1 set actual {100*(yb != 3).mean():4.1f}% | market-implied {100*(1-Dm[:,3]).mean():4.1f}% "
          f"| P-implied {100*(1-Dp[:,3]).mean():4.1f}% || dog 2-0 actual {100*(yb == 0).mean():4.1f}% | mkt {100*Dm[:,0].mean():4.1f}% | P {100*Dp[:,0].mean():4.1f}% (n={int(pb.sum())})")
