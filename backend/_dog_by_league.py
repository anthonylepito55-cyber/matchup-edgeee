"""DOG ROI BY LEAGUE -- is any of ATP / WTA / ITF negative? (2026-10-14)

Computed on the SAME basis the Dog picks tab uses, so the numbers match what is on screen:
  * one row per dog, DEDUPED across cells -- the cells overlap so heavily that a single dog can
    carry nine badges, and counting it nine times would report a number nobody could have bet
  * nothing above +300
  * gender-gated: a cell's picks only count for a gender whose own dog ROI is positive
  * forward only (recon rows never enter a lane) and $25 flat

Reported per league and per league x gender, because every cell on this board has split by
gender and a league that is flat overall can still be one good half and one bad one.
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


def gender_of(p):
    lg = str(p.get("league") or "").lower()
    return "w" if ("wta" in lg or "itf_women" in lg) else "m"


def gender_ok(c, g):
    d = (c or {}).get(g) or {}
    if not d.get("n"):
        return True                       # no settles for this gender -> unknown, not negative
    return (d.get("roi_pct") or 0) > 0


# dedupe to one row per dog, exactly as the tab does
seen, picks = set(), []
for k in CELLS:
    c = st.get(k) or {}
    for p in (c.get("picks") or []):
        od = p.get("odds")
        if od is None or od > MAX_AM:
            continue
        if not gender_ok(c, gender_of(p)):
            continue
        key = (p.get("date"), p.get("pick"), p.get("opp"))
        if key in seen:
            continue
        seen.add(key)
        picks.append(p)

done = [p for p in picks if p.get("won") is not None]
print("deduped dog picks: %d  (settled %d, pending %d)" % (len(picks), len(done), len(picks) - len(done)))


def agg(ps, lab):
    n = len(ps)
    if not n:
        return "   %-22s n=0" % lab
    w = sum(1 for p in ps if p["won"])
    prof = sum(p.get("pnl") or 0 for p in ps)
    roi = 100 * prof / (25.0 * n)
    # per-bet sd from the implied average winning payout, so the t is comparable across bands
    r = roi / 100
    t = None
    if w:
        gain = (r * n + (n - w)) / w
        var = (w * gain * gain + (n - w)) / n - r * r
        if var > 0:
            t = r / (math.sqrt(var) / math.sqrt(n))
    return ("   %-22s n=%-4d %7s  ROI %+7.2f%%  profit $%+9.2f  hit %4.1f%%%s"
            % (lab, n, "%d-%d" % (w, n - w), roi, prof, 100 * w / n,
               "  t %.2f" % t if t is not None else ""))


BAR = "=" * 104
print("\n" + BAR)
print("BY LEAGUE -- same basis as the tab (deduped, <= +%d, gender-gated, $25 flat)" % MAX_AM)
print(BAR)
LG = [("ATP (tour)", lambda p: str(p.get("league")) == "atp"),
      ("WTA (tour)", lambda p: str(p.get("league")) == "wta"),
      ("ATP challenger", lambda p: "challenger" in str(p.get("league"))),
      ("ITF men", lambda p: str(p.get("league")) == "itf_men"),
      ("ITF women", lambda p: str(p.get("league")) == "itf_women")]
for lab, f in LG:
    print(agg([p for p in done if f(p)], lab))
print(agg(done, "ALL"))

print("\n" + BAR)
print("COLLAPSED the way the user asked -- ATP / WTA / ITF")
print(BAR)
for lab, f in (("ATP (incl. chall)", lambda p: str(p.get("league")).startswith("atp")),
               ("WTA", lambda p: str(p.get("league")) == "wta"),
               ("ITF (both)", lambda p: str(p.get("league")).startswith("itf"))):
    print(agg([p for p in done if f(p)], lab))

print("\n" + BAR)
print("AND BY PRICE BAND WITHIN EACH -- where a negative league is negative")
print(BAR)
for lab, f in (("ATP (incl. chall)", lambda p: str(p.get("league")).startswith("atp")),
               ("WTA", lambda p: str(p.get("league")) == "wta"),
               ("ITF (both)", lambda p: str(p.get("league")).startswith("itf"))):
    print("   %s" % lab)
    for blab, lo, hi in (("+100..+150", 100, 150), ("+150..+200", 150, 200),
                         ("+200..+250", 200, 250), ("+250..+300", 250, 300)):
        print(agg([p for p in done if f(p) and lo <= p["odds"] <= hi], "   " + blab))
print("\n" + BAR)
