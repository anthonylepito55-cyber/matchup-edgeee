"""Model P live check (2026-10-09). The live log has C, gray (C-MA) and D-MA but not the stat
diffs, so test P-LITE = offset model on [g_C, g_gray, g_Dma] only: fit on the archive P rows
(walk-forward base probs, 2022-2026), apply UNCHANGED to the frozen live log, +100..+200 dogs.
Also reports full-P vs P-lite on the archive so the lite proxy's gap is visible."""
import numpy as np
import pandas as pd
from scipy.optimize import minimize

def lg(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))

def fit_offset(X, y, off, lam=2.0):
    n, k = X.shape
    Xb = np.column_stack([np.ones(n), X])
    def f(w):
        z = off + Xb @ w
        p = 1 / (1 + np.exp(-z))
        g = -(Xb.T @ (y - p)); g[1:] += lam * w[1:]
        return -np.sum(y * z - np.logaddexp(0, z)) + 0.5 * lam * np.sum(w[1:] ** 2), g
    return minimize(f, np.zeros(k + 1), jac=True, method="L-BFGS-B").x

def rep(won, dec, floor=15):
    n = len(won)
    if n < floor: return f"n={n} (thin)"
    w = int(np.sum(won)); p = np.where(won, dec - 1, -1.0)
    return f"{w}-{n-w} win {100*w/n:4.1f}% ROI {100*p.mean():+6.1f}% (n={n})"

A = pd.read_parquet("data_cache/_model_p_rows.parquet")
LITE = ["g_C", "g_gray", "g_Dma"]
# archive: P-lite walk-forward 2024-26 for comparison with full P
print("ARCHIVE P-lite (walk-forward, pooled 2024-26):")
W = {}
for G in "MW":
    S = A[A.G == G]; outs = []
    for yr in (2024, 2025, 2026):
        tr, te = S[S.yr < yr], S[S.yr == yr].copy()
        mu, sd = tr[LITE].mean(), tr[LITE].std()
        w = fit_offset(((tr[LITE]-mu)/sd).fillna(0).values, tr.won.values.astype(float), tr.off.values)
        te["ev"] = 1/(1+np.exp(-(te.off.values + w[0] + ((te[LITE]-mu)/sd).fillna(0).values @ w[1:]))) * te.player_odd - 1
        outs.append(te)
    T = pd.concat(outs)
    print(f"  {G}: EV>0 {rep(T[T.ev>0].won.values, T[T.ev>0].player_odd.values)} | EV>5% {rep(T[T.ev>.05].won.values, T[T.ev>.05].player_odd.values)}")
    mu, sd = S[LITE].mean(), S[LITE].std()
    W[G] = (fit_offset(((S[LITE]-mu)/sd).fillna(0).values, S.won.values.astype(float), S.off.values), mu, sd)

L = pd.read_parquet("data_cache/_ec2_log_now.parquet")
L = L[L.p1_won.notna() & L.p1_odds.notna() & L.p2_odds.notna()
      & L.model_c_p1.notna() & L.model_cma_p1.notna() & L.model_dma_p1.notna()]
dec = lambda o: 1 + o/100 if o > 0 else 1 + 100/abs(o)
R = []
for r in L.itertuples():
    d1, d2 = dec(float(r.p1_odds)), dec(float(r.p2_odds)); i1, i2 = 1/d1, 1/d2; mk1 = i1/(i1+i2)
    dog1 = mk1 < .5; od = d1 if dog1 else d2
    if not (2.0 <= od <= 3.0): continue
    m = mk1 if dog1 else 1 - mk1
    pc = r.model_c_p1 if dog1 else 1 - r.model_c_p1
    pg = r.model_cma_p1 if dog1 else 1 - r.model_cma_p1
    pd_ = r.model_dma_p1 if dog1 else 1 - r.model_dma_p1
    lg_ = str(r.league); G = "W" if ("wta" in lg_ or "itf_women" in lg_) else "M"
    off = float(lg(m)); x = np.array([float(lg(pc)) - off, float(lg(pg)) - off, float(lg(pd_)) - off])
    w, mu, sd = W[G]; xs = (x - mu.values) / sd.values
    pP = 1/(1+np.exp(-(off + w[0] + xs @ w[1:])))
    R.append({"G": G, "won": bool(r.p1_won) == dog1, "dec": od, "ev": pP*od - 1, "date": str(r.date)[:10]})
R = pd.DataFrame(R)
print(f"\nLIVE frozen log {R.date.min()}..{R.date.max()}: +100..+200 dogs {len(R)}")
for G in "MW":
    T = R[R.G == G]
    print(f"\n  {'MEN' if G=='M' else 'WOMEN'}: every dog {rep(T.won.values, T.dec.values)}")
    for thr in (0.0, 0.05, 0.10):
        s = T[T.ev > thr]; print(f"     P-lite EV > {int(thr*100):2d}%  {rep(s.won.values, s.dec.values)}")
    s = T[T.ev <= 0]; print(f"     P-lite passes   {rep(s.won.values, s.dec.values)}")
