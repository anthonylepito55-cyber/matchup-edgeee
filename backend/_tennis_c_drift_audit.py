# TENNIS MODEL C DRIFT AUDIT (2026-10-08): is live-served C systematically different from
# the clean walk-forward C on IDENTICAL games? Mirrors the 2026-09-25 MLB Model-E audit.
# Live C = frozen model_c_p1 in the prediction log (served from the Sep-28 joblib).
# Clean C = rig fit, train < 2026, predict 2026 (strictly out-of-sample).
import numpy as np
import pandas as pd

ns = {}
src = open("_tennis_abc6_agree_bt.py", encoding="utf-8").read()
exec(compile(src.split("tot = {")[0], "_prep6", "exec"), ns)
KEY = ns["KEY"]
core_c, FC_C = ns["core_c"], ns["FC_C"]
print("core ready", flush=True)
from sklearn.linear_model import LogisticRegression
import xgboost as xgb

def lg(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))

yr = 2026
tr = core_c[core_c["date"].dt.year < yr]
te = core_c[core_c["date"].dt.year == yr]
Xtr, Xte = tr[FC_C].fillna(0), te[FC_C].fillna(0)
ytr = tr["won"]
lr = LogisticRegression(max_iter=3000, C=0.5).fit(Xtr, ytr)
bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                        colsample_bytree=0.8, n_jobs=8, eval_metric="logloss").fit(Xtr, ytr)
p_clean = 0.5 * (lr.predict_proba(Xte)[:, 1] + bst.predict_proba(Xte)[:, 1])
clean = {}
for k, pr, w, m1 in zip(te[KEY].itertuples(index=False, name=None), p_clean,
                        te["won"].values, te["mkt"].values):
    d = str(k[0])[:10]
    clean[(d, str(k[1]), str(k[2]))] = (float(pr), bool(w), float(m1))
print(f"clean 2026 rows: {len(clean)}", flush=True)

import tennis_context as tc
log = pd.read_parquet("data_cache/_ec2_log_snapshot.parquet")
log = log[log["p1_won"].notna() & log["model_c_p1"].notna()].copy()
log["d"] = log["date"].astype(str).str[:10]
log = log[log["d"] >= "2026-01-01"]
print(f"live settled rows with C: {len(log)}", flush=True)

rows = []
for r in log.itertuples():
    try:
        g1 = tc.get_context(r.player_1, getattr(r, "surface", None))
        g2 = tc.get_context(r.player_2, getattr(r, "surface", None))
    except Exception:  # noqa: BLE001
        continue
    if not g1 or not g2:
        continue
    s1, s2 = str(g1["slug"]), str(g2["slug"])
    hit = clean.get((r.d, s1, s2))
    flip = False
    if hit is None:
        hit = clean.get((r.d, s2, s1))
        flip = True
    if hit is None:
        continue
    pc, won, mkt = hit
    clean_p1 = (1 - pc) if flip else pc
    mkt_p1 = (1 - mkt) if flip else mkt
    rows.append({"live": float(r.model_c_p1), "clean": clean_p1, "mkt": mkt_p1,
                 "p1_won": bool(r.p1_won), "date": r.d})
D = pd.DataFrame(rows)
print(f"\nJOINED ON IDENTICAL GAMES: {len(D)}")
if not len(D):
    raise SystemExit("no overlap -- check slug/date join")
# orient every number to the MARKET FAVORITE side
fav1 = D["mkt"] >= 0.5
live_fav = np.where(fav1, D["live"], 1 - D["live"])
clean_fav = np.where(fav1, D["clean"], 1 - D["clean"])
mkt_fav = np.where(fav1, D["mkt"], 1 - D["mkt"])
won_fav = np.where(fav1, D["p1_won"], ~D["p1_won"])
print(f"mean |live - clean|      = {100*np.mean(np.abs(live_fav-clean_fav)):.2f} pts")
print(f"FAV-SIDE PUSH live-clean = {100*np.mean(live_fav-clean_fav):+.2f} pts")
for lo, hi, lab in ((0.5, 0.6, "fav 50-60%"), (0.6, 0.7, "fav 60-70%"), (0.7, 1.01, "fav 70%+")):
    msk = (mkt_fav >= lo) & (mkt_fav < hi)
    if msk.sum() >= 10:
        print(f"  {lab:12s} n={msk.sum():4d}  push {100*np.mean(live_fav[msk]-clean_fav[msk]):+.2f} pts")
bs = lambda p: float(np.mean((p - won_fav.astype(float)) ** 2))
print(f"Brier  live {bs(live_fav):.4f} | clean {bs(clean_fav):.4f} | market {bs(mkt_fav):.4f}")
# the CE5 cell specifically: how often does each version fire a 5pt+ fav edge, and does it win?
for nm, arr in (("live", live_fav), ("clean", clean_fav)):
    fire = arr - mkt_fav >= 0.05
    if fire.sum():
        print(f"CE5 fav-edge fires ({nm}): n={fire.sum():4d}  fav win rate {100*np.mean(won_fav[fire]):.1f}%"
              f"  (market expected {100*np.mean(mkt_fav[fire]):.1f}%)")
