"""G FAV-OVER: what does a minimum margin over the market buy? (2026-10-12)

User: "lets make the black favorite highlight 4 pts over the market instead of anything over the
market". Their call either way -- a tighter gate means fewer, more deliberate marks, which is a
good reason on its own. This measures what it costs or earns so the decision is informed rather
than assumed, and so the card can state the real number.

Sweeps the minimum margin (G's read on the favourite minus the market's price on the favourite)
from 0 to 12 points, walk-forward, flat 1u at the archive's closing odds. Prints the coverage at
each step beside the ROI, because the whole point of a threshold is trading volume for quality
and both halves have to be visible. A baseline of every favourite on the same rows is printed
too: fav-over has previously measured WORSE than that, so the question is not only whether the
gate improves the cell but whether it ever gets it past simply backing chalk.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
import xgboost as xgb

ns = {}
src = open("_tennis_model_g_build.py", encoding="utf-8").read()
exec(compile(src.split("from sklearn.linear_model")[0], "_g_prep", "exec"), ns)
core, FC = ns["core"].reset_index(drop=True), ns["FC"]
print("core: %d rows" % len(core), flush=True)

oos = pd.Series(np.nan, index=core.index)
for yr in (2024, 2025, 2026):
    itr = (core["date"].dt.year < yr).to_numpy()
    ite = (core["date"].dt.year == yr).to_numpy()
    if ite.sum() < 500:
        continue
    Xtr, Xte = core.loc[itr, FC].fillna(0), core.loc[ite, FC].fillna(0)
    y = core.loc[itr, "won"]
    lr = LogisticRegression(max_iter=3000, C=0.5).fit(Xtr, y)
    bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                            colsample_bytree=0.8, n_jobs=8, eval_metric="logloss").fit(Xtr, y)
    oos[ite] = 0.5 * (lr.predict_proba(Xte)[:, 1] + bst.predict_proba(Xte)[:, 1])
    print("  %d scored" % yr, flush=True)

d = core[oos.notna() & (core["player_odd"] > 1.005) & (core["rival_odd"] > 1.005)].copy()
d["p"] = oos[d.index]
d["yr"] = d["date"].dt.year
fav1 = d["mkt"] >= 0.5
d["mkfav"] = np.where(fav1, d["mkt"], 1 - d["mkt"])
d["gfav"] = np.where(fav1, d["p"], 1 - d["p"])
d["favodd"] = np.where(fav1, d["player_odd"], d["rival_odd"])
d["favwon"] = np.where(fav1, d["won"] == 1, d["won"] == 0)
d["over"] = d["gfav"] - d["mkfav"]
d["pnl"] = np.where(d["favwon"], d["favodd"] - 1, -1.0)

print("\nevery favourite on these rows (the bar the gate has to clear):")
for g in ("M", "W"):
    sub = d[d.G == g]
    print("   %s  n=%-6d roi %+.2f%%  hit %.1f%%"
          % (g, len(sub), 100 * sub["pnl"].mean(), 100 * sub["favwon"].mean()))

print("\nFAV-OVER by minimum margin over the market:")
print("   %-6s %-26s %-26s %s" % ("min", "MEN", "WOMEN", "both"))
for t in (0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12):
    cells = []
    for g in ("M", "W", None):
        sub = d[(d["over"] > t) & ((d.G == g) if g else True)]
        tot = len(d[(d.G == g) if g else slice(None)])
        if not len(sub):
            cells.append("%-26s" % "(empty)")
            continue
        roi = 100 * sub["pnl"].mean()
        se = 100 * sub["pnl"].std() / np.sqrt(len(sub))
        cells.append("n=%-5d %+6.2f%% +/-%.1f %3.0f%%" % (len(sub), roi, se, 100 * len(sub) / max(tot, 1)))
    print("   %-6s %s %s %s" % ("%.0fpt" % (100 * t), cells[0], cells[1], cells[2]))

print("\n(the %% at the end of each cell is the share of that gender's favourites still marked)")
print("\nby year at the 4pt gate the user asked for:")
sub = d[d["over"] > 0.04]
for g in ("M", "W"):
    for yr in (2024, 2025, 2026):
        q = sub[(sub.G == g) & (sub.yr == yr)]
        if len(q):
            print("   %s %d  n=%-5d roi %+.2f%%  hit %.1f%%"
                  % (g, yr, len(q), 100 * q["pnl"].mean(), 100 * q["favwon"].mean()))
