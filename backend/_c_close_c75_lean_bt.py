"""C CLOSE, c75 LEANS (2026-10-09, user: "what's the roi when C is close but c75 is leaning
one way"). C within +-3pt (and +-5pt) of 50%; c75 leaning >= 5pt / >= 10pt off 50%.
Bet c75's side. Split dog/fav x band x gender. Backtest 2026 (walk-forward C x as-of c75)
+ live frozen log."""
import numpy as np
import pandas as pd

def rep(won, dec, floor=40):
    n = len(won)
    if n < floor:
        return f"n={n} (thin)"
    w = int(np.sum(won))
    p = np.where(won, dec - 1, -1.0)
    return f"{w}-{n-w} win {100*w/n:4.1f}% ROI {100*p.mean():+6.1f}% (n={n})"

D = pd.read_parquet("data_cache/_season_2026_dossier_rows.parquet")
D = D[D.yr == 2026].copy()
S = pd.read_parquet("data_cache/_mc_asof_bt_rows.parquet").dropna(subset=["c75"])
S["d"] = pd.to_datetime(S.date).dt.normalize()
D["d"] = D.date.dt.normalize()
r2 = lambda x: np.round(x.astype(float), 2)
a = S.assign(k1=r2(S.oa), k2=r2(S.ob), s75=S.c75)
b = S.assign(k1=r2(S.ob), k2=r2(S.oa), s75=1 - S.c75)
SS = pd.concat([a, b])[["d", "k1", "k2", "s75"]].drop_duplicates(["d", "k1", "k2"])
D["k1"], D["k2"] = r2(D.player_odd), r2(D.rival_odd)
J = D.merge(SS, on=["d", "k1", "k2"], how="inner")
J = J[J.p_C.notna() & J.s75.notna()].copy()
# everything from the DOG row's perspective: c75 side
J["s_dog"] = J.s75 >= .5
J["swon"] = np.where(J.s_dog, J.won, ~J.won.astype(bool)).astype(bool)
J["sdec"] = np.where(J.s_dog, J.player_odd, J.rival_odd)
J["sam"] = np.where(J.sdec >= 2, (J.sdec - 1) * 100, -100 / (J.sdec - 1))
J["cgap"] = (J.p_C - 0.5).abs()
J["lean"] = (J.s75 - 0.5).abs()
J["c_with"] = (J.p_C >= .5) == J.s_dog          # C (barely) on the same side as c75
BANDS = [("dog +100..+200", 100, 200), ("dog +200 and up", 200.01, 1e9),
         ("fav -100..-200", -200, -100), ("fav -200 and shorter", -1e9, -200.01)]


def block(T, title):
    print(f"\n  {title}")
    print(f"     c75 on the DOG  {rep(T[T.s_dog].swon.values, T[T.s_dog].sdec.values)}")
    print(f"     c75 on the FAV  {rep(T[~T.s_dog].swon.values, T[~T.s_dog].sdec.values)}")
    for lab, lo, hi in BANDS:
        x = T[T.sam.between(lo, hi)]
        print(f"        {lab:22s} {rep(x.swon.values, x.sdec.values)}")


print(f"BACKTEST 2026 ({len(J)} matches) -- bet c75's side")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    T = J[J.G == G]
    print(f"\n==================== {gl} ====================")
    block(T[(T.cgap < 0.03) & (T.lean >= 0.05)], "C within 3pt of 50%, c75 leans 5pt+")
    block(T[(T.cgap < 0.03) & (T.lean >= 0.10)], "C within 3pt of 50%, c75 leans 10pt+")
    block(T[(T.cgap < 0.05) & (T.lean >= 0.05)], "C within 5pt of 50%, c75 leans 5pt+")
    X = T[(T.cgap < 0.05) & (T.lean >= 0.05)]
    print(f"     ...C barely WITH c75   {rep(X[X.c_with].swon.values, X[X.c_with].sdec.values)}")
    print(f"     ...C barely AGAINST c75 {rep(X[~X.c_with].swon.values, X[~X.c_with].sdec.values)}")
    block(T[(T.cgap >= 0.05)], "comparison: C NOT close (5pt+), bet c75's side")

L = pd.read_parquet("data_cache/_ec2_log_now.parquet")
L = L[L.p1_won.notna() & L.p1_odds.notna() & L.p2_odds.notna() & L.model_c_p1.notna() & L.mc_c75_p1.notna()]
rows = []
for r in L.itertuples():
    s1 = r.mc_c75_p1 >= .5
    o1, o2 = float(r.p1_odds), float(r.p2_odds)
    d1 = 1 + o1 / 100 if o1 > 0 else 1 + 100 / abs(o1)
    d2 = 1 + o2 / 100 if o2 > 0 else 1 + 100 / abs(o2)
    lg = str(r.league)
    rows.append({"G": "W" if ("wta" in lg or "itf_women" in lg) else "M", "am": o1 if s1 else o2,
                 "won": bool(r.p1_won) == s1, "dec": d1 if s1 else d2,
                 "cgap": abs(r.model_c_p1 - .5), "lean": abs(r.mc_c75_p1 - .5)})
R = pd.DataFrame(rows)
print(f"\n==================== LIVE {L.date.astype(str).min()[:10]}..{L.date.astype(str).max()[:10]} (bet c75's side) ====================")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    T = R[R.G == G]
    for lab, m in (("C within 3pt, c75 5pt+", (T.cgap < .03) & (T.lean >= .05)),
                   ("C within 5pt, c75 5pt+", (T.cgap < .05) & (T.lean >= .05))):
        x = T[m]
        print(f"  {gl} {lab:24s} dog {rep(x[x.am > 0].won.values, x[x.am > 0].dec.values, 15)} | fav {rep(x[x.am < 0].won.values, x[x.am < 0].dec.values, 15)}")
