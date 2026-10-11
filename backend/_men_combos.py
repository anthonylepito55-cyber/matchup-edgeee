"""MEN: DO STAT COMBINATIONS DO BETTER THAN SINGLE STATS? (2026-10-11, user: "What about when
some are combined")

Same 704 settled men's rows, same as-of stats (no hindsight). Three tests, deliberately ordered
from least to most data-mined so the honest ones come first:

  A. AGREEMENT LADDER -- over six non-redundant stats, how many favour the same player, and does
     accuracy/ROI rise with that count? This is ONE pre-specified test, so it is the headline.
  B. THEORY-DRIVEN COMBOS -- a short pre-specified list, including the break%-inversion combo
     (better hold% AND worse break%), which the univariate table implies should help.
  C. ALL PAIRS, exhaustively -- 12 stats, both polarities. Reported with the share of cells that
     clear each bar, because at n~700 several will look good for free.

Against the market throughout: the market's own accuracy on the SAME subset, EDGE vs the no-vig
line, and flat ROI. A combination that calls 62% is worthless if the price calls 70% of the same
games.
"""
import itertools

import numpy as np
import pandas as pd

import tennis_context as TC
import tennis_log as TL

log = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
log["date"] = pd.to_datetime(log["date"], errors="coerce")
S = log[(log["settled"] == True) & log["p1_won"].notna()      # noqa: E712
        & log["p1_odds"].notna() & log["p2_odds"].notna()].copy()
if "surface_bad" in S.columns:
    S = S[~S["surface_bad"].fillna(False).astype(bool)]
lg = S["league"].astype(str)
S = S[~(lg.str.contains("wta") | lg.str.contains("itf_women"))]

cache = {}


def ctx(nm, surf, asof):
    k = (str(nm), str(surf), str(asof)[:10])
    if k not in cache:
        try:
            cache[k] = TC.context_asof(nm, surf, asof)
        except Exception:
            cache[k] = None
    return cache[k]


def g(c, blk, key):
    if not c:
        return None
    if key == "opp_rank":
        v = c.get("avg_opp_rank")
        return None if v is None else -float(v)
    if key == "clutch":
        v = c.get("clutch")
        return None if v is None else float(v)
    b = c.get(blk) or {}
    if key == "hpb":
        if b.get("sgw") is None or b.get("rgw") is None:
            return None
        return float(b["sgw"]) + float(b["rgw"])
    v = b.get(key)
    return None if v is None else float(v)


FEATS = [("hold%", "surface_stats", "sgw"), ("break%", "surface_stats", "rgw"),
         ("1stSv%", "surface_stats", "sv1"), ("2ndSv%", "surface_stats", "sv2"),
         ("Ret1%", "surface_stats", "r1"), ("Ret2%", "surface_stats", "r2"),
         ("win%52w", "surface_stats", "win"),
         ("hpbL10", "surface_l10", "hpb"), ("win%L10", "surface_l10", "win"),
         ("hpbL5", "surface_l5", "hpb"),
         ("clutch", None, "clutch"), ("oppRank", None, "opp_rank")]
NAMES = [f[0] for f in FEATS]
CORE = ["oppRank", "win%L10", "hpbL10", "hold%", "win%52w", "1stSv%"]   # pre-specified

rows = []
for r in S.itertuples():
    ca, cb = ctx(r.player_1, r.surface, r.date), ctx(r.player_2, r.surface, r.date)
    d1, d2 = TL._decimal(r.p1_odds), TL._decimal(r.p2_odds)
    if not d1 or not d2:
        continue
    i1, i2 = 1 / d1, 1 / d2
    vals, ok = {}, True
    for lab, blk, key in FEATS:
        a, b = g(ca, blk, key), g(cb, blk, key)
        if a is None or b is None:
            ok = False
            break
        vals[lab] = a - b
    if not ok:
        continue
    rows.append({"won1": bool(r.p1_won), "mk1": i1 / (i1 + i2), "d1": d1, "d2": d2, **vals})
D = pd.DataFrame(rows)
print("men's rows with ALL 12 stats defined: %d\n" % len(D))


def score(sideP1, mask, lab, floor=25):
    """sideP1 = boolean Series, the player this combo backs. mask = which rows it fires on."""
    f = D[mask]
    sp = sideP1[mask]
    n = len(f)
    if n < floor:
        print("   %-44s n=%d (thin)" % (lab, n))
        return None
    hit = (sp == f.won1).mean()
    mkt = ((f.mk1 > 0.5) == f.won1).mean()
    imp = np.where(sp, f.mk1, 1 - f.mk1)
    odds = np.where(sp, f.d1, f.d2)
    pnl = np.where(sp == f.won1, odds - 1, -1.0)
    se = np.sqrt(hit * (1 - hit) / n)
    print("   %-44s %5.1f%% +/- %3.1f  mkt %5.1f%%  EDGE %+5.1fpt  ROI %+6.1f%%  (n=%d)"
          % (lab, 100 * hit, 100 * se, 100 * mkt, 100 * (hit - imp.mean()),
             100 * pnl.mean(), n))
    return hit - imp.mean(), 100 * pnl.mean(), n


print("=" * 104)
print("A. AGREEMENT LADDER -- how many of the six core stats favour the same player")
print("=" * 104)
pos = pd.DataFrame({k: D[k] > 0 for k in CORE})
cnt1 = pos.sum(axis=1)                       # how many favour p1
agree = np.maximum(cnt1, len(CORE) - cnt1)   # size of the majority
sideP1 = cnt1 >= (len(CORE) - cnt1)          # back the majority side
for k in range(3, len(CORE) + 1):
    score(sideP1, agree == k, "exactly %d of 6 agree" % k)
score(sideP1, agree >= 5, "5 or 6 of 6 agree")
score(sideP1, agree == 6, "UNANIMOUS (6 of 6)")
print("   control -- fade the majority instead:")
score(~sideP1, agree == 4, "fade a 4-2 majority")
score(~sideP1, agree >= 5, "fade a 5-1 or 6-0 majority")

print("\n" + "=" * 104)
print("B. PRE-SPECIFIED COMBOS")
print("=" * 104)
P = {k: D[k] > 0 for k in NAMES}
Ng = {k: D[k] < 0 for k in NAMES}
score(P["hold%"], P["hold%"] & P["1stSv%"] & P["2ndSv%"], "serve-dominant: hold% + 1stSv + 2ndSv")
score(P["win%L10"], P["win%L10"] & P["hpbL10"], "form: win%L10 + hold+break L10")
score(P["win%L10"], P["win%L10"] & P["hpbL10"] & P["oppRank"], "form + tougher schedule")
score(P["hold%"], P["hold%"] & P["oppRank"], "hold% + tougher schedule")
score(P["hold%"], P["hold%"] & P["clutch"], "hold% + clutch")
score(P["hold%"], P["hold%"] & Ng["break%"], "INVERSION: better hold% AND worse break%")
score(P["hold%"], P["hold%"] & P["break%"], "   (control) better on hold% AND break%")
score(P["hpbL10"], P["hpbL10"] & Ng["hpbL5"], "L10 ahead but L5 behind (cooling)")
score(P["hpbL10"], P["hpbL10"] & P["hpbL5"], "   (control) L10 and L5 both ahead")
score(P["oppRank"], P["oppRank"] & P["win%52w"], "tougher schedule + better surface win%")

print("\n" + "=" * 104)
print("C. ALL PAIRS, BOTH POLARITIES -- exhaustive, so read the chance rows")
print("=" * 104)
res = []
for a, b in itertools.combinations(NAMES, 2):
    for sb, tag in ((P[b], "+"), (Ng[b], "-")):
        m = P[a] & sb
        if m.sum() < 60:
            continue
        f, sp = D[m], P[a][m]
        hit = (sp == f.won1).mean()
        imp = np.where(sp, f.mk1, 1 - f.mk1).mean()
        odds = np.where(sp, f.d1, f.d2)
        pnl = np.where(sp == f.won1, odds - 1, -1.0).mean()
        res.append((100 * (hit - imp), 100 * pnl, 100 * hit, int(m.sum()),
                    "%s & %s%s" % (a, tag, b)))
res.sort(reverse=True)
print("   %d pairs with n>=60.  top 8 by EDGE:" % len(res))
for e, roi, hit, n, lab in res[:8]:
    print("      %-34s %5.1f%% hit  EDGE %+5.1fpt  ROI %+6.1f%%  (n=%d)"
          % (lab, hit, e, roi, n))
print("   bottom 3:")
for e, roi, hit, n, lab in res[-3:]:
    print("      %-34s %5.1f%% hit  EDGE %+5.1fpt  ROI %+6.1f%%  (n=%d)"
          % (lab, hit, e, roi, n))
for bar in (3, 5, 8):
    k = sum(1 for e in res if e[0] >= bar)
    print("   pairs with EDGE >= %dpt: %d of %d (%.0f%%)"
          % (bar, k, len(res), 100 * k / len(res)))
print("   with ~66-130 cells tested at n~100-400, a handful clearing +3pt is expected noise;")
print("   only a bar that a large SHARE of cells clears, or one cell far out, means anything.")
