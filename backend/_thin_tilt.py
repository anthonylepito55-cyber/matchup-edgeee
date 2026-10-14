"""THE ACTUAL FIX: tilt the finished blend AWAY from the thinner-sampled side (2026-10-13).

THE DIAGNOSIS, from _thin_which_half.py. Both halves carry the bias in equal measure
(+8.09pt Elo / +9.64pt Markov at 10x asymmetry) and it is present inside EVERY level, so it is
not a parameter in either half and not an artifact of thin players meeting a weaker field. The
decisive table is the rating gap: the model already rates the thin player BELOW the thick one and
the gap widens correctly with asymmetry (-0.0020 at 1x -> -0.0188 at 10x), it is simply far too
SMALL -- a -0.019 point-prob gap prices the thin side near 41% where they actually win 32.2%.

WHY it is structural rather than a bug: Elo starts every player at the population mean and the
serve/return deviations start at zero, both converging toward truth as n grows. A player with few
matches is therefore PINNED too close to average by construction. The model's skill estimate is
shrunk toward the field; the market's is not. That is why two attempts to shrink HARDER made the
error worse and cost Brier monotonically -- they pushed in the direction the defect already goes.

THE FIX. Leave both halves alone and correct the finished probability, as a function of how
lopsided the samples are, toward the better-known player:

    z' = z - LAM * log10(thick_n / thin_n) * (+1 if the thin side is player 1 else -1)

One parameter, monotone in the asymmetry, zero at 1x (log10(1) = 0) so symmetric matchups are
untouched -- which is most of the board. LAM = 0 must reproduce MC3 exactly.

Judged on three things, and it ships only if all three hold:
  1. the thin-side error table FLATTENS toward the market's +/-0.75pt
  2. AUC and Brier do not degrade in any of 2024, 2025, 2026
  3. the money case -- backing the thin side where the model beats the price by 10pt+, which is
     the Silva and Wobker shape -- loses its volume or stops being a loser

Also reported: a per-LEVEL fit, because the gradient's slope differed by level (futures ran
steeper than challenger), and a two-parameter version with its own slope above 3x in case the
relationship is not linear in log(ratio).
"""
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from tennis_mc2 import _NODES, _rnd
from tennis_mc3 import p_match

F = pd.read_parquet("data_cache/_mc3_features.parquet",
                    columns=["year", "p_elo", "pa_pt", "pb_pt", "nS_a", "nS_b",
                             "imp", "won", "score", "lvlg"])
F = F[F["imp"].notna() & F["won"].notna() & F["pa_pt"].notna() & F["pb_pt"].notna()
      & F["p_elo"].notna() & (F["nS_a"] >= 4) & (F["nS_b"] >= 4)].reset_index(drop=True)
print("rows: %d" % len(F))

PA, PB = F["pa_pt"].to_numpy(float), F["pb_pt"].to_numpy(float)
NA, NB = F["nS_a"].to_numpy(float), F["nS_b"].to_numpy(float)
WON = F["won"].to_numpy(float).astype(bool)
IMP = F["imp"].to_numpy(float)
YR = F["year"].to_numpy()
LVL = pd.to_numeric(F["lvlg"], errors="coerce").fillna(-1).to_numpy(float)


def sets_won(s):
    if not isinstance(s, str) or not s.strip():
        return 0
    x = y = 0
    for tok in s.split():
        t = tok.split("(")[0]
        if "-" not in t:
            continue
        u, _, v = t.partition("-")
        try:
            u, v = int(u), int(v)
        except ValueError:
            continue
        if u > v:
            x += 1
        elif v > u:
            y += 1
    return max(x, y)


BO5 = np.array([sets_won(s) >= 3 for s in F["score"]])
SGA = 0.10 / np.sqrt(np.maximum(NA, 4.0))
SGB = 0.10 / np.sqrt(np.maximum(NB, 4.0))
MK = np.zeros(len(F))
for xi, wi in _NODES:
    for xj, wj in _NODES:
        MK += wi * wj * np.array([p_match(_rnd(x + xi * a), _rnd(y + xj * b), bool(f))
                                  for x, y, a, b, f in zip(PA, PB, SGA, SGB, BO5)])


def lg(v):
    v = np.clip(v, 1e-6, 1 - 1e-6)
    return np.log(v / (1 - v))


Z0 = 0.5 * lg(F["p_elo"].to_numpy(float)) + 0.5 * lg(MK)

thin_a = NA < NB
nthin = np.minimum(NA, NB)
ratio = np.maximum(NA, NB) / np.maximum(nthin, 1.0)
LR = np.log10(np.maximum(ratio, 1.0))
SGN = np.where(thin_a, 1.0, -1.0)           # +1 when the THIN side is player 1
won_thin = np.where(thin_a, WON, ~WON)


def on_thin(p):
    return np.where(thin_a, p, 1 - p)


print("log10(ratio): median %.3f  p90 %.3f  max %.3f   rows above 1x: %.1f%%"
      % (np.median(LR), np.percentile(LR, 90), LR.max(), 100 * (LR > 0.01).mean()))


def tilt(lam, lam_hi=None, knee=0.477):      # knee = log10(3)
    """Push probability away from the thin side, by the log of the sample asymmetry."""
    if lam_hi is None:
        adj = lam * LR
    else:
        adj = lam * np.minimum(LR, knee) + lam_hi * np.maximum(LR - knee, 0.0)
    return 1 / (1 + np.exp(-(Z0 - adj * SGN)))


BUCKETS = [(1.0, 1.2), (1.2, 2.0), (2.0, 3.0), (3.0, 5.0), (5.0, 10.0), (10.0, 1e9)]
BAR = "=" * 104
LAMS = [0.0, 0.10, 0.20, 0.30, 0.40, 0.60]
RES = {l: tilt(l) for l in LAMS}

print("\n" + BAR)
print("1. DOES THE BIAS FLATTEN? thin-side error by lopsidedness. LAM=0 is MC3 as it ships.")
print(BAR)
print("   %-13s %7s" % ("thick/thin", "n") + "".join("%11s" % ("L=%.2f" % l) for l in LAMS)
      + "    market")
for lo, hi in BUCKETS:
    m = (ratio >= lo) & (ratio < hi)
    if m.sum() < 400:
        continue
    act = won_thin[m].mean()
    print("   %-13s %7d" % ("%.2gx-%.2gx" % (lo, hi), int(m.sum()))
          + "".join("%+10.2fpt" % (100 * (on_thin(RES[l])[m].mean() - act)) for l in LAMS)
          + "%+9.2fpt" % (100 * (on_thin(IMP)[m].mean() - act)))

print("\n" + BAR)
print("2. WHAT DOES IT COST? overall accuracy. Market is AUC .7193 / Brier .2133")
print(BAR)
for l in LAMS:
    p = RES[l]
    row = "   L=%-5.2f" % l
    for y in (2024, 2025, 2026):
        q = YR == y
        row += "  %d AUC %.4f Br %.4f" % (y, roc_auc_score(WON[q], p[q]),
                                          float(((p[q] - WON[q]) ** 2).mean()))
    row += "   ALL Br %.4f" % float(((p - WON) ** 2).mean())
    print(row + ("   <-- SHIPPED" if l == 0 else ""))

print("\n" + BAR)
print("3. THE MONEY CASE -- thin side where the model beats the market by 10pt+, at FAIR odds")
print(BAR)
od_thin = np.where(thin_a, 1 / np.clip(IMP, 1e-6, 1), 1 / np.clip(1 - IMP, 1e-6, 1))
pnl = np.where(won_thin, od_thin - 1, -1.0)
for l in LAMS:
    m = (on_thin(RES[l]) - on_thin(IMP)) >= 0.10
    k = int(m.sum())
    if k < 100:
        print("   L=%-5.2f n=%-6d  the bias is gone at this lambda" % (l, k))
        continue
    print("   L=%-5.2f n=%-6d ROI %+7.2f%%   model %5.1f%% vs market %5.1f%%, actual %5.1f%%"
          % (l, k, 100 * pnl[m].mean(), 100 * on_thin(RES[l])[m].mean(),
             100 * on_thin(IMP)[m].mean(), 100 * won_thin[m].mean()))

print("\n" + BAR)
print("4. IS ONE SLOPE ENOUGH? a second slope above 3x, in case it is not linear in log(ratio)")
print(BAR)
for lo, hi in ((0.20, 0.20), (0.20, 0.40), (0.20, 0.60), (0.30, 0.50), (0.10, 0.40)):
    p = tilt(lo, hi)
    row = "   lo=%.2f hi=%.2f  ALL Br %.4f" % (lo, hi, float(((p - WON) ** 2).mean()))
    for a, b in ((2.0, 5.0), (5.0, 1e9)):
        m = (ratio >= a) & (ratio < b)
        row += "   %.2gx-%.2gx err %+6.2fpt" % (
            a, b, 100 * (on_thin(p)[m].mean() - won_thin[m].mean()))
    print(row)

print("\n" + BAR)
print("5. PER-LEVEL -- the gradient ran steeper at futures than challenger, so check one global")
print("   lambda is not fixing one level by breaking another")
print(BAR)
for lab, q in (("futures", LVL == 0), ("challenger", LVL == 1),
               ("tour", LVL == 2), ("slam", LVL == 3)):
    if q.sum() < 2000:
        continue
    row = "   %-11s n=%-6d" % (lab, int(q.sum()))
    for l in (0.0, 0.20, 0.30):
        p = RES[l]
        row += "   L=%.2f Br %.4f" % (l, float(((p[q] - WON[q]) ** 2).mean()))
        m = q & (ratio >= 3.0)
        row += " (3x+ err %+5.2fpt)" % (100 * (on_thin(p)[m].mean() - won_thin[m].mean()))
    print(row)
