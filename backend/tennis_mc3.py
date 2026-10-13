"""MC v3 (2026-10-13, user: "build mc3 with tier 1 dont touch mc2").

MC2 with three changes, each one either a measured win or an outright bug fix. It is a SEPARATE
head with its own state file and its own log column, so MC2 keeps running unchanged and the two
can be compared on a live forward record before anything is promoted.

  1. PER-SURFACE SERVE/RETURN, shrunk toward career.
     MC2's S and R are single career values -- surface reaches its Markov half only through the
     league-wide base(surface) baseline, so it cannot represent a surface-specific weakness.
     MC3 keeps a surface rating and blends it toward career by surface sample count:
         w     = nS_surf / (nS_surf + MC3_KS)
         S_eff = w * S_surf + (1 - w) * S_career
     Measured over 170,507 matches / 120,796 scored: better in all three years on BOTH AUC and
     Brier, and the mean departure from market goes DOWN rather than up. Clay 0.6615 -> 0.6680
     AUC, grass 0.6799 -> 0.6849, hard flat (hard is the modal surface, so a career rating is
     already mostly a hard-court rating). A PURE three-way split was tested and FAILED -- it
     thins every rating -- which is why this is a shrunk blend and not a split.

  2. BEST-OF-FIVE IS ACTUALLY MODELLED.
     MC2's `_p_match` is `s**2 + 2*s**2*(1-s)`, best-of-three, unconditionally. Every slam and
     Davis Cup match was priced as a three-setter, which understates the better player, since
     more sets give the favourite more chances to convert an edge. Straight bug.

  3. THE DAY-FORM TILT -- TRIED AND REJECTED, left switchable and OFF.
     The plan was to apply MC2's DAY_SD = 0.06 tilt to the pick, since Stage 3b measured it
     correcting a 7-14 point derivative bias and `predict` calls the untilted chain. Validated
     and it FAILS: best AUC of any variant, but worse Brier than the unmodified baseline in
     every year and on every surface, and the mean departure from market rises instead of
     falling (9.46 -> 9.99pt overall; on five-setters Brier 0.1995 -> 0.2053).
     The reason is that the tilt moves the two players in OPPOSITE directions, so integrating
     over it widens the distribution of the point-probability GAP, and the match function is
     convex in that gap -- which pushes the probability AWAY from 50% and makes the head more
     confident, not less. The tilt genuinely belongs where it was measured, in the set-market
     DISTRIBUTIONS, where extra set-outcome variance is the thing being modelled. MC2 was right
     not to apply it to the pick. Flip MC3_DAY_TILT to re-test, but the number above is the bar.

The Markov chain itself is IMPORTED from tennis_mc2, never re-implemented, so point -> game ->
tiebreak -> set has exactly one definition in the codebase and MC3 cannot silently drift from it.
MC3 adds only the match-level layer (best-of-3 vs best-of-5) on top of that shared set
probability.

NOT changed from MC2, deliberately, so the three above are attributable: the 50/50 Elo/Markov
log-odds blend, the surface-shrunk Elo, the 0.7 career / 0.3 fast-form split, the per-player
sigma 0.10/sqrt(nS), the >=4-serve-rated-matches gate, and the market being unused.
"""
import os
import pickle
import threading

# The chain has ONE definition, in tennis_mc2. _p_set is the shared set probability; _rnd is the
# same quantiser so the lru_caches behind it are shared rather than duplicated.
from tennis_mc2 import (_NODES, DAY_SD, _p_set, _rnd, _surf, _slug,
                        p_match as _p_match_any)

MC3_KS = 20.0          # surface-vs-career shrink; _mc3_build.py imports THIS, never its own copy
# Measured worse on Brier in every year and surface (see note 3 above). Kept as a switch so the
# experiment is reproducible, not because it is a tuning knob.
MC3_DAY_TILT = False

_DIR = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_DIR, "data_cache", "_mc3_state.pkl")
_S = None
_MT = None
_LOCK = threading.Lock()


def _state():
    """Load (and hot-reload) MC3's own state. Never reads MC2's."""
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


def _bl(st, key, cnt, srf):
    """Surface rating shrunk toward the career rating by surface sample count.

    Must stay identical to the expectation the builder trains with -- both sites in
    _mc3_build.py's transform use this same formula, and MC3_KS is imported from here so the
    two cannot fall out of step.
    """
    n = float(st[cnt][srf])
    w = n / (n + MC3_KS)
    return w * st[key + "_s"][srf] + (1 - w) * st[key]


def _point_probs(a, b, surf):
    bs = _state()["base"][surf]
    Sa = 0.7 * _bl(a, "S", "nS_s", surf) + 0.3 * a["Sf"]
    Ra = 0.7 * _bl(a, "R", "nR_s", surf) + 0.3 * a["Rf"]
    Sb = 0.7 * _bl(b, "S", "nS_s", surf) + 0.3 * b["Sf"]
    Rb = 0.7 * _bl(b, "R", "nR_s", surf) + 0.3 * b["Rf"]
    return _rnd(bs + Sa - Rb), _rnd(bs + Sb - Ra)


# sets -> match now has ONE definition, in tennis_mc2, and MC3 re-exports it. It lived here
# first because MC2 could not express best-of-five at all; now that MC2 can, keeping a second
# copy would be exactly the drift this module's docstring promises to avoid.
p_match = _p_match_any


def predict(p1_name, p2_name, surface, best_of_5=False, market_p1=None):
    """MC3's independent head. None when either player is unrated, same gate as MC2.

    market_p1 is accepted for call-site symmetry with MC2 and is NOT used -- MC3 is market-free,
    like MC2.
    """
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
        return None                      # state predates the per-surface fields
    pa, pb = _point_probs(a, b, surf)
    sg_a = 0.10 / max(a["nS"], 4) ** 0.5
    sg_b = 0.10 / max(b["nS"], 4) ** 0.5
    # Nested Gauss-Hermite integration over each player's rating uncertainty, exactly as MC2
    # does it. The day-tilt loop collapses to a single zero node because MC3_DAY_TILT is off --
    # see note 3 in the module docstring for the measurement that closed it.
    pm = 0.0
    _tn = _NODES if MC3_DAY_TILT else ((0.0, 1.0),)
    for xt, wt in _tn:
        for xi, wi in _NODES:
            for xj, wj in _NODES:
                pm += wt * wi * wj * p_match(_rnd(pa + xi * sg_a + xt * DAY_SD),
                                             _rnd(pb + xj * sg_b - xt * DAY_SD),
                                             best_of_5)
    # surface-shrunk Elo, unchanged from MC2
    wa = a["ns"][surf] / (a["ns"][surf] + 20.0)
    wb = b["ns"][surf] / (b["ns"][surf] + 20.0)
    elo_a = 0.7 * a["elo"] + 0.3 * (wa * a["elo_s"][surf] + (1 - wa) * a["elo"])
    elo_b = 0.7 * b["elo"] + 0.3 * (wb * b["elo_s"][surf] + (1 - wb) * b["elo"])
    p_elo = 1 / (1 + 10 ** ((elo_b - elo_a) / 400))
    import math
    def lg(p):
        p = min(max(p, 1e-6), 1 - 1e-6)
        return math.log(p / (1 - p))
    p_blend = 1 / (1 + math.exp(-(0.5 * lg(p_elo) + 0.5 * lg(pm))))
    return {"p1_prob": round(p_blend, 4), "elo_p1": round(p_elo, 4),
            "mkv_p1": round(pm, 4), "pa_pt": pa, "pb_pt": pb,
            "n1": int(a["nS"]), "n2": int(b["nS"]),
            "ns1": int(a["nS_s"][surf]), "ns2": int(b["nS_s"][surf]),
            "bo5": bool(best_of_5), "ks": MC3_KS, "tilt": MC3_DAY_TILT,
            "sigma": round(sg_a + sg_b, 4)}
