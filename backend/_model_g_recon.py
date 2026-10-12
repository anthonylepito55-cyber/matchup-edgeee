"""MODEL G HISTORY RECON (2026-10-12, user "show the new model on the results history as well").

G only started logging today, so without this the results-history tab shows a G line on nothing.
This backfills model_g_p1 / model_gma_p1 onto settled log games that predate the model.

HONESTY CONTRACT (the model_x_recon / mc2_recon pattern):
  * The model scoring a row is trained ONLY on seasons strictly before that row's year. Every
    log row is 2026, so the scorer here is fit on 2015-2025 and has never seen a 2026 match.
  * The features come from the archive build's own as-of window -- prior 365 days on that
    surface, shift(1) inside the player/surface group -- so a row knows nothing about itself or
    anything after it. This is the same frame the walk-forward validation used.
  * The opponent-rank discount curves and the shrinkage constants were already frozen on
    2015-2023, so they are out-of-sample for every row here too.
  * The result column is never read while producing a probability. It is read ONCE at the end,
    for a display-only sanity print.
  * Output is stamped model_g_recon=True, which the g_* forward lanes explicitly drop and the
    history dims with a ~. A backfill is not a forward pick, however honest its construction.

Writes the fill to data_cache/_model_g_recon_fill.parquet and, with --apply, merges it into the
log in place (only into rows where model_g_p1 is currently null -- a genuine frozen value is
never overwritten).

Usage:  python _model_g_recon.py [log_path] [--apply]
"""
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
import xgboost as xgb

args = [a for a in sys.argv[1:] if not a.startswith("--")]
APPLY = "--apply" in sys.argv
LOGP = args[0] if args else "data_cache/tennis_prediction_log.parquet"

log = pd.read_parquet(LOGP)
log["d"] = log["date"].astype(str).str[:10]
have = log["model_g_p1"].notna() if "model_g_p1" in log.columns else pd.Series(False, index=log.index)
need = log[log["p1_won"].notna() & ~have].copy()
print("settled log rows missing G: %d  (%s .. %s)"
      % (len(need), need["d"].min() if len(need) else "-", need["d"].max() if len(need) else "-"),
      flush=True)
if not len(need):
    raise SystemExit("nothing to backfill")

# ---- the archive build's as-of features (everything before it starts fitting) ----
ns = {}
src = open("_tennis_model_g_build.py", encoding="utf-8").read()
exec(compile(src.split("from sklearn.linear_model")[0], "_g_prep", "exec"), ns)
m, FC, core = ns["m"], ns["FC"], ns["core"]
# core lost the slugs on its way through the build, so re-key it with the build's OWN mask
# rather than a reconstruction of it -- a mask that drifted by one row would silently
# mis-attribute every probability from that point on.
key = m.loc[ns["keep"], ["date", "player_slug", "rival_slugname"]].reset_index(drop=True)
assert len(key) == len(core), (len(key), len(core))
print("archive as-of rows: %d" % len(core), flush=True)

# ---- one scorer per log year, trained strictly on earlier years ----
yrs = sorted({int(y) for y in pd.to_datetime(need["d"]).dt.year.unique()})
print("log years to score: %s" % yrs, flush=True)
preds = {}
for yr in yrs:
    itr = (core["date"].dt.year < yr).to_numpy()
    if itr.sum() < 5000:
        print("  %d: only %d earlier rows, skipped" % (yr, int(itr.sum())))
        continue
    Xtr, ytr = core.loc[itr, FC].fillna(0), core.loc[itr, "won"]
    lr = LogisticRegression(max_iter=3000, C=0.5).fit(Xtr, ytr)
    bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                            colsample_bytree=0.8, n_jobs=8, eval_metric="logloss").fit(Xtr, ytr)
    lgm = np.log(np.clip(core.loc[itr, "mkt"], 1e-6, 1 - 1e-6)
                 / (1 - np.clip(core.loc[itr, "mkt"], 1e-6, 1 - 1e-6)))
    lrm = LogisticRegression(max_iter=3000, C=0.5).fit(np.column_stack([lgm, Xtr]), ytr)
    ite = (core["date"].dt.year == yr).to_numpy()
    Xte = core.loc[ite, FC].fillna(0)
    mk = np.clip(core.loc[ite, "mkt"].to_numpy(float), 1e-6, 1 - 1e-6)
    p = 0.5 * (lr.predict_proba(Xte)[:, 1] + bst.predict_proba(Xte)[:, 1])
    pma = lrm.predict_proba(np.column_stack([np.log(mk / (1 - mk)), Xte]))[:, 1]
    sub = key[ite].reset_index(drop=True)
    for i in range(len(sub)):
        preds[(str(sub.at[i, "date"])[:10], sub.at[i, "player_slug"],
               str(sub.at[i, "rival_slugname"]))] = (float(p[i]), float(pma[i]))
    print("  %d: trained on %d earlier rows, scored %d" % (yr, int(itr.sum()), int(ite.sum())),
          flush=True)

# ---- map log names to slugs and orient to the log's player_1 ----
import tennis_model_a as T

rcache = {}


def slug(nm):
    if nm not in rcache:
        try:
            rcache[nm] = T.resolve(nm)
        except Exception:  # noqa: BLE001
            rcache[nm] = None
    return rcache[nm]


out, miss_slug, miss_row = [], 0, 0
for r in need.itertuples():
    s1, s2 = slug(r.player_1), slug(r.player_2)
    if not s1 or not s2:
        miss_slug += 1
        continue
    hit = preds.get((r.d, s1, s2))
    flip = False
    if hit is None:
        hit = preds.get((r.d, s2, s1))
        flip = True          # the archive row is oriented the other way round
    if hit is None:
        miss_row += 1
        continue
    pg, pma = hit
    out.append({"date": r.d, "player_1": r.player_1, "player_2": r.player_2,
                "model_g_p1": round(1 - pg if flip else pg, 4),
                "model_gma_p1": round(1 - pma if flip else pma, 4)})

fill = pd.DataFrame(out)
fill.to_parquet("data_cache/_model_g_recon_fill.parquet")
print("\nfilled %d / %d   (no slug %d, not in the as-of archive %d)"
      % (len(fill), len(need), miss_slug, miss_row), flush=True)

if len(fill):
    # join on the fill's own key; the suffix cannot be relied on because a log that predates
    # the model has no model_g_p1 column at all, in which case nothing collides
    res = need[["d", "player_1", "player_2", "p1_won"]].merge(
        fill.rename(columns={"date": "d", "model_g_p1": "_g"})[["d", "player_1", "player_2", "_g"]],
        on=["d", "player_1", "player_2"], how="inner")
    acc = ((res["_g"] >= 0.5) == res["p1_won"].astype(bool)).mean()
    print("sanity, DISPLAY-ONLY and not a forward record: recon picked the winner %.1f%% of %d"
          % (100 * acc, len(res)), flush=True)

if APPLY and len(fill):
    L = pd.read_parquet(LOGP)
    for c in ("model_g_p1", "model_gma_p1"):
        if c not in L.columns:
            L[c] = np.nan
    if "model_g_recon" not in L.columns:
        L["model_g_recon"] = False
    L["_d"] = L["date"].astype(str).str[:10]
    idx = {(r.date, r.player_1, r.player_2): (r.model_g_p1, r.model_gma_p1)
           for r in fill.itertuples()}
    n = 0
    for i in L.index:
        if pd.notna(L.at[i, "model_g_p1"]):
            continue                      # never overwrite a genuine frozen value
        v = idx.get((L.at[i, "_d"], L.at[i, "player_1"], L.at[i, "player_2"]))
        if v is None:
            continue
        L.at[i, "model_g_p1"], L.at[i, "model_gma_p1"] = v
        L.at[i, "model_g_recon"] = True
        n += 1
    L = L.drop(columns=["_d"])
    L.to_parquet(LOGP)
    print("applied %d recon rows to %s (stamped model_g_recon=True)" % (n, LOGP), flush=True)
elif len(fill):
    print("\ndry run -- rerun with --apply to merge into the log", flush=True)
