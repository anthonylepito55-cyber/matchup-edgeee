"""HIGHEST-ROI DOG CELLS (2026-10-14).

Every lane's DOG side, from the frozen live log, ranked. Two columns matter beyond ROI and
dollars:

  t      ROI divided by its own standard error. A flat-stake lane's per-bet payoff is (od-1) on a
         win and -1 on a loss, so the variance is driven by the price: 20 bets on +300 dogs carry
         roughly three times the standard error of 20 bets on -150 favourites. Ranking by ROI
         alone puts the noisiest cells on top, which is exactly backwards.
  share  how much of the lane overlaps the others. 60+ lanes score the same ~1,000 settled games,
         so the top of a 60-lane table is selected for luck as much as for edge -- with 60 lanes
         you expect ~3 to clear t=2 by chance alone.

Lanes that are dog-only by construction are read whole; every other lane is read through its
`dog` sub-aggregate. Recon rows never enter a lane, so these are forward records.

se is approximated by assuming the winners came in at the lane's average winning price, which
UNDERSTATES the error when a lane mixes +120 and +400 dogs -- so the t column is an upper bound
on confidence, not a precise test.
"""
import math

import tennis_log

st = (tennis_log.get_ab25_record() or {}).get("study") or {}
rows = []
for k, c in st.items():
    if not isinstance(c, dict):
        continue
    # dog-only by construction, or read the dog sub-aggregate
    dogish = ("dog" in k.lower() or k.endswith("_dis_dog") or "_dog_" in k.lower())
    src = c if dogish else (c.get("dog") or {})
    n = src.get("n") or 0
    if n < 10:
        continue
    roi = src.get("roi_pct")
    prof = src.get("profit_usd")
    w = src.get("wins")
    if roi is None or w is None or prof is None:
        continue
    r = roi / 100.0
    # implied average winning payout, then the per-bet sd
    if w > 0:
        gain = (r * n + (n - w)) / w          # od_avg - 1
        var = (w * gain * gain + (n - w) * 1.0) / n - r * r
    else:
        var = 0.0
    sd = math.sqrt(max(var, 1e-9))
    se = sd / math.sqrt(n)
    rows.append((roi, n, w, prof, 100 * se, (r / se) if se > 0 else 0.0, k, dogish))

BAR = "=" * 104
print(BAR)
print("DOG CELLS BY ROI -- frozen live log, $25 flat")
print(BAR)
print("   %-26s %5s %9s %10s %9s %6s" % ("cell", "n", "W-L", "profit", "ROI", "t"))
for roi, n, w, prof, se, t, k, dogish in sorted(rows, reverse=True):
    print("   %-26s %5d %9s %10.2f %8.2f%% %6.2f%s"
          % (k, n, "%d-%d" % (w, n - w), prof, roi, t,
             "" if dogish else "  (dog side of a mixed lane)"))

print("\n" + BAR)
print("THE SAME TABLE RANKED BY t -- which of these is actually evidence")
print(BAR)
print("   %-26s %5s %9s %10s %9s %6s" % ("cell", "n", "W-L", "profit", "ROI", "t"))
for roi, n, w, prof, se, t, k, dogish in sorted(rows, key=lambda x: -x[5]):
    flag = ""
    if t >= 2.0:
        flag = "  <- clears 2se"
    elif t >= 1.5:
        flag = "  <- approaching"
    print("   %-26s %5d %9s %10.2f %8.2f%% %6.2f%s"
          % (k, n, "%d-%d" % (w, n - w), prof, roi, t, flag))

n2 = sum(1 for r in rows if r[5] >= 2.0)
print("\n" + BAR)
print("   %d dog cells at n>=10; %d clear t=2.0" % (len(rows), n2))
print("   With this many lanes on ~1,000 shared games you would expect around %.0f to clear"
      % (0.05 * len(rows)))
print("   t=2 by chance alone, so treat the top as candidates rather than findings.")
print("   Total dollars across all dog cells: $%.2f (they overlap heavily -- NOT a portfolio)"
      % sum(r[3] for r in rows))
print(BAR)
