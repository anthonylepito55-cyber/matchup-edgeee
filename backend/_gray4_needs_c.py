"""DOES THE SHIPPED gray_dog4 MARK NEED MODEL C TO AGREE? (2026-10-11)

Fell out of the overlap test. Partitioning the "gray picks the dog at +100..+200" cell showed
91% of it is ALSO gray_dog4 AND C-agree (+22.2%), while the slice that is gray_dog4 WITHOUT C
agreeing was **+1.0% on 428 bets** -- flat. That hints the gray_dog4 mark earns only where
Model C independently backs the same dog.

But that 428 figure was restricted to the +100..+200 band, and the shipped `gray_dog4` mark
fires at ANY price. So it cannot be used to judge the mark. This measures the real universe:
every gray_dog4 bet, split by whether C agrees, with per-year splits because a decaying cell
would otherwise hide inside a 3-year pool.

gray_dog4 as the lane defines it: the gray line prices the market DOG at least 4 points above
the market's own number, and picks it. Same walk-forward rig, one row per match.
"""
import numpy as np
import pandas as pd

ns = {}
src = open("_tennis_abc6_agree_bt.py", encoding="utf-8").read()
exec(compile(src.split("tot = {")[0], "_prep6", "exec"), ns)
KEY = ns["KEY"]
core_c, FC_C = ns["core_c"], ns["FC_C"]
mC = ns["mC"] if "mC" in ns else ns["m"]

lvl = {}
for k, l in zip(mC[KEY].itertuples(index=False, name=None), mC["tournament_level"].astype(str)):
    s = l.lower()
    lvl[k] = "W" if ("wom" in s or "wta" in s) else (
        "M" if ("atp" in s or "men" in s or "challenger" in s or "future" in s) else "?")

from sklearn.linear_model import LogisticRegression          # noqa: E402
import xgboost as xgb                                        # noqa: E402


def lg(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def fit_p(core, FC, yr):
    tr = core[core["date"].dt.year < yr]
    te = core[core["date"].dt.year == yr]
    Xtr, Xte = tr[FC].fillna(0), te[FC].fillna(0)
    ytr = tr["won"]
    lr = LogisticRegression(max_iter=3000, C=0.5).fit(Xtr, ytr)
    bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                            colsample_bytree=0.8, n_jobs=8, eval_metric="logloss").fit(Xtr, ytr)
    p = 0.5 * (lr.predict_proba(Xte)[:, 1] + bst.predict_proba(Xte)[:, 1])
    lr_ms = LogisticRegression(max_iter=3000, C=0.5).fit(
        np.column_stack([lg(tr["mkt"]), Xtr]), ytr)
    p_ms = lr_ms.predict_proba(np.column_stack([lg(te["mkt"]), Xte]))[:, 1]
    return {k: (float(pr), float(pm), bool(w), float(m1), a, b)
            for k, pr, pm, w, m1, a, b in zip(te[KEY].itertuples(index=False, name=None),
                                              p, p_ms, te["won"].values, te["mkt"].values,
                                              te["player_odd"].values, te["rival_odd"].values)}


rows, seen = [], set()
for yr in (2024, 2025, 2026):
    for k, (pcr, pcg, w1, m1, a, b) in fit_p(core_c, FC_C, yr).items():
        pair = (k[0], *sorted((str(k[1]), str(k[2]))))
        if pair in seen:
            continue
        seen.add(pair)
        g = lvl.get(k, "?")
        if g == "?" or not a or not b or a <= 1.005 or b <= 1.005:
            continue
        dog1 = m1 < 0.5
        grayS, cS = pcg >= 0.5, pcr >= 0.5
        if grayS != dog1:                     # gray must be on the dog
            continue
        mdog = m1 if dog1 else 1 - m1
        gdog = pcg if dog1 else 1 - pcg
        if (gdog - mdog) < 0.04:              # the 4pt threshold the lane uses
            continue
        o = a if dog1 else b
        rows.append({"pnl": (o - 1) if (w1 == dog1) else -1.0, "won": w1 == dog1,
                     "imp": mdog, "yr": yr, "G": g, "agree": (cS == dog1),
                     "dog_dec": o, "gap_pp": 100 * (gdog - mdog)})

R = pd.DataFrame(rows)
print("gray_dog4 bets (any price, one row per match): %d\n" % len(R))


def rep(s, lab, floor=50):
    n = len(s)
    if n < floor:
        print("   %-48s n=%d (thin)" % (lab, n))
        return
    hit, imp = 100 * s.won.mean(), 100 * s.imp.mean()
    se = 100 * s.pnl.std(ddof=1) / np.sqrt(n)
    print("   %-48s wins %4.1f%%  no-vig %4.1f%%  EDGE %+5.1fpt  ROI %+6.1f%% ± %4.1f  (n=%d)"
          % (lab, hit, imp, hit - imp, 100 * s.pnl.mean(), se, n))


print("=" * 114)
print("gray_dog4 AT ANY PRICE -- split by whether Model C independently backs the same dog")
print("=" * 114)
rep(R, "the mark as shipped (all gray_dog4 bets)")
rep(R[R.agree], "   C AGREES (C also on the dog)")
rep(R[~R.agree], "   C DISAGREES")
print("   C disagrees on %.0f%% of gray_dog4 bets (%d of %d)"
      % (100 * (~R.agree).mean(), int((~R.agree).sum()), len(R)))

print("\n   C-DISAGREES half, by year:")
for y in (2024, 2025, 2026):
    rep(R[(~R.agree) & (R.yr == y)], "      %d" % y)
print("   C-AGREES half, by year:")
for y in (2024, 2025, 2026):
    rep(R[R.agree & (R.yr == y)], "      %d" % y)

print("\n   C-DISAGREES half, by gender:")
for Gg, nm in (("M", "men"), ("W", "women")):
    rep(R[(~R.agree) & (R.G == Gg)], "      %s" % nm)

print("\n   what dropping the C-disagrees half would do to the mark overall:")
rep(R, "      keep everything (status quo)")
rep(R[R.agree], "      keep only C-agrees")
