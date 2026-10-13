"""MC3 vs MC2, with each Tier-1 change isolated (2026-10-13).

Four scorings on IDENTICAL rows, so every step is attributable rather than one lump:

    MC2            career ratings, best-of-3 always, no day tilt   <- what is live today
    +surface       per-surface ratings shrunk at MC3_KS
    +surface+bo5   and best-of-five actually modelled
    MC3            and the day-form tilt in the match probability   <- the new head

Each uses the SAME Elo half, the same 50/50 log-odds blend, the same per-player sigma and the
same chain imported from tennis_mc2, so the only differences are the three listed changes.

BEST-OF-FIVE IS DERIVED FROM THE SCORE, not assumed: whoever won 3 sets was in a best-of-five
match. A best-of-three winner can only reach 2. That makes the bo5 flag a fact about the row
rather than a guess from the tournament name, at the cost of missing retirements -- which are
excluded anyway since an unfinished match has no honest set count.

Reported overall, on the best-of-five subset (where change 2 can possibly matter), by surface
(where change 1 should land), and as mean |model - market| (where change 3 should show).
"""
import gc
import math
import os

import numpy as np
import pandas as pd

from tennis_mc2 import _NODES, DAY_SD, _rnd
from tennis_mc3 import MC3_KS, p_match

BASE_FEAT = "data_cache/_mc2_features_sk1000000000.parquet"   # career-only control = MC2
MC3_FEAT = "data_cache/_mc3_features.parquet"


def sets_won(score):
    """-> (sets_a, sets_b) from a score string, or (None, None) if unparseable."""
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


def blend(F, bo5, tilt):
    """MC2's live math, with best-of-five and the day tilt switchable."""
    pa = F["pa_pt"].to_numpy(dtype=float)
    pb = F["pb_pt"].to_numpy(dtype=float)
    sga = 0.10 / np.sqrt(np.maximum(F["nS_a"].to_numpy(dtype=float), 4.0))
    sgb = 0.10 / np.sqrt(np.maximum(F["nS_b"].to_numpy(dtype=float), 4.0))
    b5 = bo5.to_numpy(dtype=bool) if hasattr(bo5, "to_numpy") else np.asarray(bo5, dtype=bool)
    tnodes = _NODES if tilt else ((0.0, 1.0),)
    pm = np.zeros(len(F))
    for xt, wt in tnodes:
        for xi, wi in _NODES:
            for xj, wj in _NODES:
                pm += wt * wi * wj * np.array(
                    [p_match(_rnd(x + xi * sa + xt * DAY_SD),
                             _rnd(y + xj * sb - xt * DAY_SD), bool(f))
                     for x, y, sa, sb, f in zip(pa, pb, sga, sgb, b5)])
    lg = np.vectorize(lambda p: math.log(min(max(p, 1e-6), 1 - 1e-6)
                                         / (1 - min(max(p, 1e-6), 1 - 1e-6))))
    z = 0.5 * lg(F["p_elo"].to_numpy(dtype=float)) + 0.5 * lg(pm)
    return 1 / (1 + np.exp(-z))


COLS = ["date", "year", "p_elo", "pa_pt", "pb_pt", "nS_a", "nS_b", "imp", "won", "surf", "score"]
for p in (BASE_FEAT, MC3_FEAT):
    if not os.path.exists(p):
        raise SystemExit("missing %s -- build it first" % p)

B = pd.read_parquet(BASE_FEAT, columns=COLS)
M = pd.read_parquet(MC3_FEAT, columns=COLS)
assert len(B) == len(M), "feature tables differ in length"
keep = (B["imp"].notna() & B["won"].notna() & B["pa_pt"].notna() & B["pb_pt"].notna()
        & B["p_elo"].notna() & (B["nS_a"] >= 4) & (B["nS_b"] >= 4)
        & M["pa_pt"].notna() & M["pb_pt"].notna()).to_numpy()
B, M = B[keep].reset_index(drop=True), M[keep].reset_index(drop=True)
sa, sb = zip(*[sets_won(s) for s in B["score"]])
sa = pd.Series(sa, dtype="float64")
sb = pd.Series(sb, dtype="float64")
bo5 = ((sa >= 3) | (sb >= 3)).fillna(False)
print("rows: %d   best-of-five identified: %d (%.1f%%)   unparseable score: %d"
      % (len(B), int(bo5.sum()), 100 * bo5.mean(), int(sa.isna().sum())))

VARIANTS = [("MC2 (live today)", B, bo5 & False, False),
            ("+surface", M, bo5 & False, False),
            ("+surface +bo5", M, bo5, False),
            ("MC3 (+ day tilt)", M, bo5, True)]
res = {}
for lab, F, b5, tl in VARIANTS:
    res[lab] = blend(F, b5, tl)
    print("   scored %s" % lab)
    gc.collect()

won = B["won"].to_numpy(dtype=float)
mkt = B["imp"].to_numpy(dtype=float)
yr = B["year"].to_numpy()
srf = B["surf"].to_numpy()


def row(lab, p, m):
    from sklearn.metrics import roc_auc_score
    n = int(m.sum())
    if n < 200:
        return "   %-20s (n=%d, too few)" % (lab, n)
    return ("   %-20s AUC %.4f  Brier %.4f   |model-mkt| %5.2fpt"
            % (lab, roc_auc_score(won[m], p[m]),
               float(((p[m] - won[m]) ** 2).mean()),
               100 * float(np.abs(p[m] - mkt[m]).mean())))


BAR = "=" * 86
print("\n" + BAR)
print("BY YEAR")
print(BAR)
for y in (2024, 2025, 2026):
    m = yr == y
    print("  %d  (n=%d)   market Brier %.4f" % (y, int(m.sum()),
                                                float(((mkt[m] - won[m]) ** 2).mean())))
    for lab in res:
        print(row(lab, res[lab], m))

print("\n" + BAR)
print("BEST-OF-FIVE ONLY -- the subset where modelling bo5 can matter at all")
print(BAR)
m = bo5.to_numpy()
print("  n=%d   market Brier %.4f" % (int(m.sum()), float(((mkt[m] - won[m]) ** 2).mean())))
for lab in res:
    print(row(lab, res[lab], m))
print("\n  best-of-three only (n=%d), as the control -- bo5 must change NOTHING here:"
      % int((~m).sum()))
for lab in res:
    print(row(lab, res[lab], ~m))

print("\n" + BAR)
print("BY SURFACE -- where the per-surface ratings should land")
print(BAR)
for s in ("hard", "clay", "grass"):
    m = srf == s
    if m.sum() < 400:
        continue
    print("  %s (n=%d)   market Brier %.4f" % (s, int(m.sum()),
                                               float(((mkt[m] - won[m]) ** 2).mean())))
    for lab in res:
        print(row(lab, res[lab], m))

print("\n" + BAR)
print("OVERALL")
print(BAR)
allm = np.ones(len(B), bool)
print("   %-20s AUC %.4f  Brier %.4f"
      % ("market", __import__("sklearn.metrics", fromlist=["x"]).roc_auc_score(won, mkt),
         float(((mkt - won) ** 2).mean())))
for lab in res:
    print(row(lab, res[lab], allm))
print("\nMC3_KS = %g" % MC3_KS)
