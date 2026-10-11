"""DOES OUR CUSTOM sUTR PICK MEN'S WINNERS? (2026-10-11, user: "What about our custom Utr if
someone's better")

sUTR is our own per-surface, UTR-style rating: each match's performance = the opponent's rating
plus how the GAMES went, recency-weighted over the last 30 on that court.

The leakage trap here is specific and worth naming. `model_artifacts/tennis_sutr.joblib` holds
ONE snapshot (asof 2026-10-10), and the log runs 2026-09-06..10-11 -- so reading today's
ratings for a September match would score it with a rating that already contains that match's
result. Nothing in the log freezes sUTR either (no sutr column).

So this uses `data_cache/tennis_sutr_prematch.parquet`, which the build writes during its single
chronological pass: r1/r2 are each player's rating STRICTLY BEFORE that match. Production's own
leak-free output, joined to our board games by slug pair + date.

Judged the same three ways as the other stats: does the higher rating win, does the market do
better on the same rows, and does it pay.
"""
import numpy as np
import pandas as pd

import tennis_log as TL
import tennis_model_a as MA

MA._load()

pre = pd.read_parquet("data_cache/tennis_sutr_prematch.parquet")
pre["date"] = pd.to_datetime(pre["date"], errors="coerce")
pre["k"] = pre["player_slug"].astype(str) + "|" + pre["rival_slugname"].astype(str)
PRE = {}
for t in pre.itertuples():
    PRE[(t.k, str(t.date)[:10])] = (float(t.r1), float(t.r2), int(t.n1), int(t.n2))

log = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
log["date"] = pd.to_datetime(log["date"], errors="coerce")
S = log[(log["settled"] == True) & log["p1_won"].notna()      # noqa: E712
        & log["p1_odds"].notna() & log["p2_odds"].notna()].copy()
if "surface_bad" in S.columns:
    S = S[~S["surface_bad"].fillna(False).astype(bool)]
lg = S["league"].astype(str)
MEN = S[~(lg.str.contains("wta") | lg.str.contains("itf_women"))]
print("men's settled rows: %d   %s..%s"
      % (len(MEN), str(MEN.date.min())[:10], str(MEN.date.max())[:10]))

rows, miss_slug, miss_join = [], 0, 0
for r in MEN.itertuples():
    s1, s2 = MA.resolve(r.player_1), MA.resolve(r.player_2)
    if not s1 or not s2:
        miss_slug += 1
        continue
    dt = str(r.date)[:10]
    hit = PRE.get((f"{s1}|{s2}", dt))
    flip = False
    if hit is None:
        hit = PRE.get((f"{s2}|{s1}", dt))
        flip = True
    if hit is None:
        miss_join += 1
        continue
    a, b, na, nb = hit
    if flip:                       # the parquet row is oriented the other way round
        a, b, na, nb = b, a, nb, na
    d1, d2 = TL._decimal(r.p1_odds), TL._decimal(r.p2_odds)
    if not d1 or not d2:
        continue
    i1, i2 = 1 / d1, 1 / d2
    rows.append({"won1": bool(r.p1_won), "mk1": i1 / (i1 + i2), "d1": d1, "d2": d2,
                 "r1": a, "r2": b, "n1": na, "n2": nb, "gap": a - b,
                 "lvl": str(r.league)})
D = pd.DataFrame(rows)
print("joined to a leak-free pre-match sUTR: %d  (%.0f%% of men's rows); "
      "unresolved names %d, no archive row %d"
      % (len(D), 100 * len(D) / max(len(MEN), 1), miss_slug, miss_join))
if D.empty:
    raise SystemExit("no coverage")


def score(f, lab, floor=25):
    n = len(f)
    if n < floor:
        print("   %-40s n=%d (thin)" % (lab, n))
        return
    sp = f.gap > 0                                    # sUTR backs player_1
    hit = (sp == f.won1).mean()
    mkt = ((f.mk1 > 0.5) == f.won1).mean()
    imp = np.where(sp, f.mk1, 1 - f.mk1)
    odds = np.where(sp, f.d1, f.d2)
    pnl = np.where(sp == f.won1, odds - 1, -1.0)
    se = np.sqrt(hit * (1 - hit) / n)
    agree = (sp == (f.mk1 > 0.5)).mean()
    print("   %-40s %5.1f%% +/- %3.1f  mkt %5.1f%%  EDGE %+5.1fpt  ROI %+6.1f%%  "
          "agrees w/ price %3.0f%%  (n=%d)"
          % (lab, 100 * hit, 100 * se, 100 * mkt, 100 * (hit - imp.mean()),
             100 * pnl.mean(), 100 * agree, n))


print("\n" + "=" * 112)
print("MEN -- THE HIGHER sUTR PICKS THE WINNER? (live log, strictly-prior ratings)")
print("=" * 112)
D = D[D.gap != 0]
score(D, "every game with both rated")
rated = D[(D.n1 >= 5) & (D.n2 >= 5)]
score(rated, "both ratings non-provisional (n>=5)")
score(D[(D.n1 < 5) | (D.n2 < 5)], "at least one provisional")

print("   by rating gap:")
for lo, hi in ((0, 0.25), (0.25, 0.5), (0.5, 1.0), (1.0, 99)):
    score(rated[rated.gap.abs().between(lo, hi, inclusive="left")],
          "      gap %.2f-%s" % (lo, "inf" if hi > 50 else "%.2f" % hi))

print("   by level:")
lv = rated.lvl.astype(str).str.lower()
for lab, m in (("tour (atp)", ~lv.str.contains("chall|itf")),
               ("challenger", lv.str.contains("chall")),
               ("ITF", lv.str.contains("itf"))):
    score(rated[m], "      " + lab)

print("\n   WHEN sUTR DISAGREES WITH THE PRICE (its pick is the market dog):")
dogpick = rated[((rated.gap > 0) & (rated.mk1 < 0.5)) | ((rated.gap < 0) & (rated.mk1 > 0.5))]
score(dogpick, "      sUTR on the dog")
for lo, hi in ((0, 0.5), (0.5, 99)):
    score(dogpick[dogpick.gap.abs().between(lo, hi, inclusive="left")],
          "         gap %.2f-%s" % (lo, "inf" if hi > 50 else "%.2f" % hi))
print("   and when it agrees (its pick is the favourite):")
favpick = rated[((rated.gap > 0) & (rated.mk1 > 0.5)) | ((rated.gap < 0) & (rated.mk1 < 0.5))]
score(favpick, "      sUTR on the favourite")
