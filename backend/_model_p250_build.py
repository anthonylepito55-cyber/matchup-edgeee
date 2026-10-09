"""MODEL P, +100..+250 variant (2026-10-09, user: "whats the roi if i move it up from +100 to +200 to +250").

Design (from the 2026 season dossier + every live/backtest finding this week):
  * OFFSET model: logit(P) = logit(market) + b.x. The market is a FIXED baseline the
    model cannot learn to copy; P only learns where the price is wrong. (Old X had the
    market as an ordinary input and copied it; new X has no market and is a worse
    forecaster -- this is the middle path.)
  * Universe: market DOGS priced +100..+200 only (decimal 2.0-3.0), one row per match.
  * Separate MEN and WOMEN models (edges differ ~2x and some signals flip by gender).
  * Inputs = the families that beat the price in BOTH 2025 and 2026 in the dossier:
      d_vs_band (record vs the rival's calibre), C gap / gray gap to market, D-MA gap,
      contrarian recent form (d_form_win), match-quality (d_m_perf, d_m_won), sUTR gap,
      rank gap, level flags (challenger / ITF).
  * Strict walk-forward at TWO levels: the base models C and D are themselves fit on
    years < Y to produce year-Y probabilities; Model P for year Y is fit only on P-rows
    from years < Y. Nothing in a test year ever touches its own training.
  * Judged on money: flat 1u on the dog when P's EV clears a threshold, at the archive
    closing odds, vs backing every +100..+200 dog. Years 2024, 2025, 2026 reported.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize

ns = {}
src = open("_tennis_abc6_agree_bt.py", encoding="utf-8").read()
exec(compile(src.split("tot = {")[0], "_prep6", "exec"), ns)
KEY = ns["KEY"]
core_c, FC_C, mC = ns["core_c"], ns["FC_C"], ns["mC"]
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


def fit_base(core, FC, yr):
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


YRS = (2022, 2023, 2024, 2025, 2026)
base = core_c[core_c["date"].dt.year.isin(YRS)].copy()
ctx = mC[KEY + ["tournament_level"]].drop_duplicates(KEY)
base = base.merge(ctx, on=KEY, how="left")
dx = [f for f in FC_D if f not in base.columns]
base = base.merge(core_d[KEY + dx].drop_duplicates(KEY), on=KEY, how="left")
for core, FC, tag in ((core_c, FC_C, "C"), (core_d, FC_D, "D")):
    P = pd.concat([fit_base(core, FC, y) for y in YRS]).drop_duplicates(KEY)
    base = base.merge(P.rename(columns={"raw": f"p_{tag}", "mb": f"pm_{tag}"}), on=KEY, how="left")
    print(f"base model {tag} walk-forward done", flush=True)

base["G"] = base["player_slug"].astype(str).map(GM)
D = base[base["G"].isin(["M", "W"]) & (base["mkt"] < 0.5)
         & base["player_odd"].between(2.0, 3.5) & (base["rival_odd"] > 1)].copy()
D = D.drop_duplicates(["date", "player_slug", "rival_slugname"])
D["yr"] = D["date"].dt.year
D["won"] = D["won"].astype(bool)
lvl = D["tournament_level"].astype(str).str.lower()
D["is_chall"] = lvl.str.contains("chall").astype(float)
D["is_itf"] = lvl.str.contains("itf|futures").astype(float)
D["off"] = lg(D["mkt"])
D["g_C"] = lg(D["p_C"]) - D["off"]
D["g_gray"] = lg(D["pm_C"]) - D["off"]
D["g_Dma"] = lg(D["pm_D"]) - D["off"]
FEATS = ["d_vs_band", "g_C", "g_gray", "g_Dma", "d_form_win", "d_m_perf", "d_m_won",
         "d_sutr", "d_lrank", "is_chall", "is_itf"]
D = D[D[["p_C", "pm_C", "pm_D"]].notna().all(axis=1)].copy()
D.to_parquet("data_cache/_model_p250_rows.parquet")
print(f"P universe (+100..+250 dogs): {len(D)} | by year {D.groupby('yr').size().to_dict()}", flush=True)


def fit_offset(X, y, off, lam=2.0):
    """L2 logistic regression with a fixed offset (no intercept penalty)."""
    n, k = X.shape
    Xb = np.column_stack([np.ones(n), X])

    def f(w):
        z = off + Xb @ w
        ll = np.sum(y * z - np.logaddexp(0, z))
        pen = 0.5 * lam * np.sum(w[1:] ** 2)
        p = 1 / (1 + np.exp(-z))
        g = -(Xb.T @ (y - p))
        g[1:] += lam * w[1:]
        return -ll + pen, g
    r = minimize(f, np.zeros(k + 1), jac=True, method="L-BFGS-B")
    return r.x


def rep(won, dec, floor=30):
    n = len(won)
    if n < floor:
        return f"n={n} (thin)"
    w = int(np.sum(won))
    p = np.where(won, dec - 1, -1.0)
    return f"{w}-{n-w} win {100*w/n:4.1f}% ROI {100*p.mean():+6.1f}% (n={n})"


OUT = []
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    print(f"\n==================== {gl} ====================")
    S = D[D.G == G].copy()
    for yr in (2024, 2025, 2026):
        tr, te = S[S.yr < yr].copy(), S[S.yr == yr].copy()
        mu, sd = tr[FEATS].mean(), tr[FEATS].std().replace(0, 1)
        Xtr = ((tr[FEATS] - mu) / sd).fillna(0).values
        Xte = ((te[FEATS] - mu) / sd).fillna(0).values
        w = fit_offset(Xtr, tr.won.values.astype(float), tr.off.values)
        te["pP"] = 1 / (1 + np.exp(-(te.off.values + w[0] + Xte @ w[1:])))
        te["ev"] = te.pP * te.player_odd - 1
        te["G"] = G
        OUT.append(te[["yr", "G", "won", "player_odd", "mkt", "pP", "ev", "date", "player_slug", "rival_slugname"]])
        if yr == 2026:
            coef = dict(zip(["intercept"] + FEATS, np.round(w, 3)))
            print(f"  2026 model weights (std units): {coef}")
        ll_m = -np.mean(np.where(te.won, np.log(te.mkt), np.log(1 - te.mkt)))
        ll_p = -np.mean(np.where(te.won, np.log(te.pP), np.log(1 - te.pP)))
        print(f"\n  {yr}: train {len(tr)} rows | logloss market {ll_m:.4f} vs P {ll_p:.4f}")
        print(f"     every +100..+200 dog   {rep(te.won.values, te.player_odd.values)}")
        for thr in (0.0, 0.03, 0.05, 0.08, 0.12):
            s = te[te.ev > thr]
            print(f"     P bets, EV > {int(thr*100):2d}%     {rep(s.won.values, s.player_odd.values)}")
        s = te[te.ev <= 0]
        print(f"     P passes (EV <= 0)     {rep(s.won.values, s.player_odd.values)}")

O = pd.concat(OUT)
O.to_parquet("data_cache/_model_p250_oos.parquet")
print("\n==================== POOLED 2024-26 (all out-of-sample) ====================")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    T = O[O.G == G]
    print(f"\n{gl}: every dog {rep(T.won.values, T.player_odd.values)}")
    for thr in (0.0, 0.03, 0.05, 0.08, 0.12):
        s = T[T.ev > thr]
        print(f"   EV > {int(thr*100):2d}%  {rep(s.won.values, s.player_odd.values)}")
    T = T.copy()
    T["dec"] = pd.qcut(T.ev, 5, labels=False, duplicates="drop")
    print("   by EV quintile (low -> high):")
    for q, s in T.groupby("dec"):
        print(f"     Q{q+1}  EV {s.ev.min():+.3f}..{s.ev.max():+.3f}  {rep(s.won.values, s.player_odd.values)}")


print("==================== BY PRICE BAND (pooled 2024-26, out of sample) ====================")
O["am"] = (O.player_odd - 1) * 100
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    for lo, hi, lab in ((100, 200, "+100..+200"), (200.01, 250, "+200..+250"), (100, 250, "+100..+250 all")):
        T = O[(O.G == G) & O.am.between(lo, hi)]
        print(f"{gl} {lab}: every dog {rep(T.won.values, T.player_odd.values)}")
        for thr in (0.0, 0.05, 0.10):
            s_ = T[T.ev > thr]
            print(f"   P EV > {int(thr*100):2d}%  {rep(s_.won.values, s_.player_odd.values)}")
        for y in (2024, 2025, 2026):
            s_ = T[(T.yr == y) & (T.ev > .05)]
            print(f"      {y} EV>5%  {rep(s_.won.values, s_.player_odd.values)}")
