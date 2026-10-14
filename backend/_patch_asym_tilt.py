"""SHIP THE SAMPLE-ASYMMETRY TILT into MC2, MC3 and MC5 (2026-10-13).

User: "it seems to me like mc 2 and mc3 definitely over price games when someone has less game
meaning betteer stats" (Silva 19 matches vs Borg 83 -> MC2 71% on Silva, market 24.3%, Borg won).

Confirmed at scale and diagnosed over three failed fix attempts (see _thin_shrink_sweep.py and
_thin_which_half.py). The bias is NOT thin stats looking too good -- it is that Elo starts every
player at the population mean and the serve/return deviations start at zero, so a barely-seen
player is PINNED too close to average by construction. The model already rates the thin player
lower and widens the gap correctly with asymmetry; the gap is simply far too small.

So the correction expands rather than shrinks, and applies to the finished blend rather than to
either half (both halves carry the bias in equal measure):

    z' = z + LAM * log10(n_thick / n_thin)      signed toward the better-known player

MEASURED (full archive, 120,877 rows, _thin_tilt.py / _thin_tilt_mc2.py):
    thin-side error at 10x asymmetry   MC3 +8.74pt -> +0.79pt  |  MC2 +10.00pt -> +1.92pt
    Brier                              MC3  .2274 -> .2261     |  MC2  .2285 -> .2270
    AUC improves in 2024, 2025 AND 2026 on both heads, and Brier improves at all four levels
    (futures, challenger, tour, slam) independently -- one parameter, seven confirmations.
    The optimum is bracketed on both sides (L=0.60 is clearly worse) and is interior.

LAM = 0.35 is one constant for all three heads, sitting between MC3's optimum (0.30) and MC2's
(0.40) rather than fitting a separate number per head. A two-slope version was tested and bought
nothing (.2262 vs .2261), so the single slope ships.
"""
import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def patch(name, olds, news, expect=1):
    p = os.path.join(HERE, name)
    s = io.open(p, encoding="utf-8").read()
    for old, new in zip(olds, news):
        assert s.count(old) == expect, "%s: found %d of %r" % (name, s.count(old), old[:70])
        s = s.replace(old, new)
    io.open(p, "w", encoding="utf-8", newline="").write(s)
    print("patched %s" % name)


# ---------------------------------------------------------------- MC2: the shared definition
HELPER = '''

# ======================================================================================
# SAMPLE-ASYMMETRY TILT (2026-10-13). One definition, imported by MC3 and MC5.
#
# Both halves of the blend start a player at the population mean (Elo 1500, serve/return
# deviation 0) and converge toward truth as matches accumulate, so a player with few
# tracked matches is structurally pinned too close to average. Measured consequence: the
# thin side was overrated by +10.00pt (MC2) / +8.74pt (MC3) at 10x sample asymmetry while
# the market was flat to +/-0.75pt everywhere.
#
# The correction is in log-odds, monotone in the asymmetry, and exactly zero when the two
# samples are equal -- so a symmetric matchup is untouched. Shrinking the ratings instead
# was tested twice and made the bias WORSE, because it pushes the way the defect already
# goes. Full evidence in _thin_tilt.py.
MC_TILT = 0.35


def asym_tilt(n1, n2):
    """Log-odds nudge AWAY from the thinner-sampled player. Positive favours player 1."""
    if not MC_TILT:
        return 0.0
    a = max(float(n1 or 0.0), 1.0)
    b = max(float(n2 or 0.0), 1.0)
    if a == b:
        return 0.0
    return MC_TILT * _log10(max(a, b) / min(a, b)) * (1.0 if a > b else -1.0)
'''

patch("tennis_mc2.py",
      ["from math import comb"],
      ["from math import comb, log10 as _log10" + HELPER])

patch("tennis_mc2.py",
      ["    p_blend = 1 / (1 + math.exp(-(0.5 * lg(p_elo) + 0.5 * lg(pm))))",
       '            "n1": int(a["nS"]), "n2": int(b["nS"]), "bo5": bool(best_of_5),'],
      ["    _asym = asym_tilt(a[\"nS\"], b[\"nS\"])\n"
       "    p_blend = 1 / (1 + math.exp(-(0.5 * lg(p_elo) + 0.5 * lg(pm) + _asym)))",
       '            "n1": int(a["nS"]), "n2": int(b["nS"]), "bo5": bool(best_of_5),\n'
       '            "asym": round(_asym, 4),'])

# ---------------------------------------------------------------------------------- MC3
patch("tennis_mc3.py",
      ["from tennis_mc2 import (_NODES, DAY_SD, _p_set, _rnd, _surf, _slug,"],
      ["from tennis_mc2 import (_NODES, DAY_SD, _p_set, _rnd, _surf, _slug, asym_tilt,"])
patch("tennis_mc3.py",
      ["    p_blend = 1 / (1 + math.exp(-(0.5 * lg(p_elo) + 0.5 * lg(pm))))",
       '            "bo5": bool(best_of_5), "ks": MC3_KS, "tilt": MC3_DAY_TILT,'],
      ["    _asym = asym_tilt(a[\"nS\"], b[\"nS\"])\n"
       "    p_blend = 1 / (1 + math.exp(-(0.5 * lg(p_elo) + 0.5 * lg(pm) + _asym)))",
       '            "bo5": bool(best_of_5), "ks": MC3_KS, "tilt": MC3_DAY_TILT,\n'
       '            "asym": round(_asym, 4),'])

# ---------------------------------------------------------------------------------- MC5
patch("tennis_mc5.py",
      ["from tennis_mc2 import _NODES, _rnd, _surf, _slug, p_match"],
      ["from tennis_mc2 import _NODES, _rnd, _surf, _slug, p_match, asym_tilt"])
patch("tennis_mc5.py",
      ["    p_blend = 1 / (1 + math.exp(-(0.5 * z_elo + 0.5 * z_mkv)))",
       '            "n1": int(a["nS"]), "n2": int(b["nS"]),\n'
       '            "ns1": int(a["nS_s"][surf]), "ns2": int(b["nS_s"][surf]),\n'
       '            "l5n1": int(n5a), "l5n2": int(n5b), "l5_live": bool(live5),'],
      ["    _asym = asym_tilt(a[\"nS\"], b[\"nS\"])\n"
       "    p_blend = 1 / (1 + math.exp(-(0.5 * z_elo + 0.5 * z_mkv + _asym)))",
       '            "n1": int(a["nS"]), "n2": int(b["nS"]), "asym": round(_asym, 4),\n'
       '            "ns1": int(a["nS_s"][surf]), "ns2": int(b["nS_s"][surf]),\n'
       '            "l5n1": int(n5a), "l5n2": int(n5b), "l5_live": bool(live5),'])

# ------------------------------------------------------------------------------- verify
for f in ("tennis_mc2.py", "tennis_mc3.py", "tennis_mc5.py"):
    s = io.open(os.path.join(HERE, f), encoding="utf-8").read()
    n = len(re.findall(r"_asym\b", s))
    assert "asym_tilt(" in s and n >= 3, "%s: tilt not wired (%d refs)" % (f, n)
    print("   %-16s asym refs %d" % (f, n))
print("RESULT: OK -- MC_TILT = 0.35 wired into all three heads")
