"""THE LIVE SIDE of the C-picks-the-dog gap (2026-10-10, user "Yes").

The backtest says Model C's "prefer the market dog" rule returns +14.2% (2024-26, archive
closing odds). The live lane showed +2.85% on 156 settles. Before calling that a gap, two
things have to be established: the live number's ERROR BAR, and the live sample's COMPOSITION,
because the backtest universe is Futures-heavy while the board is tour + ITF on Polymarket
prices.
"""
import numpy as np
import pandas as pd

L = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
L["date"] = pd.to_datetime(L["date"], errors="coerce")


def dec(o):
    o = pd.to_numeric(o, errors="coerce").astype(float)
    return np.where(o > 0, 1 + o / 100.0, 1 + 100.0 / -o)


L["d1"], L["d2"] = dec(L.p1_odds), dec(L.p2_odds)
i1, i2 = 1 / L.d1, 1 / L.d2
L["mk1"] = i1 / (i1 + i2)
S = L[(L.settled == True) & L.p1_won.notna() & L.model_c_p1.notna() & L.mk1.notna()
      & (L.d1 > 1.005) & (L.d2 > 1.005)].copy()
S["dog1"] = S.mk1 < 0.5
S["c_pref_p1"] = S.model_c_p1 >= 0.5
# the rule: C prefers the market DOG
S["fires"] = S.c_pref_p1 == S.dog1
F = S[S.fires].copy()
F["dog_dec"] = np.where(F.dog1, F.d1, F.d2)
F["won"] = np.where(F.dog1, F.p1_won == 1, F.p1_won == 0)
F["lvl"] = F.league.astype(str).str.lower()
F["W"] = F.lvl.str.contains("women|wta")


def rep(s, lab, floor=20):
    n = len(s)
    if n < floor:
        print(f"   {lab:34s} n={n} (thin)")
        return
    w = s.won.astype(bool)
    pnl = np.where(w, s.dog_dec - 1, -1.0)
    roi = 100 * pnl.mean()
    se = 100 * pnl.std(ddof=1) / np.sqrt(n)
    print(f"   {lab:34s} {int(w.sum())}-{n - int(w.sum())}  hit {100 * w.mean():4.1f}%  "
          f"ROI {roi:+6.1f}% ± {se:.1f}  (n={n})")
    return roi, se, n


print(f"settled rows with C and prices: {len(S)}   C prefers the dog on {len(F)} "
      f"({100 * len(F) / len(S):.0f}%)")
print(f"date range {F.date.min().date()}..{F.date.max().date()}\n")
print("=" * 78)
print("LIVE: back the market dog whenever Model C prefers it")
print("=" * 78)
r = rep(F, "ALL")
print()
for lab, m in (("men", ~F.W), ("women", F.W)):
    rep(F[m], lab)
print()
for lab, m in (("ITF", F.lvl.str.contains("itf")), ("tour/other", ~F.lvl.str.contains("itf"))):
    rep(F[m], lab)
print()
print("   by dog price:")
for lo, hi in ((1.0, 2.0), (2.0, 2.5), (2.5, 3.5), (3.5, 5.0), (5.0, 99)):
    rep(F[(F.dog_dec >= lo) & (F.dog_dec < hi)], f"      dog {lo:.1f}-{hi:.1f} dec")
print()
print("   COMPOSITION, for matching against the backtest:")
print(f"      ITF share of live firings: {100 * F.lvl.str.contains('itf').mean():.0f}%")
print(f"      dog price: median {F.dog_dec.median():.2f}  "
      f"p25 {F.dog_dec.quantile(.25):.2f}  p75 {F.dog_dec.quantile(.75):.2f}")
print(f"      overround: mean {(1 / F.d1 + 1 / F.d2).mean():.4f}")
if r:
    roi, se, n = r
    print(f"\n   >>> the backtest claims +14.2%. Live is {roi:+.1f}% ± {se:.1f} on n={n},")
    print(f"       so the backtest sits {(14.2 - roi) / se:.1f} standard errors away.")
    print(f"       n needed to resolve a 11-point difference at 2 se: "
          f"~{int((2 * (se * np.sqrt(n)) / 11.3) ** 2)}")
