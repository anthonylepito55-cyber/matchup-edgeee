"""MODEL G -- the two cells the live lanes now record (2026-10-12).

User narrowed G's forward record to the only two reads that say something:
    g_fav_over  -- G rates the MARKET FAVOURITE above the market's own price on it -> back the favourite
    g_dog_flip  -- G puts the market UNDERDOG above 50%, picking it outright      -> back the dog
The excluded remainder (G leaning to the dog without flipping it) is deliberately unlaned.

Same shape as the 👑 P DOG FLIP gate and the c75-flip gate, both of which measured real: a model
that merely shades toward a side is saying much less than one that overturns the price.

This gives the live lanes a prior to be read against. Walk-forward, each year trained only on
earlier years, flat 1u at the archive's closing odds. A baseline column is printed for each cell
-- every favourite / every dog over the SAME rows -- because a cell that merely reproduces the
side's base rate is not a finding.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
import xgboost as xgb

ns = {}
src = open("_tennis_model_g_build.py", encoding="utf-8").read()
exec(compile(src.split("from sklearn.linear_model")[0], "_g_prep", "exec"), ns)
core, FC = ns["core"], ns["FC"]
print("core: %d rows" % len(core), flush=True)

core = core.reset_index(drop=True)
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
d["p"] = oos[oos.notna() & (core["player_odd"] > 1.005) & (core["rival_odd"] > 1.005)]
d["yr"] = d["date"].dt.year
d["fav1"] = d["mkt"] >= 0.5
d["mkfav"] = np.where(d["fav1"], d["mkt"], 1 - d["mkt"])
d["gfav"] = np.where(d["fav1"], d["p"], 1 - d["p"])
d["favodd"] = np.where(d["fav1"], d["player_odd"], d["rival_odd"])
d["dogodd"] = np.where(d["fav1"], d["rival_odd"], d["player_odd"])
d["favwon"] = np.where(d["fav1"], d["won"] == 1, d["won"] == 0)

d["cell"] = np.where(d["gfav"] > d["mkfav"], "g_fav_over",
                     np.where(d["gfav"] < 0.5, "g_dog_flip", "(excluded: leans dog, no flip)"))
# the bet each cell makes, and what it returns
d["pnl"] = np.where(
    d["cell"] == "g_fav_over",
    np.where(d["favwon"], d["favodd"] - 1, -1.0),
    np.where(d["cell"] == "g_dog_flip",
             np.where(~d["favwon"], d["dogodd"] - 1, -1.0), np.nan))
d["hit"] = np.where(d["cell"] == "g_fav_over", d["favwon"],
                    np.where(d["cell"] == "g_dog_flip", ~d["favwon"], False))

print("\ncoverage of G's %d priced matches:" % len(d))
for c, sub in d.groupby("cell"):
    print("   %-32s %6d  (%4.1f%%)" % (c, len(sub), 100 * len(sub) / len(d)))


def tab(sub, by):
    if not len(sub):
        return "   (empty)"
    g = sub.groupby(by).agg(n=("pnl", "size"), roi=("pnl", lambda s: 100 * s.mean()),
                            hit=("hit", lambda s: 100 * s.mean()))
    g["se"] = sub.groupby(by)["pnl"].apply(lambda s: 100 * s.std() / np.sqrt(max(len(s), 1)))
    return g.round(2).to_string()


bet = d[d["cell"].isin(["g_fav_over", "g_dog_flip"])]
print("\n" + "=" * 70)
print("THE TWO CELLS, overall and by gender")
print("=" * 70)
print(tab(bet, ["cell"]))
print()
print(tab(bet, ["cell", "G"]))
print("\nby year (the only thing that says whether it is still alive):")
print(tab(bet, ["cell", "yr"]))
print("\nby gender x year:")
print(tab(bet, ["cell", "G", "yr"]))

print("\n" + "=" * 70)
print("BASELINES on the SAME rows -- is the cell doing anything the side alone does not?")
print("=" * 70)
base = []
for g in ("M", "W"):
    sub = d[d["G"] == g]
    fpnl = np.where(sub["favwon"], sub["favodd"] - 1, -1.0)
    dpnl = np.where(~sub["favwon"], sub["dogodd"] - 1, -1.0)
    base.append({"G": g, "side": "every favourite", "n": len(sub), "roi": 100 * fpnl.mean(),
                 "hit": 100 * sub["favwon"].mean()})
    base.append({"G": g, "side": "every dog", "n": len(sub), "roi": 100 * dpnl.mean(),
                 "hit": 100 * (~sub["favwon"]).mean()})
print(pd.DataFrame(base).round(2).to_string(index=False))

print("\nhow far G sits over the market on the favourite (g_fav_over only):")
fo = bet[bet["cell"] == "g_fav_over"].copy()
fo["over"] = fo["gfav"] - fo["mkfav"]
fo["ob"] = pd.cut(fo["over"], [0, 0.02, 0.05, 0.10, 1.0])
print(tab(fo, ["G", "ob"]))
print("\nhow far G flips the dog past 50% (g_dog_flip only):")
fl = bet[bet["cell"] == "g_dog_flip"].copy()
fl["flip"] = 0.5 - fl["gfav"]
fl["fb"] = pd.cut(fl["flip"], [0, 0.02, 0.05, 0.10, 1.0])
print(tab(fl, ["G", "fb"]))
print("\nby the dog's price (g_dog_flip only):")
fl["ab"] = pd.cut((fl["dogodd"] - 1) * 100, [100, 150, 200, 300, 100000])
print(tab(fl, ["G", "ab"]))
