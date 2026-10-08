# MC v2 — STAGE 4: residual-vs-close ensemble + calibration + the betting reckoning.
# Design per plan: the base layers (Elo, Markov2) stay market-blind; the FINAL layer
# learns the RESIDUAL against the no-vig close (result − market), so it can only learn
# where the market errs. Honest nesting: Markov2 predictions for every year come from
# the standard walk-forward (train < y), so residual-training years carry no in-sample
# inflation; residual model evaluated on 2025 (trained on 2024) and 2026 (2024-25).
# Outputs: logloss/AUC vs market, calibration table, and a flat-stake betting sim at
# the archive odds by edge bucket × gender × dog/fav — the final exam.
import numpy as np
import pandas as pd
import xgboost as xgb
from functools import lru_cache
from math import comb
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, log_loss

F = pd.read_parquet("data_cache/_mc2_features.parquet")
surf_d = pd.get_dummies(F["surf"], prefix="s")
F = pd.concat([F, surf_d], axis=1)
scols = [c for c in F.columns if c.startswith("s_")]
FEAT_EXTRA = ["fatigue", "injury", "clutch"]          # the kept set
UNCERT = True


def direction(df, serve_side):
    srv, ret = ("a", "b") if serve_side == "a" else ("b", "a")
    X = pd.DataFrame({
        "S": df[f"S_{srv}"], "R_opp": df[f"R_{ret}"], "nS": df[f"nS_{srv}"],
        "nR_opp": df[f"nR_{ret}"], "elo_d": df[f"elo_{srv}"] - df[f"elo_{ret}"],
        "wom": df["wom"], "lvlg": df["lvlg"],
        "pt_add": df["pa_pt"] if serve_side == "a" else df["pb_pt"]})
    for c in scols:
        X[c] = df[c].astype(int)
    X["rest"] = df[f"rest_{srv}"].clip(0, 14)
    X["m7"] = df[f"m7_{srv}"]
    X["ex7"] = df[f"ex_{srv}"]
    X["rest_opp"] = df[f"rest_{ret}"].clip(0, 14)
    X["m7_opp"] = df[f"m7_{ret}"]
    X["ex7_opp"] = df[f"ex_{ret}"]
    X["layoff"] = df[f"rest_{srv}"]
    X["ret5"] = df[f"ret5_{srv}"]
    X["layoff_opp"] = df[f"rest_{ret}"]
    X["ret5_opp"] = df[f"ret5_{ret}"]
    X["clutch"] = df[f"clutch_{srv}"]
    X["clutch_opp"] = df[f"clutch_{ret}"]
    y = df["spw_a"] if serve_side == "a" else df["spw_b"]
    return X, y


@lru_cache(maxsize=400000)
def p_game(p):
    q = 1 - p
    return (p**4) * (1 + 4 * q + 10 * q * q) + 20 * (p**3) * (q**3) * (p * p / (p * p + q * q))


@lru_cache(maxsize=400000)
def p_tb(pa, pb):
    p = 0.5 * (pa + (1 - pb))
    q = 1 - p
    win = sum(comb(6 + k, k) * (p**7) * (q**k) for k in range(6))
    return win + comb(12, 6) * (p**6) * (q**6) * (p * p / (p * p + q * q))


@lru_cache(maxsize=400000)
def p_set(pa, pb):
    ga, gb = p_game(pa), 1 - p_game(pb)

    def rec(a, b, asv, memo):
        if a >= 6 and a - b >= 2:
            return 1.0
        if b >= 6 and b - a >= 2:
            return 0.0
        if a == 6 and b == 6:
            return p_tb(pa, pb)
        k = (a, b, asv)
        if k in memo:
            return memo[k]
        pw = ga if asv else gb
        r = pw * rec(a + 1, b, not asv, memo) + (1 - pw) * rec(a, b + 1, not asv, memo)
        memo[k] = r
        return r
    return 0.5 * rec(0, 0, True, {}) + 0.5 * rec(0, 0, False, {})


@lru_cache(maxsize=400000)
def p_match(pa, pb):
    s = p_set(pa, pb)
    return s * s + 2 * s * s * (1 - s)


def lg(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


NODES = ((-1.7320508, 1 / 6), (0.0, 2 / 3), (1.7320508, 1 / 6))
# ---- walk-forward Markov2 + blend for every year 2024-26 ----
pred = {}
for Y in (2024, 2025, 2026):
    tr = F[F["year"] < Y]
    te = F[F["year"] == Y].copy()
    parts = []
    for side in ("a", "b"):
        X, y = direction(tr, side)
        ok = y.notna() & (X["nS"] >= 4) & (X["nR_opp"] >= 4)
        parts.append((X[ok], y[ok]))
    Xtr = pd.concat([p[0] for p in parts])
    ytr = pd.concat([p[1] for p in parts])
    mdl = xgb.XGBRegressor(n_estimators=400, max_depth=5, learning_rate=0.05,
                           subsample=0.9, colsample_bytree=0.8, n_jobs=8)
    mdl.fit(Xtr, ytr)
    Xa, _ = direction(te, "a")
    Xb, _ = direction(te, "b")
    pa = np.clip(mdl.predict(Xa), 0.40, 0.85)
    pb = np.clip(mdl.predict(Xb), 0.40, 0.85)
    sg_a = 0.10 / np.sqrt(np.maximum(te["nS_a"].values, 4))
    sg_b = 0.10 / np.sqrt(np.maximum(te["nS_b"].values, 4))
    pm = np.zeros(len(pa))
    for xi, wi in NODES:
        for xj, wj in NODES:
            pm += wi * wj * np.array([
                p_match(round(min(max(x + xi * sa, 0.40), 0.85), 2),
                        round(min(max(y9 + xj * sb, 0.40), 0.85), 2))
                for x, y9, sa, sb in zip(pa, pb, sg_a, sg_b)])
    te["p_mkv2"] = pm
    # learned blend fit on train-year priced rows using additive markov stand-in
    trp = tr[tr["imp"].notna() & (tr["nS_a"] >= 8) & (tr["nS_b"] >= 8)]
    pmk_tr = np.array([p_match(round(x, 2), round(y9, 2))
                       for x, y9 in zip(trp["pa_pt"], trp["pb_pt"])])
    stk = LogisticRegression(max_iter=2000).fit(
        np.column_stack([lg(trp["p_elo"]), lg(pmk_tr)]), trp["won"])
    te["p_blend"] = stk.predict_proba(
        np.column_stack([lg(te["p_elo"]), lg(te["p_mkv2"])]))[:, 1]
    pred[Y] = te
    print(f"walk-forward {Y} done ({len(te)})", flush=True)

P = pd.concat(pred.values())
P = P[P["imp"].notna() & (P["nS_a"] >= 8) & (P["nS_b"] >= 8)].copy()
P.to_parquet("data_cache/_mc2_predictions.parquet")

# ---- residual layer: learn result − market from model/market disagreement ----
def res_feats(df):
    return pd.DataFrame({
        "imp": df["imp"], "d_blend": lg(df["p_blend"]) - lg(df["imp"]),
        "d_elo": lg(df["p_elo"]) - lg(df["imp"]),
        "d_mkv": lg(df["p_mkv2"]) - lg(df["imp"]),
        "wom": df["wom"], "lvlg": df["lvlg"],
        "sgm": 0.10 / np.sqrt(np.maximum(df["nS_a"], 4))
               + 0.10 / np.sqrt(np.maximum(df["nS_b"], 4)),
        "dog": (df["imp"] < 0.5).astype(int)})


print("\n==== STAGE 4: residual layer + calibration + betting sim ====")
rows = []
for Y in (2025, 2026):
    tr = P[P["year"] < Y]
    te = P[P["year"] == Y].copy()
    rm = xgb.XGBRegressor(n_estimators=250, max_depth=3, learning_rate=0.04,
                          subsample=0.9, colsample_bytree=0.9, n_jobs=8)
    rm.fit(res_feats(tr), tr["won"] - tr["imp"])
    adj = np.clip(rm.predict(res_feats(te)), -0.25, 0.25)
    te["p_final"] = np.clip(te["imp"] + adj, 0.02, 0.98)
    y = te["won"]
    for nm, p in (("Market", te["imp"]), ("Blend", te["p_blend"]), ("Final", te["p_final"])):
        p = np.clip(p, 1e-6, 1 - 1e-6)
        print(f"{Y} {nm:7s} AUC {roc_auc_score(y, p):.4f} LL {log_loss(y, p):.4f}")
    rows.append(te)
T = pd.concat(rows)

# calibration table for p_final
print("\ncalibration (p_final):")
T["bk"] = (T["p_final"] * 10).astype(int).clip(0, 9)
for bk, g in T.groupby("bk"):
    if len(g) < 200:
        continue
    print(f"  {bk*10}-{bk*10+10}%: predicted {100*g['p_final'].mean():.1f}  actual {100*g['won'].mean():.1f}  n={len(g)}")

# betting sim: flat 1u on p1 side when p_final - imp > thr (and reverse), archive odds
print("\nbetting sim (flat 1u at archive odds, bet where final disagrees with market):")
for thr in (0.03, 0.05, 0.08):
    for seg_name, seg in (("ALL", T), ("men", T[T["wom"] == 0]), ("women", T[T["wom"] == 1])):
        edge1 = seg["p_final"] - seg["imp"]
        bet1 = seg[edge1 > thr]
        bet2 = seg[-edge1 > thr]
        pnl = 0.0
        n = w = 0
        dpnl = dn = 0.0
        for df9, side in ((bet1, True), (bet2, False)):
            if not len(df9):
                continue
            o = df9["odd_a"] if side else df9["odd_b"]
            hit = (df9["won"] == 1) if side else (df9["won"] == 0)
            pnl += float(np.where(hit, o - 1, -1.0).sum())
            w += int(hit.sum()); n += len(df9)
            isdog = (df9["imp"] < 0.5) if side else (df9["imp"] >= 0.5)
            dpnl += float(np.where(hit & isdog, o - 1, np.where(isdog, -1.0, 0.0)).sum())
            dn += int(isdog.sum())
        if n:
            print(f"  thr {thr:.2f} {seg_name:6s}: {w}-{n-w}  ROI {100*pnl/n:+.1f}%  (dog half: n={int(dn)} ROI {100*dpnl/max(dn,1):+.1f}%)")
