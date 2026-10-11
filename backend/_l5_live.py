"""THE LIVE RECORD OF THE L5 HOLD/BREAK EDGE (2026-10-11, user: "I don't want the backtest I
want the live numbers").

There is no lane for this -- "better on both last-5 hold% and break%" has never been a board
mark -- so this reconstructs its record from the FROZEN LOG instead: every settled row, each
side's last-5-on-this-surface SGW/RGW computed AS OF the match date via
tennis_context.context_asof (strictly earlier matches only, so no hindsight), then flat 1u at
the FROZEN odds the card showed.

Split dog/fav, by gender, and reported with a standard error, because the live log is small and
requiring a usable L5 on BOTH players shrinks it further.
"""
import numpy as np
import pandas as pd

import tennis_context as TC
import tennis_log as TL

STATS = ("sgw", "rgw")
log = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
log["date"] = pd.to_datetime(log["date"], errors="coerce")
S = log[(log["settled"] == True) & log["p1_won"].notna()      # noqa: E712
        & log["p1_odds"].notna() & log["p2_odds"].notna()].copy()
# wrong-court rows are not valid picks (2026-10-09) -- excluded from every live lane
if "surface_bad" in S.columns:
    S = S[~S["surface_bad"].fillna(False).astype(bool)]
print(f"settled, priced, right-court rows in the frozen log: {len(S)}   "
      f"{S.date.min().date()}..{S.date.max().date()}")

cache = {}


def l5(nm, surf, asof):
    k = (str(nm), str(surf), str(asof)[:10])
    if k in cache:
        return cache[k]
    out = None
    try:
        c = TC.context_asof(nm, surf, asof)
        q = (c or {}).get("surface_l5")
        if q and all(q.get(x) is not None for x in STATS):
            out = (float(q["sgw"]), float(q["rgw"]), int(q.get("n") or 0))
    except Exception:
        out = None
    cache[k] = out
    return out


rows = []
for r in S.itertuples():
    a = l5(r.player_1, r.surface, r.date)
    b = l5(r.player_2, r.surface, r.date)
    if not a or not b:
        continue
    d1, d2 = TL._decimal(r.p1_odds), TL._decimal(r.p2_odds)
    if not d1 or not d2:
        continue
    i1, i2 = 1 / d1, 1 / d2
    mk1 = i1 / (i1 + i2)
    lg = str(getattr(r, "league", "") or "")
    rows.append({
        "date": r.date, "dog1": mk1 < 0.5, "mk1": mk1, "d1": d1, "d2": d2,
        "won1": bool(r.p1_won), "G": "W" if ("wta" in lg or "itf_women" in lg) else "M",
        "lvl": lg, "gs1": a[0] - b[0], "gr1": a[1] - b[1],
    })
D = pd.DataFrame(rows)
print(f"rows where BOTH players have a usable as-of L5: {len(D)}"
      f"  ({100 * len(D) / max(len(S), 1):.0f}% of the settled log)")
if D.empty:
    raise SystemExit("no coverage")

# orient every row to the side being backed
def side_frame(back_dog):
    f = D.copy()
    # is player_1 the side we are backing?
    p1side = f.dog1 if back_dog else ~f.dog1
    f["bk_odds"] = np.where(p1side, f.d1, f.d2)
    f["bk_won"] = np.where(p1side, f.won1, ~f.won1)
    f["bk_imp"] = np.where(p1side, f.mk1, 1 - f.mk1)
    f["gs"] = np.where(p1side, f.gs1, -f.gs1)      # backed side's L5 hold% edge
    f["gr"] = np.where(p1side, f.gr1, -f.gr1)
    return f


def rep(f, lab, floor=10):
    n = len(f)
    if n < floor:
        print(f"   {lab:40s} n={n} (too thin)")
        return
    w = f.bk_won.astype(bool)
    pnl = np.where(w, f.bk_odds - 1, -1.0)
    hit, imp = 100 * w.mean(), 100 * f.bk_imp.mean()
    se = 100 * pnl.std(ddof=1) / np.sqrt(n)
    print(f"   {lab:40s} {int(w.sum())}-{n - int(w.sum())}  wins {hit:4.1f}%  "
          f"no-vig {imp:4.1f}%  EDGE {hit - imp:+5.1f}pt  "
          f"ROI {100 * pnl.mean():+6.1f}% ± {se:4.1f}  (n={n})")


for back_dog, lab in ((True, "DOG"), (False, "FAVOURITE")):
    f = side_frame(back_dog)
    print("\n" + "=" * 100)
    print(f"LIVE FROZEN LOG — BACKING THE {lab}, split by its last-5 hold%/break% vs the other side")
    print("=" * 100)
    rep(f, f"every {lab.lower()} (baseline)")
    both = (f.gs > 0) & (f.gr > 0)
    rep(f[both], f"{lab.lower()} better on BOTH")
    rep(f[(f.gs > 0) & (f.gr <= 0)], f"{lab.lower()} better on hold% only")
    rep(f[(f.gs <= 0) & (f.gr > 0)], f"{lab.lower()} better on break% only")
    rep(f[(f.gs <= 0) & (f.gr <= 0)], f"{lab.lower()} WORSE on both")
    print("   better on BOTH, by gender:")
    for Gg, gl in (("M", "men"), ("W", "women")):
        rep(f[both & (f.G == Gg)], f"      {gl}")
    print("   better on BOTH, tightened:")
    for x in (3, 5, 10):
        rep(f[(f.gs >= x) & (f.gr >= x)], f"      both gaps >= {x}pt")
    # THE CELL THAT PAYS (2026-10-11): back this side when the OTHER side holds the L5 edge.
    # On the dog frame that is "the favourite is better on both" -- the live inversion.
    print(f"   *** {lab}: the OTHER side better on both (fade the L5 leader) ***")
    inv = (f.gs < 0) & (f.gr < 0)
    rep(f[inv], "      baseline")
    for Gg, gl in (("M", "men"), ("W", "women")):
        rep(f[inv & (f.G == Gg)], f"      {gl}")
    for x in (3, 5, 10):
        rep(f[(f.gs <= -x) & (f.gr <= -x)], f"      other side ahead by >= {x}pt")
    lv = f.lvl.astype(str).str.lower()
    for ll, msk in (("tour", ~lv.str.contains("chall|itf")),
                    ("challenger", lv.str.contains("chall")),
                    ("ITF", lv.str.contains("itf"))):
        rep(f[inv & msk], f"      {ll}")
    rep(f[inv & f.bk_odds.between(2.0, 3.0)], "      priced +100..+200")
