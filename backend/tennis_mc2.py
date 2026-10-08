"""MC v2 — production module (2026-10-08). The day's build, shipped:
surface-Elo family + opponent-adjusted serve/return ratings (+fatigue/injury/clutch
learned features live in the ratings themselves) -> closed-form point->game->set->match
Markov with parameter-uncertainty quadrature.

predict():      display/ledger head — an INDEPENDENT, well-calibrated third opinion
                (walk-forward 2024-26: blend AUC .692/LL .636 vs market .722/.613;
                calibration within ~1pt in every 10%-bucket). NEVER a naked bet signal:
                the Stage-4 reckoning measured residual-vs-close ~= market minus vig.
distribution(): the ANCHORED engine — point-probs shifted so the match prob equals the
                live no-vig market (validated choice: the anchored twin beat the native
                model on set-score LL / TB Brier / totals Brier on 65,723 real score
                lines) -> prices for Polymarket's derivative markets (set winner/
                handicap, first-set, match/set totals).

State: data_cache/_mc2_state.pkl written by _mc2_stage1b_serve_return.py (rerun it to
refresh ratings after new archive ingests). Names resolve to TennisRatio slugs via
tennis_context.get_context.
"""
import os
import pickle
from functools import lru_cache
from math import comb

_DIR = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_DIR, "data_cache", "_mc2_state.pkl")
_S = None


def _state():
    global _S
    if _S is None:
        with open(_STATE_PATH, "rb") as f:
            _S = pickle.load(f)
    return _S


def _slug(name, surface):
    try:
        import tennis_context as tc
        g = tc.get_context(name, surface)
        return g["slug"] if g else None
    except Exception:  # noqa: BLE001
        return None


def _surf(surface):
    s = str(surface or "Hard").lower()
    return "clay" if "clay" in s else ("grass" if "grass" in s else "hard")


def _rnd(x):
    return round(min(max(x, 0.40), 0.85), 2)


@lru_cache(maxsize=100000)
def _p_game(p):
    q = 1 - p
    return (p**4) * (1 + 4 * q + 10 * q * q) + 20 * (p**3) * (q**3) * (p * p / (p * p + q * q))


@lru_cache(maxsize=100000)
def _p_tb(pa, pb):
    p = 0.5 * (pa + (1 - pb))
    q = 1 - p
    win = sum(comb(6 + k, k) * (p**7) * (q**k) for k in range(6))
    return win + comb(12, 6) * (p**6) * (q**6) * (p * p / (p * p + q * q))


@lru_cache(maxsize=50000)
def _set_dist(pa, pb):
    """{(games_a, games_b, tb): prob} for one set, serve-first averaged."""
    ga, gb = _p_game(pa), 1 - _p_game(pb)
    ptb = _p_tb(pa, pb)
    out = {}

    def rec(a, b, asv, prob):
        if prob < 1e-9:
            return
        if (a >= 6 or b >= 6) and abs(a - b) >= 2 or a == 7 or b == 7:
            out[(a, b, 0)] = out.get((a, b, 0), 0.0) + prob
            return
        if a == 6 and b == 6:
            out[(7, 6, 1)] = out.get((7, 6, 1), 0.0) + prob * ptb
            out[(6, 7, 1)] = out.get((6, 7, 1), 0.0) + prob * (1 - ptb)
            return
        pw = ga if asv else gb
        rec(a + 1, b, not asv, prob * pw)
        rec(a, b + 1, not asv, prob * (1 - pw))
    rec(0, 0, True, 0.5)
    rec(0, 0, False, 0.5)
    return tuple(sorted(out.items()))


@lru_cache(maxsize=50000)
def _p_set(pa, pb):
    return sum(v for (a, b, _), v in _set_dist(pa, pb) if a > b)


@lru_cache(maxsize=50000)
def _p_match(pa, pb):
    s = _p_set(pa, pb)
    return s * s + 2 * s * s * (1 - s)


_NODES = ((-1.7320508, 1 / 6), (0.0, 2 / 3), (1.7320508, 1 / 6))


def _point_probs(st_a, st_b, surf):
    S = _state()
    bs = S["base"][surf]
    Sa = 0.7 * st_a["S"] + 0.3 * st_a["Sf"]
    Ra = 0.7 * st_a["R"] + 0.3 * st_a["Rf"]
    Sb = 0.7 * st_b["S"] + 0.3 * st_b["Sf"]
    Rb = 0.7 * st_b["R"] + 0.3 * st_b["Rf"]
    return _rnd(bs + Sa - Rb), _rnd(bs + Sb - Ra)


def predict(p1_name, p2_name, surface, market_p1=None):
    """Independent MC2 head for display/ledger. None when either player is unrated."""
    S = _state()
    surf = _surf(surface)
    s1, s2 = _slug(p1_name, surface), _slug(p2_name, surface)
    a = S["players"].get(s1) if s1 else None
    b = S["players"].get(s2) if s2 else None
    if not a or not b or a["nS"] < 4 or b["nS"] < 4:
        return None
    pa, pb = _point_probs(a, b, surf)
    sg_a = 0.10 / max(a["nS"], 4) ** 0.5
    sg_b = 0.10 / max(b["nS"], 4) ** 0.5
    pm = 0.0
    for xi, wi in _NODES:
        for xj, wj in _NODES:
            pm += wi * wj * _p_match(_rnd(pa + xi * sg_a), _rnd(pb + xj * sg_b))
    # surface-shrunk Elo blend (same formula as the training pass)
    wa = a["ns"][surf] / (a["ns"][surf] + 20.0)
    wb = b["ns"][surf] / (b["ns"][surf] + 20.0)
    elo_a = 0.7 * a["elo"] + 0.3 * (wa * a["elo_s"][surf] + (1 - wa) * a["elo"])
    elo_b = 0.7 * b["elo"] + 0.3 * (wb * b["elo_s"][surf] + (1 - wb) * b["elo"])
    p_elo = 1 / (1 + 10 ** ((elo_b - elo_a) / 400))
    import math
    lg = lambda p: math.log(max(min(p, 1 - 1e-6), 1e-6) / (1 - max(min(p, 1 - 1e-6), 1e-6)))
    p_blend = 1 / (1 + math.exp(-(0.5 * lg(p_elo) + 0.5 * lg(pm))))
    return {"p1_prob": round(p_blend, 4), "elo_p1": round(p_elo, 4),
            "mkv_p1": round(pm, 4), "pa_pt": pa, "pb_pt": pb,
            "n1": int(a["nS"]), "n2": int(b["nS"]),
            "sigma": round(sg_a + sg_b, 4)}


@lru_cache(maxsize=20000)
def _anchor(pa, pb, target):
    lo, hi = -0.10, 0.10
    for _ in range(24):
        mid = 0.5 * (lo + hi)
        if _p_match(_rnd(pa + mid), _rnd(pb - mid)) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def distribution(p1_name, p2_name, surface, market_p1):
    """ANCHORED derivative prices for PM's set/total/handicap markets. Requires a live
    no-vig market_p1 (the anchor). None when unrated or unanchored."""
    if market_p1 is None or not (0.02 < market_p1 < 0.98):
        return None
    base = predict(p1_name, p2_name, surface)
    if base is None:
        return None
    pa, pb = base["pa_pt"], base["pb_pt"]
    d = _anchor(pa, pb, round(float(market_p1), 3))
    pa, pb = _rnd(pa + d), _rnd(pb - d)
    sd = dict(_set_dist(pa, pb))
    s = sum(v for (a, b, _), v in sd.items() if a > b)
    p20, p21 = s * s, 2 * s * s * (1 - s)
    q20, q21 = (1 - s) ** 2, 2 * (1 - s) ** 2 * s
    # set-winner marginals -> games/tb convolution over match paths
    winA, winB = {}, {}
    for (a, b, t), v in sd.items():
        dct = winA if a > b else winB
        dct[(a + b, t)] = dct.get((a + b, t), 0.0) + v
    sA = sum(winA.values()) or 1.0
    sB = sum(winB.values()) or 1.0
    nA = {k: v / sA for k, v in winA.items()}
    nB = {k: v / sB for k, v in winB.items()}
    games, tb_any = {}, 0.0
    paths = [([nA, nA], p20), ([nB, nB], q20),
             ([nA, nB, nA], p21 / 2), ([nB, nA, nA], p21 / 2),
             ([nB, nA, nB], q21 / 2), ([nA, nB, nB], q21 / 2)]
    for seq, pw in paths:
        if pw <= 0:
            continue
        cur = {(0, 0): 1.0}
        for dd in seq:
            nxt = {}
            for (g0, t0), v0 in cur.items():
                for (g1, t1), v1 in dd.items():
                    k = (g0 + g1, max(t0, t1))
                    nxt[k] = nxt.get(k, 0.0) + v0 * v1
            cur = nxt
        for (g, t), v in cur.items():
            games[g] = games.get(g, 0.0) + pw * v
            if t:
                tb_any += pw * v
    tot = sum(games.values()) or 1.0
    overs = {ln: round(sum(v for g, v in games.items() if g > ln) / tot, 4)
             for ln in (19.5, 20.5, 21.5, 22.5, 23.5)}
    return {"match_p1": round(float(market_p1), 4), "set1_p1": round(s, 4),
            "p1_20": round(p20, 4), "p1_21": round(p21, 4),
            "p2_21": round(q21, 4), "p2_20": round(q20, 4),
            "straight_sets": round(p20 + q20, 4), "tb_any": round(tb_any, 4),
            "over_games": overs,
            "p1_set_hcp_m1_5": round(p20, 4),      # p1 -1.5 sets = wins 2-0
            "p2_set_hcp_p1_5": round(1 - p20, 4)}


if __name__ == "__main__":
    print(predict("Carlos Alcaraz", "Holger Rune", "Hard"))
    print(distribution("Carlos Alcaraz", "Holger Rune", "Hard", 0.74))
