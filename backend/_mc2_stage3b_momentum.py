# MC v2 — STAGE 3b: SET-DEPENDENCE CALIBRATION (2026-10-08). The iid-sets engine
# over-predicts 3-setters (46% vs 34.9% real), TBs (35 vs 28) and overs (61 vs 47).
# Fix: a COMMON day-form tilt tau (one player is better today), integrated at match
# level: pa+tau, pb-tau over GH nodes -> sets become positively correlated and the
# match compresses. This grid-fits sigma_day to the realized 3-set rate and verifies
# TB/O21.5 improve too (Brier) on 20k sampled real score lines.
import numpy as np
import pandas as pd
from functools import lru_cache
from math import comb

F = pd.read_parquet("data_cache/_mc2_features.parquet")
F = F[(F["year"] >= 2024) & F["imp"].notna() & (F["nS_a"] >= 8) & (F["nS_b"] >= 8)]


def parse_score(sc):
    if not isinstance(sc, str) or not sc.strip() or "ret" in sc.lower() or "w/o" in sc.lower():
        return None
    sa = sb = g = tb = 0
    for tok in sc.split():
        t = tok.split("(")[0]
        if "-" not in t:
            continue
        try:
            x, y = map(int, t.split("-"))
        except ValueError:
            return None
        if x > 20 or y > 20:
            return None
        g += x + y
        if (x, y) in ((7, 6), (6, 7)):
            tb = 1
        sa += x > y
        sb += y > x
    if sa + sb < 2 or sa + sb > 3 or max(sa, sb) != 2:
        return None
    return sa, sb, g, tb


par = F["score"].map(parse_score)
F = F[par.notna()].sample(n=min(20000, int(par.notna().sum())), random_state=7).copy()
pr = np.array([list(x) for x in F["score"].map(parse_score)])
F["r3"] = (pr[:, 0] + pr[:, 1]) == 3
F["rg"] = pr[:, 2]
F["rtb"] = pr[:, 3]
print(f"sample: {len(F)}", flush=True)


@lru_cache(maxsize=200000)
def p_game(p):
    q = 1 - p
    return (p**4) * (1 + 4 * q + 10 * q * q) + 20 * (p**3) * (q**3) * (p * p / (p * p + q * q))


@lru_cache(maxsize=200000)
def p_tb(pa, pb):
    p = 0.5 * (pa + (1 - pb))
    q = 1 - p
    w = sum(comb(6 + k, k) * (p**7) * (q**k) for k in range(6))
    return w + comb(12, 6) * (p**6) * (q**6) * (p * p / (p * p + q * q))


@lru_cache(maxsize=100000)
def set_summary(pa, pb):
    """(s_win, e_games, p_settb) one set."""
    ga, gb = p_game(pa), 1 - p_game(pb)
    ptb = p_tb(pa, pb)
    acc = [0.0, 0.0, 0.0]

    def rec(a, b, asv, prob):
        if prob < 1e-9:
            return
        if (a >= 6 or b >= 6) and abs(a - b) >= 2 or a == 7 or b == 7:
            acc[0] += prob if a > b else 0.0
            acc[1] += prob * (a + b)
            return
        if a == 6 and b == 6:
            acc[0] += prob * ptb
            acc[1] += prob * 13
            acc[2] += prob
            return
        pw = ga if asv else gb
        rec(a + 1, b, not asv, prob * pw)
        rec(a, b + 1, not asv, prob * (1 - pw))
    rec(0, 0, True, 0.5)
    rec(0, 0, False, 0.5)
    return tuple(acc)


@lru_cache(maxsize=100000)
def match_stats(pa, pb):
    """(p_match, p3sets, e_games, p_anytb approx) with iid sets given (pa,pb)."""
    s, eg, ptb = set_summary(pa, pb)
    p3 = 2 * s * (1 - s)                      # first two sets split
    pm = s * s + 2 * s * s * (1 - s)
    e_sets = 2 + p3
    e_g = eg * e_sets
    p_no_tb = (1 - ptb) ** e_sets             # approx
    return pm, p3, e_g, 1 - p_no_tb


def rnd(x):
    return round(min(max(x, 0.40), 0.85), 2)


@lru_cache(maxsize=100000)
def anchor(pa, pb, target):
    lo, hi = -0.10, 0.10
    for _ in range(22):
        mid = 0.5 * (lo + hi)
        if match_stats(rnd(pa + mid), rnd(pb - mid))[0] < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


NOD = ((-1.7320508, 1 / 6), (0.0, 2 / 3), (1.7320508, 1 / 6))
pa0 = F["pa_dec"].round(2).values
pb0 = F["pb_dec"].round(2).values
imp = F["imp"].round(3).values
deltas = np.array([anchor(a, b, t) for a, b, t in zip(pa0, pb0, imp)])
paA = np.clip(pa0 + deltas, 0.40, 0.85)
pbA = np.clip(pb0 - deltas, 0.40, 0.85)

real3 = F["r3"].mean()
realO = (F["rg"] >= 22).mean()
realTB = F["rtb"].mean()
print(f"realized: 3set {100*real3:.1f}%  O21.5 {100*realO:.1f}%  TB {100*realTB:.1f}%", flush=True)
for sd in (0.0, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08):
    p3 = np.zeros(len(F)); eg = np.zeros(len(F)); ptb = np.zeros(len(F)); pm = np.zeros(len(F))
    for x, w in NOD:
        tau = x * sd
        r = np.array([match_stats(rnd(a + tau), rnd(b - tau))
                      for a, b in zip(paA, pbA)])
        pm += w * r[:, 0]; p3 += w * r[:, 1]; eg += w * r[:, 2]; ptb += w * r[:, 3]
    pO = np.clip((eg - 18.0) / 9.0, 0.02, 0.98)        # placeholder monotone map
    b3 = np.mean((p3 - F["r3"].values) ** 2)
    btb = np.mean((ptb - F["rtb"].values) ** 2)
    print(f"sigma_day {sd:.2f}: 3set {100*p3.mean():.1f}% (Brier {b3:.4f})  "
          f"TB {100*ptb.mean():.1f}% (Brier {btb:.4f})  e_games {eg.mean():.1f} "
          f"(real {F['rg'].mean():.1f})  anchor-drift pm {100*pm.mean():.1f} vs imp {100*imp.mean():.1f}",
          flush=True)
