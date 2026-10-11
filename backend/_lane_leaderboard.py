"""EVERY LANE RANKED BY LIVE ROI, WITH A SAMPLE-SIZE GATE (2026-10-10, user ask).

Carries an approximate standard error on every row, because this session produced two false
alarms from quoting an ROI without one. For a flat-stake bet the P/L is either (d-1) or -1, so
with the win rate and the average winning price implied by the P/L the spread is recoverable:
    mean = roi,  sd ~= sqrt(p*(dbar-1)^2 + (1-p) - mean^2),  se = sd / sqrt(n)
Approximate because it assumes one representative price per lane; the t column (roi/se) is what
separates a real edge from a lucky run.
"""
import math

import tennis_log as TL

st = (TL.get_ab25_record() or {}).get("study") or {}
FAVISH = ("fav", "close", "leanfav", "gold_names", "green_names", "all10_price_m")


def row(k, v):
    n, w = v.get("n") or 0, v.get("wins") or 0
    staked, profit = v.get("staked_usd") or 0.0, v.get("profit_usd") or 0.0
    if not n or not staked or not w:
        return None
    unit = staked / n
    roi = profit / staked
    p = w / n
    dbar = 1 + (profit + (n - w) * unit) / (w * unit)
    var = p * (dbar - 1) ** 2 + (1 - p) - roi ** 2
    se = math.sqrt(max(var, 0.0) / n)
    return {"lane": k, "n": n, "w": w, "rec": f"{w}-{n - w}", "hit": 100 * p,
            "roi": 100 * roi, "se": 100 * se, "profit": profit,
            "side": "FAV" if any(t in k for t in FAVISH) else "dog/other",
            "t": (roi / se) if se > 0 else 0.0}


rows = [r for r in (row(k, v) for k, v in st.items() if isinstance(v, dict)) if r]
print(f"lanes with at least one win: {len(rows)}\n")
HDR = (f"   {'lane':26s} {'record':>9s} {'hit':>6s} {'ROI':>8s} {'se':>6s} {'t':>5s} "
       f"{'profit':>8s} {'side':>9s}")

for floor in (50, 25):
    sel = sorted([r for r in rows if r["n"] >= floor], key=lambda r: -r["roi"])
    print("=" * 94)
    print(f"LANES WITH n >= {floor}, RANKED BY LIVE ROI")
    print("=" * 94)
    print(HDR)
    for r in sel:
        star = " <<<" if r["t"] >= 2 else ("  ~" if r["t"] >= 1 else "")
        print(f"   {r['lane']:26s} {r['rec']:>9s} {r['hit']:5.1f}% {r['roi']:+7.1f}% "
              f"{r['se']:6.1f} {r['t']:5.1f} {r['profit']:+8.0f} {r['side']:>9s}{star}")
    hot = [r for r in sel if r["t"] >= 2]
    print(f"\n   '<<<' = ROI at least 2 standard errors above zero  ->  {len(hot)} of "
          f"{len(sel)} lanes qualify")
    if hot:
        print("   those: " + ", ".join(f"{r['lane']} ({r['roi']:+.0f}%, n={r['n']})"
                                       for r in hot))
    print()

print("=" * 94)
print("THIN BUT LOUD -- under n=25, the ones that would look great if you ignored the sample")
print("=" * 94)
thin = sorted([r for r in rows if r["n"] < 25 and r["roi"] > 20], key=lambda r: -r["roi"])
for r in thin[:12]:
    print(f"   {r['lane']:26s} {r['rec']:>9s} {r['roi']:+7.1f}% +/- {r['se']:.0f}   "
          f"t={r['t']:.1f}   (n={r['n']})")
print("   not one of these is evidence yet")
