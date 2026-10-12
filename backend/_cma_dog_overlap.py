"""IS THE GRAY-DOG BAND CELL ACTUALLY NEW? (2026-10-11, user: "yes")

The cell "gray line picks the dog, dog priced +100..+200" backtests +20.3% on 5,274 bets. But
two cells already marked on the board cover similar ground:

    gray_dog4   gray prices the dog >= 4pt ABOVE the market  (and picks it)
    agree_dog   Model C AND the gray line both on the dog    (the star / C+GRAY DOG cell)

If the new cell's bets are mostly those, it is a reformulation of something already being acted
on, not a discovery. So this partitions the 5,274 into four disjoint groups and prices each:

    both        already covered twice over
    gray4 only
    agree only
    NEITHER     the genuinely new ground -- this is the number that decides it

Same walk-forward rig, same one-row-per-match guard. If NEITHER is strongly positive with real
n, the cell adds something; if it is flat, the edge lives entirely in the existing marks.
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
        dog_dec = a if dog1 else b
        if not (2.00 <= dog_dec <= 3.00):      # the +100..+200 band
            continue
        if grayS != dog1:                      # the gray line must pick the dog
            continue
        # the two existing marks, defined exactly as the shipped lanes define them
        mdog = m1 if dog1 else 1 - m1          # market's prob on the dog
        gdog = pcg if dog1 else 1 - pcg        # gray's prob on the dog
        is_gray4 = (gdog - mdog) >= 0.04
        is_agree = (cS == dog1)                # C also on the dog -> the star cell
        grp = ("both" if (is_gray4 and is_agree)
               else "gray4_only" if is_gray4
               else "agree_only" if is_agree
               else "NEITHER")
        o = a if dog1 else b
        rows.append({"grp": grp, "pnl": (o - 1) if (w1 == dog1) else -1.0,
                     "won": w1 == dog1, "imp": mdog, "yr": yr, "G": g,
                     "gap_pp": 100 * (gdog - mdog)})

R = pd.DataFrame(rows)
print("gray-dog band bets: %d\n" % len(R))


def rep(s, lab, floor=50):
    n = len(s)
    if n < floor:
        print("   %-44s n=%d (thin)" % (lab, n))
        return
    hit, imp = 100 * s.won.mean(), 100 * s.imp.mean()
    se = 100 * s.pnl.std(ddof=1) / np.sqrt(n)
    print("   %-44s wins %4.1f%%  no-vig %4.1f%%  EDGE %+5.1fpt  ROI %+6.1f%% ± %4.1f  (n=%d, %2.0f%% of cell)"
          % (lab, hit, imp, hit - imp, 100 * s.pnl.mean(), se, n, 100 * n / len(R)))


print("=" * 112)
print("DOES THE CELL OVERLAP THE EXISTING MARKS? (disjoint partition)")
print("=" * 112)
rep(R, "the whole cell")
print()
for grp, lab in (("both", "already BOTH gray4 and agree (double-marked)"),
                 ("gray4_only", "already gray_dog4 only"),
                 ("agree_only", "already agree_dog (C+gray) only"),
                 ("NEITHER", "** NEITHER -- the genuinely new ground **")):
    rep(R[R.grp == grp], lab)

print("\n   covered by at least one existing mark: %.0f%% of the cell"
      % (100 * (R.grp != "NEITHER").mean()))

print("\n" + "=" * 112)
print("THE NEW GROUND, BROKEN DOWN -- does it hold up on its own?")
print("=" * 112)
N = R[R.grp == "NEITHER"]
if len(N) >= 50:
    for y in (2024, 2025, 2026):
        rep(N[N.yr == y], "      %d" % y)
    for Gg, nm in (("M", "men"), ("W", "women")):
        rep(N[N.G == Gg], "      %s" % nm)
    print("   by how far gray sits above the market on the dog:")
    for lo, hi, nm in ((-99, 0, "gray BELOW market"), (0, 2, "0-2pt above"),
                       (2, 4, "2-4pt above")):
        rep(N[(N.gap_pp >= lo) & (N.gap_pp < hi)], "      %s" % nm)

print("\n" + "=" * 112)
print("LIVE CHECK on the same partition (tiny, for direction only)")
print("=" * 112)
d = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
S = d[(d["settled"] == True) & d.p1_won.notna() & d.p1_odds.notna()      # noqa: E712
      & d.p2_odds.notna() & d.model_cma_p1.notna() & d.model_c_p1.notna()].copy()
for c in ("surface_bad", "inplay_suspect"):
    if c in S.columns:
        S = S[~S[c].fillna(False).astype(bool)]


def dec(x):
    x = float(x)
    return 1 + x / 100.0 if x > 0 else 1 + 100.0 / abs(x)


S["d1"], S["d2"] = S.p1_odds.map(dec), S.p2_odds.map(dec)
i1, i2 = 1 / S.d1, 1 / S.d2
S["mkt1"] = i1 / (i1 + i2)
out = []
for r in S.itertuples():
    dog1 = r.mkt1 < 0.5
    grayS = float(r.model_cma_p1) >= 0.5
    if grayS != dog1:
        continue
    dog_dec = r.d1 if dog1 else r.d2
    if not (2.00 <= dog_dec <= 3.00):
        continue
    mdog = r.mkt1 if dog1 else 1 - r.mkt1
    gdog = float(r.model_cma_p1) if dog1 else 1 - float(r.model_cma_p1)
    is_gray4 = (gdog - mdog) >= 0.04
    is_agree = (float(r.model_c_p1) >= 0.5) == dog1
    grp = ("both" if (is_gray4 and is_agree) else "gray4_only" if is_gray4
           else "agree_only" if is_agree else "NEITHER")
    won = bool(r.p1_won) == dog1
    o = r.d1 if dog1 else r.d2
    out.append({"grp": grp, "pnl": (o - 1) if won else -1.0, "won": won, "imp": mdog})
L = pd.DataFrame(out)
if len(L):
    for grp in ("both", "gray4_only", "agree_only", "NEITHER"):
        s = L[L.grp == grp]
        if len(s) < 5:
            print("   %-30s n=%d (too thin)" % (grp, len(s)))
            continue
        print("   %-30s %d-%d  ROI %+6.1f%%  (n=%d)"
              % (grp, int(s.won.sum()), len(s) - int(s.won.sum()),
                 100 * s.pnl.mean(), len(s)))
    print("   live cell total n=%d, of which NEITHER n=%d"
          % (len(L), int((L.grp == "NEITHER").sum())))
