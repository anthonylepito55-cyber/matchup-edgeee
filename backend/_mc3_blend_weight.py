"""HOW MUCH OF THE TIER-3 GAIN IS THE BLEND WEIGHT, AND HOW MUCH IS RESCALING? (2026-10-13)

Tier 3's refit beat shipped MC3 out of sample by a lot -- Brier .2236 -> .2220 testing on 2026 --
and the fitted weights said Elo should carry ~0.79 of the log-odds rather than 0.50. But that
logistic fit ALSO learned an intercept and an overall scale: its raw coefficients sum to 1.55 and
1.66, where the shipped head is implicitly fixed at 1.00. So the gain is a mixture of

    (a) re-weighting Elo vs Markov        -- a clean one-parameter change to the head
    (b) sharpening the whole thing        -- a calibration layer, which this project has
                                            tested and lost with before (Model E)

and those must be separated before anything ships, because (a) is a model fix and (b) is a
different animal that would need its own justification and its own forward validation.

This evaluates, out of sample on the same walk-forward splits:

    w sweep at FIXED total scale 1.0:   p = sigmoid(w*logit_elo + (1-w)*logit_mkv)
    the full refit, for reference       p = sigmoid(c0 + c1*logit_elo + c2*logit_mkv)
    the full refit with fatigue         as above plus the three fatigue differentials

Nothing here is fit on the test period. The w sweep is fit on nothing at all -- w is a constant
chosen on the TRAIN period and applied to TEST -- so it is the honest shippable form.
"""
import os
from functools import lru_cache

import numpy as np
import pandas as pd

from tennis_mc2 import _NODES, _rnd
from tennis_mc3 import p_match

FEAT = "data_cache/_mc3_features.parquet"
if not os.path.exists(FEAT):
    raise SystemExit("missing %s" % FEAT)


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
        "rest_a", "m7_a", "ex_a", "rest_b", "m7_b", "ex_b"]
F = pd.read_parquet(FEAT, columns=COLS)
F = F[F["imp"].notna() & F["won"].notna() & F["pa_pt"].notna() & F["pb_pt"].notna()
      & F["p_elo"].notna() & (F["nS_a"] >= 4) & (F["nS_b"] >= 4)].reset_index(drop=True)
sa, sb = zip(*[sets_won(s) for s in F["score"]])
bo5 = ((pd.Series(sa, dtype="float64") >= 3)
       | (pd.Series(sb, dtype="float64") >= 3)).fillna(False).to_numpy()

pa = F["pa_pt"].to_numpy(dtype=float)
pb = F["pb_pt"].to_numpy(dtype=float)
sga = 0.10 / np.sqrt(np.maximum(F["nS_a"].to_numpy(dtype=float), 4.0))
sgb = 0.10 / np.sqrt(np.maximum(F["nS_b"].to_numpy(dtype=float), 4.0))
mkv = np.zeros(len(F))
for xi, wi in _NODES:
    for xj, wj in _NODES:
        mkv += wi * wj * np.array([_pm(_rnd(x + xi * s1), _rnd(y + xj * s2), bool(f))
                                   for x, y, s1, s2, f in zip(pa, pb, sga, sgb, bo5)])


def lg(v):
    v = np.clip(v, 1e-6, 1 - 1e-6)
    return np.log(v / (1 - v))


L_ELO, L_MKV = lg(F["p_elo"].to_numpy(dtype=float)), lg(mkv)
WON = F["won"].to_numpy(dtype=float)
MKT = F["imp"].to_numpy(dtype=float)
YR = F["year"].to_numpy()
num = lambda c: pd.to_numeric(F[c], errors="coerce").fillna(0.0).to_numpy(dtype=float)
FAT = np.column_stack([np.clip(num("rest_a"), 0, 30) - np.clip(num("rest_b"), 0, 30),
                       num("m7_a") - num("m7_b"),
                       num("ex_a") - num("ex_b")])
from sklearn.linear_model import LogisticRegression              # noqa: E402
from sklearn.metrics import roc_auc_score                        # noqa: E402


def ev(lab, p, m, star=""):
    print("   %-28s AUC %.4f  Brier %.4f   |model-mkt| %5.2fpt%s"
          % (lab, roc_auc_score(WON[m], p[m]),
             float(((p[m] - WON[m]) ** 2).mean()),
             100 * float(np.abs(p[m] - MKT[m]).mean()), star))


WS = [0.50, 0.60, 0.70, 0.75, 0.79, 0.85, 0.90, 1.00]
BAR = "=" * 94
for tr_years, te in (([2024], 2025), ([2024, 2025], 2026)):
    trm = np.isin(YR, tr_years)
    tem = YR == te
    print("\n" + BAR)
    print("TRAIN %s -> TEST %d (n=%d)   market Brier %.4f"
          % ("+".join(map(str, tr_years)), te, int(tem.sum()),
             float(((MKT[tem] - WON[tem]) ** 2).mean())))
    print(BAR)
    print("   -- fixed total scale 1.0, w on Elo (shipped head is w=0.50) --")
    best = None
    for w in WS:
        p = 1 / (1 + np.exp(-(w * L_ELO + (1 - w) * L_MKV)))
        br_tr = float(((p[trm] - WON[trm]) ** 2).mean())
        if best is None or br_tr < best[1]:
            best = (w, br_tr)
        ev("w=%.2f%s" % (w, "  <- SHIPPED" if w == 0.50 else ""), p, tem)
    print("   best w on the TRAIN period: %.2f (train Brier %.4f)" % best)
    w = best[0]
    p = 1 / (1 + np.exp(-(w * L_ELO + (1 - w) * L_MKV)))
    ev("-> applied to test, w=%.2f" % w, p, tem, "   <== shippable form")

    print("   -- for reference, fits that also learn scale and intercept --")
    for lab, X in (("full refit (elo,mkv)", np.column_stack([L_ELO, L_MKV])),
                   ("full refit + fatigue", np.column_stack([L_ELO, L_MKV, FAT]))):
        mdl = LogisticRegression(max_iter=2000, C=1e6).fit(X[trm], WON[trm])
        pf = np.full(len(F), np.nan)
        pf[tem] = mdl.predict_proba(X[tem])[:, 1]
        ev(lab, pf, tem)
        print("      scale sum %.3f  intercept %+.4f"
              % (abs(mdl.coef_[0][0]) + abs(mdl.coef_[0][1]), mdl.intercept_[0]))

print("\n" + BAR)
print("READ: if the w sweep alone recovers most of the full refit's gain, the fix is the")
print("WEIGHT and it ships as one constant. If the full refit is much better than the best w,")
print("the rest is a calibration layer and needs its own decision.")
print(BAR)
