"""MEN: WHICH STATS ADD ANYTHING THE PRICE DOES NOT ALREADY KNOW (2026-10-11).

The univariate table ranks stats against the outcome, but every one of them is confounded --
"average opponent rank faced" tops it mostly because it proxies for tour vs challenger, and the
market knows that already. So this fits an OFFSET logistic regression: the market's own log-odds
go in as a fixed baseline with coefficient 1, and the stats only get credit for what they
explain ON TOP of the price. Same construction as Model P.

Features are standardised on this sample, so a coefficient reads as "log-odds moved per 1 SD of
this stat". Positive = the stat genuinely adds information the price is missing.

Fitted with plain gradient descent on the penalised likelihood (lam=2.0), no sklearn needed.
Reported with bootstrap standard errors, and a univariate offset fit per stat alongside the
joint fit, because with ~690 rows and 12 correlated features the joint coefficients trade off
against each other.
"""
import numpy as np
import pandas as pd

import tennis_context as TC
import tennis_log as TL

log = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
log["date"] = pd.to_datetime(log["date"], errors="coerce")
S = log[(log["settled"] == True) & log["p1_won"].notna()          # noqa: E712
        & log["p1_odds"].notna() & log["p2_odds"].notna()].copy()
if "surface_bad" in S.columns:
    S = S[~S["surface_bad"].fillna(False).astype(bool)]
lg = S["league"].astype(str)
S = S[~(lg.str.contains("wta") | lg.str.contains("itf_women"))]

cache = {}


def ctx(nm, surf, asof):
    k = (str(nm), str(surf), str(asof)[:10])
    if k not in cache:
        try:
            cache[k] = TC.context_asof(nm, surf, asof)
        except Exception:
            cache[k] = None
    return cache[k]


def g(c, blk, key):
    if not c:
        return None
    if key == "opp_rank":
        v = c.get("avg_opp_rank")
        return None if v is None else -float(v)
    if key == "clutch":
        v = c.get("clutch")
        return None if v is None else float(v)
    b = c.get(blk) or {}
    if key == "hpb":
        if b.get("sgw") is None or b.get("rgw") is None:
            return None
        return float(b["sgw"]) + float(b["rgw"])
    v = b.get(key)
    return None if v is None else float(v)


FEATS = [("hold% 52w", "surface_stats", "sgw"), ("break% 52w", "surface_stats", "rgw"),
         ("1st-serve% 52w", "surface_stats", "sv1"), ("2nd-serve% 52w", "surface_stats", "sv2"),
         ("return-v-1st% 52w", "surface_stats", "r1"), ("return-v-2nd% 52w", "surface_stats", "r2"),
         ("surface win% 52w", "surface_stats", "win"),
         ("hold+break L10", "surface_l10", "hpb"), ("win% L10", "surface_l10", "win"),
         ("hold+break L5", "surface_l5", "hpb"),
         ("clutch", None, "clutch"), ("opp rank faced", None, "opp_rank")]

rows = []
for r in S.itertuples():
    ca, cb = ctx(r.player_1, r.surface, r.date), ctx(r.player_2, r.surface, r.date)
    d1, d2 = TL._decimal(r.p1_odds), TL._decimal(r.p2_odds)
    if not d1 or not d2:
        continue
    i1, i2 = 1 / d1, 1 / d2
    mk = i1 / (i1 + i2)
    vals = {}
    ok = True
    for lab, blk, key in FEATS:
        a, b = g(ca, blk, key), g(cb, blk, key)
        if a is None or b is None:
            ok = False
            break
        vals[lab] = a - b
    if not ok:
        continue
    rows.append({"y": 1.0 if bool(r.p1_won) else 0.0,
                 "mk": min(max(mk, 1e-4), 1 - 1e-4), **vals})
D = pd.DataFrame(rows)
names = [f[0] for f in FEATS]
X = D[names].to_numpy(float)
X = (X - X.mean(0)) / X.std(0, ddof=0)
y = D.y.to_numpy(float)
off = np.log(D.mk.to_numpy(float) / (1 - D.mk.to_numpy(float)))
print(f"complete men's rows for the joint fit: {len(D)}")
base = -np.mean(y * np.log(1 / (1 + np.exp(-off))) + (1 - y) * np.log(1 - 1 / (1 + np.exp(-off))))
print(f"market-only log loss (the baseline to beat): {base:.4f}\n")


def fit(Xm, lam=2.0, iters=4000, lr=0.12):
    w = np.zeros(Xm.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(off + Xm @ w)))
        gr = Xm.T @ (p - y) + lam * w
        w -= lr * gr / len(y)
    return w


def loss(Xm, w):
    p = 1 / (1 + np.exp(-(off + Xm @ w)))
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))


W = fit(X)
# bootstrap SEs
rng = np.random.default_rng(7)
B = np.zeros((300, X.shape[1]))
for b in range(300):
    idx = rng.integers(0, len(y), len(y))
    Xb, yb, ob = X[idx], y[idx], off[idx]
    w = np.zeros(X.shape[1])
    for _ in range(1500):
        p = 1 / (1 + np.exp(-(ob + Xb @ w)))
        w -= 0.12 * (Xb.T @ (p - yb) + 2.0 * w) / len(yb)
    B[b] = w
SE = B.std(0, ddof=1)

uni = {}
for j, nm in enumerate(names):
    wj = fit(X[:, [j]])
    uni[nm] = (wj[0], base - loss(X[:, [j]], wj))

order = sorted(range(len(names)), key=lambda j: -abs(W[j]))
print("=" * 104)
print("ADDED VALUE OVER THE PRICE — offset logistic, men, standardised (log-odds per 1 SD)")
print("=" * 104)
print(f"   {'stat':22s} {'joint coef':>12} {'boot SE':>9} {'t':>6}   {'alone: coef':>12} "
      f"{'alone: logloss gain':>20}")
for j in order:
    nm = names[j]
    t = W[j] / SE[j] if SE[j] > 1e-9 else 0.0
    uc, ug = uni[nm]
    print(f"   {nm:22s} {W[j]:+12.3f} {SE[j]:9.3f} {t:+6.2f}   {uc:+12.3f} {ug:+20.4f}")
print(f"\n   joint fit log loss {loss(X, W):.4f} vs market-only {base:.4f}  "
      f"(gain {base - loss(X, W):+.4f}; a POSITIVE gain means the stats beat the price)")
print("   note: with n~690 and 12 correlated stats, individual joint coefficients are unstable;")
print("   the |t| column and the sign agreement with the 'alone' column are what to read.")
