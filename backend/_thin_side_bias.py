"""DO MC2/MC3 OVERRATE THE THINNER-SAMPLED PLAYER? (2026-10-13)

User: "it seems to me like mc 2 and mc3 definitely over price games when someone has less game
meaning betteer stats", with two examples:

    Silva (career 19 matches, 6 on surface, 0 service points) vs Borg (83 / 57 / 281)
        market 24.3% on Silva    MC2 70.5%    MC3 66.9%    -> Borg won
    Wobker (37 / 6 / 40 svc pts) vs Bassols Ribera (153 / 75 / 367)
        MC2 favours Wobker at 55.2%

The mechanism is plausible: fewer matches means a noisier rate, and a noisy rate is as likely to
look GREAT as terrible -- but a player only reaches a board when something about them looks
good, so the thin side's stats are selected upward.

WHY THIS IS NOT THE n0 SWEEP I ALREADY REFUTED. This morning's sweep raised the global
shrinkage constant from 6 to 45 and Brier got monotonically worse, so I concluded more shrinkage
does not help. That measured the AVERAGE over 120,877 rows, where lopsided matchups are a
minority -- a global knob trades the asymmetric cases against the typical ones and can lose on
net while the asymmetric cases stay broken. This test looks only at the subset, which the
earlier one could not see.

MEASURED: the model's mean probability on the THIN side against that side's realised win rate,
bucketed by how lopsided the sample is. A positive error means the model overrates thin players.
The market is scored on the same rows, because the question that matters is not whether the
models err but whether they err WORSE than the price does.
"""
import numpy as np
import pandas as pd

COLS = ["year", "p_elo", "pa_pt", "pb_pt", "nS_a", "nS_b", "imp", "won", "surf"]
A = pd.read_parquet("data_cache/_mc2_features.parquet", columns=COLS)
B = pd.read_parquet("data_cache/_mc3_features.parquet", columns=COLS)
print("rows: mc2 %d, mc3 %d" % (len(A), len(B)))


def prep(F):
    F = F[F["imp"].notna() & F["won"].notna() & F["pa_pt"].notna() & F["pb_pt"].notna()
          & F["p_elo"].notna() & (F["nS_a"] >= 4) & (F["nS_b"] >= 4)].reset_index(drop=True)
    return F


A, B = prep(A), prep(B)
n = min(len(A), len(B))
A, B = A.iloc[:n], B.iloc[:n]

from _mc2_shrink_sweep import live_blend                           # noqa: E402

P2, _ = live_blend(A)
P3, _ = live_blend(B)
NA = A["nS_a"].to_numpy(float)
NB = A["nS_b"].to_numpy(float)
WON = A["won"].to_numpy(float).astype(bool)
IMP = A["imp"].to_numpy(float)
YR = A["year"].to_numpy()

# the THIN side is whoever has fewer serve-rated matches
thin_is_a = NA < NB
nthin = np.minimum(NA, NB)
nthick = np.maximum(NA, NB)
ratio = nthick / np.maximum(nthin, 1.0)


def on_thin(p):
    return np.where(thin_is_a, p, 1 - p)


won_thin = np.where(thin_is_a, WON, ~WON)
print("thin side wins overall: %.1f%% of %d" % (100 * won_thin.mean(), len(A)))

BUCKETS = [(1.0, 1.25), (1.25, 2.0), (2.0, 3.0), (3.0, 5.0), (5.0, 10.0), (10.0, 1e9)]
print("\n" + "=" * 104)
print("ERROR ON THE THIN SIDE, by how lopsided the sample is")
print("   positive = the model rates the thin player ABOVE what they actually win")
print("=" * 104)
print("   %-16s %8s %9s %9s %9s %9s" % ("thick/thin", "n", "MC2 err", "MC3 err",
                                        "market err", "thin win%"))
for lo, hi in BUCKETS:
    m = (ratio >= lo) & (ratio < hi)
    k = int(m.sum())
    if k < 400:
        continue
    act = won_thin[m].mean()
    e2 = on_thin(P2)[m].mean() - act
    e3 = on_thin(P3)[m].mean() - act
    em = on_thin(IMP)[m].mean() - act
    print("   %-16s %8d %+8.2fpt %+8.2fpt %+9.2fpt %8.1f%%"
          % ("%.2gx..%.2gx" % (lo, hi), k, 100 * e2, 100 * e3, 100 * em, 100 * act))

print("\n" + "=" * 104)
print("THE SAME, by the THIN side's absolute match count")
print("=" * 104)
print("   %-16s %8s %9s %9s %9s" % ("thin nS", "n", "MC2 err", "MC3 err", "market err"))
for lo, hi in [(4, 10), (10, 20), (20, 40), (40, 80), (80, 1e9)]:
    m = (nthin >= lo) & (nthin < hi)
    k = int(m.sum())
    if k < 400:
        continue
    act = won_thin[m].mean()
    print("   %-16s %8d %+8.2fpt %+8.2fpt %+9.2fpt"
          % ("%d-%d" % (lo, hi), k, 100 * (on_thin(P2)[m].mean() - act),
             100 * (on_thin(P3)[m].mean() - act), 100 * (on_thin(IMP)[m].mean() - act)))

print("\n" + "=" * 104)
print("WHERE IT COSTS MONEY -- backing the thin side when the model likes it MORE than the")
print("market does, which is exactly the Silva and Wobker shape")
print("=" * 104)
od_thin = np.where(thin_is_a,
                   1 / np.clip(IMP, 1e-6, 1), 1 / np.clip(1 - IMP, 1e-6, 1))
pnl_thin = np.where(won_thin, od_thin - 1, -1.0)      # at the DE-VIGGED price, so the
# number isolates the model error rather than mixing in the book's margin
for lab, lo in (("model over market by 5pt+", 0.05), ("10pt+", 0.10), ("20pt+", 0.20)):
    for nm, p in (("MC2", P2), ("MC3", P3)):
        m = (on_thin(p) - on_thin(IMP)) >= lo
        k = int(m.sum())
        if k < 200:
            continue
        print("   %-26s %-4s n=%-6d thin-side ROI at FAIR odds %+7.2f%%  (model %.1f%% vs market %.1f%%, actual %.1f%%)"
              % (lab, nm, k, 100 * pnl_thin[m].mean(), 100 * on_thin(p)[m].mean(),
                 100 * on_thin(IMP)[m].mean(), 100 * won_thin[m].mean()))

print("\n" + "=" * 104)
print("STABILITY -- the 3x+ lopsided bucket, by year")
print("=" * 104)
m0 = ratio >= 3.0
for y in (2024, 2025, 2026):
    m = m0 & (YR == y)
    if m.sum() < 200:
        continue
    act = won_thin[m].mean()
    print("   %d  n=%-6d MC2 %+6.2fpt  MC3 %+6.2fpt  market %+6.2fpt"
          % (y, int(m.sum()), 100 * (on_thin(P2)[m].mean() - act),
             100 * (on_thin(P3)[m].mean() - act), 100 * (on_thin(IMP)[m].mean() - act)))
