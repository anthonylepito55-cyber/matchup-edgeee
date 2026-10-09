"""A/B/C 2-of-3 MAJORITY (2026-10-09, user: "if model a b and c 2/3 agree on a pick what's
the roi"). Bet the side 2 of the 3 back (3/3 shown for comparison), split by WHICH pair
agrees, dog vs favourite, price band, gender. Backtest = walk-forward dossier rows 2025-26
(one row per match, true gender, closing odds); live = frozen log."""
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
D = D[D[["p_A", "p_B", "p_C"]].notna().all(axis=1)].copy()
a, b, c = D.p_A >= .5, D.p_B >= .5, D.p_C >= .5          # True = on the dog
nd = a.astype(int) + b.astype(int) + c.astype(int)
D["maj_dog"] = nd >= 2
D["pair"] = np.select([nd.isin([0, 3]), a == b, a == c], ["3/3", "A+B (vs C)", "A+C (vs B)"], "B+C (vs A)")
D["mwon"] = np.where(D.maj_dog, D.won, ~D.won.astype(bool)).astype(bool)
D["mdec"] = np.where(D.maj_dog, D.player_odd, D.rival_odd)
D["mam"] = np.where(D.mdec >= 2, (D.mdec - 1) * 100, -100 / (D.mdec - 1))
BANDS = [("dog +100..+200", 100, 200), ("dog +200 and up", 200, 1e9),
         ("fav -100..-200", -200, -100), ("fav -200 and shorter", -1e9, -200)]
for yr in (2026, 2025):
    print(f"\n==================== BACKTEST {yr} ====================")
    for G, gl in (("M", "MEN"), ("W", "WOMEN")):
        T = D[(D.yr == yr) & (D.G == G)]
        two = T[T.pair != "3/3"]
        print(f"\n{gl}  any 2-of-3 majority pick      {rep(two.mwon.values, two.mdec.values)}")
        print(f"{gl}  all 3 agree (comparison)      {rep(T[T.pair == '3/3'].mwon.values, T[T.pair == '3/3'].mdec.values)}")
        for pr in ("A+B (vs C)", "A+C (vs B)", "B+C (vs A)"):
            s = T[T.pair == pr]
            print(f"   {pr}")
            for lab, lo, hi in BANDS:
                x = s[s.mam.between(lo, hi)]
                print(f"      {lab:22s} {rep(x.mwon.values, x.mdec.values)}")

L = pd.read_parquet("data_cache/_ec2_log_now.parquet")
L = L[L.p1_won.notna() & L.p1_odds.notna() & L.p2_odds.notna()
      & L.model_a_p1.notna() & L.model_b_p1.notna() & L.model_c_p1.notna()]
rows = []
for r in L.itertuples():
    a1, b1, c1 = r.model_a_p1 >= .5, r.model_b_p1 >= .5, r.model_c_p1 >= .5
    n1 = int(a1) + int(b1) + int(c1)
    side1 = n1 >= 2
    pair = "3/3" if n1 in (0, 3) else ("A+B (vs C)" if a1 == b1 else ("A+C (vs B)" if a1 == c1 else "B+C (vs A)"))
    od = float(r.p1_odds if side1 else r.p2_odds)
    lg = str(r.league)
    rows.append({"G": "W" if ("wta" in lg or "itf_women" in lg) else "M", "pair": pair, "am": od,
                 "won": bool(r.p1_won) == side1, "dec": 1 + od / 100 if od > 0 else 1 + 100 / abs(od)})
R = pd.DataFrame(rows)
print(f"\n==================== LIVE {L.date.astype(str).min()[:10]}..{L.date.astype(str).max()[:10]} ====================")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    T = R[R.G == G]
    two = T[T.pair != "3/3"]
    print(f"\n{gl}  any 2-of-3 majority pick      {rep(two.won.values, two.dec.values, 20)}")
    print(f"{gl}  all 3 agree                   {rep(T[T.pair == '3/3'].won.values, T[T.pair == '3/3'].dec.values, 20)}")
    for pr in ("A+B (vs C)", "A+C (vs B)", "B+C (vs A)"):
        s = T[T.pair == pr]
        print(f"   {pr}")
        for lab, lo, hi in BANDS:
            x = s[s.am.between(lo, hi)]
            print(f"      {lab:22s} {rep(x.won.values, x.dec.values, 20)}")
