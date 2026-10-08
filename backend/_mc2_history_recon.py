# MC v2 HISTORY RECON (2026-10-08, user "put it on previous games without knowing who
# won them"): walk-forward backfill of mc2_p1 for settled log games that predate the
# model. HONESTY CONTRACT:
#   - date <= 2026-09-28 (the archive/state cutoff): ratings come from the training
#     table's PRE-MATCH columns (p_elo, pa_pt/pb_pt, nS) — built chronologically, so
#     the row knows nothing about the match or anything after it.
#   - date > 2026-09-28: production tennis_mc2.predict() is itself pre-match for these
#     games (its state ends at the cutoff), exactly as live operation.
#   - The result column is never read. Output marked mc2_recon=True -> dimmed ~ display,
#     EXCLUDED from the mc2_* forward lanes (model_x_recon pattern).
# Emits data_cache/_mc2_recon_fill.parquet: (date, player_1, player_2, mc2_p1).
import math
import sys

import pandas as pd

import tennis_mc2 as m2
import tennis_context as tc

CUTOFF = "2026-09-28"

log = pd.read_parquet(sys.argv[1] if len(sys.argv) > 1 else "data_cache/tennis_prediction_log.parquet")
log["d"] = log["date"].astype(str).str[:10]
need = log[log["p1_won"].notna()
           & (log["mc2_p1"].isna() if "mc2_p1" in log.columns else True)].copy()
print(f"settled rows missing mc2: {len(need)} ({need['d'].min()}..{need['d'].max()})")

F = pd.read_parquet("data_cache/_mc2_features.parquet")
F["dd"] = F["date"].astype(str).str[:10]
idx = {}
for r in F.itertuples():
    idx.setdefault((r.a, r.b, r.dd), r)

lg = lambda p: math.log(max(min(p, 1 - 1e-6), 1e-6) / (1 - max(min(p, 1 - 1e-6), 1e-6)))


def from_features(sa, sb, day):
    """Production predict() replicated from the training table's pre-match columns."""
    for d2 in (day, (pd.Timestamp(day) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
               (pd.Timestamp(day) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")):
        r = idx.get((sa, sb, d2))
        flip = False
        if r is None:
            r = idx.get((sb, sa, d2))
            flip = True
        if r is None:
            continue
        if r.nS_a < 4 or r.nS_b < 4 or pd.isna(r.p_elo) or pd.isna(r.pa_pt):
            return None
        pa, pb = round(float(r.pa_pt), 2), round(float(r.pb_pt), 2)
        sg_a = 0.10 / max(r.nS_a, 4) ** 0.5
        sg_b = 0.10 / max(r.nS_b, 4) ** 0.5
        pm = 0.0
        for xi, wi in m2._NODES:
            for xj, wj in m2._NODES:
                pm += wi * wj * m2._p_match(m2._rnd(pa + xi * sg_a), m2._rnd(pb + xj * sg_b))
        p = 1 / (1 + math.exp(-(0.5 * lg(float(r.p_elo)) + 0.5 * lg(pm))))
        return round(1 - p, 4) if flip else round(p, 4)
    return None


out, n_feat, n_state = [], 0, 0
for r in need.itertuples():
    p1, p2, day, surf = r.player_1, r.player_2, r.d, getattr(r, "surface", None)
    val = None
    if day <= CUTOFF:
        g1 = tc.get_context(p1, surf)
        g2 = tc.get_context(p2, surf)
        if g1 and g2:
            val = from_features(g1["slug"], g2["slug"], day)
            if val is not None:
                n_feat += 1
    else:
        pr = m2.predict(p1, p2, surf)
        if pr:
            val = pr["p1_prob"]
            n_state += 1
    if val is not None:
        out.append({"date": day, "player_1": p1, "player_2": p2, "mc2_p1": val})

fill = pd.DataFrame(out)
fill.to_parquet("data_cache/_mc2_recon_fill.parquet")
print(f"filled {len(fill)} / {len(need)} (features-table {n_feat}, frozen-state {n_state})")
if len(fill):
    merged = need.merge(fill, left_on=["d", "player_1", "player_2"],
                        right_on=["date", "player_1", "player_2"], suffixes=("", "_f"))
    hit = ((merged["mc2_p1_f"] >= 0.5) == merged["p1_won"].astype(bool)).mean()
    print(f"sanity (display-only, NOT a forward record): recon hit {100 * hit:.1f}% on {len(merged)}")
