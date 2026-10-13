"""MC3 TIER 3 (2026-10-13, user: "yes try tier 3 too").

Three candidates, all of them re-weightings of information MC3 already has nearby rather than
structure it is missing. Today's pattern says to expect failure: of six changes tried, the two
that worked (per-surface ratings, best-of-five) added missing structure, and the four that failed
(input shrinkage, day tilt, serve decomposition, tiebreak skill) all re-weighted what was
already there. Tier 3 is entirely the second kind, so this is a disconfirmation attempt.

  7. PRESSURE / CLUTCH   -- `clutch` = pressure points won; in the state and feature table,
                            unused by the head.
  8. FATIGUE             -- `rest` days, `m7` matches in the last 7 days, `ex` games played;
                            computed pre-match by the builder, unused by the head.
  9. THE BLEND WEIGHT    -- the head fixes Elo and Markov at 0.5/0.5 in log-odds. Never re-fit.

METHOD -- walk-forward logistic regression, not a hand sweep.

Each candidate is a question of the form "does X add signal beyond MC3's own probability", which
is exactly a logistic residual test, so:

    train on 2024          -> evaluate on 2025
    train on 2024 + 2025   -> evaluate on 2026

Models, all fit on the training period only and scored out of sample:

    refit blend   logit(p) ~ logit(p_elo) + logit(p_mkv)
    + clutch      and the clutch differential
    + fatigue     and rest / matches-7d / games-7d differentials
    + all

Compared against SHIPPED MC3 on the identical test rows. Shipped MC3 is not fit to anything, so
it has no training advantage to give back -- any refit model that fails to beat it out of sample
has genuinely found nothing.

A refit that wins only because the hard-coded 0.5/0.5 was set on an older period would still be
a real improvement, so the blend-weight row is reported with the fitted coefficients printed:
if they come out near 0.5/0.5 the original was simply right.
"""
import gc
import math
import os

from functools import lru_cache

import numpy as np
import pandas as pd

from tennis_mc2 import _NODES, _rnd
from tennis_mc3 import p_match

FEAT = "data_cache/_mc3_features.parquet"
if not os.path.exists(FEAT):
    raise SystemExit("missing %s -- run _mc3_build.py" % FEAT)


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


COLS = ["year", "p_elo", "pa_pt", "pb_pt", "nS_a", "nS_b", "imp", "won", "score",
        "clutch_a", "clutch_b", "rest_a", "m7_a", "ex_a", "rest_b", "m7_b", "ex_b"]
F = pd.read_parquet(FEAT, columns=COLS)
F = F[F["imp"].notna() & F["won"].notna() & F["pa_pt"].notna() & F["pb_pt"].notna()
      & F["p_elo"].notna() & (F["nS_a"] >= 4) & (F["nS_b"] >= 4)].reset_index(drop=True)
sa, sb = zip(*[sets_won(s) for s in F["score"]])
bo5 = ((pd.Series(sa, dtype="float64") >= 3)
       | (pd.Series(sb, dtype="float64") >= 3)).fillna(False).to_numpy()

# MC3's Markov half, sigma-integrated exactly as the head does it
pa = F["pa_pt"].to_numpy(dtype=float)
pb = F["pb_pt"].to_numpy(dtype=float)
sga = 0.10 / np.sqrt(np.maximum(F["nS_a"].to_numpy(dtype=float), 4.0))
sgb = 0.10 / np.sqrt(np.maximum(F["nS_b"].to_numpy(dtype=float), 4.0))
mkv = np.zeros(len(F))
for xi, wi in _NODES:
    for xj, wj in _NODES:
        mkv += wi * wj * np.array([_pm(_rnd(x + xi * s1), _rnd(y + xj * s2), bool(f))
                                   for x, y, s1, s2, f in zip(pa, pb, sga, sgb, bo5)])
elo = F["p_elo"].to_numpy(dtype=float)


def lg(v):
    v = np.clip(v, 1e-6, 1 - 1e-6)
    return np.log(v / (1 - v))


L_ELO, L_MKV = lg(elo), lg(mkv)
MC3 = 1 / (1 + np.exp(-(0.5 * L_ELO + 0.5 * L_MKV)))     # shipped, not fit

num = lambda c: pd.to_numeric(F[c], errors="coerce").fillna(0.0).to_numpy(dtype=float)
CLUTCH = num("clutch_a") - num("clutch_b")
REST = np.clip(num("rest_a"), 0, 30) - np.clip(num("rest_b"), 0, 30)
M7 = num("m7_a") - num("m7_b")
EX = num("ex_a") - num("ex_b")
WON = F["won"].to_numpy(dtype=float)
MKT = F["imp"].to_numpy(dtype=float)
YR = F["year"].to_numpy()
print("rows %d   bo5 %d   clutch nonzero on %.0f%%   rest nonzero on %.0f%%"
      % (len(F), int(bo5.sum()), 100 * (CLUTCH != 0).mean(), 100 * (REST != 0).mean()))

SETS = {
    "refit blend": [L_ELO, L_MKV],
    "+ clutch": [L_ELO, L_MKV, CLUTCH],
    "+ fatigue": [L_ELO, L_MKV, REST, M7, EX],
    "+ all": [L_ELO, L_MKV, CLUTCH, REST, M7, EX],
}
NAMES = {
    "refit blend": ["logit_elo", "logit_mkv"],
    "+ clutch": ["logit_elo", "logit_mkv", "clutch_diff"],
    "+ fatigue": ["logit_elo", "logit_mkv", "rest_diff", "m7_diff", "ex_diff"],
    "+ all": ["logit_elo", "logit_mkv", "clutch_diff", "rest_diff", "m7_diff", "ex_diff"],
}


def ev(lab, p, m):
    from sklearn.metrics import roc_auc_score
    n = int(m.sum())
    if n < 300:
        return "   %-16s (n=%d)" % (lab, n)
    return ("   %-16s AUC %.4f  Brier %.4f   |model-mkt| %5.2fpt"
            % (lab, roc_auc_score(WON[m], p[m]),
               float(((p[m] - WON[m]) ** 2).mean()),
               100 * float(np.abs(p[m] - MKT[m]).mean())))


from sklearn.linear_model import LogisticRegression            # noqa: E402

BAR = "=" * 88
for tr_years, te_year in (([2024], 2025), ([2024, 2025], 2026)):
    tr = np.isin(YR, tr_years)
    te = YR == te_year
    print("\n" + BAR)
    print("TRAIN %s (n=%d)  ->  TEST %d (n=%d)   market Brier %.4f"
          % ("+".join(map(str, tr_years)), int(tr.sum()), te_year, int(te.sum()),
             float(((MKT[te] - WON[te]) ** 2).mean())))
    print(BAR)
    print(ev("MC3 (shipped)", MC3, te))
    for lab, cols in SETS.items():
        X = np.column_stack(cols)
        mdl = LogisticRegression(max_iter=2000, C=1e6)
        mdl.fit(X[tr], WON[tr])
        # ev() indexes with a full-length mask, so scatter the test-only predictions back
        pf = np.full(len(F), np.nan)
        pf[te] = mdl.predict_proba(X[te])[:, 1]
        print(ev(lab, pf, te))
        co = ", ".join("%s %+.4f" % (n, c) for n, c in zip(NAMES[lab], mdl.coef_[0]))
        print("      coefs: %s" % co)
        del X
        gc.collect()

print("\n" + BAR)
print("IS 0.5/0.5 RIGHT? the refit blend's two coefficients, normalised to sum to 1")
print(BAR)
for tr_years, te_year in (([2024], 2025), ([2024, 2025], 2026)):
    tr = np.isin(YR, tr_years)
    X = np.column_stack([L_ELO, L_MKV])
    mdl = LogisticRegression(max_iter=2000, C=1e6).fit(X[tr], WON[tr])
    a, b = mdl.coef_[0]
    print("   train %-12s elo %.3f / mkv %.3f  (raw %+.3f, %+.3f; shipped is 0.500 / 0.500)"
          % ("+".join(map(str, tr_years)), a / (a + b), b / (a + b), a, b))
