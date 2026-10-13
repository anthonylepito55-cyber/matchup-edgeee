"""Does EXCLUDING walkovers from the last-10 block actually help? (2026-10-12)

The user asked for it, so it ships either way -- a win over a player who retired is not a win
over them, which is a correctness point about what the feature MEANS, not a performance claim.
But an instruction that costs accuracy is worth knowing about, so this builds the identical
last-10 block twice, once over all matches and once over completed ones only, and runs both
through the same walk-forward.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score
import xgboost as xgb

ns = {}
src = open("_tennis_model_g2_build.py", encoding="utf-8").read()
MARK = chr(10) + "from sklearn.linear_model import LogisticRegression"
exec(compile(src[:src.index(MARK)], "_g2", "exec"), ns)
exec(compile(src.split(MARK)[0], "_g2", "exec"), ns)
df, SN, L10, GCOLS = ns["df"], ns["SN"], ns["L10"], ns["GCOLS"]
T10 = list(L10) + ["t10_n"]
print("base frame ready: %d rows" % len(df), flush=True)


def l10_block(use_all):
    """The same block, over every match or over completed ones only."""
    src_ = df if use_all else df[~df["walkover"]]
    src_ = src_.sort_values(["punit", "date"], kind="stable")
    g = src_.groupby("punit", sort=False)
    agg = {}
    for nm, (col, how) in L10.items():
        agg[nm] = getattr(g[col].rolling(10, min_periods=3), how)().reset_index(level=0, drop=True)
    agg["t10_n"] = g["won"].rolling(10, min_periods=3).count().reset_index(level=0, drop=True)
    out = pd.DataFrame(agg)
    out["punit"] = src_["punit"].to_numpy()
    out["date"] = src_["date"].to_numpy()
    out = out.sort_values("date", kind="stable").reset_index(drop=True)
    left = df[["punit", "date"]].copy()
    left["_i"] = np.arange(len(left))
    left = left.sort_values("date", kind="stable")
    mg = pd.merge_asof(left, out, on="date", by="punit", direction="backward",
                       allow_exact_matches=False).sort_values("_i")
    return {nm: mg[nm].to_numpy() for nm in T10}


def fitpair(Xtr, ytr, Xte):
    lr = LogisticRegression(max_iter=3000, C=0.5).fit(Xtr, ytr)
    bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                            colsample_bytree=0.8, n_jobs=8, eval_metric="logloss").fit(Xtr, ytr)
    return 0.5 * (lr.predict_proba(Xte)[:, 1] + bst.predict_proba(Xte)[:, 1])


res = {}
for tag, use_all in (("walkovers EXCLUDED (shipped)", False), ("walkovers included", True)):
    blk = l10_block(use_all)
    d2 = df.copy()
    for nm in T10:
        d2[nm] = blk[nm]
    CARRY = (["g_" + n for n in SN] + ["n_" + n for n in SN]
             + ["w_n", "w_logr", "wide"] + T10)
    mir = d2[["player_slug", "rival_slugname", "date"] + CARRY].copy()
    mir.columns = ["rival_slugname", "player_slug", "date"] + ["o_" + c for c in CARRY]
    m = d2.merge(mir, on=["player_slug", "rival_slugname", "date"], how="inner")
    m = m[m["player_slug"] < m["rival_slugname"].astype(str)]
    m = m.drop_duplicates(["player_slug", "rival_slugname", "date"]).reset_index(drop=True)
    i1 = 1 / m["player_odd"].where(m["player_odd"] > 1.005)
    i2 = 1 / m["rival_odd"].where(m["rival_odd"] > 1.005)
    m["mkt"] = i1 / (i1 + i2)
    f = {}
    for nm in SN:
        f["d_" + nm] = m["g_" + nm] - m["o_g_" + nm]
        f["dn_" + nm] = np.log1p(m["n_" + nm]) - np.log1p(m["o_n_" + nm])
    f["d_matches"] = np.log1p(m["w_n"]) - np.log1p(m["o_w_n"])
    f["f_nmin"] = np.log1p(np.minimum(m["w_n"], m["o_w_n"]))
    f["d_faced"] = m["o_w_logr"] - m["w_logr"]
    f["f_wide"] = m["wide"].fillna(0) + m["o_wide"].fillna(0)
    for a, b in (("win", 1), ("meff", 1), ("hold", 1), ("brk", 1), ("losscl", 1),
                 ("faced", -1), ("beaten", -1), ("bestwin", -1), ("lost", -1), ("worstloss", -1)):
        c = "t10_" + a
        f["d_" + c] = (m[c] - m["o_" + c]) if b == 1 else (m["o_" + c] - m[c])
    f["d_t10_n"] = m["t10_n"] - m["o_t10_n"]
    f["f_t10_nmin"] = np.minimum(m["t10_n"], m["o_t10_n"])
    FC = list(f.keys())
    X = pd.DataFrame({k: pd.to_numeric(v, errors="coerce") for k, v in f.items()})
    keep = m["mkt"].notna() & X[GCOLS].notna().sum(axis=1).ge(14) & m["G"].isin(["M", "W"])
    core = m.loc[keep, ["date", "won", "mkt"]].join(X).reset_index(drop=True)
    res[tag] = {}
    for yr in (2024, 2025, 2026):
        itr = (core["date"].dt.year < yr).to_numpy()
        ite = (core["date"].dt.year == yr).to_numpy()
        if ite.sum() < 500:
            continue
        p = fitpair(core.loc[itr, FC].fillna(0), core.loc[itr, "won"], core.loc[ite, FC].fillna(0))
        y = core.loc[ite, "won"]
        res[tag][yr] = (roc_auc_score(y, p), log_loss(y, p), float(((p >= .5) == y).mean()))
    print("%-30s done (core %d)" % (tag, len(core)), flush=True)

print("\n%-30s %-24s %-24s %s" % ("last-10 built over", "2024 auc/ll", "2025 auc/ll", "2026 auc/ll"))
for tag, r in res.items():
    print("%-30s %s" % (tag, "  ".join("%.4f/%.4f" % (r[y][0], r[y][1]) for y in sorted(r))))
a, b = res["walkovers EXCLUDED (shipped)"], res["walkovers included"]
print("\nexcluding them is worth, in AUC points:")
for y in sorted(a):
    print("   %d  %+.2f pt" % (y, 100 * (a[y][0] - b[y][0])))
