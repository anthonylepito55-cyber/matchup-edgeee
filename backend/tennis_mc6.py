"""MC v6 (2026-10-15, user: "we should make an mc6 thats exactly like mc2 but has recent h2h
surface form as well").

EXACTLY MC2, PLUS TWO TERMS. MC6 does not re-implement anything: it calls tennis_mc2.predict and
re-blends its own published legs, so the Elo leg, the Markov leg, the quadrature over day-form
nodes and the thin-sample tilt are literally MC2's and cannot drift from it.

    MC2 :  p = sigmoid( 0.5*logit(p_elo) + 0.5*logit(p_markov) + asym_tilt )
    MC6 :  p = sigmoid( 0.5*logit(p_elo) + 0.5*logit(p_markov) + asym_tilt
                        + MC6_WH * h2h  +  MC6_WS * sform )

At MC6_WH = MC6_WS = 0 it IS MC2, to the last decimal. That is deliberate: it makes the two
heads' difference exactly the two new terms and nothing else.

  h2h    RECENCY-WEIGHTED head-to-head, 365-day half-life, damped by how much weighted evidence
         exists (w/(w+1)), so a single old meeting barely moves anything and four recent ones
         move it properly. Carries the weighted win share and a games-margin component -- "if the
         h2h is recent and they beat them easily" was the user's formulation and the margin is
         how "easily" enters.
  sform  SURFACE FORM as a RESIDUAL: the exponentially-weighted mean of (result - what Elo
         expected) over that player's matches on this surface, 5-match half-life, differenced
         between the two players. A plain surface win rate would mostly re-state Elo; the
         residual is the part Elo has NOT absorbed.

WEIGHTS WERE MEASURED FIRST, NOT AFTER (_mc6_sweep.py, 170,714 archive rows, walk-forward,
held-out years). This is the one process lesson from MC5, whose weights had to be set
retrospectively at the smallest values tested:

    held-out            2025            2026
    MC2 baseline        .6820 / .2249   .6853 / .2237
    surface form only   +.0034 / -.0010  +.0024 / -.0006      <- the term that works
    h2h only            +.0011 / -.0003  +.0007 / -.0002      <- small, but positive both years
    wH .25 / wS .50     +.0043 / -.0013  +.0045 / -.0012      <- shipped
    wH .25 / wS 1.0     +.0041 / -.0014  +.0048 / -.0014
    wH 1.0 / wS 0       -.0016 / +.0002  -.0023 / +.0005      <- H2H alone, turned up, HURTS

So wS = 0.50 and wH = 0.25. Three things stated honestly about that choice:

 1. THE WIN IS SURFACE FORM, NOT H2H. On its own H2H is worth +0.0007 to +0.0011 AUC, and turned
    up to weight 1.0 it is NEGATIVE in both years. It ships at 0.25 because at that weight it is
    positive in both held-out years and costs nothing -- not because H2H was vindicated.
 2. H2H HAD ALREADY FAILED TWICE on 2026-10-15, before this module existed: the market prices it
    (+0.75pt residual over the de-vigged close at z 2.41, and exactly zero on the bettable dog
    cells), and bolting it onto MC2's full pipeline moved AUC by +0.0001 with a 95% interval
    through zero. MC6 exists at the user's explicit direction after that evidence was presented.
    What changed the number here is the SURFACE-FORM term, which had not been tested before.
 3. THE WEIGHTS WERE CHOSEN ON THE SAME HELD-OUT YEARS THEY ARE REPORTED ON, so +0.0043 is the
    optimistic end. wS = 0.50 is taken rather than the argmax (wS = 1.0 on 2026) precisely to
    leave some of that selection on the table; 2024 shows the same monotone shape, so the
    DIRECTION has three years of agreement even if the exact value does not.

AND THE THING AUC DOES NOT TELL YOU: a better predictor is not a better bet. MC3 and MC5 both beat
MC2 on AUC and neither is bettable -- every MC head measured -8.7% to -9.7% at every edge gate.
MC6 is WATCH-ONLY: a display column and a lane, no board mark, until its own forward record says
otherwise.

State comes from _mc6_build_state.py (rebuilt nightly beside the MC2/MC3 ratings). A missing or
unreadable state makes MC6 return None rather than silently fall back to MC2, so a dead state
shows up as a blank column instead of as MC2's number wearing MC6's name.
"""
import math
import os
import pickle
import threading
import time

import tennis_mc2
from tennis_mc2 import _slug, _surf

# --- the two measured weights (see the table above) -------------------------------------
MC6_WH = 0.25           # recency-weighted H2H -> blend log-odds
MC6_WS = 0.50           # surface-form residual -> blend log-odds
MC6_HL_DAYS = 365.0     # H2H half-life, in days
MC6_MARG_W = 0.35       # how much of the H2H term comes from margin rather than win share
MC6_SFORM_CAP = 0.6     # the residual difference is clipped before weighting

_DIR = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_DIR, "data_cache", "_mc6_state.pkl")
_S = None
_MT = None
_LOCK = threading.Lock()


def _state():
    """Reload when the pickle's mtime changes, so a nightly rebuild is picked up without a
    restart -- the staleness bug of 2026-10-13 was a cached state no one reloaded."""
    global _S, _MT
    if not os.path.exists(_STATE_PATH):
        return None
    mt = os.path.getmtime(_STATE_PATH)
    with _LOCK:
        if _S is None or mt != _MT:
            try:
                with open(_STATE_PATH, "rb") as f:
                    _S = pickle.load(f)
                _MT = mt
            except Exception:  # noqa: BLE001
                return None
    return _S


def _lg(p):
    p = max(min(float(p), 1 - 1e-6), 1e-6)
    return math.log(p / (1 - p))


def _h2h_term(S, s1, s2, surf, today):
    """Recency-weighted H2H from player 1's perspective, damped by weighted evidence."""
    first_is_1 = s1 < s2
    key = (s1, s2) if first_is_1 else (s2, s1)
    mts = (S.get("h2h") or {}).get(key)
    if not mts:
        return 0.0, 0, 0.0
    wsum = shr = mrg = 0.0
    for d, wf, mf, _sf in mts:
        age = max(today - float(d), 0.0)
        w = 0.5 ** (age / MC6_HL_DAYS)
        wsum += w
        shr += w * (1.0 if wf else 0.0)
        mrg += w * float(mf)
    if wsum <= 0:
        return 0.0, len(mts), 0.0
    share = shr / wsum - 0.5                      # +0.5 = first-named won everything recently
    marg = max(min((mrg / wsum) / 6.0, 1.5), -1.5)
    raw = (1.0 - MC6_MARG_W) * (2.0 * share) + MC6_MARG_W * marg
    damp = wsum / (wsum + 1.0)                    # one old meeting must barely count
    sgn = 1.0 if first_is_1 else -1.0
    return sgn * raw * damp, len(mts), wsum


def _sform_term(S, s1, s2, surf):
    """Difference of the two players' surface-form residuals."""
    sf = S.get("sform") or {}
    a = sf.get((s1, surf))
    b = sf.get((s2, surf))
    if a is None and b is None:
        return 0.0, None, None
    a = 0.0 if a is None else float(a)
    b = 0.0 if b is None else float(b)
    return max(min(a - b, MC6_SFORM_CAP), -MC6_SFORM_CAP), a, b


def predict(p1_name, p2_name, surface, market_p1=None, best_of_5=False):
    """MC6 = MC2's blend plus the recency-weighted H2H and surface-form terms.

    Returns None when MC2 returns None (either player unrated) or when MC6's own state is
    missing -- never a silent fallback to MC2, so a dead state reads as a blank column rather
    than as MC2's number under MC6's name.
    """
    base = tennis_mc2.predict(p1_name, p2_name, surface,
                              market_p1=market_p1, best_of_5=best_of_5)
    if base is None:
        return None
    S = _state()
    if not S:
        return None
    surf = _surf(surface)
    s1, s2 = _slug(p1_name, surface), _slug(p2_name, surface)
    if not s1 or not s2:
        return None
    today = time.time() / 86400.0
    h2h, h_n, h_w = _h2h_term(S, s1, s2, surf, today)
    sform, sf1, sf2 = _sform_term(S, s1, s2, surf)
    # MC2's own legs, re-blended. At MC6_WH = MC6_WS = 0 this reproduces base["p1_prob"] exactly.
    z = (0.5 * _lg(base["elo_p1"]) + 0.5 * _lg(base["mkv_p1"]) + float(base.get("asym") or 0.0)
         + MC6_WH * h2h + MC6_WS * sform)
    p = 1.0 / (1.0 + math.exp(-z))
    out = dict(base)
    out.update({
        "p1_prob": round(p, 4),
        "mc2_p1": base["p1_prob"],                 # what MC2 said, so the delta is visible
        "d_mc2": round(p - base["p1_prob"], 4),
        "h2h": round(h2h, 4), "h2h_n": int(h_n), "h2h_w": round(h_w, 3),
        "sform": round(sform, 4),
        "sf1": None if sf1 is None else round(sf1, 4),
        "sf2": None if sf2 is None else round(sf2, 4),
        "wh": MC6_WH, "ws": MC6_WS,
        "asof": S.get("asof"),
    })
    return out
