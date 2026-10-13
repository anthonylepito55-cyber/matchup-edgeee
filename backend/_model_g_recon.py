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
RESCORE = "--rescore" in sys.argv
LOGP = args[0] if args else "data_cache/tennis_prediction_log.parquet"

log = pd.read_parquet(LOGP)
log["d"] = log["date"].astype(str).str[:10]
if RESCORE and "model_g_recon" in log.columns:
    _old = log["model_g_recon"].fillna(False).astype(bool)
    print("--rescore: %d previously backfilled rows will be recomputed with the current artifact"
          % int(_old.sum()), flush=True)
    log.loc[_old, "model_g_p1"] = np.nan
    log.loc[_old, "model_gma_p1"] = np.nan
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
preds, fitted = {}, {}


def _dec(am):
    """American odds -> decimal. The log stores American; the model needs a probability."""
    try:
        a = float(am)
    except (TypeError, ValueError):
        return None
    if a == 0:
        return None
    return 1 + a / 100.0 if a > 0 else 1 + 100.0 / abs(a)

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
    fitted[yr] = (lr, bst, lrm)
    ite = (core["date"].dt.year == yr).to_numpy()
    Xte = core.loc[ite, FC].fillna(0)
    mk = np.clip(core.loc[ite, "mkt"].to_numpy(float), 1e-6, 1 - 1e-6)
    p = 0.5 * (lr.predict_proba(Xte)[:, 1] + bst.predict_proba(Xte)[:, 1])
    pma = lrm.predict_proba(np.column_stack([np.log(mk / (1 - mk)), Xte]))[:, 1]
    sub = key[ite].reset_index(drop=True)
    for i in range(len(sub)):
        # keyed on the PAIR, carrying every date the archive holds it on. The log's date and
        # the archive's disagree constantly -- measured on the 509 misses from the exact-date
        # version, 402 of them (79%) were a pure date mismatch: off by one day for 208, two for
        # 81. That is the same fixture-date-vs-local-date drift behind the timezone rollover
        # bug, not a different match. So resolve the date by nearest-within-tolerance instead
        # of demanding equality.
        pair = tuple(sorted((str(sub.at[i, "player_slug"]), str(sub.at[i, "rival_slugname"]))))
        preds.setdefault(pair, []).append(
            (str(sub.at[i, "date"])[:10], float(p[i]), float(pma[i])))
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


TOL = 3          # days; beyond this it is a different meeting, not a date discrepancy
out, miss_slug, miss_row, ambiguous, offs = [], 0, 0, 0, {}
for r in need.itertuples():
    s1, s2 = slug(r.player_1), slug(r.player_2)
    if not s1 or not s2:
        miss_slug += 1
        continue
    cands = preds.get(tuple(sorted((s1, s2))))
    if not cands:
        miss_row += 1
        continue
    # nearest archive date within tolerance. If two candidate meetings sit the SAME distance
    # away, the pair played twice that week and there is no way to tell which row is this match
    # -- skip rather than guess, because attributing the wrong probability to a settled result
    # would quietly corrupt the record this whole exercise exists to produce.
    scored = sorted((abs((pd.Timestamp(d) - pd.Timestamp(r.d)).days), d, pg, pma)
                    for d, pg, pma in cands)
    if scored[0][0] > TOL:
        miss_row += 1
        continue
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        ambiguous += 1
        continue
    off, _d, pg, pma = scored[0]
    offs[off] = offs.get(off, 0) + 1
    # the archive pair is oriented player_slug < rival_slugname; flip when the log's player_1
    # is the HIGHER slug, or every probability lands on the wrong player
    flip = not (s1 < s2)
    out.append({"date": r.d, "player_1": r.player_1, "player_2": r.player_2,
                "model_g_p1": round(1 - pg if flip else pg, 4),
                "model_gma_p1": round(1 - pma if flip else pma, 4)})

fill = pd.DataFrame(out)
fill.to_parquet("data_cache/_model_g_recon_fill.parquet")
print("\nfilled %d / %d   (no slug %d, pair not in the as-of archive %d, ambiguous date %d)"
      % (len(fill), len(need), miss_slug, miss_row, ambiguous), flush=True)
print("date offset between the log and the archive: %s"
      % dict(sorted(offs.items())), flush=True)

if len(fill):
    # join on the fill's own key; the suffix cannot be relied on because a log that predates
    # the model has no model_g_p1 column at all, in which case nothing collides
    res = need[["d", "player_1", "player_2", "p1_won"]].merge(
        fill.rename(columns={"date": "d", "model_g_p1": "_g"})[["d", "player_1", "player_2", "_g"]],
        on=["d", "player_1", "player_2"], how="inner")
    acc = ((res["_g"] >= 0.5) == res["p1_won"].astype(bool)).mean()
    print("sanity, DISPLAY-ONLY and not a forward record: recon picked the winner %.1f%% of %d"
          % (100 * acc, len(res)), flush=True)

# ===========================================================================================
# DIRECT AS-OF FALLBACK (2026-10-12). The paired-archive lookup above cannot reach a match
# whose two sides were never both ingested -- 219 rows after the date fix, every one of them
# with both players fully priceable. That dependency is incidental: the paired frame is only how
# the BUILD convenes a training row, and nothing about scoring needs it. So for whatever the
# lookup missed, rebuild each player's as-of window straight from the archive and score it the
# way predict_g does live.
#
# Leakage discipline is unchanged and if anything tighter: windows are strictly date < match
# day, the rank-discount curves and shrinkage constants were frozen on 2015-23, and the scorer
# is still the one trained only on seasons before the row's year. The market for the
# market-aware head comes from the LOG's own frozen closing odds, which is the real price this
# card was shown at rather than whatever the archive later recorded.
# ===========================================================================================
import tennis_model_a as _T
import gc  # noqa: E402

MDL = _T.g_model()
if MDL is not None and (miss_row or miss_slug):
    # free the build frame before loading the archive again -- holding both is what killed the
    # G2 recon (OOM at 5.7GB RSS, 2026-10-13 01:32Z)
    for _n in ("core", "m", "key", "ns"):
        if _n in dir():
            del globals()[_n]
    gc.collect()
    raw2 = _T._parse(pd.read_parquet(_T.LOGS_PARQUET))
    raw2["date"] = pd.to_datetime(raw2["date"]).dt.normalize()
    raw2["surf"] = raw2["surface"].astype(str).str.title()
    bysurf = {k: v.sort_values("date") for k, v in raw2.groupby(["player_slug", "surf"])}
    EDGES = np.asarray(MDL["bin_edges"], dtype=float)
    NBIN = len(EDGES) - 1
    GENDER = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()

    def _win(sl, surf, day):
        """The player's as-of window: prior 365 days on this surface, or the last 20 on it when
        that holds under five. Identical rule to the build and to _profile."""
        on = bysurf.get((sl, str(surf or "").title()))
        if on is None or not len(on):
            return None, 0.0
        before = on[on["date"] < pd.Timestamp(day)]
        if not len(before):
            return None, 0.0
        w = before[before["date"] >= pd.Timestamp(day) - pd.Timedelta(days=365)]
        if len(w) >= 5:
            return w, 0.0
        return before.tail(20), 1.0

    def _stats(w, gd):
        """The nine figures, opponent-rank-discounted then shrunk by each one's own denominator."""
        out = {}
        b = np.clip(np.searchsorted(EDGES, w["logr"].to_numpy(float), side="left") - 1, 0, NBIN - 1)
        for nm, num, den in _T.G_STATS:
            if den is None:
                r = pd.to_numeric(w[num], errors="coerce").astype(float)
                if nm != "win":
                    r = r / 100.0
                r = r.where(r.between(0, 1))
                d = r.notna().astype(float)
            else:
                dd = pd.to_numeric(w[den], errors="coerce").astype(float).replace(0, np.nan)
                r = pd.to_numeric(w[num], errors="coerce").astype(float) / dd
                d = dd.where(r.notna())
            ok = r.notna().to_numpy() & np.isfinite(d.to_numpy(float))
            dv = np.where(ok, d.to_numpy(float), 0.0)
            rv = np.where(ok, r.to_numpy(float), 0.0)
            if dv.sum() <= 0:
                out[nm] = (None, 0.0)
                continue
            eff = np.asarray(MDL["opp_eff"].get((gd, nm), np.zeros(NBIN)), dtype=float)
            k = float(MDL["k"].get((gd, nm), 1.0))
            pr = float(MDL["prior"].get((gd, nm), 0.0))
            num_ = (rv * dv).sum() - (eff[b] * dv).sum()
            out[nm] = ((num_ + k * pr) / (dv.sum() + k), float(dv.sum()))
        return out

    import sklearn  # noqa: F401
    direct, dmiss = [], 0
    for r in need.itertuples():
        s1, s2 = slug(r.player_1), slug(r.player_2)
        if not s1 or not s2:
            dmiss += 1
            continue
        if any(x["date"] == r.d and x["player_1"] == r.player_1 for x in out):
            continue                                  # the paired lookup already covered it
        yr = int(str(r.d)[:4])
        if yr not in fitted:
            dmiss += 1
            continue
        lg = str(getattr(r, "league", "") or "").lower()
        gd = "W" if lg in ("wta", "itf_women") else "M"
        surf = getattr(r, "surface", None)
        w1, wd1 = _win(s1, surf, r.d)
        w2, wd2 = _win(s2, surf, r.d)
        if w1 is None or w2 is None:
            dmiss += 1
            continue
        a, bb = _stats(w1, gd), _stats(w2, gd)
        f = {}
        for nm, _, _ in _T.G_STATS:
            v1, d1 = a[nm]
            v2, d2 = bb[nm]
            f["d_" + nm] = (v1 - v2) if (v1 is not None and v2 is not None) else 0.0
            f["dn_" + nm] = float(np.log1p(d1) - np.log1p(d2))
        n1, n2 = float(len(w1)), float(len(w2))
        f["d_matches"] = float(np.log1p(n1) - np.log1p(n2))
        f["f_nmin"] = float(np.log1p(min(n1, n2)))
        fa1 = float(w1["logr"].dropna().mean()) if w1["logr"].notna().any() else None
        fa2 = float(w2["logr"].dropna().mean()) if w2["logr"].notna().any() else None
        f["d_faced"] = float(fa2 - fa1) if (fa1 is not None and fa2 is not None) else 0.0
        f["f_wide"] = float(wd1) + float(wd2)
        lr_, bst_, lrm_ = fitted[yr]
        X1 = np.array([[f.get(k, 0.0) for k in MDL["features"]]])
        pg = float(0.5 * (lr_.predict_proba(X1)[0, 1] + bst_.predict_proba(X1)[0, 1]))
        o1, o2 = getattr(r, "p1_odds", None), getattr(r, "p2_odds", None)
        pma = None
        try:
            d1o, d2o = _dec(o1), _dec(o2)
            if d1o and d2o:
                mk = (1 / d1o) / ((1 / d1o) + (1 / d2o))
                pma = float(lrm_.predict_proba(
                    np.column_stack([[np.log(mk / (1 - mk))], X1]))[0, 1])
        except Exception:  # noqa: BLE001
            pma = None
        direct.append({"date": r.d, "player_1": r.player_1, "player_2": r.player_2,
                       "model_g_p1": round(pg, 4),
                       "model_gma_p1": None if pma is None else round(pma, 4)})
    print("\ndirect as-of fallback: priced %d more, still unreachable %d"
          % (len(direct), dmiss), flush=True)
    if direct:
        fill = pd.concat([fill, pd.DataFrame(direct)], ignore_index=True)
        fill.to_parquet("data_cache/_model_g_recon_fill.parquet")
        res2 = need[["d", "player_1", "player_2", "p1_won"]].merge(
            pd.DataFrame(direct).rename(columns={"date": "d", "model_g_p1": "_g"}),
            on=["d", "player_1", "player_2"], how="inner")
        if len(res2):
            print("   sanity on the direct rows: picked the winner %.1f%% of %d"
                  % (100 * ((res2["_g"] >= 0.5) == res2["p1_won"].astype(bool)).mean(), len(res2)),
                  flush=True)

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
    if RESCORE and "model_g_recon" in L.columns:
        _o = L["model_g_recon"].fillna(False).astype(bool)
        L.loc[_o, "model_g_p1"] = np.nan   # clear the stale batch here too, so it can be rewritten
        L.loc[_o, "model_gma_p1"] = np.nan
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
