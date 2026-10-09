"""MODEL P -- the PROFIT model (2026-10-09, user: "build it but only +100 to +200").

An OFFSET model on the market: logit(P) = logit(market) + b.x. The market is a fixed
baseline P cannot learn to copy; P only learns where the price is wrong. Scope: market
DOGS priced +100..+200 only. Separate MEN / WOMEN weights.

Inputs (dog minus favourite, standardised with the training mean/sd):
  d_vs_band   record vs opponents of the rival's calibre      (from predict_c)
  g_C         logit(C) - logit(market) on the dog
  g_gray      logit(C market-aware) - logit(market)
  g_Dma       logit(D market-aware) - logit(market)
  d_form_win  recent form vs own baseline (contrarian)          (from predict_d)
  d_m_perf, d_m_won   52w match-quality                         (from predict_c)
  d_sutr      court UTR gap                                     (from predict_d)
  d_lrank     rank gap                                          (from predict_c)
  is_chall, is_itf    level flags

Validation (_model_p_build.py; strict two-level walk-forward, base C/D fit on years < Y,
P fit on years < Y): pooled 2024-26 out-of-sample, +100..+200 dogs at closing odds --
  men   every dog -7.4% (n=11,497) | P EV>0 +10.1% (n=4,316) | EV>5% +14.2% (n=3,235)
  women every dog -6.0% (n=7,162)  | P EV>0 +19.2% (n=2,863) | EV>5% +21.4% (n=2,442)
  monotone by EV quintile both genders; positive every year (2026: M +8.1%, W +12.0% at 5%).
Live proxy (P-lite on C/gray/D-MA only, frozen log 10/01-10/09): bets M +24.8% (58) vs
passes -3.8%; W +25.4% (26) vs -0.1%. Small; the p_dog lane is the judge.
The bet rule shown on the board is EV >= 5%.
"""
import json
import os

import numpy as np

_here = os.path.dirname(os.path.abspath(__file__))
ARTIFACT_P = os.path.join(_here, "model_artifacts", "tennis_model_p.json")
FEATS = ["d_vs_band", "g_C", "g_gray", "g_Dma", "d_form_win", "d_m_perf", "d_m_won",
         "d_sutr", "d_lrank", "is_chall", "is_itf"]
EV_BET = 0.05
_CACHE = {"mtime": None, "art": None}


def _lg(p):
    p = min(max(float(p), 1e-6), 1 - 1e-6)
    return float(np.log(p / (1 - p)))


def _dec(a):
    try:
        a = float(a)
    except (TypeError, ValueError):
        return None
    if a == 0:
        return None
    return 1 + a / 100.0 if a > 0 else 1 + 100.0 / abs(a)


def train(rows_path=os.path.join(_here, "data_cache", "_model_p_rows.parquet"), lam=2.0):
    """Fit the serving weights on ALL archive P rows (2022-2026), per gender."""
    import pandas as pd
    from scipy.optimize import minimize
    D = pd.read_parquet(rows_path)
    out = {"feats": FEATS, "ev_bet": EV_BET, "trained_on": int(len(D)), "g": {}}
    for G in ("M", "W"):
        S = D[D.G == G]
        mu, sd = S[FEATS].mean(), S[FEATS].std().replace(0, 1)
        X = ((S[FEATS] - mu) / sd).fillna(0).values
        y, off = S.won.values.astype(float), S.off.values
        Xb = np.column_stack([np.ones(len(X)), X])

        def f(w):
            z = off + Xb @ w
            p = 1 / (1 + np.exp(-z))
            g = -(Xb.T @ (y - p))
            g[1:] += lam * w[1:]
            return -np.sum(y * z - np.logaddexp(0, z)) + 0.5 * lam * np.sum(w[1:] ** 2), g
        w = minimize(f, np.zeros(len(FEATS) + 1), jac=True, method="L-BFGS-B").x
        out["g"][G] = {"w": [float(v) for v in w], "mu": [float(v) for v in mu.values],
                       "sd": [float(v) for v in sd.values], "n": int(len(S))}
    os.makedirs(os.path.dirname(ARTIFACT_P), exist_ok=True)
    with open(ARTIFACT_P, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    return out


def _load():
    if not os.path.exists(ARTIFACT_P):
        return None
    mt = os.path.getmtime(ARTIFACT_P)
    if _CACHE["mtime"] != mt:
        with open(ARTIFACT_P, encoding="utf-8") as fh:
            _CACHE["art"] = json.load(fh)
        _CACHE["mtime"] = mt
    return _CACHE["art"]


def predict_p(mc, md, market_p1, league, p1_odds, p2_odds):
    """Model P for one match. Returns None unless the market dog is priced +100..+200
    and C, gray and D-MA are all present. Output is from the DOG's side."""
    art = _load()
    if not art or not mc or not md or market_p1 is None:
        return None
    dog1 = market_p1 < 0.5
    od = _dec(p1_odds if dog1 else p2_odds)
    if od is None or not (2.0 <= od <= 3.0):
        return None
    cp, gp, dp = mc.get("p1_prob"), mc.get("market_aware_p1"), md.get("market_aware_p1")
    if cp is None or gp is None or dp is None:
        return None
    sgn = 1.0 if dog1 else -1.0
    pick = (lambda v: v if dog1 else 1 - v)
    mk = pick(market_p1)
    off = _lg(mk)
    pc, pdf = (mc.get("pf") or {}), (md.get("pf") or {})
    lg9 = str(league or "").lower()
    x = {
        "d_vs_band": sgn * float(pc.get("d_vs_band") or 0.0),
        "g_C": _lg(pick(cp)) - off, "g_gray": _lg(pick(gp)) - off, "g_Dma": _lg(pick(dp)) - off,
        "d_form_win": sgn * float(pdf.get("d_form_win") or 0.0),
        "d_m_perf": sgn * float(pc.get("d_m_perf") or 0.0),
        "d_m_won": sgn * float(pc.get("d_m_won") or 0.0),
        "d_sutr": sgn * float(pdf.get("d_sutr") or 0.0),
        "d_lrank": sgn * float(pc.get("d_lrank") or 0.0),
        "is_chall": 1.0 if "challenger" in lg9 else 0.0,
        "is_itf": 1.0 if "itf" in lg9 else 0.0,
    }
    G = "W" if ("wta" in lg9 or "itf_women" in lg9) else "M"
    g = art["g"][G]
    xs = np.array([(x[k] - m) / s for k, m, s in zip(art["feats"], g["mu"], g["sd"])])
    z = off + g["w"][0] + float(xs @ np.array(g["w"][1:]))
    p = 1 / (1 + np.exp(-z))
    ev = p * od - 1
    return {"dog": 1 if dog1 else 2, "p_dog": round(float(p), 4), "mkt_dog": round(float(mk), 4),
            "ev": round(float(ev), 4), "bet": bool(ev >= art.get("ev_bet", EV_BET)), "g": G}
