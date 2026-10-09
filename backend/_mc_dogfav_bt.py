# ALL MONTE CARLOS, DOG vs FAV, M/W (2026-10-08 user ask). HONEST SCOPE:
# - MC2 has a GENUINE walk-forward backtest (pre-match ratings in _mc2_features.parquet,
#   production blend formula reproduced) -> real 2024-26 numbers, split dog/fav x gender.
# - c50 / c75 / cUTR / serve-MC CANNOT be archive-backtested (historical sim states were
#   never saved; simulate_match needs live profiles) -> their record is the frozen log,
#   reported separately by the caller.
import math
import numpy as np
import pandas as pd
import tennis_mc2 as m2

F = pd.read_parquet("data_cache/_mc2_features.parquet")
F = F[F["imp"].notna() & F["odd_a"].notna() & F["odd_b"].notna()
      & (F["nS_a"] >= 4) & (F["nS_b"] >= 4) & F["p_elo"].notna() & F["pa_pt"].notna()]
print(f"rows: {len(F)}  years {sorted(F['year'].unique())}", flush=True)

lg = lambda p: math.log(max(min(p, 1 - 1e-6), 1e-6) / (1 - max(min(p, 1 - 1e-6), 1e-6)))
cache = {}

def mc2_prob(pa, pb, nsa, nsb, p_elo):
    key = (round(pa, 2), round(pb, 2), min(int(nsa), 60), min(int(nsb), 60))
    pm = cache.get(key)
    if pm is None:
        sg_a = 0.10 / max(key[2], 4) ** 0.5
        sg_b = 0.10 / max(key[3], 4) ** 0.5
        pm = 0.0
        for xi, wi in m2._NODES:
            for xj, wj in m2._NODES:
                pm += wi * wj * m2._p_match(m2._rnd(key[0] + xi * sg_a), m2._rnd(key[1] + xj * sg_b))
        cache[key] = pm
    return 1 / (1 + math.exp(-(0.5 * lg(float(p_elo)) + 0.5 * lg(pm))))

probs = []
for r in F.itertuples():
    probs.append(mc2_prob(float(r.pa_pt), float(r.pb_pt), r.nS_a, r.nS_b, float(r.p_elo)))
F = F.assign(mc2=probs)
print(f"mc2 computed (unique quadrature keys: {len(cache)})", flush=True)

F["isW"] = F["wom"].astype(bool) if "wom" in F.columns else False
F["dog_a"] = F["imp"] < 0.5          # side A is the market dog
F["mc2_a"] = F["mc2"] >= 0.5         # MC2 takes side A

def report(label, sub, want_dog, band=None, edge=None):
    rows = sub[sub["mc2_a"] == (sub["dog_a"] if want_dog else ~sub["dog_a"])]
    if edge is not None:
        side_p = np.where(rows["mc2_a"], rows["mc2"], 1 - rows["mc2"])
        side_m = np.where(rows["mc2_a"], rows["imp"], 1 - rows["imp"])
        rows = rows[(side_p - side_m) >= edge]
    od = np.where(rows["mc2_a"], rows["odd_a"], rows["odd_b"])
    if band:
        keep = (od >= band[0]) & (od <= band[1])
        rows, od = rows[keep], od[keep]
    if len(rows) < 25:
        return
    won = np.where(rows["mc2_a"], rows["won"].astype(bool), ~rows["won"].astype(bool))
    pnl = np.where(won, od - 1.0, -1.0)
    print(f"  {label:34s} {int(won.sum())}-{int((~won).sum())}  win {100*won.mean():.1f}%  "
          f"ROI {100*pnl.mean():+.1f}%  (n={len(rows)})", flush=True)

for gl, gsub in (("MEN", F[~F["isW"]]), ("WOMEN", F[F["isW"]])):
    print(f"\n=== MC2 {gl} (walk-forward archive, flat 1u) ===")
    report("DOG side (all prices)", gsub, True)
    report("DOG +100..+200 (2.0-3.0)", gsub, True, (2.0, 3.0))
    report("DOG +200..+250", gsub, True, (3.0, 3.5))
    report("DOG, MC2 5pt+ over mkt", gsub, True, None, 0.05)
    report("FAV side (all prices)", gsub, False)
    report("FAV -150..-200 (1.5-1.667)", gsub, False, (1.5, 1.667))
    report("FAV -200..-300 (1.333-1.5)", gsub, False, (1.333, 1.5))
    report("FAV, MC2 2pt+ over mkt", gsub, False, None, 0.02)
    for y in (2025, 2026):
        print(f"  -- {y} only --")
        report(f"DOG +100..+200 {y}", gsub[gsub["year"] == y], True, (2.0, 3.0))
        report(f"FAV -150..-300 {y}", gsub[gsub["year"] == y], False, (1.333, 1.667))
