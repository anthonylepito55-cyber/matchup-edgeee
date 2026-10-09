"""WHAT ARE WE MISSING? Scan the UNMARKED games (default 2026-09-18..10-08) for
profitable conditions the board never flagged (user ask 2026-10-08).

Honesty rules baked in, learned the hard way tonight:
  * the candidate list is PRE-SPECIFIED below -- no fishing past it
  * every cell reports n; under 40 is printed as thin and ignored
  * a cell only counts as a find if it also BEATS ITS COMPLEMENT by 5pts -- one positive
    number out of twenty tries is what noise looks like
  * nothing here ships: findings become watch lanes and need a forward record first
"""
import sys

import numpy as np
import pandas as pd

START = sys.argv[1] if len(sys.argv) > 1 else "2026-09-18"
df = pd.read_parquet("data_cache/_ec2_log_now.parquet")
df["d"] = df["date"].astype(str).str[:10]
d = df[(df["d"] >= START) & df["p1_won"].notna()
       & df["p1_odds"].notna() & df["p2_odds"].notna()].copy()


def dec(o):
    o = float(o)
    return 1 + o / 100 if o > 0 else 1 + 100 / abs(o)


SIMS = ("mc_c_p1", "mc_c75_p1", "mc_cutr_p1", "mc_p1")
rows = []
for r in d.itertuples():
    if any(pd.isna(getattr(r, c)) for c in ("model_a_p1", "model_b_p1", "model_c_p1", "model_cma_p1")):
        continue
    i1, i2 = 1 / dec(r.p1_odds), 1 / dec(r.p2_odds)
    mk1 = i1 / (i1 + i2)
    dog1 = mk1 < 0.5
    lg = str(r.league or "")
    wom = ("wta" in lg) or ("itf_women" in lg)
    c1 = float(r.model_c_p1) >= 0.5
    g1 = float(r.model_cma_p1) >= 0.5
    aS, bS = float(r.model_a_p1) >= 0.5, float(r.model_b_p1) >= 0.5
    alone = (aS != c1) and (bS != c1)
    mdog = mk1 if dog1 else 1 - mk1
    gdog = float(r.model_cma_p1) if dog1 else 1 - float(r.model_cma_p1)
    favP = 1 - mdog
    star = (c1 == g1) and (g1 == dog1)
    gray4 = (g1 == dog1) and (gdog - mdog >= 0.04)
    dog_od = float(r.p1_odds if dog1 else r.p2_odds)
    fav_od = float(r.p1_odds if not dog1 else r.p2_odds)
    marked = False
    if (alone and g1 == c1 and c1 == dog1) or (star and (alone or gray4)) or gray4:
        marked = True
    if (aS != c1) and (bS == c1) and c1 == dog1 and g1 == c1:
        marked = True
    if pd.notna(r.mc_c75_p1):
        c75dog = (float(r.mc_c75_p1) >= 0.5) == dog1
        if c75dog and (100 <= dog_od <= 200 or (wom and dog_od >= 100)):
            marked = True
    if all(pd.notna(getattr(r, c)) for c in SIMS):
        favs = [(float(getattr(r, c)) if not dog1 else 1 - float(getattr(r, c))) for c in SIMS]
        disc = 0.04 if wom else 0.06
        if sum(1 for f in favs if f <= favP - disc) == 4 and 100 <= dog_od <= 200:
            marked = True
    if alone and g1 == c1 and c1 != dog1:
        gE = (float(r.model_cma_p1) if c1 else 1 - float(r.model_cma_p1)) - favP
        if (-200 if wom else -150) <= fav_od <= -100 and gE >= 0.05 and "challenger" not in lg:
            marked = True
    cfav = float(r.model_c_p1) if not dog1 else 1 - float(r.model_c_p1)
    if cfav - favP >= 0.05 and -200 <= fav_od <= -150:
        marked = True
    if wom and (mdog - gdog) >= 0.02 and -300 <= fav_od <= -200:
        marked = True

    def gv(c):
        v = getattr(r, c, np.nan)
        return None if pd.isna(v) else float(v)

    rows.append({
        "marked": marked, "wom": wom, "ch": "challenger" in lg, "dog1": bool(dog1),
        "mk_dog": mdog, "dog_od": dog_od, "fav_od": fav_od,
        "dog_won": (bool(r.p1_won) == bool(dog1)),
        "A": gv("model_a_p1"), "B": gv("model_b_p1"), "C": gv("model_c_p1"),
        "G": gv("model_cma_p1"), "D": gv("model_d_p1"), "DMA": gv("model_dma_p1"),
        "X": gv("model_x_p1"), "MC2": gv("mc2_p1"), "c50": gv("mc_c_p1"),
        "c75": gv("mc_c75_p1"), "cu": gv("mc_cutr_p1"), "svmc": gv("mc_p1"),
        "pf": gv("pf_edge_p1"), "utr": gv("utr_edge_p1"),
        "late": any(t in str(r.round or "").lower() for t in ("final", "semi", "quarter")),
        "p1_is_dog": bool(dog1),
    })
R = pd.DataFrame(rows)
U = R[~R.marked].copy()
print(f"{START}..10-08: {len(R)} settled | MARKED {int(R.marked.sum())} | UNMARKED {len(U)}\n")


def dogprob(frame, col):
    """the model's probability for the DOG side"""
    v = frame[col]
    return np.where(frame.p1_is_dog, v, 1 - v)


def picks_dog(frame, col):
    return pd.Series(dogprob(frame, col) > 0.5, index=frame.index) & frame[col].notna()


def rep(label, sub, bet_dog, floor=40):
    if len(sub) < floor:
        print(f"  {label:48s} n={len(sub)} (thin)")
        return None
    won = sub.dog_won.values if bet_dog else ~sub.dog_won.values
    od = sub.dog_od.values if bet_dog else sub.fav_od.values
    pnl = np.where(won, [dec(o) - 1 for o in od], -1)
    roi = 100 * pnl.mean()
    print(f"  {label:48s} {int(won.sum())}-{int((~won).sum())}  win {100*won.mean():.1f}%  "
          f"ROI {roi:+7.1f}%  (n={len(sub)})")
    return roi


print("=== BASELINE on unmarked games ===")
rep("back every market DOG", U, True)
rep("back every market FAVOURITE", U, False)

CANDS = [
    ("c75 on the dog, OUTSIDE +100..+200", True,
     lambda f: picks_dog(f, "c75") & ((f.dog_od < 100) | (f.dog_od > 200))),
    ("gray on the dog by 2-4pt (under the gate)", True,
     lambda f: picks_dog(f, "G") & pd.Series(dogprob(f, "G") - f.mk_dog, index=f.index).between(0.02, 0.04)),
    ("C on the dog but gray disagrees", True,
     lambda f: picks_dog(f, "C") & ~picks_dog(f, "G")),
    ("D-MA on the dog, 2pt+ over market", True,
     lambda f: picks_dog(f, "DMA") & (pd.Series(dogprob(f, "DMA") - f.mk_dog, index=f.index) >= 0.02)),
    ("Model X on the dog, 3pt+ over market", True,
     lambda f: picks_dog(f, "X") & (pd.Series(dogprob(f, "X") - f.mk_dog, index=f.index) >= 0.03)),
    ("MC2 on the dog, 3pt+ over market", True,
     lambda f: picks_dog(f, "MC2") & (pd.Series(dogprob(f, "MC2") - f.mk_dog, index=f.index) >= 0.03)),
    ("A alone on the dog", True,
     lambda f: picks_dog(f, "A") & ~picks_dog(f, "B") & ~picks_dog(f, "C")),
    ("3+ of 4 sims on the dog", True,
     lambda f: (picks_dog(f, "c50").astype(int) + picks_dog(f, "c75").astype(int)
                + picks_dog(f, "cu").astype(int) + picks_dog(f, "svmc").astype(int)) >= 3),
    ("cUTR on the dog", True, lambda f: picks_dog(f, "cu")),
    ("serve-MC on the dog", True, lambda f: picks_dog(f, "svmc")),
    ("form 15pt+ against the dog -> back the FAV", False,
     lambda f: pd.Series(np.where(f.p1_is_dog, f.pf, -f.pf), index=f.index) <= -0.15),
    ("UTR 1.0+ on the dog", True,
     lambda f: pd.Series(np.where(f.p1_is_dog, f.utr, -f.utr), index=f.index) >= 1.0),
    ("late round, dog +100..+250", True,
     lambda f: f.late & f.dog_od.between(100, 250)),
    ("challenger dogs +100..+250", True,
     lambda f: f.ch & f.dog_od.between(100, 250)),
    ("dogs +100..+200 (price alone)", True, lambda f: f.dog_od.between(100, 200)),
]
print("\n=== PRE-SPECIFIED CANDIDATES (unmarked pool only) ===")
found = []
for label, bet_dog, fn in CANDS:
    try:
        mask = fn(U).fillna(False)
    except Exception as e:  # noqa: BLE001
        print(f"  {label:48s} ERROR {type(e).__name__}: {e}")
        continue
    sub, comp = U[mask], U[~mask]
    roi = rep(label, sub, bet_dog)
    croi = rep("      complement", comp, bet_dog) if len(comp) >= 40 else None
    if roi is not None and roi > 5 and (croi is None or roi > croi + 5):
        found.append((label, roi, len(sub), croi))

print("\n=== CLEARED +5% AND BEAT ITS COMPLEMENT BY 5pt ===")
if not found:
    print("  (none -- the unmarked pool shows no missed edge)")
for label, roi, nn, croi in sorted(found, key=lambda x: -x[1]):
    c = f"{croi:+.1f}%" if croi is not None else "n/a"
    print(f"  {label:48s} {roi:+7.1f}%  (n={nn})   complement {c}")
