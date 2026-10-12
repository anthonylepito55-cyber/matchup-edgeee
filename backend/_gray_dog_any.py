"""THE GRAY LINE ON THE DOG, UNFILTERED (2026-10-11, user: "when market model c agrees with the
dog what's the roi").

Everything reported so far put a filter in front of it -- the +100..+200 band, or the 4pt
gray_dog4 threshold. This is the plain question: whenever the market-aware C (the gray line)
prefers the market underdog, back it. No threshold, no band.

Then the splits that matter, in the order they change a decision:
  * does Model C independently agree? (the last test showed the gray4 mark is 92% C-agreeing
    and the disagreeing slice is flat)
  * how far above the market is the gray line? -- the 4pt lane threshold is one cut of this,
    but the full gradient says whether the threshold is in the right place
  * price, year, gender, level

Same shipped walk-forward rig and one-row-per-match guard as the other backtests.
Backtest first, then the live frozen log for the same cells.
"""
import numpy as np
import pandas as pd

ns = {}
src = open("_tennis_abc6_agree_bt.py", encoding="utf-8").read()
exec(compile(src.split("tot = {")[0], "_prep6", "exec"), ns)
KEY = ns["KEY"]
core_c, FC_C = ns["core_c"], ns["FC_C"]
mC = ns["mC"] if "mC" in ns else ns["m"]

lvl, lvlraw = {}, {}
for k, l in zip(mC[KEY].itertuples(index=False, name=None), mC["tournament_level"].astype(str)):
    s = l.lower()
    lvl[k] = "W" if ("wom" in s or "wta" in s) else (
        "M" if ("atp" in s or "men" in s or "challenger" in s or "future" in s) else "?")
    lvlraw[k] = s

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


rows, seen, n_all = [], set(), 0
for yr in (2024, 2025, 2026):
    for k, (pcr, pcg, w1, m1, a, b) in fit_p(core_c, FC_C, yr).items():
        pair = (k[0], *sorted((str(k[1]), str(k[2]))))
        if pair in seen:
            continue
        seen.add(pair)
        g = lvl.get(k, "?")
        if g == "?" or not a or not b or a <= 1.005 or b <= 1.005:
            continue
        n_all += 1
        dog1 = m1 < 0.5
        if (pcg >= 0.5) != dog1:               # the gray line must prefer the DOG
            continue
        mdog = m1 if dog1 else 1 - m1
        gdog = pcg if dog1 else 1 - pcg
        o = a if dog1 else b
        lv = lvlraw.get(k, "")
        rows.append({"pnl": (o - 1) if (w1 == dog1) else -1.0, "won": w1 == dog1,
                     "imp": mdog, "yr": yr, "G": g, "dog_dec": o,
                     "agree": (pcr >= 0.5) == dog1, "gap_pp": 100 * (gdog - mdog),
                     "level": ("itf" if ("itf" in lv or "future" in lv)
                               else "challenger" if "challenger" in lv else "tour")})

R = pd.DataFrame(rows)
print("matches scored: %d   gray line prefers the dog on %d of them (%.0f%%)\n"
      % (n_all, len(R), 100 * len(R) / max(n_all, 1)))


def rep(s, lab, floor=50):
    n = len(s)
    if n < floor:
        print("   %-46s n=%d (thin)" % (lab, n))
        return
    hit, imp = 100 * s.won.mean(), 100 * s.imp.mean()
    se = 100 * s.pnl.std(ddof=1) / np.sqrt(n)
    print("   %-46s wins %4.1f%%  no-vig %4.1f%%  EDGE %+5.1fpt  ROI %+6.1f%% ± %4.1f  (n=%d)"
          % (lab, hit, imp, hit - imp, 100 * s.pnl.mean(), se, n))


print("=" * 114)
print("BACKTEST -- gray line on the dog, NO filters")
print("=" * 114)
rep(R, "** every gray-line dog pick **")
print()
rep(R[R.agree], "   Model C AGREES (both on the dog)")
rep(R[~R.agree], "   Model C DISAGREES (gray alone on the dog)")
print()
print("   by how far the gray line sits ABOVE the market on that dog:")
for lo, hi, nm in ((-99, 0, "below market"), (0, 2, "0-2pt"), (2, 4, "2-4pt"),
                   (4, 6, "4-6pt"), (6, 10, "6-10pt"), (10, 999, "10pt+")):
    rep(R[(R.gap_pp >= lo) & (R.gap_pp < hi)], "      %s" % nm)
print()
print("   by dog price:")
for lo, hi, nm in ((1.0, 2.0, "under +100"), (2.0, 2.5, "+100..+150"),
                   (2.5, 3.0, "+150..+200"), (3.0, 4.0, "+200..+300"),
                   (4.0, 99, "+300 and longer")):
    rep(R[(R.dog_dec >= lo) & (R.dog_dec < hi)], "      %s" % nm)
print()
print("   by year:")
for y in (2024, 2025, 2026):
    rep(R[R.yr == y], "      %d" % y)
print("   by gender:")
for Gg, nm in (("M", "men"), ("W", "women")):
    rep(R[R.G == Gg], "      %s" % nm)
print("   by level:")
for lv in ("tour", "challenger", "itf"):
    rep(R[R.level == lv], "      %s" % lv)

# ------------------------------------------------------------------ live
print("\n" + "=" * 114)
print("LIVE FROZEN LOG -- the same cells")
print("=" * 114)
d = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
S = d[(d["settled"] == True) & d.p1_won.notna() & d.p1_odds.notna()       # noqa: E712
      & d.p2_odds.notna() & d.model_cma_p1.notna()].copy()
for c in ("surface_bad", "inplay_suspect"):
    if c in S.columns:
        S = S[~S[c].fillna(False).astype(bool)]


def dec(x):
    x = float(x)
    return 1 + x / 100.0 if x > 0 else 1 + 100.0 / abs(x)


S["d1"], S["d2"] = S.p1_odds.map(dec), S.p2_odds.map(dec)
i1, i2 = 1 / S.d1, 1 / S.d2
S["mkt1"] = i1 / (i1 + i2)
lgs = S.league.astype(str)
out = []
for r in S.itertuples():
    dog1 = r.mkt1 < 0.5
    if (float(r.model_cma_p1) >= 0.5) != dog1:
        continue
    mdog = r.mkt1 if dog1 else 1 - r.mkt1
    gdog = float(r.model_cma_p1) if dog1 else 1 - float(r.model_cma_p1)
    o = r.d1 if dog1 else r.d2
    won = bool(r.p1_won) == dog1
    ag = None
    if r.model_c_p1 is not None and not pd.isna(r.model_c_p1):
        ag = (float(r.model_c_p1) >= 0.5) == dog1
    out.append({"pnl": (o - 1) if won else -1.0, "won": won, "imp": mdog, "dog_dec": o,
                "agree": ag, "gap_pp": 100 * (gdog - mdog),
                "G": "W" if ("wta" in str(r.league) or "itf_women" in str(r.league)) else "M"})
L = pd.DataFrame(out)


def repl(s, lab, floor=10):
    n = len(s)
    if n < floor:
        print("   %-46s n=%d (too thin)" % (lab, n))
        return
    hit, imp = 100 * s.won.mean(), 100 * s.imp.mean()
    se = 100 * s.pnl.std(ddof=1) / np.sqrt(n)
    print("   %-46s %d-%d  wins %4.1f%%  EDGE %+5.1fpt  ROI %+6.1f%% ± %4.1f  (n=%d)"
          % (lab, int(s.won.sum()), n - int(s.won.sum()), hit, hit - imp,
             100 * s.pnl.mean(), se, n))


repl(L, "** every gray-line dog pick **")
repl(L[L.agree == True], "   Model C AGREES")           # noqa: E712
repl(L[L.agree == False], "   Model C DISAGREES")       # noqa: E712
for Gg, nm in (("M", "men"), ("W", "women")):
    repl(L[L.G == Gg], "      %s" % nm)
for lo, hi, nm in ((1.0, 2.0, "under +100"), (2.0, 3.0, "+100..+200"), (3.0, 99, "+200+")):
    repl(L[(L.dog_dec >= lo) & (L.dog_dec < hi)], "      %s" % nm)
