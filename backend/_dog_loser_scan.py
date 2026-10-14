"""WHICH DOG PICKS LOSE MORE THAN THEIR PRICE IMPLIES? a veto scan (2026-10-14).

User: "Is there anyway to see if we can track losing dogs like dog picks that lose".

THE TRAP THIS AVOIDS. Dogs lose most of the time by construction -- the tab's picks hit 46% at a
median +136, so "what do the losers look like" would mostly reproduce the base rate and find
nothing. The question that pays is narrower: are there SUBSETS where the dog loses more often
than its own price needs, i.e. negative-EV slices worth vetoing.

So every slice is scored against its own break-even at its own median price, not against a flat
50%, and the output is ROI (which already nets the price out) rather than hit rate.

THE OTHER TRAP, stated before the results rather than after. This scans ~60 slices over ~480
shared bets. At p<0.05 you expect ABOUT THREE to look significantly negative by chance, and the
same data already produced 4 of 104 dog cells clearing t=2 which is exactly the chance rate. So
the output below is a CANDIDATE LIST, and a slice only deserves action if it (a) clears |t| ~2,
(b) has a mechanism you can state, and (c) survives being split in half. The script reports the
expected false-positive count alongside the hits so the comparison is unavoidable.

Same basis as the tab: deduped one row per dog, <= +300, gender-gated, no ITF men, forward only,
$25 flat.
"""
import math
from collections import defaultdict

import pandas as pd

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
            rows[key] = [dict(p), set()]
        rows[key][1].add(k)

# join the frozen log for fields the pick record does not carry
log = pd.read_parquet(tennis_log.LOG_PATH)
log["_d"] = log["date"].astype(str).str[:10]
idx = {}
for _, r in log.iterrows():
    idx[(r["_d"], str(r.get("player_1")), str(r.get("player_2")))] = r
    idx[(r["_d"], str(r.get("player_2")), str(r.get("player_1")))] = r

recs = []
for (d, pick, opp), (p, cs) in rows.items():
    if p.get("won") is None:
        continue
    r = idx.get((d, str(pick), str(opp)))
    p["_cells"] = len(cs)
    p["_cellset"] = cs
    p["_g"] = gof(p)
    rg = (lambda k: (r.get(k) if r is not None else None))
    p["_round"] = str(rg("round") or "?")
    p["_surf"] = str(p.get("surface") or rg("surface") or "?")
    _svv = rg("surface_verified")
    p["_sv"] = (None if _svv is None or pd.isna(_svv) else bool(_svv))
    try:
        p["_hour"] = int(str(p.get("start") or "")[11:13])
    except ValueError:
        p["_hour"] = None
    recs.append(p)

print("deduped settled dog picks: %d" % len(recs))


def stat(ps):
    n = len(ps)
    if not n:
        return None
    w = sum(1 for p in ps if p["won"])
    prof = sum((p.get("pnl") or 0) for p in ps)
    roi = 100 * prof / (25.0 * n)
    odds = sorted(p["odds"] for p in ps)
    med = odds[n // 2]
    r = roi / 100
    t = None
    if w:
        g = (r * n + (n - w)) / w
        v = (w * g * g + (n - w)) / n - r * r
        if v > 0:
            t = r / (math.sqrt(v) / math.sqrt(n))
    return {"n": n, "w": w, "roi": roi, "prof": prof, "med": med, "t": t,
            "hit": 100 * w / n, "be": 100.0 / (1 + med / 100.0)}


SLICES = []
def add(lab, f):
    SLICES.append((lab, f))


for lg in sorted({str(p.get("league")) for p in recs}):
    add("league = %s" % lg, lambda p, lg=lg: str(p.get("league")) == lg)
for sf in sorted({p["_surf"] for p in recs}):
    add("surface = %s" % sf, lambda p, sf=sf: p["_surf"] == sf)
for g in ("m", "w"):
    add("gender = %s" % g, lambda p, g=g: p["_g"] == g)
for lo, hi in ((100, 150), (150, 200), (200, 250), (250, 300)):
    add("price %d-%d" % (lo, hi), lambda p, lo=lo, hi=hi: lo <= p["odds"] <= hi)
for k in range(1, 8):
    add("%d cells" % k, lambda p, k=k: p["_cells"] == k)
add("7+ cells", lambda p: p["_cells"] >= 7)
for rd in sorted({p["_round"] for p in recs}):
    if sum(1 for p in recs if p["_round"] == rd) >= 15:
        add("round = %s" % rd[:22], lambda p, rd=rd: p["_round"] == rd)
add("surface UNVERIFIED", lambda p: p["_sv"] is False)
for k in CELLS:
    if sum(1 for p in recs if k in p["_cellset"]) >= 20:
        add("cell fired: %s" % k, lambda p, k=k: k in p["_cellset"])
# gender x band, the interaction that already showed up
for g in ("m", "w"):
    for lo, hi in ((100, 150), (150, 200), (200, 250), (250, 300)):
        add("%s %d-%d" % (g, lo, hi),
            lambda p, g=g, lo=lo, hi=hi: p["_g"] == g and lo <= p["odds"] <= hi)

BAR = "=" * 118
base = stat(recs)
print("\n" + BAR)
print("BASELINE -- every deduped dog pick on the tab")
print(BAR)
print("   n=%d  %d-%d  hit %.1f%% (needs %.1f%% at med %+d)  ROI %+.2f%%  $%+.2f  t %.2f"
      % (base["n"], base["w"], base["n"] - base["w"], base["hit"], base["be"], base["med"],
         base["roi"], base["prof"], base["t"]))

out = []
for lab, f in SLICES:
    s = stat([p for p in recs if f(p)])
    if s and s["n"] >= 15:
        out.append((lab, s))

print("\n" + BAR)
print("LOSING SLICES -- worst ROI first. 'needs' is break-even at that slice's median price.")
print(BAR)
print("   %-26s %5s %8s %7s %9s %9s %10s %6s" % ("slice", "n", "W-L", "hit", "needs", "ROI", "profit", "t"))
neg = [(lab, s) for lab, s in out if s["roi"] < 0]
for lab, s in sorted(neg, key=lambda x: x[1]["roi"]):
    print("   %-26s %5d %8s %6.1f%% %8.1f%% %+8.2f%% %+10.2f %6s"
          % (lab, s["n"], "%d-%d" % (s["w"], s["n"] - s["w"]), s["hit"], s["be"],
             s["roi"], s["prof"], ("%.2f" % s["t"]) if s["t"] is not None else "-"))

sig = [(lab, s) for lab, s in neg if s["t"] is not None and s["t"] <= -1.6]
print("\n" + BAR)
print("MULTIPLE-COMPARISON CHECK -- the number that decides whether any of this is real")
print(BAR)
print("   slices tested (n>=15):            %d" % len(out))
print("   negative-ROI slices:              %d" % len(neg))
print("   negative AND |t| >= 1.6:          %d" % len(sig))
print("   expected by chance at p<0.05:     ~%.1f" % (0.05 * len(out)))
print("   expected NEGATIVE-side by chance: ~%.1f" % (0.025 * len(out)))
if sig:
    print()
    print("   the ones clearing |t| >= 1.6:")
    for lab, s in sorted(sig, key=lambda x: x[1]["t"]):
        print("      %-26s n=%-4d ROI %+7.2f%%  t %5.2f" % (lab, s["n"], s["roi"], s["t"]))
print()
print("   READ: if the count in row 3 is at or below the count in row 5, this scan has found")
print("   nothing that chance would not also produce, and no slice should be vetoed on it.")
print("\n" + BAR)
