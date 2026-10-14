"""DOES STACKING CELLS HELP? hit rate and ROI by HOW MANY dog cells back the same dog (2026-10-14).

User: "What's the diff in hit rates between cells 2-6".

The Dog picks tab groups each pick by how many cells fired on it ("9 cells", "7 cells", ...). The
question is whether that count carries information: is a dog six cells agree on actually better
than one two cells agree on, or is the count just measuring how correlated the cells are?

There is a strong prior that it may measure nothing. The cells overlap enormously -- c75_dog,
c75_dog_100plus, cc75_dog and pink_cc75_dog are near-restatements of each other -- so a high count
can mean "four flavours of the same read" rather than four independent confirmations. Median
pairwise correlation across the model heads was already measured at 0.796.

Same basis as the tab: deduped one row per dog, <= +300, gender-gated, no ITF men, forward only,
$25 flat. The PRICE is reported per bucket as well, because hit rate alone is not comparable
across buckets if the stacks sit at different prices -- a 6-cell stack at +120 should win more
often than a 2-cell stack at +280 without that meaning anything.
"""
import math

import tennis_log

CELLS = ["mc2_dog6_all", "mc2_take_dog_all", "mc3_take_dog_all", "mc5_take_dog_all",
         "pf_c75_dis_dog", "split64_fade_dog", "mc_c75_dog", "mc2_dog_flip",
         "c75_dog_100plus", "returner_dog_w", "allround_dog_w", "cc75_nod_dog",
         "cr1_stardog", "cc75_dog", "pink_fadeb_dog_m", "pink_mc2_dog",
         "tier_avoid_dog", "dma_dog", "mc2_dog_band", "cgray_dog_late",
         "ovl_dog", "fight_mc4_dog"]
MAX_AM = 300

st = (tennis_log.get_ab25_record() or {}).get("study") or {}
gof = lambda p: "w" if any(x in str(p.get("league", "")).lower()
                           for x in ("wta", "itf_women")) else "m"


def gok(c, g):
    d = (c or {}).get(g) or {}
    return True if not d.get("n") else (d.get("roi_pct") or 0) > 0


# build: key -> (pick, set of cells that fired on it)
rows = {}
for k in CELLS:
    c = st.get(k) or {}
    for p in (c.get("picks") or []):
        od, lg = p.get("odds"), str(p.get("league") or "").lower()
        if od is None or od > MAX_AM or lg == "itf_men":
            continue
        if not gok(c, gof(p)):
            continue
        key = (p.get("date"), p.get("pick"), p.get("opp"))
        if key not in rows:
            rows[key] = [p, set()]
        rows[key][1].add(k)

done = [(p, cs) for p, cs in rows.values() if p.get("won") is not None]
print("deduped settled dog picks: %d" % len(done))


def agg(items, lab):
    n = len(items)
    if not n:
        return "   %-16s n=0" % lab
    w = sum(1 for p, _ in items if p["won"])
    prof = sum((p.get("pnl") or 0) for p, _ in items)
    roi = 100 * prof / (25.0 * n)
    odds = [p["odds"] for p, _ in items]
    med = sorted(odds)[n // 2]
    # break-even hit rate at the median price, so hit% is readable against what it needs to be
    be = 100.0 / (1 + med / 100.0)
    r = roi / 100
    t = None
    if w:
        g = (r * n + (n - w)) / w
        v = (w * g * g + (n - w)) / n - r * r
        if v > 0:
            t = r / (math.sqrt(v) / math.sqrt(n))
    return ("   %-16s n=%-4d %7s  hit %5.1f%%  (needs %4.1f%% at med %+d)  ROI %+7.2f%%  $%+8.2f%s"
            % (lab, n, "%d-%d" % (w, n - w), 100 * w / n, be, med, roi, prof,
               "  t %5.2f" % t if t is not None else ""))


BAR = "=" * 116
print("\n" + BAR)
print("HIT RATE AND ROI BY NUMBER OF CELLS ON THE SAME DOG")
print("   'needs' = the break-even hit rate at that bucket's MEDIAN price, so the hit column is")
print("   readable: beating it means the bucket made money, missing it means it lost.")
print(BAR)
for k in range(1, 10):
    sel = [(p, cs) for p, cs in done if len(cs) == k]
    if sel:
        print(agg(sel, "%d cell%s" % (k, "" if k == 1 else "s")))
extra = [(p, cs) for p, cs in done if len(cs) >= 10]
if extra:
    print(agg(extra, "10+ cells"))

print("\n" + BAR)
print("THE USER'S RANGE -- 2 through 6 cells, and the ends for contrast")
print(BAR)
for lo, hi, lab in ((1, 1, "exactly 1"), (2, 2, "exactly 2"), (3, 3, "exactly 3"),
                    (4, 4, "exactly 4"), (5, 5, "exactly 5"), (6, 6, "exactly 6"),
                    (7, 99, "7 or more")):
    print(agg([(p, cs) for p, cs in done if lo <= len(cs) <= hi], lab))
print()
for lo, hi, lab in ((2, 6, "2-6 cells"), (2, 3, "2-3 cells"), (4, 6, "4-6 cells")):
    print(agg([(p, cs) for p, cs in done if lo <= len(cs) <= hi], lab))

print("\n" + BAR)
print("IS THE COUNT JUST A PRICE PROXY? median price per bucket")
print(BAR)
for k in range(1, 10):
    sel = [p["odds"] for p, cs in done if len(cs) == k]
    if sel:
        sel.sort()
        print("   %-10s n=%-4d median %+5d   range %+d .. %+d"
              % ("%d cells" % k, len(sel), sel[len(sel) // 2], sel[0], sel[-1]))

print("\n" + BAR)
print("AND CONTROLLED FOR PRICE -- inside +100..+150 only, where most volume sits")
print(BAR)
for lo, hi, lab in ((1, 2, "1-2 cells"), (3, 4, "3-4 cells"), (5, 99, "5+ cells")):
    print(agg([(p, cs) for p, cs in done
               if lo <= len(cs) <= hi and 100 <= p["odds"] <= 150], lab))
print("\n" + BAR)
