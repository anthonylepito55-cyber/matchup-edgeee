"""MODEL G -- ablation, head-to-head vs Model C, and the side split (2026-10-12).

Three questions the build run leaves open:

 1. WHICH HALF OF G IS WORKING? G does two things to the 52-week stat line: shrinks each
    rate by its own sample size, and discounts it for the ranks of the opponents who
    produced it. The build only showed adjusted+shrunk against shrunk-only. This runs the
    full 2x2 so the opponent adjustment and the shrinkage are separated:
        A raw        -- plain 52w rates, the way the card prints them and the way C uses them
        B shrunk     -- A, pulled toward the tour mean by sample size
        C opp-adj    -- A, discounted for opponent rank, NOT shrunk
        D G          -- both

 2. IS G BETTER THAN MODEL C's STATS-ONLY HEAD? C has 29 features (last-10 block, season
    block, H2H, odds performance, vs-band) against G's nine stats. If nine adjusted stats
    match 29 raw ones, the adjustment is worth more than everything C adds. Scored on the
    rows BOTH models can price, so the comparison is like-for-like.

 3. WHERE DOES G'S MONEY LIVE? Overall ROI at a 5pt threshold was -9 to -11%, but every
    live lane we have says the edge is on dogs and that favourites are where models die
    (reference_live_dog_fav_all_records: 0 of 13 heads positive on favourites). So split
    gender x side, and bucket by how far G sits from the price.

Backtest only -- G has no live record yet, so nothing here is a forward test.
"""
import time
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score
import xgboost as xgb

t0 = time.time()


def say(*a):
    print("[%6.1fs]" % (time.time() - t0), *a, flush=True)


# ---- reuse the G build's prep verbatim (everything before it starts fitting) ----
src = open("_tennis_model_g_build.py", encoding="utf-8").read()
ns = {}
exec(compile(src.split("from sklearn.linear_model")[0], "_g_prep", "exec"), ns)
df, STATS, SN = ns["df"], ns["STATS"], [s[0] for s in ns["STATS"]]
say("G prep reused: %d player-match rows" % len(df))

# unshrunk window ratios, so the ablation can switch shrinkage off as well as on
for nm in SN:
    d = df["dsum_" + nm].replace(0, np.nan)
    df["uraw_" + nm] = df["rnum_" + nm] / d
    df["uadj_" + nm] = df["wnum_" + nm] / d

VARIANTS = {"A raw": "uraw_", "B shrunk": "graw_", "C opp-adj": "uadj_", "D G (both)": "g_"}
CARRY = ([p + n for p in VARIANTS.values() for n in SN] + ["n_" + n for n in SN]
         + ["w_n", "w_logr"])
mirror = df[["player_slug", "rival_slugname", "date"] + CARRY].copy()
mirror.columns = ["rival_slugname", "player_slug", "date"] + ["o_" + c for c in CARRY]
m = df.merge(mirror, on=["player_slug", "rival_slugname", "date"], how="inner")
m = m[m["player_slug"] < m["rival_slugname"].astype(str)]
m = m.drop_duplicates(["player_slug", "rival_slugname", "date"]).reset_index(drop=True)
ip1 = 1 / m["player_odd"].where(m["player_odd"] > 1.005)
ip2 = 1 / m["rival_odd"].where(m["rival_odd"] > 1.005)
m["mkt"] = ip1 / (ip1 + ip2)
say("paired: %d matches" % len(m))

# the sample-size and schedule features are identical across variants -- only the stat
# values change -- so the ablation isolates the stats and nothing else
SHARED = {"d_matches": np.log1p(m["w_n"]) - np.log1p(m["o_w_n"]),
          "f_nmin": np.log1p(np.minimum(m["w_n"], m["o_w_n"])),
          "d_faced": m["o_w_logr"] - m["w_logr"]}
for nm in SN:
    SHARED["dn_" + nm] = np.log1p(m["n_" + nm]) - np.log1p(m["o_n_" + nm])

keep = m["mkt"].notna() & m["G"].isin(["M", "W"]) & m[["g_" + n for n in SN]].notna().sum(axis=1).ge(7)
base = m.loc[keep, ["date", "won", "mkt", "player_odd", "rival_odd", "G",
                    "player_slug", "rival_slugname"]].reset_index(drop=True)
say("scorable: %d matches" % len(base))


def lg(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def fitpred(X, y, Xte):
    lr = LogisticRegression(max_iter=3000, C=0.5).fit(X, y)
    bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                            colsample_bytree=0.8, n_jobs=8, eval_metric="logloss").fit(X, y)
    return 0.5 * (lr.predict_proba(Xte)[:, 1] + bst.predict_proba(Xte)[:, 1])


def walkforward(X, tag):
    """Train on everything before the year, score the year. Returns per-year metrics and
    the out-of-sample probability for every scored row."""
    out, oos = [], pd.Series(np.nan, index=base.index)
    for yr in (2024, 2025, 2026):
        itr = (base["date"].dt.year < yr).to_numpy()
        ite = (base["date"].dt.year == yr).to_numpy()
        if ite.sum() < 500:
            continue
        p = fitpred(X[itr].fillna(0), base.loc[itr, "won"], X[ite].fillna(0))
        y = base.loc[ite, "won"].to_numpy()
        oos[ite] = p
        out.append({"variant": tag, "yr": yr, "n": int(ite.sum()), "logloss": log_loss(y, p),
                    "auc": roc_auc_score(y, p), "acc": float(((p >= .5) == y).mean())})
    return pd.DataFrame(out), oos


# ============================= 1. ABLATION =============================
print("\n" + "=" * 78)
print("1. ABLATION -- what the shrinkage and the opponent adjustment each contribute")
print("=" * 78, flush=True)
res, oosmap = [], {}
for tag, pre in VARIANTS.items():
    X = pd.DataFrame({("d_" + n): pd.to_numeric(m[pre + n] - m["o_" + pre + n], errors="coerce")
                      for n in SN})
    for k_, v_ in SHARED.items():
        X[k_] = pd.to_numeric(v_, errors="coerce")
    X = X[keep.to_numpy()].reset_index(drop=True)
    r, oos = walkforward(X, tag)
    res.append(r)
    oosmap[tag] = oos
    say("%s done" % tag)
mk = pd.DataFrame([{"variant": "market", "yr": yr,
                    "n": int((base["date"].dt.year == yr).sum()),
                    "logloss": log_loss(base.loc[base["date"].dt.year == yr, "won"],
                                        base.loc[base["date"].dt.year == yr, "mkt"]),
                    "auc": roc_auc_score(base.loc[base["date"].dt.year == yr, "won"],
                                         base.loc[base["date"].dt.year == yr, "mkt"]),
                    "acc": float(((base.loc[base["date"].dt.year == yr, "mkt"] >= .5)
                                  == base.loc[base["date"].dt.year == yr, "won"]).mean())}
                   for yr in (2024, 2025, 2026)])
res = pd.concat(res + [mk], ignore_index=True)
piv = res.pivot_table(index="variant", columns="yr", values="auc")
print("\nAUC by year:")
print(piv.round(4).to_string())
print("\nAccuracy by year:")
print(res.pivot_table(index="variant", columns="yr", values="acc").round(4).to_string())
print("\nLogloss by year (lower is better):")
print(res.pivot_table(index="variant", columns="yr", values="logloss").round(4).to_string())
res.to_csv("_model_g_ablation.csv", index=False)

# ============================= 2. VS MODEL C =============================
print("\n" + "=" * 78)
print("2. HEAD-TO-HEAD vs MODEL C stats-only, on the rows both can price")
print("=" * 78, flush=True)
nc = {}
csrc = open("_tennis_model_c_build.py", encoding="utf-8").read()
exec(compile(csrc.split("from sklearn.linear_model")[0], "_c_prep", "exec"), nc)
cm, CFC = nc["core"], nc["FC"]
cm = cm.reset_index(drop=True)
say("C prep: %d rows, %d features" % (len(cm), len(CFC)))
# C's core has no slugs, so re-key it off the frame it came from
cfull = nc["m"]
cf = cfull.loc[cfull.index, ["date", "player_slug", "rival_slugname"]].reset_index(drop=True)
cm2 = nc["m2"] if "m2" in nc else None
ckey = nc["m"][["date", "player_slug", "rival_slugname"]].copy()
ckey["_ci"] = np.arange(len(ckey))
# rebuild C's core mask the same way the C build does, to line indices up
cX = nc["X"]
cmask = (nc["m"]["mkt"].notna() & cX.notna().sum(axis=1).ge(18)).to_numpy()
ckey = ckey[cmask].reset_index(drop=True)
cm = cm.reset_index(drop=True)
assert len(ckey) == len(cm), (len(ckey), len(cm))
ckey["_row"] = np.arange(len(cm))

gk = base[["date", "player_slug", "rival_slugname"]].copy()
gk["_grow"] = np.arange(len(base))
j = gk.merge(ckey[["date", "player_slug", "rival_slugname", "_row"]],
             on=["date", "player_slug", "rival_slugname"], how="inner")
say("shared rows G n C: %d" % len(j))

cXk = cm[CFC].reset_index(drop=True)
shared_rows = {}
for yr in (2024, 2025, 2026):
    jj = j[pd.to_datetime(j["date"]).dt.year == yr]
    if len(jj) < 500:
        continue
    # C, trained on its own pre-year rows, scored on the shared rows of this year
    citr = (pd.to_datetime(cm["date"]).dt.year < yr).to_numpy()
    cp = fitpred(cXk[citr].fillna(0), cm.loc[citr, "won"],
                 cXk.iloc[jj["_row"].to_numpy()].fillna(0))
    y = base.loc[jj["_grow"].to_numpy(), "won"].to_numpy()
    mkv = base.loc[jj["_grow"].to_numpy(), "mkt"].to_numpy()
    line = {"yr": yr, "n": len(jj)}
    for tag in ("A raw", "D G (both)"):
        p = oosmap[tag].iloc[jj["_grow"].to_numpy()].to_numpy()
        line[tag + " auc"] = roc_auc_score(y, p)
        line[tag + " acc"] = float(((p >= .5) == y).mean())
    line["C stats auc"] = roc_auc_score(y, cp)
    line["C stats acc"] = float(((cp >= .5) == y).mean())
    line["market auc"] = roc_auc_score(y, mkv)
    line["market acc"] = float(((mkv >= .5) == y).mean())
    shared_rows[yr] = line
    print("  %d (n=%d)  G %.4f | C %.4f | G-raw %.4f | market %.4f   (AUC)"
          % (yr, len(jj), line["D G (both) auc"], line["C stats auc"],
             line["A raw auc"], line["market auc"]), flush=True)
pd.DataFrame(shared_rows.values()).to_csv("_model_g_vs_c.csv", index=False)

# ============================= 3. SIDE SPLIT =============================
print("\n" + "=" * 78)
print("3. WHERE G's MONEY LIVES -- gender x side, flat 1u at the archive's closing odds")
print("=" * 78, flush=True)
b = base.copy()
b["p"] = oosmap["D G (both)"]
b = b[b["p"].notna() & (b["player_odd"] > 1.005) & (b["rival_odd"] > 1.005)].copy()
# one bet per match: whichever side G likes more than the price does
b["edge1"] = b["p"] - b["mkt"]
b["edge2"] = (1 - b["p"]) - (1 - b["mkt"])
rec = []
for _, r in b.iterrows():
    for side, edge, odd, won in ((1, r.edge1, r.player_odd, r.won),
                                 (2, r.edge2, r.rival_odd, 1 - r.won)):
        if edge < 0.05:
            continue
        rec.append({"G": r.G, "yr": pd.to_datetime(r.date).year, "edge": edge, "odd": odd,
                    "pnl": (odd - 1) if won else -1.0, "won": won,
                    "dog": odd >= 2.0, "am": (odd - 1) * 100})
bt = pd.DataFrame(rec)
print("\ntotal bets at the 5pt threshold: %d" % len(bt))


def tab(d, by):
    g = d.groupby(by).agg(n=("pnl", "size"), roi=("pnl", lambda s: 100 * s.mean()),
                          hit=("won", "mean"))
    g["se"] = d.groupby(by)["pnl"].apply(lambda s: 100 * s.std() / np.sqrt(len(s)))
    g["hit"] = (100 * g["hit"]).round(1)
    return g.round(2)


print("\nby gender x side:")
print(tab(bt, ["G", "dog"]).to_string())
print("\nby gender x side x year:")
print(tab(bt, ["G", "dog", "yr"]).to_string())
print("\nby how far G sits from the price (dogs only):")
bt["eb"] = pd.cut(bt["edge"], [0.05, 0.08, 0.12, 0.20, 1.0])
print(tab(bt[bt.dog], ["G", "eb"]).to_string())
print("\nby price band (dogs only):")
bt["ab"] = pd.cut(bt["am"], [100, 150, 200, 300, 100000])
print(tab(bt[bt.dog], ["G", "ab"]).to_string())
# the pd.cut bucket columns are interval categoricals, which parquet refuses
bt.drop(columns=["eb", "ab"]).to_parquet("data_cache/_model_g_bets.parquet")
say("wrote _model_g_ablation.csv, _model_g_vs_c.csv, data_cache/_model_g_bets.parquet")
