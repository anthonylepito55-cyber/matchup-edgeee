# MC v2 — STAGE 2: SUPERVISED point-prob model (user priority #1+#3+#7 merged).
# XGBoost learns P(server wins point) from the Stage-1b ratings — replacing the
# hand-set additive formula — trained CHRONOLOGICALLY (train < Y, score Y), stacked
# over both serve directions, with gender as a first-class feature. Then the cached
# closed-form Markov converts the two learned point-probs into match probability,
# and a LEARNED logistic blend stacks [Elo, Markov2] (fit on train years only).
import numpy as np
import pandas as pd
import xgboost as xgb
from functools import lru_cache
from math import comb
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, log_loss

F = pd.read_parquet("data_cache/_mc2_features.parquet")
print(f"feature table: {len(F)}", flush=True)

# ---- closed-form Markov (same as stage 1b) ----
@lru_cache(maxsize=400000)
def p_game(p):
    q = 1 - p
    pd2 = p * p / (p * p + q * q)
    return (p**4) * (1 + 4 * q + 10 * q * q) + 20 * (p**3) * (q**3) * pd2


@lru_cache(maxsize=400000)
def p_tb(pa, pb):
    p = 0.5 * (pa + (1 - pb))
    q = 1 - p
    win = sum(comb(6 + k, k) * (p**7) * (q**k) for k in range(6))
    reach66 = comb(12, 6) * (p**6) * (q**6)
    return win + reach66 * (p * p / (p * p + q * q))


@lru_cache(maxsize=400000)
def p_set(pa, pb):
    ga, gb = p_game(pa), 1 - p_game(pb)

    def win_from(a, b, aserves, memo):
        if a >= 6 and a - b >= 2:
            return 1.0
        if b >= 6 and b - a >= 2:
            return 0.0
        if a == 6 and b == 6:
            return p_tb(pa, pb)
        key = (a, b, aserves)
        if key in memo:
            return memo[key]
        pw = ga if aserves else gb
        r = pw * win_from(a + 1, b, not aserves, memo) \
            + (1 - pw) * win_from(a, b + 1, not aserves, memo)
        memo[key] = r
        return r
    return 0.5 * win_from(0, 0, True, {}) + 0.5 * win_from(0, 0, False, {})


@lru_cache(maxsize=400000)
def p_match_bo3(pa, pb):
    s = p_set(pa, pb)
    return s * s + 2 * s * s * (1 - s)


# ---- build direction-stacked training rows: one row = (server, returner) ----
surf_d = pd.get_dummies(F["surf"], prefix="s")
base_feats = pd.concat([F, surf_d], axis=1)
scols = [c for c in base_feats.columns if c.startswith("s_")]


FEAT_EXTRA = []     # ablation slot: [] = base, ['tspeed','tsp_x_S'] = +court speed


def direction(df, serve_side):
    if serve_side == "a":
        X = pd.DataFrame({
            "S": df["S_a"], "R_opp": df["R_b"], "nS": df["nS_a"], "nR_opp": df["nR_b"],
            "elo_d": df["elo_a"] - df["elo_b"], "wom": df["wom"], "lvlg": df["lvlg"],
            "pt_add": df["pa_pt"]})
        y = df["spw_a"]
    else:
        X = pd.DataFrame({
            "S": df["S_b"], "R_opp": df["R_a"], "nS": df["nS_b"], "nR_opp": df["nR_a"],
            "elo_d": df["elo_b"] - df["elo_a"], "wom": df["wom"], "lvlg": df["lvlg"],
            "pt_add": df["pb_pt"]})
        y = df["spw_b"]
    for c in scols:
        X[c] = df[c].astype(int)
    if 'tspeed' in FEAT_EXTRA:
        X['tspeed'] = df['tspeed']
        X['tsp_x_S'] = df['tspeed'] * X['S']
    if 'fatigue' in FEAT_EXTRA:
        srv, ret = ('a', 'b') if serve_side == 'a' else ('b', 'a')
        X['rest'] = df[f'rest_{srv}'].clip(0, 14)
        X['m7'] = df[f'm7_{srv}']
        X['ex7'] = df[f'ex_{srv}']
        X['rest_opp'] = df[f'rest_{ret}'].clip(0, 14)
        X['m7_opp'] = df[f'm7_{ret}']
        X['ex7_opp'] = df[f'ex_{ret}']
    if 'clutch' in FEAT_EXTRA:
        srv, ret = ('a', 'b') if serve_side == 'a' else ('b', 'a')
        X['clutch'] = df[f'clutch_{srv}']
        X['clutch_opp'] = df[f'clutch_{ret}']
    if 'tb' in FEAT_EXTRA:
        srv, ret = ('a', 'b') if serve_side == 'a' else ('b', 'a')
        X['tbr'] = df[f'tbr_{srv}']
        X['tbr_opp'] = df[f'tbr_{ret}']
    if 'decomp' in FEAT_EXTRA:
        srv, ret = ('a', 'b') if serve_side == 'a' else ('b', 'a')
        X['f1'] = df[f'f1_{srv}']
        X['S1'] = df[f'S1_{srv}']
        X['R1_opp'] = df[f'R1_{ret}']
        X['S2'] = df[f'S2_{srv}']
        X['R2_opp'] = df[f'R2_{ret}']
        X['s2_x_r2'] = df[f'S2_{srv}'] * df[f'R2_{ret}']   # the 2nd-serve matchup
        X['pt_dec'] = df['pa_dec'] if serve_side == 'a' else df['pb_dec']
    if 'injury' in FEAT_EXTRA:
        srv, ret = ('a', 'b') if serve_side == 'a' else ('b', 'a')
        X['layoff'] = df[f'rest_{srv}']            # unclipped, 0-99: long gaps = layoffs
        X['ret5'] = df[f'ret5_{srv}']
        X['layoff_opp'] = df[f'rest_{ret}']
        X['ret5_opp'] = df[f'ret5_{ret}']
    return X, y


import sys
if '--speed' in sys.argv:
    FEAT_EXTRA = ['tspeed', 'tsp_x_S']
    print('ABLATION: + court speed', flush=True)
if '--fatigue' in sys.argv:
    FEAT_EXTRA = FEAT_EXTRA + ['fatigue']
    print('ABLATION: + fatigue (learned)', flush=True)
if '--injury' in sys.argv:
    FEAT_EXTRA = FEAT_EXTRA + ['injury']
    print('ABLATION: + injury/availability', flush=True)
if '--clutch' in sys.argv:
    FEAT_EXTRA = FEAT_EXTRA + ['clutch']
    print('ABLATION: + score-state clutch', flush=True)
if '--tb' in sys.argv:
    FEAT_EXTRA = FEAT_EXTRA + ['tb']
    print('ABLATION: + tiebreak skill', flush=True)
if '--decomp' in sys.argv:
    FEAT_EXTRA = FEAT_EXTRA + ['decomp']
    print('ABLATION: + serve decomposition', flush=True)
UNCERT = '--uncert' in sys.argv
if UNCERT:
    print('ABLATION: + parameter uncertainty (GH quadrature)', flush=True)
results = []
for Y in (2024, 2025, 2026):
    tr = base_feats[base_feats["year"] < Y]
    te = base_feats[base_feats["year"] == Y]
    # SPW model: stack both directions, drop rows without targets, need some history
    parts = []
    for side in ("a", "b"):
        X, y = direction(tr, side)
        ok = y.notna() & (X["nS"] >= 4) & (X["nR_opp"] >= 4)
        parts.append((X[ok], y[ok]))
    Xtr = pd.concat([p[0] for p in parts])
    ytr = pd.concat([p[1] for p in parts])
    mdl = xgb.XGBRegressor(n_estimators=400, max_depth=5, learning_rate=0.05,
                           subsample=0.9, colsample_bytree=0.8, n_jobs=8,
                           objective="reg:squarederror")
    mdl.fit(Xtr, ytr)
    Xa, _ = direction(te, "a")
    Xb, _ = direction(te, "b")
    pa = np.clip(mdl.predict(Xa), 0.40, 0.85)
    pb = np.clip(mdl.predict(Xb), 0.40, 0.85)
    if UNCERT:
        # integrate the match prob over rating uncertainty: 3-node Gauss-Hermite per
        # side, sigma ~ 1/sqrt(serve sample) -> thin-data players get shrunk toward 50%
        sg_a = 0.10 / np.sqrt(np.maximum(te['nS_a'].values, 4))
        sg_b = 0.10 / np.sqrt(np.maximum(te['nS_b'].values, 4))
        NODES = ((-1.7320508, 1 / 6), (0.0, 2 / 3), (1.7320508, 1 / 6))
        p_mkv2 = np.zeros(len(pa))
        for xi, wi in NODES:
            for xj, wj in NODES:
                p_mkv2 += wi * wj * np.array([
                    p_match_bo3(round(min(max(x + xi * sa, 0.40), 0.85), 3),
                                round(min(max(y9 + xj * sb, 0.40), 0.85), 3))
                    for x, y9, sa, sb in zip(pa, pb, sg_a, sg_b)])
    else:
        p_mkv2 = np.array([p_match_bo3(round(x, 3), round(y9, 3)) for x, y9 in zip(pa, pb)])
    te = te.assign(p_mkv2=p_mkv2)
    # learned blend: logistic stack of logits, FIT ON TRAIN YEARS' own walk-forward...
    # (approximation tonight: fit the stack on the train years using the additive
    # markov as stand-in; honest refit later. Here: fit stack on train-year rows
    # scored by THIS model would leak; instead fit on p_elo + additive pa_pt markov.)
    def lg(p):
        p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
        return np.log(p / (1 - p))
    tr_pr = tr[tr["imp"].notna() & (tr["nS_a"] >= 8) & (tr["nS_b"] >= 8)]
    pmkv_tr = np.array([p_match_bo3(round(x, 3), round(y9, 3))
                        for x, y9 in zip(tr_pr["pa_pt"], tr_pr["pb_pt"])])
    stk = LogisticRegression(max_iter=2000).fit(
        np.column_stack([lg(tr_pr["p_elo"]), lg(pmkv_tr)]), tr_pr["won"])
    sc = te[te["imp"].notna() & (te["nS_a"] >= 8) & (te["nS_b"] >= 8)]
    p_blend = stk.predict_proba(np.column_stack([lg(sc["p_elo"]), lg(sc["p_mkv2"])]))[:, 1]
    y = sc["won"]
    row = {"year": Y, "n": len(sc)}
    for name, p in (("Elo", sc["p_elo"]), ("Markov2", sc["p_mkv2"]),
                    ("Blend", p_blend), ("Market", sc["imp"])):
        p = np.clip(p, 1e-6, 1 - 1e-6)
        row[f"{name}_auc"] = roc_auc_score(y, p)
        row[f"{name}_ll"] = log_loss(y, p)
    results.append(row)
    print(f"{Y} n={row['n']} | " + " | ".join(
        f"{nm} AUC {row[f'{nm}_auc']:.4f} LL {row[f'{nm}_ll']:.4f}"
        for nm in ("Elo", "Markov2", "Blend", "Market")), flush=True)

R = pd.DataFrame(results)
print("\nALL:", {nm: (round(R[f'{nm}_auc'].mean(), 4), round(R[f'{nm}_ll'].mean(), 4))
                for nm in ("Elo", "Markov2", "Blend", "Market")})
