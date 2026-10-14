"""FIX THE THIN-SIDE BIAS: shrink a thin player's rating toward the surface baseline (2026-10-13).

MEASURED DEFECT (_thin_side_bias.py, 120,877 rows). MC2 and MC3 overrate whichever player has
the smaller sample, monotonically in how lopsided it is, while the market shows no such bias:

    thick/thin    MC2      MC3      market
    1x-1.2x     -0.47pt  -0.49pt   -0.75pt
    2x-3x       +3.49    +3.24     +0.31
    5x-10x      +7.52    +6.63     +0.58
    10x+       +10.00    +8.74     -0.12

Where the model likes the thin side by 10pt+ more than the market: model 46.6%, market 29.7%,
ACTUAL 29.2%. The market is right to half a point and the model is 17 points wrong.

WHY. `S += 0.8/(nS+6) * err` stops shrinking far too early -- the cumulative weight on
observations is already ~85% by 19 matches -- so a 6-surface-match serve number arrives almost
undamped. Per-surface ratings do not fix it and cannot: splitting by surface makes the thin side
THINNER (Silva is 19 career, 6 on hard).

THE FIX TESTED HERE. Leave the training pass alone and damp at READ time, by the player's own
sample size, toward the surface baseline (deviation zero):

    S_read = S_eff * nS/(nS + K)        R_read likewise

so a thin player's rating deviation is pulled toward the field rather than trusted. At K=20,
Silva's 19 matches keep 49% of their deviation and Borg's 83 keep 81%. K=0 is the current model
and must reproduce it.

WHY THIS IS NOT THE n0 SWEEP THAT FAILED THIS MORNING. That raised the TRAINING rate globally
and Brier worsened monotonically -- but it measured the average over all rows, where lopsided
matchups are a minority, so a single knob traded the asymmetric cases against the typical ones.
This damps at read time as a function of EACH SIDE's own n, so it can leave a 100-vs-100 matchup
untouched while fixing a 19-vs-83 one. Reported BOTH ways: on the lopsided subset, where it has
to work, and globally, where it must not do harm.
"""
import gc
import os
import sys

import numpy as np
import pandas as pd

from tennis_mc2 import _NODES, _rnd
from tennis_mc3 import p_match

FEAT = "data_cache/_mc3_features.parquet"
if not os.path.exists(FEAT):
    raise SystemExit("missing %s" % FEAT)

F = pd.read_parquet(FEAT, columns=["year", "p_elo", "pa_pt", "pb_pt", "nS_a", "nS_b",
                                   "S_a", "R_a", "S_b", "R_b",
                                   "imp", "won", "score", "surf"])
F = F[F["imp"].notna() & F["won"].notna() & F["pa_pt"].notna() & F["pb_pt"].notna()
      & F["p_elo"].notna() & (F["nS_a"] >= 4) & (F["nS_b"] >= 4)].reset_index(drop=True)
print("rows: %d" % len(F))

# the point probs are base + S_server - R_returner, so the DEVIATION from the surface base is
# what a thin-sample damp should shrink. The base is recovered as the sample mean of the pair,
# which is exact up to the pair's own average deviation and is the only handle the feature table
# gives -- the alternative is rebuilding, and this is a screening test.
PA = F["pa_pt"].to_numpy(float)
PB = F["pb_pt"].to_numpy(float)
SA = F["S_a"].to_numpy(float)
RA = F["R_a"].to_numpy(float)
SB = F["S_b"].to_numpy(float)
RB = F["R_b"].to_numpy(float)
# ATTEMPT 1 WAS STRUCTURALLY WRONG and is recorded so the mistake is not repeated: it damped
# pa_pt by A's sample size, but pa_pt = base + S_a - R_b MIXES THE TWO PLAYERS, so it shrank
# B's return contribution by A's count and vice versa. The result (the error getting worse with
# damping) measured that bug, not the idea.
# Done properly: recover the base per row, then damp EACH PLAYER'S OWN S and R by that player's
# own sample size before recomposing the point probabilities.
BASE_ROW = PA - SA + RB
BASE = float(np.median(BASE_ROW))
print("per-row base recovered: median %.4f, sd %.4f (should be near-constant per surface)"
      % (BASE, float(np.std(BASE_ROW))))
NA = F["nS_a"].to_numpy(float)
NB = F["nS_b"].to_numpy(float)
WON = F["won"].to_numpy(float).astype(bool)
IMP = F["imp"].to_numpy(float)
YR = F["year"].to_numpy()
ELO = F["p_elo"].to_numpy(float)
print("recovered surface base (mean point prob): %.4f" % BASE)


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


def lg(v):
    v = np.clip(v, 1e-6, 1 - 1e-6)
    return np.log(v / (1 - v))


LGE = lg(ELO)


# THE DIAGNOSIS INVERTED (attempt 3). Damping toward the base made the error WORSE, which
# revealed the real mechanism: in this builder a new player starts at S=0, which IS league
# average, and 0.8/(nS+6) has not moved them far after 19 matches -- so the model already treats
# a barely-seen player as average, while the market knows a player with 19 tracked matches is
# BELOW average. Damping toward the field pulls them further up, hence the backfire.
#
# So the prior is wrong, not the shrinkage. This shrinks a thin player's rating toward a
# NEGATIVE offset instead of zero: the less we have seen of someone, the worse we assume they
# are. PRIOR is in point-probability units, so -0.02 means "assume an unseen player is 2 points
# of serve-points-won below the field".
PRIOR = -0.02


def run(K):
    """Shrink each player's own S and R toward a BELOW-average prior, by their own sample size."""
    if K <= 0:
        pa, pb = PA, PB
    else:
        wa = NA / (NA + K)
        wb = NB / (NB + K)
        sa = SA * wa + PRIOR * (1 - wa)
        ra = RA * wa - PRIOR * (1 - wa)      # a weak player also returns worse
        sb = SB * wb + PRIOR * (1 - wb)
        rb = RB * wb - PRIOR * (1 - wb)
        pa = BASE_ROW + sa - rb
        pb = BASE_ROW + sb - ra
    pm = np.zeros(len(F))
    for xi, wi in _NODES:
        for xj, wj in _NODES:
            pm += wi * wj * np.array(
                [p_match(_rnd(x + xi * sa), _rnd(y + xj * sb), bool(f))
                 for x, y, sa, sb, f in zip(pa, pb, SGA, SGB, BO5)])
    return 1 / (1 + np.exp(-(0.5 * LGE + 0.5 * lg(pm))))


thin_a = NA < NB
nthin = np.minimum(NA, NB)
ratio = np.maximum(NA, NB) / np.maximum(nthin, 1.0)
won_thin = np.where(thin_a, WON, ~WON)
on_thin = lambda p: np.where(thin_a, p, 1 - p)

KS = [0, 5, 10, 20, 40, 80]
res = {}
for K in KS:
    res[K] = run(K)
    print("   scored K=%d" % K)
    gc.collect()

from sklearn.metrics import roc_auc_score                          # noqa: E402

BAR = "=" * 100
print("\n" + BAR)
print("THE DEFECT: error on the thin side, by lopsidedness. K=0 is the current model.")
print(BAR)
print("   %-12s" % "thick/thin" + "".join("%11s" % ("K=%d" % K) for K in KS) + "    market")
for lo, hi in ((1.0, 1.2), (1.2, 2.0), (2.0, 3.0), (3.0, 5.0), (5.0, 10.0), (10.0, 1e9)):
    m = (ratio >= lo) & (ratio < hi)
    if m.sum() < 400:
        continue
    act = won_thin[m].mean()
    row = "   %-12s" % ("%.2gx-%.2gx" % (lo, hi))
    for K in KS:
        row += "%+10.2fpt" % (100 * (on_thin(res[K])[m].mean() - act))
    row += "%+9.2fpt" % (100 * (on_thin(IMP)[m].mean() - act))
    print(row)

print("\n" + BAR)
print("THE COST: overall accuracy must not degrade. Market is AUC .7193 / Brier .2133")
print(BAR)
for K in KS:
    p = res[K]
    row = "   K=%-4d" % K
    for y in (2024, 2025, 2026):
        q = YR == y
        row += "   %d AUC %.4f Br %.4f" % (y, roc_auc_score(WON[q], p[q]),
                                           float(((p[q] - WON[q]) ** 2).mean()))
    row += "   ALL Br %.4f" % float(((p - WON) ** 2).mean())
    print(row)

print("\n" + BAR)
print("AND THE MONEY CASE: thin side where the model beats the market by 10pt+, at FAIR odds")
print(BAR)
od_thin = np.where(thin_a, 1 / np.clip(IMP, 1e-6, 1), 1 / np.clip(1 - IMP, 1e-6, 1))
pnl = np.where(won_thin, od_thin - 1, -1.0)
for K in KS:
    m = (on_thin(res[K]) - on_thin(IMP)) >= 0.10
    k = int(m.sum())
    if k < 100:
        print("   K=%-4d n=%-6d (too few -- the bias is gone at this K)" % (K, k))
        continue
    print("   K=%-4d n=%-6d ROI %+7.2f%%   model %5.1f%% vs market %5.1f%%, actual %5.1f%%"
          % (K, k, 100 * pnl[m].mean(), 100 * on_thin(res[K])[m].mean(),
             100 * on_thin(IMP)[m].mean(), 100 * won_thin[m].mean()))
