"""DOES THE ABANDONED-MATCH GUARD HELP MC3? (2026-10-13)

9,011 matches (1.46%) in TennisRatio end with nobody reaching 2 sets, and 4,389 of those still
carry a serve stat line -- a serve rate off a handful of games, fed into the ratings at full
weight. The builder's own is_ret() matches 0 of 616,725 rows because this source has no "ret" or
"w/o" strings, so they were entirely invisible.

The guard skips the serve/return rating update and the surface-baseline update for those matches
while KEEPING the Elo update, because an abandoned match still has a real winner.

Scored the same way everything else today was: MC3's live-equivalent blend (per-surface point
probs, sigma integration, best-of-five from the score, 50/50 log-odds Elo blend) on the rows
BOTH builds priced, so the comparison is paired rather than two different samples.

Pre-guard features were backed up to /tmp before the rebuild.
"""
import math
import os
from functools import lru_cache

import numpy as np
import pandas as pd

from tennis_mc2 import _NODES, _rnd
from tennis_mc3 import p_match

OLD = "/tmp/_mc3_features_preaband.parquet"
NEW = "data_cache/_mc3_features.parquet"
for p in (OLD, NEW):
    if not os.path.exists(p):
        raise SystemExit("missing %s" % p)


@lru_cache(maxsize=2000000)
def _pm(pa, pb, bo5):
    return p_match(pa, pb, bo5)


def sets_won(score):
    if not isinstance(score, str) or not score.strip():
        return None, None
    a = b = 0
    for tok in score.split():
        t = tok.split("(")[0]
        if "-" not in t:
            continue
        x, _, y = t.partition("-")
        try:
            x, y = int(x), int(y)
        except ValueError:
            continue
        if x > y:
            a += 1
        elif y > x:
            b += 1
    return (a, b) if (a or b) else (None, None)


COLS = ["date", "year", "a", "b", "p_elo", "pa_pt", "pb_pt", "nS_a", "nS_b",
        "imp", "won", "surf", "score"]
A = pd.read_parquet(OLD, columns=COLS)
B = pd.read_parquet(NEW, columns=COLS)
print("rows: pre-guard %d, with-guard %d" % (len(A), len(B)))
key = ["date", "a", "b"]
A["_k"] = list(zip(A["date"], A["a"], A["b"]))
B["_k"] = list(zip(B["date"], B["a"], B["b"]))
common = set(A["_k"]) & set(B["_k"])
A = A[A["_k"].isin(common)].drop_duplicates("_k").set_index("_k").sort_index()
B = B[B["_k"].isin(common)].drop_duplicates("_k").set_index("_k").sort_index()
A, B = A.align(B, join="inner", axis=0)
ok = (A["imp"].notna() & A["won"].notna() & A["pa_pt"].notna() & A["pb_pt"].notna()
      & A["p_elo"].notna() & B["pa_pt"].notna() & B["pb_pt"].notna() & B["p_elo"].notna()
      & (A["nS_a"] >= 4) & (A["nS_b"] >= 4) & (B["nS_a"] >= 4) & (B["nS_b"] >= 4)).to_numpy()
A, B = A[ok], B[ok]
print("paired, scorable rows: %d" % len(A))
sa, sb = zip(*[sets_won(s) for s in A["score"]])
bo5 = ((pd.Series(sa, dtype="float64") >= 3)
       | (pd.Series(sb, dtype="float64") >= 3)).fillna(False).to_numpy()
WON = A["won"].to_numpy(dtype=float)
MKT = A["imp"].to_numpy(dtype=float)
YR = A["year"].to_numpy()
SRF = A["surf"].to_numpy()
# how much did the guard actually move the ratings?
d_pa = (B["pa_pt"].to_numpy(dtype=float) - A["pa_pt"].to_numpy(dtype=float))
print("point-prob change from the guard: mean |d| %.4f, p90 |d| %.4f, rows changed %.1f%%"
      % (np.abs(d_pa).mean(), np.percentile(np.abs(d_pa), 90), 100 * (d_pa != 0).mean()))


def blend(F):
    pa = F["pa_pt"].to_numpy(dtype=float)
    pb = F["pb_pt"].to_numpy(dtype=float)
    sga = 0.10 / np.sqrt(np.maximum(F["nS_a"].to_numpy(dtype=float), 4.0))
    sgb = 0.10 / np.sqrt(np.maximum(F["nS_b"].to_numpy(dtype=float), 4.0))
    pm = np.zeros(len(F))
    for xi, wi in _NODES:
        for xj, wj in _NODES:
            pm += wi * wj * np.array([_pm(_rnd(x + xi * s1), _rnd(y + xj * s2), bool(f))
                                      for x, y, s1, s2, f in zip(pa, pb, sga, sgb, bo5)])
    lgm = np.log(np.clip(pm, 1e-6, 1 - 1e-6) / (1 - np.clip(pm, 1e-6, 1 - 1e-6)))
    e = F["p_elo"].to_numpy(dtype=float)
    lge = np.log(np.clip(e, 1e-6, 1 - 1e-6) / (1 - np.clip(e, 1e-6, 1 - 1e-6)))
    return 1 / (1 + np.exp(-(0.5 * lge + 0.5 * lgm)))


PA, PB = blend(A), blend(B)


def row(lab, p, m):
    from sklearn.metrics import roc_auc_score
    n = int(m.sum())
    if n < 300:
        return "   %-18s (n=%d)" % (lab, n)
    return ("   %-18s AUC %.4f  Brier %.4f   |model-mkt| %5.2fpt"
            % (lab, roc_auc_score(WON[m], p[m]),
               float(((p[m] - WON[m]) ** 2).mean()),
               100 * float(np.abs(p[m] - MKT[m]).mean())))


BAR = "=" * 84
print("\n" + BAR)
print("PAIRED COMPARISON -- same rows, same scoring")
print(BAR)
allm = np.ones(len(A), bool)
print(row("pre-guard", PA, allm))
print(row("with guard", PB, allm))
print("   market Brier %.4f" % float(((MKT - WON) ** 2).mean()))
for y in (2024, 2025, 2026):
    m = YR == y
    print("  %d (n=%d)" % (y, int(m.sum())))
    print(row("   pre-guard", PA, m))
    print(row("   with guard", PB, m))
print("\n  by surface:")
for sf in ("hard", "clay", "grass"):
    m = SRF == sf
    if m.sum() < 400:
        continue
    print("  %s (n=%d)" % (sf, int(m.sum())))
    print(row("   pre-guard", PA, m))
    print(row("   with guard", PB, m))

print("\n" + BAR)
print("ROWS THE GUARD ACTUALLY TOUCHED (|point-prob change| > 0.002)")
print(BAR)
m = np.abs(d_pa) > 0.002
print("  n=%d (%.1f%% of rows)" % (int(m.sum()), 100 * m.mean()))
print(row("   pre-guard", PA, m))
print(row("   with guard", PB, m))
