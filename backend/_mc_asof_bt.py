"""AS-OF BACKTEST OF THE LIVE MONTE CARLOS (2026-10-08, user: "not just mc2, every monte
carlo we have c50 c75 mc 1").

Earlier tonight I said the sims couldn't be archive-backtested. That was wrong:
tennis_model_a._profile(gdf, today) is as-of aware, so historical profiles CAN be rebuilt
and injected into the module cache, and the PRODUCTION simulate_match then runs on them.

HONEST DESIGN
  * Weekly as-of buckets: for each test week, profiles are built from archive rows strictly
    BEFORE that week's Monday, so no match sees itself or anything after it. (Live rebuilds
    daily, so <=6 days of extra staleness here -- conservative, slightly handicaps the sim.)
  * rank_proxy and opp_form are recomputed on the historical slice only (the production
    _load computes rank_proxy from the LATEST known opponent rank over the whole file,
    which would leak future ranks into a retro run).
  * The Model-C anchor is the CLEAN walk-forward C (train < 2026), never production C.
  * sutr_weight is forced to 0.0 everywhere, which is exactly the production c50/c75
    recipe, and gives a pure-serve variant for the plain MC. **cUTR is NOT backtestable**:
    it anchors on the sUTR artifact, which holds current ratings only (retro = leakage).
  * n=3000 sims/match (set-level randomness, exact game math -> prob SE ~0.9pt, averages
    out across the sample); flat 1u at the archive's own closing odds.

Variants: mc1_serve (no anchor), c50 (c_weight .50), c75 (c_weight .75).
Cells: dog side / fav side, by gender, plus the +100..+200 dog and -150..-300 fav bands.
"""
import os
import sys

import numpy as np
import pandas as pd

import tennis_model_a as T

SAMPLE = int(sys.argv[1]) if len(sys.argv) > 1 else 2400
NSIM = 3000
rng = np.random.default_rng(11)

# ---- clean walk-forward C for 2026 (the anchor), from the backtest rig -------------
ns = {}
src = open("_tennis_abc6_agree_bt.py", encoding="utf-8").read()
exec(compile(src.split("tot = {")[0], "_prep6", "exec"), ns)
KEY = ns["KEY"]
core_c, FC_C = ns["core_c"], ns["FC_C"]
from sklearn.linear_model import LogisticRegression
import xgboost as xgb

tr = core_c[core_c["date"].dt.year < 2026]
te = core_c[core_c["date"].dt.year == 2026]
lr = LogisticRegression(max_iter=3000, C=0.5).fit(tr[FC_C].fillna(0), tr["won"])
bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                        colsample_bytree=0.8, n_jobs=8, eval_metric="logloss").fit(
    tr[FC_C].fillna(0), tr["won"])
pC = 0.5 * (lr.predict_proba(te[FC_C].fillna(0))[:, 1] + bst.predict_proba(te[FC_C].fillna(0))[:, 1])
cleanC = {}
for k, pr, w, m1, oa, ob in zip(te[KEY].itertuples(index=False, name=None), pC, te["won"].values,
                                te["mkt"].values, te["player_odd"].values, te["rival_odd"].values):
    cleanC[(pd.Timestamp(k[0]).normalize(), str(k[1]), str(k[2]))] = (float(pr), bool(w), float(m1),
                                                                      float(oa) if oa else None)
print(f"clean C 2026 rows: {len(cleanC)}", flush=True)

# ---- test universe: 2026 archive rows that have a clean-C prob + usable odds --------
df_all = T._parse(pd.read_parquet(T.LOGS_PARQUET))
df_all["date"] = pd.to_datetime(df_all["date"]).dt.normalize()
cand = df_all[(df_all["date"].dt.year == 2026) & df_all["rival_slugname"].notna()].copy()
keys = list(zip(cand["date"], cand["player_slug"].astype(str), cand["rival_slugname"].astype(str)))
cand["_k"] = keys
cand = cand[cand["_k"].isin(cleanC.keys())]
# one row per match (the rig has both orientations; keep the lexicographically-first side)
cand = cand[cand["player_slug"].astype(str) < cand["rival_slugname"].astype(str)]
# TRUE GENDER (2026-10-08 fix): tournament_level says only "futures" for ITF, so a
# level-based rule files every women's ITF match as MEN. Use the slug gender map.
_GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
cand["isW"] = cand["player_slug"].astype(str).map(_GM).eq("W")
print(f"candidate 2026 matches: {len(cand)}  (W {int(cand['isW'].sum())})", flush=True)
if len(cand) > SAMPLE:
    cand = cand.iloc[rng.choice(len(cand), SAMPLE, replace=False)]
cand = cand.sort_values("date")
cand["wk"] = cand["date"] - pd.to_timedelta(cand["date"].dt.dayofweek, unit="D")
print(f"sampled: {len(cand)} matches across {cand['wk'].nunique()} weeks", flush=True)

MTIME = os.path.getmtime(T.LOGS_PARQUET)
SURF_OK = True


def build_asof(cutoff, slugs):
    """Inject as-of profiles for `slugs` (history strictly before `cutoff`)."""
    hist = df_all[df_all["date"] < cutoff]
    own = (hist[["rival_slugname", "date", "rival_rank"]].dropna()
           .sort_values("date").groupby("rival_slugname")["rival_rank"].last())
    hist = hist[hist["player_slug"].isin(slugs)].copy()
    if not len(hist):
        return 0
    hist["rank_proxy"] = hist["player_slug"].map(own)
    hist = hist.sort_values(["player_slug", "date"], kind="stable").reset_index(drop=True)
    s0 = hist.groupby("player_slug", sort=False)["won"].shift(1)
    hist["_o10w"] = (s0.groupby(hist["player_slug"]).rolling(10, min_periods=4).mean()
                     .reset_index(level=0, drop=True))
    hist["opp_form"] = np.nan          # opponents' as-of form: not needed by the sim block
    sl = hist["tournament_level"].astype(str).str.lower()
    hist["lvl"] = np.where(sl.str.contains("challenger"), 1,
                           np.where(sl.str.contains("future") | sl.str.contains("itf"), 2, 0))
    profiles = {slug: T._profile(g, cutoff) for slug, g in hist.groupby("player_slug")}
    T._cache.update({"mtime": MTIME, "profiles": profiles, "h2h": {},
                     "name_map": {T._norm_name(T._slug_name(s)): s for s in profiles},
                     "sutr": None, "sutr_mtime": None})
    return len(profiles)


VAR = (("mc1_serve", None, None), ("c50", 0.50, "c"), ("c75", 0.75, "c"))
rows = []
for wk, g in cand.groupby("wk"):
    slugs = set(g["player_slug"].astype(str)) | set(g["rival_slugname"].astype(str))
    if not build_asof(wk, slugs):
        continue
    for r in g.itertuples():
        k = (r.date, str(r.player_slug), str(r.rival_slugname))
        cc = cleanC.get(k)
        if cc is None:
            continue
        pc, won, mkt, oa = cc
        ob = None
        try:
            ob = float(r.rival_odd) if r.rival_odd and float(r.rival_odd) > 1 else None
        except (TypeError, ValueError):
            ob = None
        if not oa or not ob or oa <= 1 or ob <= 1:
            continue
        n1, n2 = T._slug_name(str(r.player_slug)), T._slug_name(str(r.rival_slugname))
        out = {"won": won, "mkt": mkt, "oa": oa, "ob": ob, "isW": bool(r.isW), "date": r.date}
        ok = False
        for name, cw, kind in VAR:
            try:
                sim = T.simulate_match(n1, n2, r.surface, level=r.tournament_level, n=NSIM,
                                       c_anchor=(pc if kind == "c" else None),
                                       c_weight=(cw if kind == "c" else 0.5),
                                       sutr_weight=0.0)
            except Exception:  # noqa: BLE001
                sim = None
            out[name] = (sim["p1_pct"] / 100.0) if (sim and sim.get("p1_pct") is not None) else None
            ok = ok or out[name] is not None
        if ok:
            rows.append(out)
    print(f"  {wk.date()}  cum rows {len(rows)}", flush=True)

D = pd.DataFrame(rows)
D.to_parquet("data_cache/_mc_asof_bt_rows.parquet")
print(f"\nSIMULATED: {len(D)} matches ({int(D['isW'].sum())} women)\n", flush=True)


def report(label, sub, col, want_dog, band=None):
    s = sub[sub[col].notna()].copy()
    if not len(s):
        return
    pick_a = s[col] >= 0.5
    dog_a = s["mkt"] < 0.5
    keep = pick_a == (dog_a if want_dog else ~dog_a)
    s, pick_a = s[keep], pick_a[keep]
    od = np.where(pick_a, s["oa"], s["ob"])
    if band is not None:
        m = (od >= band[0]) & (od <= band[1])
        s, pick_a, od = s[m], pick_a[m], od[m]
    if len(s) < 20:
        return
    won = np.where(pick_a, s["won"].astype(bool), ~s["won"].astype(bool))
    pnl = np.where(won, od - 1.0, -1.0)
    print(f"  {label:30s} {int(won.sum())}-{int((~won).sum())}  win {100*won.mean():.1f}%  "
          f"ROI {100*pnl.mean():+.1f}%  (n={len(s)})", flush=True)


for col in ("mc1_serve", "c50", "c75"):
    for gl, gs in (("MEN", D[~D["isW"]]), ("WOMEN", D[D["isW"]])):
        print(f"=== {col} / {gl} ===")
        report("dog side (all prices)", gs, col, True)
        report("dog +100..+200", gs, col, True, (2.0, 3.0))
        report("fav side (all prices)", gs, col, False)
        report("fav -150..-300", gs, col, False, (1.333, 1.667))
    print()
