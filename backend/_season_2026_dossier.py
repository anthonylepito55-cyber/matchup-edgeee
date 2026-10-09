"""2026 SEASON DOSSIER (2026-10-08, user: "analyze all of the 2026 season and intently what
signs or stats make underdogs have a good chance of winning or favorites").

Every match once, from the DOG's side (market devig prob < 0.5), true gender.
For every pre-match stat the four models use (A/B/C/D, diffs = dog minus favourite) plus the
walk-forward model-vs-market gaps and match context, two DIFFERENT questions:
  Q1 WIN CHANCE  -- does the dog win more often?               (raw win rate; mostly the market)
  Q2 BEATS PRICE -- does the dog win more than the odds imply?  (won - market prob; ROI)
Only Q2 makes money. Multiple-comparison guard: a 2026 finding must point the same way in
2025 (out-of-sample for the selection) before it is called real.
"""
import numpy as np
import pandas as pd

ns = {}
src = open("_tennis_abc6_agree_bt.py", encoding="utf-8").read()
exec(compile(src.split("tot = {")[0], "_prep6", "exec"), ns)
KEY = ns["KEY"]
core_a, FC_A = ns["core_a"], ns["FC_A"]
core_b, FC_B = ns["core_b"], ns["FC_B"]
core_c, FC_C = ns["core_c"], ns["FC_C"]
mC = ns["mC"]
nd = {}
srcd = open("_tennis_model_d_build.py", encoding="utf-8").read()
exec(compile(srcd.split("from sklearn.linear_model")[0], "_tmd_prep", "exec"), nd)
core_d, FC_D = nd["core"], nd["FC_D"]
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
from sklearn.linear_model import LogisticRegression
import xgboost as xgb


def lg(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def fit_p(core, FC, yr):
    tr = core[core["date"].dt.year < yr]
    te = core[core["date"].dt.year == yr]
    Xtr, Xte = tr[FC].fillna(0), te[FC].fillna(0)
    lr = LogisticRegression(max_iter=3000, C=0.5).fit(Xtr, tr["won"])
    bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                            colsample_bytree=0.8, n_jobs=8, eval_metric="logloss").fit(Xtr, tr["won"])
    p = 0.5 * (lr.predict_proba(Xte)[:, 1] + bst.predict_proba(Xte)[:, 1])
    lrm = LogisticRegression(max_iter=3000, C=0.5).fit(np.column_stack([lg(tr["mkt"]), Xtr]), tr["won"])
    pm = lrm.predict_proba(np.column_stack([lg(te["mkt"]), Xte]))[:, 1]
    o = te[KEY].copy()
    o["raw"], o["mb"] = p, pm
    return o


YRS = (2025, 2026)
base = core_c[core_c["date"].dt.year.isin(YRS)].copy()
ctx = mC[KEY + ["tournament_level", "surface", "round", "tournament"]].drop_duplicates(KEY)
base = base.merge(ctx, on=KEY, how="left")
for core, FC in ((core_a, FC_A), (core_b, FC_B), (core_d, FC_D)):
    extra = [f for f in FC if f not in base.columns]
    if extra:
        base = base.merge(core[KEY + extra].drop_duplicates(KEY), on=KEY, how="left")
for core, FC, tag in ((core_a, FC_A, "A"), (core_b, FC_B, "B"), (core_c, FC_C, "C"), (core_d, FC_D, "D")):
    P = pd.concat([fit_p(core, FC, y) for y in YRS]).drop_duplicates(KEY)
    P = P.rename(columns={"raw": f"p_{tag}", "mb": f"pm_{tag}"})
    base = base.merge(P, on=KEY, how="left")
    print(f"model {tag} walk-forward fitted", flush=True)

base["G"] = base["player_slug"].astype(str).map(GM)
base = base[base["G"].isin(["M", "W"])]
D = base[(base["mkt"] < 0.5) & (base["player_odd"] > 1) & (base["rival_odd"] > 1)].copy()
D = D.drop_duplicates(["date", "player_slug", "rival_slugname"])
D["yr"] = D["date"].dt.year
D["won"] = D["won"].astype(bool)
D["res"] = D["won"].astype(float) - D["mkt"]
D["dog_pnl"] = np.where(D["won"], D["player_odd"] - 1, -1.0)
D["fav_pnl"] = np.where(~D["won"], D["rival_odd"] - 1, -1.0)
for t in "ABCD":
    D[f"gap_{t}"] = D[f"p_{t}"] - D["mkt"]
    D[f"gapm_{t}"] = D[f"pm_{t}"] - D["mkt"]
lvl = D["tournament_level"].astype(str).str.lower()
D["level"] = np.select([lvl.str.contains("grand"), lvl.str.contains("masters|1000"),
                        lvl.str.contains("chall"), lvl.str.contains("itf|futures"),
                        lvl.str.contains("500|250|tour|main|wta|atp")],
                       ["slam", "1000", "challenger", "itf", "tour"], "other")
D["dog_am"] = np.where(D["player_odd"] >= 2, (D["player_odd"] - 1) * 100, -100 / (D["player_odd"] - 1))
D.to_parquet("data_cache/_season_2026_dossier_rows.parquet")
print(f"\nrows: 2026 {int((D.yr == 2026).sum())} | 2025 {int((D.yr == 2025).sum())}\n")

FEATS = list(dict.fromkeys(FC_A + FC_B + FC_C + FC_D)) + [f"gap_{t}" for t in "ABCD"] + [f"gapm_{t}" for t in "ABCD"]
FEATS = [f for f in FEATS if f in D.columns]
L = []


def cell(s):
    n = len(s)
    if n < 60:
        return None
    sd = s.res.std(ddof=1)
    return dict(n=n, win=s.won.mean(), mkt=s.mkt.mean(), res=s.res.mean(),
                z=s.res.mean() / (sd / np.sqrt(n)) if sd > 0 else 0.0,
                dog=s.dog_pnl.mean(), fav=s.fav_pnl.mean())


for G in "MW":
    for f in FEATS:
        S6 = D[(D.yr == 2026) & (D.G == G) & D[f].notna()]
        S5 = D[(D.yr == 2025) & (D.G == G) & D[f].notna()]
        if len(S6) < 500 or S6[f].nunique() < 5:
            continue
        cuts = np.unique(np.quantile(S6[f], [0, .2, .4, .6, .8, 1]))
        if len(cuts) < 4:
            continue
        q6 = pd.cut(S6[f], cuts, include_lowest=True, labels=False, duplicates="drop")
        q5 = pd.cut(S5[f].clip(cuts[0], cuts[-1]), cuts, include_lowest=True, labels=False, duplicates="drop")
        top = q6.max()
        spread = S6[q6 == top].won.mean() - S6[q6 == 0].won.mean()
        for qi, end in ((0, "LOW"), (top, "HIGH")):
            c6, c5 = cell(S6[q6 == qi]), cell(S5[q5 == qi])
            if c6 is None:
                continue
            row = dict(G=G, feat=f, end=end, spread=spread, **{f"{k}6": v for k, v in c6.items()})
            if c5:
                row.update({f"{k}5": v for k, v in c5.items()})
            L.append(row)
R = pd.DataFrame(L)
for c in ("res5", "dog5", "n5", "z5"):
    if c not in R.columns:
        R[c] = np.nan
R.to_parquet("data_cache/_season_2026_dossier_cells.parquet")


def pct(x):
    return f"{100*x:+5.1f}" if pd.notna(x) else "  n/a"


def show(Rs):
    print(f"  G {'stat (dog minus fav)':24s} end  | 2026 dogwin  mkt  beat     z  dogROI  favROI     n | 2025 beat dogROI     n")
    for r in Rs.itertuples():
        n5 = f"{int(r.n5):5d}" if pd.notna(r.n5) else "    -"
        print(f"  {r.G} {r.feat:24s} {r.end:4s} | {100*r.win6:9.1f}%  {100*r.mkt6:4.1f} {pct(r.res6)} {r.z6:+5.1f} {pct(r.dog6)}%  {pct(r.fav6)}%  {int(r.n6):5d} |"
              f"  {pct(r.res5)}  {pct(r.dog5)}%  {n5}")


print("=" * 110)
print("Q1  WHAT MAKES A DOG WIN MORE OFTEN (raw win rate, bottom vs top fifth of the stat) -- biggest spreads")
for G in "MW":
    t = R[(R.G == G) & (R.end == "HIGH")].copy()
    t = t.reindex(t.spread.abs().sort_values(ascending=False).index).head(14)
    print(f"\n  {'MEN' if G == 'M' else 'WOMEN'}")
    for r in t.itertuples():
        lo = R[(R.G == G) & (R.feat == r.feat) & (R.end == "LOW")]
        lw = lo.win6.iloc[0] if len(lo) else np.nan
        lm = lo.mkt6.iloc[0] if len(lo) else np.nan
        print(f"    {r.feat:24s} dog wins {100*lw:4.1f}% (mkt {100*lm:4.1f}) bottom fifth -> {100*r.win6:4.1f}% (mkt {100*r.mkt6:4.1f}) top fifth")

print("\n" + "=" * 110)
R["rep"] = (np.sign(R.res6) == np.sign(R.res5)) & (R.res5.abs() >= 0.01) & (R.n5 >= 60)
print("Q2  BEATS THE PRICE in 2026 (|z|>=2)   + = dog underpriced (back dog)   - = favourite underpriced (back fav)")
show(R[R.z6.abs() >= 2.0].sort_values("z6", ascending=False))
print("\n  ...of those, SAME DIRECTION in 2025 (>=1pt):")
show(R[(R.z6.abs() >= 2.0) & R.rep].sort_values("z6", ascending=False))
print(f"\n  tests run: {len(R)} | expected |z|>=2 by luck alone: ~{0.046*len(R):.0f} | found: {int((R.z6.abs() >= 2).sum())}"
      f" | replicated in 2025: {int(((R.z6.abs() >= 2) & R.rep).sum())}")

print("\n" + "=" * 110)
print("CONTEXT (dog side, 2026 vs 2025)")


def ctxrep(col, order=None):
    for G in "MW":
        print(f"  {'MEN' if G == 'M' else 'WOMEN'} by {col}")
        S = D[D.G == G]
        vals = order or sorted(S[col].dropna().unique())
        for v in vals:
            a, b = cell(S[(S.yr == 2026) & (S[col] == v)]), cell(S[(S.yr == 2025) & (S[col] == v)])
            if a is None:
                continue
            b_s = f"2025 beat {pct(b['res'])} dogROI {pct(b['dog'])}% n={b['n']}" if b else "2025 thin"
            print(f"    {str(v):12s} dog wins {100*a['win']:4.1f}% vs mkt {100*a['mkt']:4.1f} beat {pct(a['res'])} "
                  f"dogROI {pct(a['dog'])}% favROI {pct(a['fav'])}% n={a['n']:5d} | {b_s}")


D["band"] = pd.cut(D.dog_am, [-1e9, 120, 150, 200, 250, 350, 500, 1e9],
                   labels=["<+120", "+120-150", "+150-200", "+200-250", "+250-350", "+350-500", "+500+"]).astype(str)
ctxrep("band", ["<+120", "+120-150", "+150-200", "+200-250", "+250-350", "+350-500", "+500+"])
ctxrep("level")
D["surf"] = D["surface"].astype(str).str.title()
ctxrep("surf")
rd = D["round"].astype(str).str.lower()
D["rnd"] = np.select([rd.str.contains("qual"), rd.str.contains("semi"), rd.str.contains("quarter"),
                      rd.str.contains("final")], ["qualifying", "semi", "quarter", "final"], "early")
ctxrep("rnd", ["qualifying", "early", "quarter", "semi", "final"])
D["month"] = D["date"].dt.month
ctxrep("month")
