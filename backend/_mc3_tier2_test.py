"""MC3 TIER 2 (2026-10-13, user: "do tier 2").

Three pieces of information already sitting in MC3's state and feature table, unused by the
live head. Each tested on its own against shipped MC3, on identical rows, then the winners
combined.

  4. SERVE DECOMPOSITION. The head collapses a player to one serve-points-won number. The
     builder already computes the decomposed version per match as `pa_dec`:
         f1*(base1[surf] + S1 - R1_opp) + (1-f1)*(base2[surf] + S2 - R2_opp) + 0.5*tspeed
     i.e. first-serve-in rate times first-serve-points-won, plus the second-serve branch, with
     a tournament-speed term. CAVEAT, stated up front: pa_dec uses CAREER S1/S2/R1/R2 (the
     per-surface change applied only to S/R) and adds tspeed, so swapping it in changes more
     than one thing. If it wins, the follow-up is to make the 1st/2nd ratings per-surface too.
     Also tested as a 50/50 average of the two point estimates, which is the conservative way
     to use a second opinion about the same quantity.

  5. TIEBREAK SKILL. `_p_tb` prices a tiebreak off the two serve numbers alone:
     p = 0.5*(pa + (1-pb)). The state carries tbw/tbn and the builder exposes the shrunk,
     centred rate `tbr = (tbw + 2.5)/(tbn + 5) - 0.5`. Tiebreaks decide a lot of tennis.
     Done WITHOUT re-implementing the set recursion: `_set_dist` returns the full
     {(games_a, games_b, was_tiebreak): prob} map, so
         P(reach tb)      = sum of the two tb-flagged entries
         P(win, no tb)    = sum of non-tb entries where a > b
         P(win set | ptb) = P(win, no tb) + P(reach tb) * ptb
     is an exact substitution of any tiebreak probability into the engine's own set
     distribution.

  6. RESOLUTION. `_rnd` clamps the serve-point probability to [0.40, 0.85] and rounds to 2
     decimals, so the chain's input is quantised to 1% steps and dominant servers saturate at
     the cap. Tested at 3 decimals with the clamp widened to [0.35, 0.92].

Everything else is shipped MC3: per-surface ratings, best-of-five from the score, the same
per-player sigma, the same 50/50 Elo blend, day tilt off.
"""
import gc
import math
import os

from functools import lru_cache

import numpy as np
import pandas as pd

from tennis_mc2 import _NODES, _p_tb, _rnd, _set_dist
from tennis_mc3 import MC3_KS

FEAT = "data_cache/_mc3_features.parquet"
if not os.path.exists(FEAT):
    raise SystemExit("missing %s -- run _mc3_build.py" % FEAT)


def rnd3(x):
    return round(min(max(x, 0.35), 0.92), 3)


@lru_cache(maxsize=400000)
def set_parts(pa, pb):
    """-> (P(win set, no tiebreak), P(reach tiebreak)) from the engine's own distribution."""
    d = _set_dist(pa, pb)
    reach = sum(v for (_a, _b, tb), v in d if tb == 1)
    nowin = sum(v for (a, b, tb), v in d if tb == 0 and a > b)
    return nowin, reach


@lru_cache(maxsize=2000000)
def p_match_of(pa, pb, bo5, tb_adj=0.0):
    nowin, reach = set_parts(pa, pb)
    ptb = _p_tb(pa, pb) + tb_adj
    ptb = min(max(ptb, 0.0), 1.0)
    s = nowin + reach * ptb
    s = min(max(s, 1e-6), 1 - 1e-6)
    if bo5:
        q = 1 - s
        return s ** 3 * (1 + 3 * q + 6 * q * q)
    return s * s * (1 + 2 * (1 - s))


def sets_won(score):
    if not isinstance(score, str) or not score.strip():
        return None, None
    a = b = 0
    for tok in score.split():
        t = tok.split("(")[0]
        if "-" not in t:
            continue
        x, _, y = t.partition("-")
        try:
            x, y = int(x), int(y)
        except ValueError:
            continue
        if x > y:
            a += 1
        elif y > x:
            b += 1
    return (a, b) if (a or b) else (None, None)


COLS = ["year", "p_elo", "pa_pt", "pb_pt", "pa_dec", "pb_dec", "nS_a", "nS_b",
        "tbr_a", "tbr_b", "imp", "won", "surf", "score"]
F = pd.read_parquet(FEAT, columns=COLS)
F = F[F["imp"].notna() & F["won"].notna() & F["pa_pt"].notna() & F["pb_pt"].notna()
      & F["p_elo"].notna() & (F["nS_a"] >= 4) & (F["nS_b"] >= 4)].reset_index(drop=True)
sa, sb = zip(*[sets_won(s) for s in F["score"]])
bo5 = ((pd.Series(sa, dtype="float64") >= 3)
       | (pd.Series(sb, dtype="float64") >= 3)).fillna(False).to_numpy()
dec_ok = F["pa_dec"].notna().to_numpy() & F["pb_dec"].notna().to_numpy()
print("rows %d   bo5 %d   pa_dec present on %d (%.0f%%)"
      % (len(F), int(bo5.sum()), int(dec_ok.sum()), 100 * dec_ok.mean()))

PA = F["pa_pt"].to_numpy(dtype=float)
PB = F["pb_pt"].to_numpy(dtype=float)
DA = F["pa_dec"].to_numpy(dtype=float)
DB = F["pb_dec"].to_numpy(dtype=float)
SGA = 0.10 / np.sqrt(np.maximum(F["nS_a"].to_numpy(dtype=float), 4.0))
SGB = 0.10 / np.sqrt(np.maximum(F["nS_b"].to_numpy(dtype=float), 4.0))
TBA = F["tbr_a"].fillna(0.0).to_numpy(dtype=float)
TBB = F["tbr_b"].fillna(0.0).to_numpy(dtype=float)
ELO = F["p_elo"].to_numpy(dtype=float)
WON = F["won"].to_numpy(dtype=float)
MKT = F["imp"].to_numpy(dtype=float)
YR = F["year"].to_numpy()


def run(pa, pb, tb_adj, quant):
    """Sigma-integrated match prob, then the 50/50 log-odds Elo blend."""
    pm = np.zeros(len(F))
    for xi, wi in _NODES:
        for xj, wj in _NODES:
            pm += wi * wj * np.array(
                [p_match_of(quant(x + xi * sa_), quant(y + xj * sb_), bool(f),
                            round(t, 3))
                 for x, y, sa_, sb_, f, t in zip(pa, pb, SGA, SGB, bo5, tb_adj)])
    lgm = np.log(np.clip(pm, 1e-6, 1 - 1e-6) / (1 - np.clip(pm, 1e-6, 1 - 1e-6)))
    lge = np.log(np.clip(ELO, 1e-6, 1 - 1e-6) / (1 - np.clip(ELO, 1e-6, 1 - 1e-6)))
    return 1 / (1 + np.exp(-(0.5 * lge + 0.5 * lgm)))


ZERO = np.zeros(len(F))
TBADJ = TBA - TBB
MIX_A = np.where(dec_ok, 0.5 * (PA + DA), PA)
MIX_B = np.where(dec_ok, 0.5 * (PB + DB), PB)
DEC_A = np.where(dec_ok, DA, PA)
DEC_B = np.where(dec_ok, DB, PB)

VARIANTS = [
    ("MC3 (shipped)", PA, PB, ZERO, _rnd),
    ("+ decomposition", DEC_A, DEC_B, ZERO, _rnd),
    ("+ decomp 50/50 mix", MIX_A, MIX_B, ZERO, _rnd),
    ("+ tiebreak skill", PA, PB, TBADJ, _rnd),
    ("+ resolution (3dp)", PA, PB, ZERO, rnd3),
]
res = {}
for lab, pa, pb, tb, q in VARIANTS:
    res[lab] = run(pa, pb, tb, q)
    print("   scored %s" % lab)
    gc.collect()


def line(lab, p, m):
    from sklearn.metrics import roc_auc_score
    n = int(m.sum())
    if n < 200:
        return "   %-22s (n=%d)" % (lab, n)
    return ("   %-22s AUC %.4f  Brier %.4f   |model-mkt| %5.2fpt"
            % (lab, roc_auc_score(WON[m], p[m]),
               float(((p[m] - WON[m]) ** 2).mean()),
               100 * float(np.abs(p[m] - MKT[m]).mean())))


BAR = "=" * 86
print("\n" + BAR)
print("OVERALL  (n=%d)   market Brier %.4f" % (len(F), float(((MKT - WON) ** 2).mean())))
print(BAR)
allm = np.ones(len(F), bool)
for lab in res:
    print(line(lab, res[lab], allm))

print("\n" + BAR)
print("BY YEAR -- a Tier-2 change has to hold in all three, like the Tier-1 ones did")
print(BAR)
for y in (2024, 2025, 2026):
    m = YR == y
    print("  %d (n=%d)   market Brier %.4f" % (y, int(m.sum()),
                                               float(((MKT[m] - WON[m]) ** 2).mean())))
    for lab in res:
        print(line(lab, res[lab], m))

print("\n" + BAR)
print("TIEBREAK SKILL -- only meaningful where the two actually differ")
print(BAR)
big = np.abs(TBADJ) > 0.05
print("  |tbr gap| > 5pt  (n=%d)" % int(big.sum()))
for lab in ("MC3 (shipped)", "+ tiebreak skill"):
    print(line(lab, res[lab], big))

print("\n" + BAR)
print("RESOLUTION -- only meaningful where the clamp or rounding actually bit")
print(BAR)
at_cap = (PA >= 0.85) | (PB >= 0.85) | (PA <= 0.40) | (PB <= 0.40)
print("  at the [0.40, 0.85] clamp  (n=%d, %.1f%% of rows)"
      % (int(at_cap.sum()), 100 * at_cap.mean()))
for lab in ("MC3 (shipped)", "+ resolution (3dp)"):
    print(line(lab, res[lab], at_cap))

print("\nMC3_KS=%g" % MC3_KS)
