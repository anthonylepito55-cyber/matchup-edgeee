"""WHAT ACTUALLY MATTERS FOR WINNING, MEN, ON OUR OWN LIVE GAMES (2026-10-11, user: "go through
all our lives games what stats matter the most for winning games for men").

Every settled MEN'S row in the frozen log. Each candidate stat is computed AS OF the match date
with tennis_context.context_asof (strictly earlier matches on that surface, so nothing sees its
own result), as a p1-minus-p2 difference, and then judged three ways -- because "matters" can
mean three different things and they do not agree:

  1. PREDICTIVE POWER -- how often the player ahead on that stat wins. This is the literal
     question and the most stable number here.
  2. VS THE MARKET -- the market's own accuracy on the SAME rows. A stat that calls 62% of
     matches is worthless if the price calls 66% of the same ones.
  3. WHETHER IT PAYS -- EDGE against the no-vig line, and flat ROI, which is the only one that
     turns into money.

Also split by whether the stat's pick is the market DOG, since a stat that only agrees with
the favourite is just reading the price back.

Caveats stated up front: n is roughly 700, ~11 stats are ranked, so the gaps between
neighbouring rows are mostly noise -- read the top and bottom, not the order. UE and UTR are
excluded: they exist on 18 and 101 men's rows.
"""
import numpy as np
import pandas as pd

import tennis_context as TC
import tennis_log as TL

log = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
log["date"] = pd.to_datetime(log["date"], errors="coerce")
S = log[(log["settled"] == True) & log["p1_won"].notna()          # noqa: E712
        & log["p1_odds"].notna() & log["p2_odds"].notna()].copy()
if "surface_bad" in S.columns:
    S = S[~S["surface_bad"].fillna(False).astype(bool)]
lg = S["league"].astype(str)
S = S[~(lg.str.contains("wta") | lg.str.contains("itf_women"))]
print(f"men's settled, priced, right-court rows: {len(S)}  "
      f"{S.date.min().date()}..{S.date.max().date()}")

cache = {}


def ctx(nm, surf, asof):
    k = (str(nm), str(surf), str(asof)[:10])
    if k not in cache:
        try:
            cache[k] = TC.context_asof(nm, surf, asof)
        except Exception:
            cache[k] = None
    return cache[k]


def pick(c, block, key):
    """One stat out of one window. avg_opp_rank/clutch/vs_top200 live at the top level."""
    if not c:
        return None
    if key == "opp_rank":
        v = c.get("avg_opp_rank")
        return None if v is None else -float(v)          # lower rank number = tougher = better
    if key == "clutch":
        v = c.get("clutch")
        return None if v is None else float(v)
    if key == "vs200":
        vt = c.get("vs_top200") or {}
        n = (vt.get("w") or 0) + (vt.get("l") or 0)
        return None if n < 4 else float(vt["w"]) / n
    b = c.get(block)
    if not b:
        return None
    if key == "hold_plus_break":
        if b.get("sgw") is None or b.get("rgw") is None:
            return None
        return float(b["sgw"]) + float(b["rgw"])
    v = b.get(key)
    return None if v is None else float(v)


# (label, context block, key)
FEATS = [
    ("hold% + break% (52w)", "surface_stats", "hold_plus_break"),
    ("hold%  SGW (52w)", "surface_stats", "sgw"),
    ("break% RGW (52w)", "surface_stats", "rgw"),
    ("1st-serve won % (52w)", "surface_stats", "sv1"),
    ("2nd-serve won % (52w)", "surface_stats", "sv2"),
    ("return v 1st % (52w)", "surface_stats", "r1"),
    ("return v 2nd % (52w)", "surface_stats", "r2"),
    ("win rate on surface (52w)", "surface_stats", "win"),
    ("hold% + break% (L10)", "surface_l10", "hold_plus_break"),
    ("hold% + break% (L5)", "surface_l5", "hold_plus_break"),
    ("win rate (L10)", "surface_l10", "win"),
    ("clutch (pressure pts won)", None, "clutch"),
    ("avg opponent rank faced", None, "opp_rank"),
    ("win rate vs top-200", None, "vs200"),
]

recs = []
for r in S.itertuples():
    ca = ctx(r.player_1, r.surface, r.date)
    cb = ctx(r.player_2, r.surface, r.date)
    d1, d2 = TL._decimal(r.p1_odds), TL._decimal(r.p2_odds)
    if not d1 or not d2:
        continue
    i1, i2 = 1 / d1, 1 / d2
    row = {"won1": bool(r.p1_won), "mk1": i1 / (i1 + i2), "d1": d1, "d2": d2,
           "lvl": str(r.league)}
    for lab, blk, key in FEATS:
        va, vb = pick(ca, blk, key), pick(cb, blk, key)
        row[lab] = None if (va is None or vb is None) else va - vb
    # the models, for scale
    for lab, col in (("[Model C]", "model_c_p1"), ("[Model A]", "model_a_p1"),
                     ("[Model B]", "model_b_p1"), ("[c75 sim]", "mc_c75_p1")):
        v = getattr(r, col, None)
        row[lab] = None if (v is None or pd.isna(v)) else float(v) - 0.5
    recs.append(row)
D = pd.DataFrame(recs)
print(f"rows usable: {len(D)}\n")

MKT_ALL = None
out = []
for lab in [f[0] for f in FEATS] + ["[Model C]", "[Model A]", "[Model B]", "[c75 sim]"]:
    f = D[D[lab].notna() & (D[lab] != 0)].copy()
    n = len(f)
    if n < 60:
        out.append((lab, n, None, None, None, None, None, None))
        continue
    p1better = f[lab] > 0
    hit = (p1better == f.won1).mean()                       # stat's pick wins
    mkt = ((f.mk1 > 0.5) == f.won1).mean()                  # the price's pick wins, same rows
    odds = np.where(p1better, f.d1, f.d2)
    imp = np.where(p1better, f.mk1, 1 - f.mk1)
    pnl = np.where(p1better == f.won1, odds - 1, -1.0)
    isdog = imp < 0.5
    dog_hit = (p1better[isdog] == f.won1[isdog]).mean() if isdog.sum() >= 25 else None
    out.append((lab, n, 100 * hit, 100 * mkt, 100 * (hit - imp.mean()),
                100 * pnl.mean(), 100 * np.sqrt(hit * (1 - hit) / n),
                (100 * dog_hit if dog_hit is not None else None, int(isdog.sum()))))

out.sort(key=lambda x: (x[2] is None, -(x[2] or 0)))
print("=" * 108)
print("MEN — WHAT PREDICTS THE WINNER (live frozen log, as-of stats, no hindsight)")
print("=" * 108)
print(f"   {'stat (p1 minus p2)':30s} {'n':>5} {'picks the winner':>17} "
      f"{'price, same rows':>17} {'EDGE':>7} {'flat ROI':>9}   dog subset")
for lab, n, hit, mkt, edge, roi, se, dog in out:
    if hit is None:
        print(f"   {lab:30s} {n:>5}   (too thin)")
        continue
    dtxt = f"{dog[0]:.0f}% of {dog[1]}" if dog and dog[0] is not None else "—"
    print(f"   {lab:30s} {n:>5}   {hit:5.1f}% ± {se:3.1f}      "
          f"{mkt:5.1f}%        {edge:+5.1f}pt  {roi:+7.1f}%   {dtxt}")
