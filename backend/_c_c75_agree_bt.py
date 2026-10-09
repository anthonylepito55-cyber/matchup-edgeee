"""MODEL C + c75 AGREE (2026-10-09, user: "what if model c and mc c75 agree"). Bet the side
both back, split dog/fav x price band x gender; also C-vs-c75 disagreements for contrast.
Backtest 2026 = walk-forward C joined to as-of c75 sims (production simulate_match on as-of
profiles); live = frozen log."""
import numpy as np
import pandas as pd

def rep(won, dec, floor=40):
    n = len(won)
    if n < floor:
        return f"n={n} (thin)"
    w = int(np.sum(won))
    p = np.where(won, dec - 1, -1.0)
    return f"{w}-{n-w} win {100*w/n:4.1f}% ROI {100*p.mean():+6.1f}% (n={n})"

BANDS = [("dog +100..+200", 100, 200), ("dog +200..+300", 200.01, 300), ("dog +300 and up", 300.01, 1e9),
         ("fav -100..-150", -150, -100), ("fav -150..-200", -200, -150.01), ("fav -200..-300", -300, -200.01),
         ("fav -300 and shorter", -1e9, -300.01)]

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
cD, sD = J.p_C >= .5, J.s75 >= .5                     # True = on the dog
J["agree"] = cD == sD
J["on_dog"] = cD                                       # side when they agree (C's side)
J["pwon"] = np.where(J.on_dog, J.won, ~J.won.astype(bool)).astype(bool)
J["pdec"] = np.where(J.on_dog, J.player_odd, J.rival_odd)
J["pam"] = np.where(J.pdec >= 2, (J.pdec - 1) * 100, -100 / (J.pdec - 1))
print(f"BACKTEST 2026: {len(J)} matches with C + as-of c75")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    T = J[J.G == G]
    A = T[T.agree]
    print(f"\n{gl}: C and c75 AGREE on {100*len(A)/len(T):.0f}% of matches")
    print(f"   any agreed pick          {rep(A.pwon.values, A.pdec.values)}")
    print(f"   agreed on the DOG        {rep(A[A.on_dog].pwon.values, A[A.on_dog].pdec.values)}")
    print(f"   agreed on the FAV        {rep(A[~A.on_dog].pwon.values, A[~A.on_dog].pdec.values)}")
    for lab, lo, hi in BANDS:
        x = A[A.pam.between(lo, hi)]
        print(f"      {lab:22s} {rep(x.pwon.values, x.pdec.values)}")
    X = T[~T.agree]
    # disagreement: back c75's side
    xw = np.where(X.s75 >= .5, X.won, ~X.won.astype(bool)).astype(bool)
    xd = np.where(X.s75 >= .5, X.player_odd, X.rival_odd)
    xdog = (X.s75 >= .5).values
    print(f"   DISAGREE, back c75 side: dog {rep(xw[xdog], xd[xdog])} | fav {rep(xw[~xdog], xd[~xdog])}")
    print(f"   DISAGREE, back C side:   dog {rep(~xw[~xdog], X.player_odd.values[~xdog])} | fav {rep(~xw[xdog], X.rival_odd.values[xdog])}")

L = pd.read_parquet("data_cache/_ec2_log_now.parquet")
L = L[L.p1_won.notna() & L.p1_odds.notna() & L.p2_odds.notna() & L.model_c_p1.notna() & L.mc_c75_p1.notna()]
rows = []
for r in L.itertuples():
    c1, s1 = r.model_c_p1 >= .5, r.mc_c75_p1 >= .5
    if c1 != s1:
        continue
    o1, o2 = float(r.p1_odds), float(r.p2_odds)
    d1 = 1 + o1 / 100 if o1 > 0 else 1 + 100 / abs(o1)
    d2 = 1 + o2 / 100 if o2 > 0 else 1 + 100 / abs(o2)
    am = o1 if c1 else o2
    lg = str(r.league)
    rows.append({"G": "W" if ("wta" in lg or "itf_women" in lg) else "M", "am": am,
                 "won": bool(r.p1_won) == c1, "dec": d1 if c1 else d2})
R = pd.DataFrame(rows)
print(f"\nLIVE {L.date.astype(str).min()[:10]}..{L.date.astype(str).max()[:10]}: C + c75 agree")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    T = R[R.G == G]
    print(f"\n{gl}: any agreed pick {rep(T.won.values, T.dec.values, 20)}")
    print(f"   on the DOG {rep(T[T.am > 0].won.values, T[T.am > 0].dec.values, 20)} | on the FAV {rep(T[T.am < 0].won.values, T[T.am < 0].dec.values, 20)}")
    for lab, lo, hi in BANDS:
        x = T[T.am.between(lo, hi)]
        print(f"      {lab:22s} {rep(x.won.values, x.dec.values, 20)}")
