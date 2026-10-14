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

FAVOURITE PICKS (2026-10-09, user "build the p favorite picks", after being shown the
live check): same model, the other side -- back the -100..-200 favourite (in matches whose
dog is +100..+200, P's universe) when P's favourite EV >= 3%. Out-of-sample 2024-26:
men +8.6% (n=1,752), women +17.1% (n=1,476), positive every year. BUT the live P-lite
check (frozen log, n=200) was negative: men -12.7% (37), women -6.8% (14) -- the same
backtest-favourite / live-fail pattern seen four times. Shown with both numbers; lane
p_fav decides.
"""
import json
import os

import numpy as np

_here = os.path.dirname(os.path.abspath(__file__))
ARTIFACT_P = os.path.join(_here, "model_artifacts", "tennis_model_p.json")
FEATS = ["d_vs_band", "g_C", "g_gray", "g_Dma", "d_form_win", "d_m_perf", "d_m_won",
         "d_sutr", "d_lrank", "is_chall", "is_itf"]
EV_BET = 0.05
EV_FAV = 0.03
# DOG BAND by gender (2026-10-09, user "ship P" after the +250 rebuild): women +100..+250
# (+200..+250 slice +27.2% n=666, every year +, 2026 +35.3%); men stay +100..+200 (men's
# +200..+250 went -0.2% in 2026). Max decimal odds per gender:
# WIDENED 2026-10-13 (user: "model p can go over -250 and over +250 now") from
# {"M": 3.0, "W": 3.5} to +500 both genders, with the model RETRAINED on the wider
# universe rather than the filter merely lifted. See _patch_p_wide.py for the numbers;
# the new regions are watch-only lanes (p_dog_250up / p_fav_250up), not board marks.
BAND = {"M": 6.0, "W": 6.0}
# the favourite gate's shortest acceptable price. 1.2 decimal = -500, the paired side of
# a +500 dog. Was 1.5 (-200).
FAV_DEC_MIN = 1.2
# Ⓟ CLOSE (2026-10-09, user "mark the 3pt and up ones"): a -100..-150 favourite that P
# reads >= 3pt above the market. Out-of-sample 2024-26: men 63.1% hit +8.2% (n=869),
# women 67.8% hit +16.4% (n=587); every year positive. Live ~P check (9/28-10/9): men
# +2.6% (n=38), women -23.2% (n=14). Lane p_close.
CLOSE_EDGE = 0.03


# CLOSE TIERS (2026-10-09, user "yes" to splitting by edge). Disjoint, out-of-sample
# 2024-26 (_close_tiers.out): T1 3-10pt  M 59.7% hit +2.2% (580) | W 63.8% +9.6% (257)
#                             T2 10-15pt M 62.5% +7.5% (168)    | W 62.2% +7.1% (143)
#                             T3 15pt+   M 80.2% +37.6% (121)   | W 77.5% +32.9% (187)
def close_tier(edge):
    return 3 if edge >= 0.15 else (2 if edge >= 0.10 else 1)


def _close(p_fav, mkt_fav, fod):
    return bool(fod is not None and (1 + 100 / 150) <= fod <= 2.0
                and (p_fav - mkt_fav) >= CLOSE_EDGE)
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


def train(rows_path=os.path.join(_here, "data_cache", "_model_p250_rows.parquet"), lam=2.0):
    """Fit the serving weights on ALL archive P rows (2022-2026), per gender, each gender on
    its own dog band (BAND)."""
    import pandas as pd
    from scipy.optimize import minimize
    D = pd.read_parquet(rows_path)
    out = {"feats": FEATS, "ev_bet": EV_BET, "band": BAND, "trained_on": int(len(D)), "g": {}}
    keep_lite = (_load() or {}).get("lite")
    for G in ("M", "W"):
        S = D[(D.G == G) & (D.player_odd <= BAND[G])]
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
    if keep_lite:
        out["lite"] = keep_lite
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
    _lgG = str(league or "").lower()
    _G = "W" if ("wta" in _lgG or "itf_women" in _lgG) else "M"
    if od is None or not (2.0 <= od <= art.get("band", BAND).get(_G, 3.0)):
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
    fod = _dec(p2_odds if dog1 else p1_odds)
    fev = ((1 - p) * fod - 1) if fod else None
    fav_bet = bool(fev is not None and FAV_DEC_MIN <= fod <= 2.0 and fev >= EV_FAV)
    return {"dog": 1 if dog1 else 2, "p_dog": round(float(p), 4), "mkt_dog": round(float(mk), 4),
            "ev": round(float(ev), 4), "bet": bool(ev >= art.get("ev_bet", EV_BET)), "g": G,
            "fav": 2 if dog1 else 1, "p_fav": round(float(1 - p), 4),
            "fav_ev": (round(float(fev), 4) if fev is not None else None), "fav_bet": fav_bet,
            "close": _close(1 - p, 1 - mk, fod), "close_edge": round(float((1 - p) - (1 - mk)), 4),
            "close_tier": close_tier(float((1 - p) - (1 - mk)))}


# ---------------------------------------------------------------------------------------
# ~P REPLAY for previous days (2026-10-09, user "and on any previous day picks it would
# have had the signal for"). Before 10-09 the log has no Model P and P's stat inputs were
# never frozen, and rebuilding them from today's profiles would leak results. So history
# uses a LITE replay from the frozen pre-match numbers only: g_C + g_gray (+ g_Dma where
# D-MA was logged), weights fit on archive P rows dated BEFORE 2026-09-01 -- earlier than
# every game in the live log, so no replayed game was in its training. Shown as "~P",
# never counted in the P lanes.
LITE_CUTOFF = "2026-09-01"


def train_lite(rows_path=os.path.join(_here, "data_cache", "_model_p250_rows.parquet"), lam=2.0):
    import pandas as pd
    from scipy.optimize import minimize
    D = pd.read_parquet(rows_path)
    D = D[pd.to_datetime(D["date"]) < pd.Timestamp(LITE_CUTOFF)]
    D = D[D.player_odd <= D.G.map(BAND)]
    art = _load() or {}
    lite = {"cutoff": LITE_CUTOFF}
    for tag, feats in (("l3", ["g_C", "g_gray", "g_Dma"]), ("l2", ["g_C", "g_gray"])):
        lite[tag] = {"feats": feats}
        for G in ("M", "W"):
            S = D[D.G == G]
            mu, sd = S[feats].mean(), S[feats].std().replace(0, 1)
            X = ((S[feats] - mu) / sd).fillna(0).values
            y, off = S.won.values.astype(float), S.off.values
            Xb = np.column_stack([np.ones(len(X)), X])

            def f(w):
                z = off + Xb @ w
                p = 1 / (1 + np.exp(-z))
                g = -(Xb.T @ (y - p))
                g[1:] += lam * w[1:]
                return -np.sum(y * z - np.logaddexp(0, z)) + 0.5 * lam * np.sum(w[1:] ** 2), g
            w = minimize(f, np.zeros(len(feats) + 1), jac=True, method="L-BFGS-B").x
            lite[tag][G] = {"w": [float(v) for v in w], "mu": [float(v) for v in mu.values],
                            "sd": [float(v) for v in sd.values], "n": int(len(S))}
    art["lite"] = lite
    with open(ARTIFACT_P, "w", encoding="utf-8") as fh:
        json.dump(art, fh, indent=1)
    return lite


def history_p(r, mk1):
    """Model P for a logged (finished) row: the frozen pick when P was live (recon False),
    else the ~P lite replay (recon True). Returns None when P doesn't apply."""
    import pandas as pd

    def g(k):
        v = r.get(k)
        return None if (v is None or pd.isna(v)) else float(v)
    if mk1 is None:
        return None
    dog1 = mk1 < 0.5
    od, fo = _dec(r.get("p1_odds") if dog1 else r.get("p2_odds")), _dec(r.get("p2_odds") if dog1 else r.get("p1_odds"))
    lg9 = str(r.get("league") or "").lower()
    G = "W" if ("wta" in lg9 or "itf_women" in lg9) else "M"
    if od is None or not (2.0 <= od <= BAND[G]):
        return None
    mk = mk1 if dog1 else 1 - mk1
    if g("model_p_ev") is not None and g("model_p_prob") is not None:
        p, recon = g("model_p_prob"), False
    else:
        art = _load() or {}
        lite = art.get("lite")
        c, cma, dma = g("model_c_p1"), g("model_cma_p1"), g("model_dma_p1")
        if not lite or c is None or cma is None:
            return None
        pick = (lambda v: v if dog1 else 1 - v)
        off = _lg(mk)
        x = {"g_C": _lg(pick(c)) - off, "g_gray": _lg(pick(cma)) - off}
        tag = "l2"
        if dma is not None:
            x["g_Dma"] = _lg(pick(dma)) - off
            tag = "l3"
        mdl = lite[tag][G]
        xs = np.array([(x[k] - m) / s for k, m, s in zip(lite[tag]["feats"], mdl["mu"], mdl["sd"])])
        p = float(1 / (1 + np.exp(-(off + mdl["w"][0] + float(xs @ np.array(mdl["w"][1:]))))))
        recon = True
    ev = p * od - 1
    fev = ((1 - p) * fo - 1) if fo else None
    return {"dog": 1 if dog1 else 2, "p_dog": round(p, 4), "p_fav": round(1 - p, 4), "mkt_dog": round(mk, 4),
            "ev": round(ev, 4), "bet": bool(ev >= EV_BET), "g": G,
            "fav": 2 if dog1 else 1, "fav_ev": (round(fev, 4) if fev is not None else None),
            "fav_bet": bool(fev is not None and FAV_DEC_MIN <= fo <= 2.0 and fev >= EV_FAV),
            "recon": recon,
            "close": _close(1 - p, 1 - mk, fo), "close_edge": round(1 - p - (1 - mk), 4),
            "close_tier": close_tier(1 - p - (1 - mk))}
