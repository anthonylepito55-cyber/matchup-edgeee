"""THE GRAY LINE BY PRICE BAND -- ARCHIVE BACKTEST (2026-10-11, user: "What's the backtests").

Companion to `_cma_band_roi.py`, which measured the two cells on the live log and found the
favourite side dead (-7.9%, n=468) and the dog side promising but tiny (+11.8%, n=60, 0.8se,
and only two weeks of data because `model_cma_p1` starts 2026-09-28).

So: what does the archive say? Reuses the SAME prep and the SAME walk-forward recipe as
`_tennis_gender_full_bt.py` -- `_tennis_abc6_agree_bt.py` builds the feature frames, then for
each year a model is fit on all PRIOR years only, in two flavours:

    p      Model C proper (LR + XGB averaged)
    p_ms   the GRAY LINE -- the same features with logit(market) added as an input

Then the two cells the user asked about:
    FAVOURITES  gray picks the favourite, favourite priced -100..-250 (decimal 1.40-2.00)
    DOGS        gray picks the dog, dog priced +100..+200 (decimal 2.00-3.00)

Both against the band's own baseline, because a cell's ROI is meaningless without knowing what
the band returns on its own.

**One row per match.** The archive carries both orientations of every fixture and the old rig
double-counted them (project_gender_side_backtest); this keys each match on the unordered slug
pair + date and keeps the first.
"""
import numpy as np

ns = {}
src = open("_tennis_abc6_agree_bt.py", encoding="utf-8").read()
exec(compile(src.split("tot = {")[0], "_prep6", "exec"), ns)
KEY = ns["KEY"]
core_c, FC_C = ns["core_c"], ns["FC_C"]
mC = ns["mC"] if "mC" in ns else ns["m"]

lvl = {}
for k, l in zip(mC[KEY].itertuples(index=False, name=None), mC["tournament_level"].astype(str)):
    s = l.lower()
    if "wom" in s or "wta" in s:
        lvl[k] = "W"
    elif "atp" in s or "men" in s or "challenger" in s or "future" in s:
        lvl[k] = "M"
    else:
        lvl[k] = "?"
# tournament level string, for a tour/challenger/ITF split
lvlraw = {k: str(l).lower() for k, l in
          zip(mC[KEY].itertuples(index=False, name=None), mC["tournament_level"].astype(str))}

from sklearn.linear_model import LogisticRegression          # noqa: E402
import xgboost as xgb                                        # noqa: E402


def lg(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def fit_p(core, FC, yr):
    """Walk-forward: train on every year BEFORE yr, predict yr. Identical to the shipped rig."""
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


YEARS = (2024, 2025, 2026)
# cell -> list of (pnl, won, implied, year, gender, level)
rows = []
seen = set()
for yr in YEARS:
    pc = fit_p(core_c, FC_C, yr)
    for k, (pcr, pcg, w1, m1, a, b) in pc.items():
        dt, s1, s2 = k[0], str(k[1]), str(k[2])
        pair = (dt, *sorted((s1, s2)))
        if pair in seen:                      # ONE ROW PER MATCH
            continue
        seen.add(pair)
        g = lvl.get(k, "?")
        if g == "?" or not a or not b or a <= 1.005 or b <= 1.005:
            continue
        lv = lvlraw.get(k, "")
        level = ("itf" if ("itf" in lv or "future" in lv)
                 else "challenger" if "challenger" in lv else "tour")
        dog1 = m1 < 0.5
        grayS = pcg >= 0.5                    # the gray line prefers this row's player
        fav_dec = b if dog1 else a            # the FAVOURITE's decimal price
        dog_dec = a if dog1 else b            # the DOG's decimal price

        def add(cell, side1):
            o = a if side1 else b
            pnl = (o - 1) if (w1 == side1) else -1.0
            imp = m1 if side1 else 1 - m1
            rows.append((cell, pnl, w1 == side1, imp, yr, g, level))

        # FAVOURITES -100..-250  == decimal 1.40 .. 2.00
        if 1.40 <= fav_dec <= 2.00:
            add("fav_band_all", not dog1)
            if grayS == (not dog1):
                add("fav_band_gray", not dog1)
            else:
                add("fav_band_graydog", not dog1)     # control
        # DOGS +100..+200 == decimal 2.00 .. 3.00
        if 2.00 <= dog_dec <= 3.00:
            add("dog_band_all", dog1)
            if grayS == dog1:
                add("dog_band_gray", dog1)
            else:
                add("dog_band_grayfav", dog1)         # control

import pandas as pd                                           # noqa: E402

R = pd.DataFrame(rows, columns=["cell", "pnl", "won", "imp", "yr", "G", "level"])
print("backtest bets: %d over %s   (one row per match)" % (len(R), list(YEARS)))


def rep(s, lab, floor=60):
    n = len(s)
    if n < floor:
        print("   %-46s n=%d (thin)" % (lab, n))
        return
    hit, imp = 100 * s.won.mean(), 100 * s.imp.mean()
    se = 100 * s.pnl.std(ddof=1) / np.sqrt(n)
    print("   %-46s wins %4.1f%%  no-vig %4.1f%%  EDGE %+5.1fpt  ROI %+6.1f%% ± %4.1f  (n=%d)"
          % (lab, hit, imp, hit - imp, 100 * s.pnl.mean(), se, n))


for band, allc, gray, ctrl, title in (
        ("fav", "fav_band_all", "fav_band_gray", "fav_band_graydog",
         "FAVOURITES -100..-250"),
        ("dog", "dog_band_all", "dog_band_gray", "dog_band_grayfav",
         "UNDERDOGS +100..+200")):
    print("\n" + "=" * 110)
    print("%s  (archive walk-forward)" % title)
    print("=" * 110)
    A, Gc, C = R[R.cell == allc], R[R.cell == gray], R[R.cell == ctrl]
    rep(A, "baseline: back every %s in the band" % band)
    rep(Gc, "** gray line picks the %s **" % band.upper())
    rep(C, "control: gray picks the other side, bet anyway")
    for Gg, nm in (("M", "men"), ("W", "women")):
        rep(Gc[Gc.G == Gg], "      %s" % nm)
    print("   by year:")
    for y in YEARS:
        rep(Gc[Gc.yr == y], "      %d" % y)
    print("   by level:")
    for lv in ("tour", "challenger", "itf"):
        rep(Gc[Gc.level == lv], "      %s" % lv)
