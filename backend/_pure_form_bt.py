"""PURE-FORM AS-OF BACKTEST (2026-10-08, user: "test it").

Pure form was shipped forward-only on the grounds that it couldn't be backtested -- but
tennis_pure_form.form(slug, surface, asof=...) is as-of aware, so it CAN be replayed
historically with no leakage (the `asof` cut only ever reads matches strictly before the
date, inside a 540-day cap).

Tests, 2024-26, flat 1u at the archive's own closing odds, true gender, one row per match:
  1. standalone -- back the player in better quality-adjusted recent form (dog/fav split)
  2. contrarian -- fade that player (the live doctrine's claim)
  3. form vs the market -- does form add anything once the price is known
  4. form x Model C -- the shipped use is "C/c75 and form DISAGREE"; replayed against the
     clean walk-forward C, split by whether C's side is the dog or the favourite
"""
import numpy as np
import pandas as pd

import tennis_pure_form as pf

ns = {}
src = open("_tennis_abc6_agree_bt.py", encoding="utf-8").read()
exec(compile(src.split("tot = {")[0], "_prep6", "exec"), ns)
KEY = ns["KEY"]
core_c, FC_C = ns["core_c"], ns["FC_C"]
mC = ns["mC"] if "mC" in ns else ns["m"]
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
surf = {}
for k, sf in zip(mC[KEY].itertuples(index=False, name=None), mC["surface"].astype(str)):
    surf[k] = sf.title()
print("prep done", flush=True)
from sklearn.linear_model import LogisticRegression
import xgboost as xgb


def lgit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


rows = []
for yr in (2024, 2025, 2026):
    tr = core_c[core_c["date"].dt.year < yr]
    te = core_c[core_c["date"].dt.year == yr]
    lr = LogisticRegression(max_iter=3000, C=0.5).fit(tr[FC_C].fillna(0), tr["won"])
    bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                            colsample_bytree=0.8, n_jobs=8, eval_metric="logloss").fit(
        tr[FC_C].fillna(0), tr["won"])
    pc = 0.5 * (lr.predict_proba(te[FC_C].fillna(0))[:, 1]
                + bst.predict_proba(te[FC_C].fillna(0))[:, 1])
    for k, p, w, m1, oa, ob in zip(te[KEY].itertuples(index=False, name=None), pc,
                                   te["won"].values, te["mkt"].values,
                                   te["player_odd"].values, te["rival_odd"].values):
        if not oa or not ob or oa <= 1 or ob <= 1:
            continue
        slug_a, slug_b = str(k[1]), str(k[2])
        if slug_a >= slug_b:            # one row per match
            continue
        g = GM.get(slug_a, "?")
        if g == "?":
            continue
        sf = surf.get(k, "Hard")
        f1, n1 = pf.form(slug_a, sf, asof=k[0])
        f2, n2 = pf.form(slug_b, sf, asof=k[0])
        if f1 is None or f2 is None:
            continue
        rows.append({"yr": yr, "G": g, "fe": f1 - f2, "C": float(p), "mkt": float(m1),
                     "oa": float(oa), "ob": float(ob), "won": bool(w)})
    print(f"{yr} done  cum {len(rows)}", flush=True)

D = pd.DataFrame(rows)
D.to_parquet("data_cache/_pure_form_rows.parquet")
print(f"\nmatches with as-of form for BOTH players: {len(D)}  "
      f"({int((D.G == 'W').sum())} women)\n")

dog_a = (D["mkt"] < 0.5).values
form_a = (D["fe"] > 0).values                    # side A is in better form
W = (D["G"] == "W").values


def run(label, pick_a, mask, floor=60):
    m = mask & ~pd.isna(pick_a)
    if m.sum() < floor:
        print(f"  {label:44s} n={int(m.sum())} (thin)")
        return
    pa = pick_a[m]
    od = np.where(pa, D["oa"].values[m], D["ob"].values[m])
    won = np.where(pa, D["won"].values[m], ~D["won"].values[m])
    pnl = np.where(won, od - 1.0, -1.0)
    print(f"  {label:44s} {int(won.sum())}-{int((~won).sum())}  win {100*won.mean():.1f}%  "
          f"ROI {100*pnl.mean():+.1f}%  (n={int(m.sum())})")


print("=== 1. STANDALONE: back the better-form player ===")
for G, gl in (("M", ~W), ("W", W)):
    run(f"{G}: all", form_a, gl)
    run(f"{G}: when he/she is the DOG", form_a, gl & (form_a == dog_a))
    run(f"{G}: when he/she is the FAVOURITE", form_a, gl & (form_a != dog_a))
    run(f"{G}: form gap top quartile", form_a,
        gl & (np.abs(D["fe"].values) >= np.quantile(np.abs(D["fe"]), 0.75)))
print("\n=== 2. CONTRARIAN: fade the better-form player ===")
for G, gl in (("M", ~W), ("W", W)):
    run(f"{G}: all", ~form_a, gl)
    run(f"{G}: fade a better-form FAVOURITE", ~form_a, gl & (form_a != dog_a))
    run(f"{G}: fade a better-form DOG", ~form_a, gl & (form_a == dog_a))
print("\n=== 3. FORM x MODEL C (the shipped contrarian use) ===")
C_a = (D["C"].values >= 0.5)
agree = C_a == form_a
for G, gl in (("M", ~W), ("W", W)):
    run(f"{G}: C+form AGREE -> back C", C_a, gl & agree)
    run(f"{G}: C+form DISAGREE -> back C", C_a, gl & ~agree)
    run(f"{G}:   disagree & C's side is the DOG", C_a, gl & ~agree & (C_a == dog_a))
    run(f"{G}:   disagree & C's side is the FAV", C_a, gl & ~agree & (C_a != dog_a))
    run(f"{G}: DISAGREE -> back FORM instead", form_a, gl & ~agree)
print("\n=== 4. BY YEAR (standalone, both genders) ===")
for y in (2024, 2025, 2026):
    run(f"back better form {y}", form_a, (D["yr"].values == y))
