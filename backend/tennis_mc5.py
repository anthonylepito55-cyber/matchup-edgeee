"""MC v5 (2026-10-13, user: "i want a mc5 shipped with all that").

MC3 plus the two things the user asked for: a recency-weighted LAST FIVE ON THIS SURFACE, and
PRESSURE/CLUTCH points. Its own head and its own state, so MC2 and MC3 are untouched and all
three earn separate records.

HONEST STATUS, recorded here because it would be wrong to bury it. Every one of these terms was
measured against MC3 on 120,877 archive rows before shipping, and NONE of them improved it:

    surface L5 results into Elo     w=0.10 identical to MC3, degrades monotonically above
    surface L5 serve residual       w=0.10 identical in 2024-25, worse in 2026
    clutch into the Markov log-odds w=1.0  identical to MC3, degrades above

The reason is not that the ideas are poor, it is that MC3 already holds this information in a
better form:
  * the last five RESULTS are already in Elo, which moves 5-10 points per match
  * the last five SERVE performances are already in `Sf`, an exponentially-weighted serve
    residual whose 5.4-match half-life makes ~47% of it the last five matches
  * per-surface is already in MC3's serve/return ratings (shrunk at KS=20) and its surface Elo
  * clutch has now been refuted three separate ways on this family -- as tiebreak skill, as a
    stacker feature where its coefficient flipped sign between windows, and directly here

So the weights below are set at the smallest values tested, where the measured cost against MC3
is zero to four decimals. The terms are live and functioning; they are simply quiet. Turning
them up is a one-line change and the numbers above say what it costs.

Shipped at the user's explicit direction after that evidence was presented.
"""
import math
import os
import pickle
import threading

from tennis_mc2 import _NODES, _rnd, _surf, _slug, p_match
from tennis_mc3 import MC3_KS, MC3_MOV_W

# --- the MC3 recipe MC5 inherits, imported so they cannot drift -------------------------
MC5_KS = MC3_KS                 # per-surface serve/return shrink
MC5_MOV_W = MC3_MOV_W           # margin-aware Elo

# --- the three new terms, at the weights where the measured cost is zero ----------------
MC5_L5_RES = 0.10               # surface last-5 RESULTS -> Elo log-odds
# "l5 stats dont matter as much" (user, 2026-10-13), and the measurement agreed -- the serve
# residual was the worst of the three terms, degrading AUC by 0.3pt at 0.25 and 4pt at 1.0. So
# it is kept at a third of the results weight: present, barely audible.
MC5_L5_SRV = 0.03               # surface last-5 serve residual -> point probability
# SEASON-TO-DATE ON THIS SURFACE -- the one term in MC5 that MEASURES BETTER than MC3, and the
# one that shipped untested. Swept afterwards (_mc5_seasonal_sweep.py) on 120,877 rows:
#   W     2024            2025            2026
#   0     .6723 / .2274   .6806 / .2254   .6882 / .2231   (MC3)
#   0.50  .6733 / .2271   .6807 / .2252   .6889 / .2228   <- raised to this
#   1.00  .6737 / .2269   .6804 / .2252   .6892 / .2227   2025 AUC now BELOW control
#   3.00  .6712 / .2271   .6766 / .2260   .6872 / .2231
# 0.50 is the largest weight that improves AUC and Brier in all three years; 2024 and 2026 keep
# gaining to 1.00 but 2025 turns over first, and the curve is clearly bracketed by 3.00.
#
# The user's refinement -- scale this by how many games the player had that season -- was tested
# and is WORSE at every weight and every constant (W=0.50: fixed .6733 vs scaled .6726-.6728,
# monotone in the scaling strength). It double-discounts: the EB shrinkage below already handles
# an unreliable RATE, so scaling the WEIGHT on top discards the thin-season rows twice, and the
# thinner side has 4 or fewer matches on 37.8% of rows. Flat weight stays.
MC5_SEAS = 0.50                 # season-to-date win rate ON THIS SURFACE -> Elo log-odds
MC5_SEAS_K = 5.0                # EB pseudo-matches at 50%, so a 2-match season cannot shout
MC5_CLUTCH = 1.0                # pressure-point residual -> Markov log-odds
MC5_L5_MIN = 3                  # both sides need this many prior matches on the surface
L5_WEIGHTS = [5.0, 4.0, 3.0, 2.0, 1.0]      # most recent first: "soonest to latest"

_DIR = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_DIR, "data_cache", "_mc5_state.pkl")
_S = None
_MT = None
_LOCK = threading.Lock()


def _state():
    global _S, _MT
    if not os.path.exists(_STATE_PATH):
        return None
    mt = os.path.getmtime(_STATE_PATH)
    with _LOCK:
        if _S is None or mt != _MT:
            with open(_STATE_PATH, "rb") as f:
                _S = pickle.load(f)
            _MT = mt
    return _S


def _l5_surf(st, surf):
    """(win rate, serve residual, n) over the last five matches ON THIS SURFACE.

    Weighted 5/4/3/2/1 from the MOST RECENT backwards -- the user's "soonest wins or losses to
    latest" -- and normalised over however many of the five exist, so a player with three prior
    matches on the surface is not penalised for the two that do not.

    hist rows are (date, nsets, is_ret, won, spw_resid, surf), newest last. The serve value is
    a RESIDUAL (actual minus what was expected against that specific opponent), so it already
    carries the opponent adjustment and a high number means "served above their own level
    against that returner" rather than "played someone weak".
    """
    h = [x for x in (st.get("hist") or [])
         if len(x) > 5 and x[5] == surf and x[3] is not None][-5:]
    if not h:
        return 0.5, 0.0, 0
    rec = list(reversed(h))
    w = L5_WEIGHTS[:len(rec)]
    tot = sum(w)
    win = sum(wi * float(r[3]) for wi, r in zip(w, rec)) / tot
    srv = sum(wi * float(r[4] if r[4] is not None else 0.0) for wi, r in zip(w, rec)) / tot
    return win, srv, len(rec)


def _season_surf(st, surf, year):
    """Season-to-date win rate ON THIS SURFACE, empirical-Bayes shrunk toward 0.5.

    A longer window than the last five and a shorter one than the career rating, which is the
    gap the user pointed at. Counted from a per-(year, surface) tally the builder keeps, updated
    only AFTER each match's feature row is emitted, so it is strictly prior at read time.

    Shrinkage matters here more than for the L5 block: in January a player may have two matches
    on the surface, and an unshrunk 100% would swamp the Elo term. With k=5 a 2-0 season reads
    0.64 rather than 1.00.
    """
    tally = (st.get("seas") or {}).get((int(year), surf))
    if not tally:
        return 0.5, 0
    wins, n = float(tally[0]), float(tally[1])
    if n <= 0:
        return 0.5, 0
    return (wins + MC5_SEAS_K * 0.5) / (n + MC5_SEAS_K), int(n)


def _clutch(st):
    """Empirical-Bayes pressure-point rate, centred on zero. 25 pseudo-points at 50%."""
    pw = float(st.get("pw") or 0.0)
    pa = float(st.get("pa") or 0.0)
    return (pw + 25 * 0.5) / (pa + 25) - 0.5


def _bl(st, key, cnt, srf):
    n = float(st[cnt][srf])
    w = n / (n + MC5_KS)
    return w * st[key + "_s"][srf] + (1 - w) * st[key]


def _point_probs(a, b, surf):
    bs = _state()["base"][surf]
    Sa = 0.7 * _bl(a, "S", "nS_s", surf) + 0.3 * a["Sf"]
    Ra = 0.7 * _bl(a, "R", "nR_s", surf) + 0.3 * a["Rf"]
    Sb = 0.7 * _bl(b, "S", "nS_s", surf) + 0.3 * b["Sf"]
    Rb = 0.7 * _bl(b, "R", "nR_s", surf) + 0.3 * b["Rf"]
    return _rnd(bs + Sa - Rb), _rnd(bs + Sb - Ra)


def _lg(p):
    p = min(max(float(p), 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def predict(p1_name, p2_name, surface, best_of_5=False, market_p1=None):
    """MC5's head. None when either player is unrated. Market-free, like MC2 and MC3."""
    S = _state()
    if not S:
        return None
    surf = _surf(surface)
    s1, s2 = _slug(p1_name, surface), _slug(p2_name, surface)
    a = S["players"].get(s1) if s1 else None
    b = S["players"].get(s2) if s2 else None
    if not a or not b or a["nS"] < 4 or b["nS"] < 4:
        return None
    if "S_s" not in a or "S_s" not in b:
        return None
    pa, pb = _point_probs(a, b, surf)

    # the surface last-5 block, applied only where BOTH sides have enough of a history for it
    w5a, s5a, n5a = _l5_surf(a, surf)
    w5b, s5b, n5b = _l5_surf(b, surf)
    live5 = (n5a >= MC5_L5_MIN and n5b >= MC5_L5_MIN)
    if live5:
        pa = _rnd(pa + MC5_L5_SRV * s5a)
        pb = _rnd(pb + MC5_L5_SRV * s5b)

    sg_a = 0.10 / max(a["nS"], 4) ** 0.5
    sg_b = 0.10 / max(b["nS"], 4) ** 0.5
    pm = 0.0
    for xi, wi in _NODES:
        for xj, wj in _NODES:
            pm += wi * wj * p_match(_rnd(pa + xi * sg_a), _rnd(pb + xj * sg_b), best_of_5)

    # clutch adjusts the Markov half in log-odds
    dclutch = _clutch(a) - _clutch(b)
    z_mkv = _lg(pm) + MC5_CLUTCH * dclutch

    # surface-shrunk Elo, plus the last-5 RESULT differential in log-odds
    wa = a["ns"][surf] / (a["ns"][surf] + 20.0)
    wb = b["ns"][surf] / (b["ns"][surf] + 20.0)
    elo_a = 0.7 * a["elo"] + 0.3 * (wa * a["elo_s"][surf] + (1 - wa) * a["elo"])
    elo_b = 0.7 * b["elo"] + 0.3 * (wb * b["elo_s"][surf] + (1 - wb) * b["elo"])
    p_elo = 1 / (1 + 10 ** ((elo_b - elo_a) / 400))
    z_elo = _lg(p_elo) + (MC5_L5_RES * (w5a - w5b) if live5 else 0.0)
    # season-to-date on this surface, on top of the last-5 and independent of it
    import datetime
    _yr = datetime.date.today().year
    sw_a, sn_a = _season_surf(a, surf, _yr)
    sw_b, sn_b = _season_surf(b, surf, _yr)
    if sn_a > 0 and sn_b > 0:
        z_elo += MC5_SEAS * (sw_a - sw_b)

    p_blend = 1 / (1 + math.exp(-(0.5 * z_elo + 0.5 * z_mkv)))
    return {"p1_prob": round(p_blend, 4), "elo_p1": round(p_elo, 4),
            "mkv_p1": round(pm, 4), "pa_pt": pa, "pb_pt": pb,
            "n1": int(a["nS"]), "n2": int(b["nS"]),
            "ns1": int(a["nS_s"][surf]), "ns2": int(b["nS_s"][surf]),
            "l5n1": int(n5a), "l5n2": int(n5b), "l5_live": bool(live5),
            "l5win1": round(w5a, 3), "l5win2": round(w5b, 3),
            "seas1": round(sw_a, 3), "seas2": round(sw_b, 3),
            "seasn1": int(sn_a), "seasn2": int(sn_b),
            "clutch1": round(_clutch(a), 4), "clutch2": round(_clutch(b), 4),
            "bo5": bool(best_of_5),
            "sigma": round(sg_a + sg_b, 4)}
