"""WHICH HALF OF MC2 CARRIES THE THIN-SIDE BIAS? (2026-10-13)

MC2/MC3 blend two independent halves in log-odds:

    p = sigmoid(0.5*logit(p_elo) + 0.5*logit(p_markov))

The measured defect is that both heads overrate whoever has the smaller sample, monotonically,
by up to +10pt at 10x asymmetry, while the market is flat to +/-0.75pt everywhere.

Two attempts to fix it by damping the MARKOV half's serve/return ratings toward the field (and
then toward a below-average prior) made the bias WORSE and cost Brier monotonically. That is
evidence the bias is not stored where I was reaching for it, so this stops fixing and measures:
the SAME thin-side error table computed on p_elo alone, p_markov alone, and the blend.

Whichever half shows the gradient is where any fix has to go. If BOTH show it, it is not a
parameter, it is the thing all three share -- the training population, i.e. a thin player's
record is accumulated against a weaker field than a thick player's, so the ratings are not on a
comparable scale and no amount of shrinking one fixes it.
"""
import numpy as np
import pandas as pd

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
ELO = F["p_elo"].to_numpy(float)
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


BLEND = 1 / (1 + np.exp(-(0.5 * lg(ELO) + 0.5 * lg(MK))))

thin_a = NA < NB
ratio = np.maximum(NA, NB) / np.maximum(np.minimum(NA, NB), 1.0)
won_thin = np.where(thin_a, WON, ~WON)
on_thin = lambda p: np.where(thin_a, p, 1 - p)

HEADS = [("p_elo", ELO), ("p_markov", MK), ("BLEND (=MC3)", BLEND), ("market", IMP)]
BUCKETS = [(1.0, 1.2), (1.2, 2.0), (2.0, 3.0), (3.0, 5.0), (5.0, 10.0), (10.0, 1e9)]
BAR = "=" * 96

print("\n" + BAR)
print("THIN-SIDE ERROR BY HALF  (positive = that half overrates the thinner-sampled player)")
print(BAR)
print("   %-14s %8s" % ("thick/thin", "n") + "".join("%14s" % h for h, _ in HEADS))
for lo, hi in BUCKETS:
    m = (ratio >= lo) & (ratio < hi)
    if m.sum() < 400:
        continue
    act = won_thin[m].mean()
    print("   %-14s %8d" % ("%.2gx-%.2gx" % (lo, hi), int(m.sum()))
          + "".join("%+13.2fpt" % (100 * (on_thin(p)[m].mean() - act)) for _, p in HEADS))

print("\n" + BAR)
print("IS IT THE OPPONENT POOL? the same gradient split by LEVEL of the match")
print("   if thin players are only mispriced because they played a weaker field, the gradient")
print("   should be much flatter inside a single level than across all of them")
print(BAR)
for lab, q in (("futures", LVL == 0), ("challenger", LVL == 1),
               ("tour", LVL == 2), ("slam", LVL == 3)):
    if q.sum() < 2000:
        continue
    print("   %s  (n=%d)" % (lab, int(q.sum())))
    for lo, hi in ((1.0, 2.0), (2.0, 5.0), (5.0, 1e9)):
        m = q & (ratio >= lo) & (ratio < hi)
        if m.sum() < 300:
            continue
        act = won_thin[m].mean()
        print("      %-12s n=%-6d" % ("%.2gx-%.2gx" % (lo, hi), int(m.sum()))
              + "".join("  %s %+6.2fpt" % (h, 100 * (on_thin(p)[m].mean() - act))
                        for h, p in HEADS))

print("\n" + BAR)
print("WHAT A THIN PLAYER'S RATING IS ACTUALLY BUILT ON -- are they rated too high, or is the")
print("rating fine and the UNCERTAINTY mispriced? Mean rating of thin vs thick side.")
print(BAR)
for lo, hi in BUCKETS:
    m = (ratio >= lo) & (ratio < hi)
    if m.sum() < 400:
        continue
    pt_thin = np.where(thin_a, PA, PB)[m]
    pt_thick = np.where(thin_a, PB, PA)[m]
    print("   %-14s n=%-6d thin point-prob %.4f  thick %.4f  gap %+.4f   thin wins %.1f%%"
          % ("%.2gx-%.2gx" % (lo, hi), int(m.sum()), pt_thin.mean(), pt_thick.mean(),
             pt_thin.mean() - pt_thick.mean(), 100 * won_thin[m].mean()))
