"""SCORE-STRING CLASSIFICATION: did this match actually finish? (2026-10-16)

TennisRatio strips retirement and walkover markers and KEEPS the row -- zero of its 617,495 rows
contain "ret", "w/o" or "def". So an unfinished match is indistinguishable from a finished one
unless the SCORE SHAPE is inspected, which is why nothing downstream has ever excluded them.

Measured on the archive (_unfinished_match_audit.py):

    retired mid-set      24,134   3.91%
    retired after a set   2,460   0.40%
    walkover                 57   0.01%
    UNFINISHED total     26,651   4.32%      (ITF 5.16%, challenger 3.40%, tour 3.05%)

    and 1 in 33 matches the margin term calls "dominant" (+4 games) never finished.

ONE DEFINITION, SHARED. The state builder, the head and the sweeps all import from here so they
cannot drift -- the duplicate-key bug of 2026-10-13 came from two places implementing "the same"
rule slightly differently.

THE RULE, structural rather than label-based:
  * no sets recorded                -> WALKOVER. No tennis was played.
  * the LAST set is not a legitimate completed set -> RETIRED MID-SET. A set ends 6-0..6-4, 7-5
    or 7-6 (or mirrored); a match whose final set reads 4-1, 3-0 or 2-1 stopped part-way.
  * exactly one set, legitimately won -> RETIRED AFTER A SET. Best-of-three has no one-set
    outcome, so a single completed set means the opponent stopped.
  * otherwise                       -> COMPLETE.

A deliberately conservative edge: a first-to-4 or short-set format would be misread as a
retirement. Those are rare in this archive (the set-count distribution is overwhelmingly 2 and 3)
and the failure is in the safe direction -- a real match dropped from a margin average costs
almost nothing, while a retirement counted as a thrashing is exactly the error being removed.
"""
import re

_SET_RE = re.compile(r"(\d+)\s*-\s*(\d+)")

COMPLETE = "complete"
RETIRED_MIDSET = "retired_midset"
RETIRED_AFTER_SET = "retired_after_set"
WALKOVER = "walkover"


def sets_of(score):
    """Every set in the string as (a, b). Tie-break point scores are excluded by the 30 cap."""
    out = []
    for a, b in _SET_RE.findall(str(score or "")):
        a, b = int(a), int(b)
        if a > 30 or b > 30:
            continue
        out.append((a, b))
    return out


def is_legit_set(a, b):
    """A completed set: 6-0..6-4, 7-5 or 7-6, either way round."""
    hi, lo = max(a, b), min(a, b)
    return (hi == 6 and lo <= 4) or (hi == 7 and lo in (5, 6))


def classify(score):
    """COMPLETE / RETIRED_MIDSET / RETIRED_AFTER_SET / WALKOVER."""
    sets = sets_of(score)
    if not sets:
        return WALKOVER
    if not is_legit_set(*sets[-1]):
        return RETIRED_MIDSET
    if len(sets) == 1:
        return RETIRED_AFTER_SET
    return COMPLETE


def is_unfinished(score):
    return classify(score) != COMPLETE


def games_margin(score):
    """(games for the first-named player) - (games for the other), over completed sets only.

    Note this is the RAW margin and says nothing about whether the match finished -- callers that
    care (MC6's "beat them easily" term) must gate on classify() themselves, which is the point of
    keeping the two separate.
    """
    d = 0
    for a, b in sets_of(score):
        d += a - b
    return float(d)
