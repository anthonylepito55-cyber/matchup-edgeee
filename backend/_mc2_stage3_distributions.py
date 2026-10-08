# MC v2 — STAGE 3 FINALE: the DISTRIBUTION ENGINE (user points 11-12). Exact
# game-level DP (no sampling noise): point-probs -> per-set game-score distribution
# (6-0..7-6 both sides, tiebreak flagged) -> best-of-3 convolution -> per match:
#   P(win), P(2-0)/P(2-1) both sides, P(any tiebreak), total-games distribution.
# Uses the DECOMPOSED point estimates (pa_dec/pb_dec — this is where the benched
# symmetric features earn their keep) + parameter-uncertainty GH mixing + the tbr
# tiebreak-skill adjustment (its own ablation here, where it was predicted to matter).
#
# HONEST SCORECARD vs realized outcomes parsed from 70k score strings (2024+, bo3):
#   set-score multiclass logloss, totals Brier (over 21.5/22.5), TB-occurrence Brier —
#   MC2-native vs MARKET-ANCHORED twin (same engine, point-probs shifted so the match
#   prob equals the no-vig market: the strongest fair baseline). If native structure
#   beats market-anchored anywhere, that's genuine edge beyond the moneyline.
import numpy as np
import pandas as pd
from functools import lru_cache
from math import comb

F = pd.read_parquet("data_cache/_mc2_features.parquet")
F = F[(F["year"] >= 2024) & F["imp"].notna() & (F["nS_a"] >= 8) & (F["nS_b"] >= 8)].copy()
print(f"scored pool: {len(F)}", flush=True)


# ---- realized outcomes from score strings ----
def parse_score(sc):
    """(sets_a, sets_b, games_total, tb_any) or None (ret/w.o./bo5/garbage)."""
    if not isinstance(sc, str) or not sc.strip():
        return None
    low = sc.lower()
    if "ret" in low or "w/o" in low or "wo" == low.strip():
        return None
    sa = sb = g = 0
    tb = 0
    for tok in sc.split():
        t = tok.split("(")[0]
        if "-" not in t:
            continue
        try:
            x, y = t.split("-")
            x, y = int(x), int(y)
        except ValueError:
            return None
        if x > 20 or y > 20:
            return None
        g += x + y
        if (x, y) in ((7, 6), (6, 7)):
            tb = 1
        if x > y:
            sa += 1
        elif y > x:
            sb += 1
    if sa + sb < 2 or sa + sb > 3 or max(sa, sb) != 2:
        return None          # bo3 completed matches only
    return sa, sb, g, tb


parsed = F["score"].map(parse_score)
F = F[parsed.notna()].copy()
pr = np.array([list(x) for x in parsed.dropna()])
F["r_sa"], F["r_sb"], F["r_g"], F["r_tb"] = pr[:, 0], pr[:, 1], pr[:, 2], pr[:, 3]
print(f"with parsed bo3 outcomes: {len(F)}", flush=True)


# ---- exact set distribution DP ----
@lru_cache(maxsize=50000)
def p_game(p):
    q = 1 - p
    return (p**4) * (1 + 4 * q + 10 * q * q) + 20 * (p**3) * (q**3) * (p * p / (p * p + q * q))


@lru_cache(maxsize=50000)
def p_tb(pa, pb):
    p = 0.5 * (pa + (1 - pb))
    q = 1 - p
    win = sum(comb(6 + k, k) * (p**7) * (q**k) for k in range(6))
    return win + comb(12, 6) * (p**6) * (q**6) * (p * p / (p * p + q * q))


@lru_cache(maxsize=20000)
def set_dist(pa, pb, tb_shift):
    """{(games_a, games_b, tb_flag): prob} for one set, serve-first averaged."""
    ga, gb = p_game(pa), 1 - p_game(pb)       # A hold / A break prob
    ptb = min(max(p_tb(pa, pb) + tb_shift, 0.02), 0.98)
    out = {}

    def rec(a, b, aserves, prob, first_a):
        if prob < 1e-9:
            return
        if (a >= 6 or b >= 6) and abs(a - b) >= 2:
            k = (a, b, 0)
            out[k] = out.get(k, 0.0) + prob
            return
        if a == 7 or b == 7:
            k = (a, b, 0)
            out[k] = out.get(k, 0.0) + prob
            return
        if a == 6 and b == 6:
            out[(7, 6, 1)] = out.get((7, 6, 1), 0.0) + prob * ptb
            out[(6, 7, 1)] = out.get((6, 7, 1), 0.0) + prob * (1 - ptb)
            return
        pw = ga if aserves else gb
        rec(a + 1, b, not aserves, prob * pw, first_a)
        rec(a, b + 1, not aserves, prob * (1 - pw), first_a)
    rec(0, 0, True, 0.5, True)
    rec(0, 0, False, 0.5, False)
    return tuple(sorted(out.items()))


def match_dist(pa, pb, tb_shift):
    """per-match: (p_win, p20, p21, q21, q20, p_tb_any, games_pmf dict)."""
    sd = dict(set_dist(round(pa, 2), round(pb, 2), round(tb_shift, 2)))
    s_win = sum(v for (a, b, _), v in sd.items() if a > b)
    # aggregate set outcome -> (win_flag, games, tb)
    p20 = s_win * s_win
    p21 = 2 * s_win * s_win * (1 - s_win)
    q20 = (1 - s_win) ** 2
    q21 = 2 * (1 - s_win) ** 2 * s_win
    # games + tb via convolution over 2 or 3 sets
    # set-level marginals conditioned on winner
    winA = {(g, t): 0.0 for g in range(6, 14) for t in (0, 1)}
    winB = {(g, t): 0.0 for g in range(6, 14) for t in (0, 1)}
    for (a, b, t), v in sd.items():
        d = winA if a > b else winB
        key = (a + b, t)
        d[key] = d.get(key, 0.0) + v
    sA = sum(winA.values())
    sB = sum(winB.values())
    nA = {k: v / sA for k, v in winA.items() if v} if sA else {}
    nB = {k: v / sB for k, v in winB.items() if v} if sB else {}

    games = {}
    tb_any = 0.0

    def acc(seq_p, seq_sets):
        nonlocal tb_any
        tot_p = seq_p
        for combo in seq_sets:
            pass
    # enumerate match paths: AA, BB, ABA.., use set-winner marginals
    paths = [([nA, nA], p20), ([nB, nB], q20),
             ([nA, nB, nA], 0.0), ([nB, nA, nB], 0.0)]
    # 2-1 paths: winner takes 2 sets incl. the 3rd; order of first two = one each (x2)
    p21_each = p21 / 2 if p21 else 0.0
    q21_each = q21 / 2 if q21 else 0.0
    paths = [([nA, nA], p20), ([nB, nB], q20),
             ([nA, nB, nA], p21_each), ([nB, nA, nA], p21_each),
             ([nB, nA, nB], q21_each), ([nA, nB, nB], q21_each)]
    for sets_seq, pw in paths:
        if pw <= 0:
            continue
        # convolve
        cur = {(0, 0): 1.0}
        for d in sets_seq:
            nxt = {}
            for (g0, t0), v0 in cur.items():
                for (g1, t1), v1 in d.items():
                    k = (g0 + g1, max(t0, t1))
                    nxt[k] = nxt.get(k, 0.0) + v0 * v1
            cur = nxt
        for (g, t), v in cur.items():
            games[g] = games.get(g, 0.0) + pw * v
            if t:
                tb_any += pw * v
    return s_win * s_win + p21, p20, p21, q21, q20, tb_any, games


# GH nodes for parameter uncertainty
NODES = ((-1.7320508, 1 / 6), (0.0, 2 / 3), (1.7320508, 1 / 6))


def match_dist_gh(pa, pb, sa, sb, tb_shift):
    agg = None
    for xi, wi in NODES:
        for xj, wj in NODES:
            r = match_dist(min(max(pa + xi * sa, 0.40), 0.85),
                           min(max(pb + xj * sb, 0.40), 0.85), tb_shift)
            w = wi * wj
            if agg is None:
                agg = [w * r[k] for k in range(6)] + [{g: w * v for g, v in r[6].items()}]
            else:
                for k in range(6):
                    agg[k] += w * r[k]
                for g, v in r[6].items():
                    agg[6][g] = agg[6].get(g, 0.0) + w * v
    return agg


# market-anchored twin: shift both point-probs equally to hit the market match prob
@lru_cache(maxsize=20000)
def anchor_delta(pa, pb, target):
    lo, hi = -0.10, 0.10
    for _ in range(24):
        mid = 0.5 * (lo + hi)
        r = match_dist(min(max(pa + mid, 0.40), 0.85), min(max(pb - mid, 0.40), 0.85), 0.0)
        if r[0] < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


rows = []
sg_a = (0.10 / np.sqrt(np.maximum(F["nS_a"].values, 4)))
sg_b = (0.10 / np.sqrt(np.maximum(F["nS_b"].values, 4)))
K_TB = 0.6
for i, t in enumerate(F.itertuples(index=False)):
    pa, pb = round(t.pa_dec, 2), round(t.pb_dec, 2)
    tbs = K_TB * (t.tbr_a - t.tbr_b)
    nat = match_dist_gh(pa, pb, sg_a[i], sg_b[i], tbs)
    nat0 = match_dist_gh(pa, pb, sg_a[i], sg_b[i], 0.0)       # no tb-skill, for ablation
    d = anchor_delta(pa, pb, round(float(t.imp), 3))
    mkt = match_dist(min(max(pa + d, 0.40), 0.85), min(max(pb - d, 0.40), 0.85), 0.0)
    def pick(r):
        g = r[6]
        tot = sum(g.values()) or 1.0
        o215 = sum(v for k, v in g.items() if k >= 22) / tot
        o225 = sum(v for k, v in g.items() if k >= 23) / tot
        return r[1], r[2], r[3], r[4], r[5], o215, o225
    rows.append((t.year, t.won, t.r_sa, t.r_sb, t.r_g, t.r_tb,
                 *pick(nat), nat0[5], *pick(mkt)))
    if i % 10000 == 0:
        print(f"  {i}/{len(F)}", flush=True)

C = ["year", "won", "r_sa", "r_sb", "r_g", "r_tb",
     "n20", "n21", "nq21", "nq20", "ntb", "no215", "no225", "ntb0",
     "m20", "m21", "mq21", "mq20", "mtb", "mo215", "mo225"]
D = pd.DataFrame(rows, columns=C)
D.to_parquet("data_cache/_mc2_dist_scored.parquet")

# ---- scorecards ----
def mc_logloss(df, pre):
    # realized class: A2-0, A2-1, B2-1, B2-0  (A = row perspective player)
    cls = np.select(
        [(df.r_sa == 2) & (df.r_sb == 0) & (df.won == 1),
         (df.r_sa == 2) & (df.r_sb == 1) & (df.won == 1),
         (df.r_sb == 2) & (df.r_sa == 1) & (df.won == 0),
         (df.r_sb == 2) & (df.r_sa == 0) & (df.won == 0)], [0, 1, 2, 3], default=-1)
    ok = cls >= 0
    P = np.column_stack([df[f"{pre}20"], df[f"{pre}21"], df[f"{pre}q21"], df[f"{pre}q20"]])
    P = np.clip(P, 1e-6, 1)
    P = P / P.sum(axis=1, keepdims=True)
    return -np.mean(np.log(P[ok, cls[ok]])), int(ok.sum())


def brier(y, p):
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


print("\n==== DISTRIBUTION SCORECARD (native vs market-anchored twin) ====")
for yr in (2024, 2025, 2026, None):
    g = D if yr is None else D[D.year == yr]
    if len(g) < 500:
        continue
    lln, nn = mc_logloss(g, "n")
    llm, _ = mc_logloss(g, "m")
    print(f"{yr or 'ALL'} n={len(g)} | set-score LL: native {lln:.4f} vs mkt-anch {llm:.4f} | "
          f"TB Brier: native {brier(g.r_tb, g.ntb):.4f} (no-skill {brier(g.r_tb, g.ntb0):.4f}) "
          f"mkt {brier(g.r_tb, g.mtb):.4f} | O21.5 Brier: native {brier((g.r_g >= 22).astype(float), g.no215):.4f} "
          f"mkt {brier((g.r_g >= 22).astype(float), g.mo215):.4f}", flush=True)
