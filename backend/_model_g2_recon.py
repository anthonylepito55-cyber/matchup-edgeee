"""MODEL G2 HISTORY RECON (2026-10-12, user "And I want g2 to show on previous day slips also" /
"the games we've already logged").

G2 only started logging at 01:00Z, so without this the previous-day slips show it on nothing.
This prices every settled log row directly from the archive, which is the path that took G from
84.5% to 99.1%: it rebuilds each player's as-of windows itself rather than depending on the
archive having convened a paired training row for that match.

HONESTY CONTRACT (the model_x_recon / mc2_recon pattern):
  * the scorer for a row is trained ONLY on seasons strictly before that row's year;
  * both windows are strictly `date < match day` -- the 365-day-or-last-20 surface window G uses,
    and the last-10-completed-on-this-surface block G2 adds;
  * walkovers and retirements are dropped from the last-10 block, same rule as live;
  * the rank-discount curves and shrinkage constants were frozen on 2015-23, so they are
    out-of-sample for every row here;
  * the result column is never read while producing a probability -- only once at the end, for a
    display-only sanity print;
  * output is stamped model_g2_recon=True, which the g2_* lanes drop and the history dims with a
    ~. The lanes are additionally gated on start_time >= G2_LIVE_FROM, so a backfill cannot reach
    the money tracker by either route.

The market-aware head uses the LOG's own frozen closing odds, which is the price the card
actually carried rather than whatever the archive later recorded.

Usage:  python _model_g2_recon.py [log_path] [--apply]
"""
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
import xgboost as xgb

import tennis_model_a as T

args = [a for a in sys.argv[1:] if not a.startswith("--")]
APPLY = "--apply" in sys.argv
LOGP = args[0] if args else "data_cache/tennis_prediction_log.parquet"

MDL = T.g2_model()
if MDL is None:
    raise SystemExit("G2 artifact not built")

log = pd.read_parquet(LOGP)
log["d"] = log["date"].astype(str).str[:10]
have = log["model_g2_p1"].notna() if "model_g2_p1" in log.columns else pd.Series(False, index=log.index)
need = log[log["p1_won"].notna() & ~have].copy()
print("settled log rows missing G2: %d  (%s .. %s)"
      % (len(need), need["d"].min() if len(need) else "-", need["d"].max() if len(need) else "-"),
      flush=True)
if not len(need):
    raise SystemExit("nothing to backfill")

# ---- the training frame, straight from the G2 build (as-of by construction) ----
ns = {}
src = open("_tennis_model_g2_build.py", encoding="utf-8").read()
MARK = chr(10) + "from sklearn.linear_model import LogisticRegression"
exec(compile(src[:src.index(MARK)], "_g2", "exec"), ns)
core, FC = ns["core"].reset_index(drop=True), ns["FC"]
print("G2 core: %d rows, %d features" % (len(core), len(FC)), flush=True)

yrs = sorted({int(y) for y in pd.to_datetime(need["d"]).dt.year.unique()})
fitted = {}
for yr in yrs:
    itr = (core["date"].dt.year < yr).to_numpy()
    if itr.sum() < 5000:
        print("  %d: only %d earlier rows, skipped" % (yr, int(itr.sum())), flush=True)
        continue
    Xtr, ytr = core.loc[itr, FC].fillna(0), core.loc[itr, "won"]
    lr = LogisticRegression(max_iter=3000, C=0.5).fit(Xtr, ytr)
    bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                            colsample_bytree=0.8, n_jobs=8, eval_metric="logloss").fit(Xtr, ytr)
    mk = np.clip(core.loc[itr, "mkt"].to_numpy(float), 1e-6, 1 - 1e-6)
    lrm = LogisticRegression(max_iter=3000, C=0.5).fit(
        np.column_stack([np.log(mk / (1 - mk)), Xtr]), ytr)
    fitted[yr] = (lr, bst, lrm)
    print("  %d: trained on %d earlier rows" % (yr, int(itr.sum())), flush=True)

# ---- as-of windows, rebuilt per player ----
raw = T._parse(pd.read_parquet(T.LOGS_PARQUET))
raw["date"] = pd.to_datetime(raw["date"]).dt.normalize()
raw["surf"] = raw["surface"].astype(str).str.title()
raw["wo"] = T._walkover_mask(raw)
bysurf = {k: v.sort_values("date") for k, v in raw.groupby(["player_slug", "surf"])}
EDGES = np.asarray(MDL["bin_edges"], dtype=float)
NBIN = len(EDGES) - 1
rc = {}


def slug(nm):
    if nm not in rc:
        try:
            rc[nm] = T.resolve(nm)
        except Exception:  # noqa: BLE001
            rc[nm] = None
    return rc[nm]


def _dec(am):
    try:
        a = float(am)
    except (TypeError, ValueError):
        return None
    if a == 0:
        return None
    return 1 + a / 100.0 if a > 0 else 1 + 100.0 / abs(a)


def windows(sl, surf, day):
    """(52w-or-last-20 window, widened flag, last-10-completed window). All strictly prior."""
    on = bysurf.get((sl, str(surf or "").title()))
    if on is None or not len(on):
        return None, 0.0, None
    before = on[on["date"] < pd.Timestamp(day)]
    if not len(before):
        return None, 0.0, None
    w = before[before["date"] >= pd.Timestamp(day) - pd.Timedelta(days=365)]
    wide = 0.0
    if len(w) < 5:
        w, wide = before.tail(20), 1.0
    comp = before[~before["wo"]]
    t10 = comp.tail(10) if len(comp) >= 3 else None
    return (w if len(w) else None), wide, t10


def stats52(w, gd):
    out = {}
    b = np.clip(np.searchsorted(EDGES, w["logr"].to_numpy(float), side="left") - 1, 0, NBIN - 1)
    for nm, num, den in T.G_STATS:
        if den is None:
            r = pd.to_numeric(w[num], errors="coerce").astype(float)
            if nm != "win":
                r = r / 100.0
            r = r.where(r.between(0, 1))
            dd = r.notna().astype(float)
        else:
            dv = pd.to_numeric(w[den], errors="coerce").astype(float).replace(0, np.nan)
            r = pd.to_numeric(w[num], errors="coerce").astype(float) / dv
            dd = dv.where(r.notna())
        ok = r.notna().to_numpy() & np.isfinite(dd.to_numpy(float))
        d_ = np.where(ok, dd.to_numpy(float), 0.0)
        r_ = np.where(ok, r.to_numpy(float), 0.0)
        if d_.sum() <= 0:
            out[nm] = (None, 0.0)
            continue
        eff = np.asarray(MDL["opp_eff"].get((gd, nm), np.zeros(NBIN)), dtype=float)
        k = float(MDL["k"].get((gd, nm), 1.0))
        pr = float(MDL["prior"].get((gd, nm), 0.0))
        out[nm] = (((r_ * d_).sum() - (eff[b] * d_).sum() + k * pr) / (d_.sum() + k), float(d_.sum()))
    return out


def block10(t):
    if t is None or not len(t):
        return {}
    def mn(v):
        v = pd.to_numeric(v, errors="coerce").dropna()
        return float(v.mean()) if len(v) else None
    wl = t.loc[t["won"] == 1, "logr"].dropna()
    ll = t.loc[t["won"] == 0, "logr"].dropna()
    sga = t["sg_all"].replace(0, np.nan)
    rga = t["rg_all"].replace(0, np.nan)
    return {"t10_win": float(t["won"].mean()), "t10_faced": mn(t["logr"]),
            "t10_beaten": float(wl.mean()) if len(wl) else None,
            "t10_bestwin": float(wl.min()) if len(wl) else None,
            "t10_lost": float(ll.mean()) if len(ll) else None,
            "t10_worstloss": float(ll.max()) if len(ll) else None,
            "t10_meff": mn(t["meff"]), "t10_losscl": mn(t["l_meff"]),
            "t10_hold": mn(t["sg_won"] / sga), "t10_brk": mn(t["rg_won"] / rga),
            "t10_n": float(len(t))}


out, miss = [], {"slug": 0, "year": 0, "window": 0}
for r in need.itertuples():
    s1, s2 = slug(r.player_1), slug(r.player_2)
    if not s1 or not s2:
        miss["slug"] += 1
        continue
    yr = int(str(r.d)[:4])
    if yr not in fitted:
        miss["year"] += 1
        continue
    lg = str(getattr(r, "league", "") or "").lower()
    gd = "W" if lg in ("wta", "itf_women") else "M"
    surf = getattr(r, "surface", None)
    w1, wd1, t1w = windows(s1, surf, r.d)
    w2, wd2, t2w = windows(s2, surf, r.d)
    if w1 is None or w2 is None:
        miss["window"] += 1
        continue
    a, b = stats52(w1, gd), stats52(w2, gd)
    t1, t2 = block10(t1w), block10(t2w)
    f = {}
    for nm, _, _ in T.G_STATS:
        v1, d1 = a[nm]
        v2, d2 = b[nm]
        f["d_" + nm] = (v1 - v2) if (v1 is not None and v2 is not None) else 0.0
        f["dn_" + nm] = float(np.log1p(d1) - np.log1p(d2))
    n1, n2 = float(len(w1)), float(len(w2))
    f["d_matches"] = float(np.log1p(n1) - np.log1p(n2))
    f["f_nmin"] = float(np.log1p(min(n1, n2)))
    fa1 = float(w1["logr"].dropna().mean()) if w1["logr"].notna().any() else None
    fa2 = float(w2["logr"].dropna().mean()) if w2["logr"].notna().any() else None
    f["d_faced"] = float(fa2 - fa1) if (fa1 is not None and fa2 is not None) else 0.0
    f["f_wide"] = float(wd1) + float(wd2)

    def d_(nm, flip=False):
        x, y = t1.get(nm), t2.get(nm)
        if x is None or y is None:
            return 0.0
        return float(y - x) if flip else float(x - y)
    for nm in ("t10_win", "t10_meff", "t10_hold", "t10_brk", "t10_losscl"):
        f["d_" + nm] = d_(nm)
    for nm in ("t10_faced", "t10_beaten", "t10_bestwin", "t10_lost", "t10_worstloss"):
        f["d_" + nm] = d_(nm, flip=True)
    f["d_t10_n"] = float((t1.get("t10_n") or 0) - (t2.get("t10_n") or 0))
    f["f_t10_nmin"] = float(min(t1.get("t10_n") or 0, t2.get("t10_n") or 0))

    lr_, bst_, lrm_ = fitted[yr]
    X = np.array([[f.get(k, 0.0) for k in MDL["features"]]])
    pg = float(0.5 * (lr_.predict_proba(X)[0, 1] + bst_.predict_proba(X)[0, 1]))
    pma = None
    d1o, d2o = _dec(getattr(r, "p1_odds", None)), _dec(getattr(r, "p2_odds", None))
    if d1o and d2o:
        mk = (1 / d1o) / ((1 / d1o) + (1 / d2o))
        try:
            pma = float(lrm_.predict_proba(
                np.column_stack([[np.log(mk / (1 - mk))], X]))[0, 1])
        except Exception:  # noqa: BLE001
            pma = None
    out.append({"date": r.d, "player_1": r.player_1, "player_2": r.player_2,
                "model_g2_p1": round(pg, 4),
                "model_g2ma_p1": None if pma is None else round(pma, 4)})

fill = pd.DataFrame(out)
fill.to_parquet("data_cache/_model_g2_recon_fill.parquet")
print("\nfilled %d / %d   (no slug %d, no earlier-season model %d, no usable window %d)"
      % (len(fill), len(need), miss["slug"], miss["year"], miss["window"]), flush=True)

if len(fill):
    res = need[["d", "player_1", "player_2", "p1_won"]].merge(
        fill.rename(columns={"date": "d", "model_g2_p1": "_g"})[["d", "player_1", "player_2", "_g"]],
        on=["d", "player_1", "player_2"], how="inner")
    print("sanity, DISPLAY-ONLY and not a forward record: recon picked the winner %.1f%% of %d"
          % (100 * ((res["_g"] >= 0.5) == res["p1_won"].astype(bool)).mean(), len(res)), flush=True)

if APPLY and len(fill):
    L = pd.read_parquet(LOGP)
    for c in ("model_g2_p1", "model_g2ma_p1"):
        if c not in L.columns:
            L[c] = np.nan
    if "model_g2_recon" not in L.columns:
        L["model_g2_recon"] = False
    L["_d"] = L["date"].astype(str).str[:10]
    idx = {(x.date, x.player_1, x.player_2): (x.model_g2_p1, x.model_g2ma_p1)
           for x in fill.itertuples()}
    n = 0
    for i in L.index:
        if pd.notna(L.at[i, "model_g2_p1"]):
            continue                      # never overwrite a genuine frozen value
        v = idx.get((L.at[i, "_d"], L.at[i, "player_1"], L.at[i, "player_2"]))
        if v is None:
            continue
        L.at[i, "model_g2_p1"], L.at[i, "model_g2ma_p1"] = v
        L.at[i, "model_g2_recon"] = True
        n += 1
    L.drop(columns=["_d"]).to_parquet(LOGP)
    print("applied %d recon rows to %s (stamped model_g2_recon=True)" % (n, LOGP), flush=True)
elif len(fill):
    print("\ndry run -- rerun with --apply to merge into the log", flush=True)
