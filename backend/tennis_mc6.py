"""MC v6 (2026-10-15). Asked for as "exactly like mc2 but has recent h2h surface form as
well", then moved onto MC5's base the same day on the user's call ("switch it to mc5 and get
rid of the mc2 version") after the base comparison measured MC5 as the better place for the
terms -- see _mc6_base_choice.py and the table below.

EXACTLY MC5, PLUS TWO TERMS. MC6 does not re-implement anything: it calls tennis_mc5.predict and
shifts its published probability, so every layer below -- MC2's Elo and Markov legs, MC3's
per-surface serve/return ratings, best-of-five, margin-aware Elo, MC5's surface L5, season and
clutch terms, and the thin-sample tilt -- is literally MC5's and cannot drift from it.

    MC6 :  p = sigmoid( logit(p_mc5) + MC6_WH * h2h  +  MC6_WS * sform )

At MC6_WH = MC6_WS = 0 it IS MC5, to the last decimal, which makes the two heads' difference
exactly the two new terms and nothing else. Taking logit of the base's OWN probability rather
than rebuilding its blend by hand is deliberate: the arithmetic is identical for a 50/50 blend,
and it does not assume one, so MC5's predict-time terms are picked up automatically instead of
being silently dropped by a hand-rebuilt blend.

  h2h    RECENCY-WEIGHTED head-to-head, 365-day half-life, damped by how much weighted evidence
         exists (w/(w+1)), so a single old meeting barely moves anything and four recent ones
         move it properly. Carries the weighted win share and a games-margin component -- "if the
         h2h is recent and they beat them easily" was the user's formulation and the margin is
         how "easily" enters.
  sform  SURFACE FORM as a RESIDUAL: the exponentially-weighted mean of (result - what Elo
         expected) over that player's matches on this surface, 5-match half-life, differenced
         between the two players. A plain surface win rate would mostly re-state Elo; the
         residual is the part Elo has NOT absorbed.

WHY MC5'S BASE AND NOT MC2'S (_mc6_base_choice.py, identical rows / terms / weights):

    held-out                 2025              2026
    MC2 + h2h + sform    .6864 / .2236     .6898 / .2224
    MC5 + h2h + sform    .6893 / .2226     .6910 / .2220     <- better on both, both metrics

The two terms add LESS on MC5 (+.0032/+.0031) than on MC2 (+.0044/+.0045) -- the surface-form
term loses about a third of its value, because MC5 already holds per-surface serve/return,
surface Elo, surface L5 and season-on-surface. H2H is unchanged on every base (+.0010/+.0007),
since no base contains H2H. But MC5's base starts +.0041/+.0026 ahead, which more than covers the
third given back. The same redundancy shows in the weight grid: wS = 1.00 was fine on MC2 and is
WORSE than 0.50 on MC5, so the optimum shifts down. wH .25 / wS .50 stays the best tested pair.

A caveat that belongs here rather than in a commit message: the sweep could NOT separate MC3 from
MC5 -- their feature-table legs are byte-identical, because MC5's extra terms live at predict time
rather than in the features, so "MC5" in that table is MC3's legs. By MC5's own design those terms
sit where the cost against MC3 is zero to four decimals, so MC3 is approximately MC5; the live
head now sits on MC5's ACTUAL output, which includes terms the sweep never saw.

WEIGHTS WERE MEASURED FIRST, NOT AFTER (_mc6_sweep.py, 170,714 archive rows, walk-forward,
held-out years). This is the one process lesson from MC5, whose weights had to be set
retrospectively at the smallest values tested. The table below is on MC2's base, where the sweep
was originally run:

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

import tennis_mc5
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

    Returns None when MC5 returns None (either player unrated) or when MC6's own state is
    missing -- never a silent fallback to MC5, so a dead state reads as a blank column rather
    than as MC5's number under MC6's name.
    """
    base = tennis_mc5.predict(p1_name, p2_name, surface, best_of_5=best_of_5)
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
    # MC5's own probability, shifted. At MC6_WH = MC6_WS = 0 this reproduces base["p1_prob"]
    # exactly. Using the base's published number rather than rebuilding its blend means MC5's
    # predict-time terms (surface L5, season, clutch) are carried rather than silently dropped.
    z = _lg(base["p1_prob"]) + MC6_WH * h2h + MC6_WS * sform
    p = 1.0 / (1.0 + math.exp(-z))
    out = dict(base)
    out.update({
        "p1_prob": round(p, 4),
        "mc5_p1": base["p1_prob"],                 # what MC5 said, so the delta is visible
        "d_mc5": round(p - base["p1_prob"], 4),
        "h2h": round(h2h, 4), "h2h_n": int(h_n), "h2h_w": round(h_w, 3),
        "sform": round(sform, 4),
        "sf1": None if sf1 is None else round(sf1, 4),
        "sf2": None if sf2 is None else round(sf2, 4),
        "wh": MC6_WH, "ws": MC6_WS,
        "asof": S.get("asof"),
    })
    return out
