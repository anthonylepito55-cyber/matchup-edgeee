"""EVERY DOG CELL x EVERY PRICE BAND (2026-10-14).

User: "check how each and every diff dog signal does for each +100 and so on".

22 cells x 4 bands = 88 combinations over ~480 shared bets, so most buckets are small and a few
will look excellent purely by chance. At p<0.05 you expect ABOUT FOUR of 88 to clear |t| >= 2 with
no edge at all, and the same dataset already produced 4 of 104 cells clearing t=2, which is the
chance rate exactly. The script therefore prints the hit count next to the expected count, and
every bucket carries its n so a +80% on 6 bets cannot be mistaken for a finding.

Per-cell records here are the cell's OWN picks (not deduped against other cells) because the
question is how each signal performs -- but the tab's gates still apply: <= +300, no ITF men, and
the gender gate, so these match what the tab shows.
"""
import math

import tennis_log

CELLS = [
    ("MC2 6pt+ DOG", "mc2_dog6_all"),
    ("MC2 TAKE DOG (unstamped)", "mc2_take_dog_all"),
    ("MC3 TAKE DOG (unstamped)", "mc3_take_dog_all"),
    ("MC5 TAKE DOG (unstamped)", "mc5_take_dog_all"),
    ("FADE FORM dogs", "pf_c75_dis_dog"),
    ("6-4 SPLIT dogs", "split64_fade_dog"),
    ("c75 DOG FLIP", "mc_c75_dog"),
    ("MC2 DOG FLIP", "mc2_dog_flip"),
    ("c75 DOG +100up", "c75_dog_100plus"),
    ("RETURNER DOG (W)", "returner_dog_w"),
    ("ALL-ROUND DOG (W)", "allround_dog_w"),
    ("c50+c75 DOG no D", "cc75_nod_dog"),
    ("STAR DOG (resolver1)", "cr1_stardog"),
    ("c50+c75 DOG", "cc75_dog"),
    ("FADE-B DOG (M)", "pink_fadeb_dog_m"),
    ("MC2 DOG (pink)", "pink_mc2_dog"),
    ("TIER-AVOID dogs", "tier_avoid_dog"),
    ("D-MA DOG", "dma_dog"),
    ("MC2 DOG BAND", "mc2_dog_band"),
    ("C+GRAY DOG late", "cgray_dog_late"),
    ("OVERLAY DOG", "ovl_dog"),
    ("FIGHT MC4 DOG", "fight_mc4_dog"),
]
BANDS = [("+100-150", 100, 150), ("+150-200", 150, 200),
         ("+200-250", 200, 250), ("+250-300", 250, 300)]
MAX_AM = 300

st = (tennis_log.get_ab25_record() or {}).get("study") or {}
gof = lambda p: "w" if any(x in str(p.get("league", "")).lower()
                           for x in ("wta", "itf_women")) else "m"


def gok(c, g):
    d = (c or {}).get(g) or {}
    return True if not d.get("n") else (d.get("roi_pct") or 0) > 0


def stat(ps):
    n = len(ps)
    if not n:
        return None
    w = sum(1 for p in ps if p["won"])
    prof = sum((p.get("pnl") or 0) for p in ps)
    roi = 100 * prof / (25.0 * n)
    r = roi / 100
    t = None
    if w:
        odds = sorted(p["odds"] for p in ps)
        g = (r * n + (n - w)) / w
        v = (w * g * g + (n - w)) / n - r * r
        if v > 0:
            t = r / (math.sqrt(v) / math.sqrt(n))
    return {"n": n, "w": w, "roi": roi, "prof": prof, "t": t}


table, hits, tested = [], [], 0
for lab, key in CELLS:
    c = st.get(key) or {}
    ps = []
    for p in (c.get("picks") or []):
        od, lg = p.get("odds"), str(p.get("league") or "").lower()
        if od is None or od > MAX_AM or lg == "itf_men":
            continue
        if p.get("won") is None or not gok(c, gof(p)):
            continue
        ps.append(p)
    row = {"lab": lab, "key": key, "all": stat(ps), "bands": {}}
    for blab, lo, hi in BANDS:
        s = stat([p for p in ps if lo <= p["odds"] <= hi])
        row["bands"][blab] = s
        if s and s["n"] >= 10:
            tested += 1
            if s["t"] is not None and abs(s["t"]) >= 2.0:
                hits.append((lab, blab, s))
    table.append(row)

table = [r for r in table if r["all"]]
table.sort(key=lambda r: -(r["all"]["t"] if r["all"]["t"] is not None else -9))

BAR = "=" * 126
print(BAR)
print("EVERY DOG CELL x PRICE BAND -- n and ROI. <= +300, no ITF men, gender-gated, $25 flat")
print("   small n is the norm here: read a band only where n is double digits")
print(BAR)
hdr = "   %-26s %14s" % ("cell", "ALL BANDS")
for blab, _, _ in BANDS:
    hdr += " %16s" % blab
print(hdr)
for r in table:
    a = r["all"]
    line = "   %-26s %5d %+7.1f%%" % (r["lab"], a["n"], a["roi"])
    for blab, _, _ in BANDS:
        s = r["bands"][blab]
        line += "  %14s" % (("%3d %+7.1f%%" % (s["n"], s["roi"])) if s else "       -      ")
    print(line)

print("\n" + BAR)
print("BEST CELL x BAND BUCKETS at n>=15, ranked by t")
print(BAR)
flat = []
for r in table:
    for blab, _, _ in BANDS:
        s = r["bands"][blab]
        if s and s["n"] >= 15 and s["t"] is not None:
            flat.append((s["t"], r["lab"], blab, s))
for t, lab, blab, s in sorted(flat, reverse=True)[:14]:
    print("   %-26s %-9s n=%-4d %7s  ROI %+7.2f%%  $%+8.2f  t %5.2f"
          % (lab, blab, s["n"], "%d-%d" % (s["w"], s["n"] - s["w"]), s["roi"], s["prof"], t))

print("\n" + BAR)
print("WORST at n>=15")
print(BAR)
for t, lab, blab, s in sorted(flat)[:10]:
    print("   %-26s %-9s n=%-4d %7s  ROI %+7.2f%%  $%+8.2f  t %5.2f"
          % (lab, blab, s["n"], "%d-%d" % (s["w"], s["n"] - s["w"]), s["roi"], s["prof"], t))

print("\n" + BAR)
print("MULTIPLE-COMPARISON CHECK")
print(BAR)
print("   cell x band buckets tested (n>=10):   %d" % tested)
print("   clearing |t| >= 2.0:                  %d" % len(hits))
print("   expected by chance at p<0.05:         ~%.1f" % (0.05 * tested))
for lab, blab, s in sorted(hits, key=lambda x: -abs(x[2]["t"])):
    print("      %-26s %-9s n=%-4d ROI %+7.2f%%  t %5.2f" % (lab, blab, s["n"], s["roi"], s["t"]))
print()
print("   READ: if the hit count is at or near the expected count, the standouts in this matrix")
print("   are what chance produces and none of them is a cell x band finding on its own.")
print(BAR)
