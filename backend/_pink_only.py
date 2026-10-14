"""WHAT IF ONLY THE PINK PICKS WERE TAKEN? (2026-10-14)

User: "If I faded all the green pinks and only took pink highlighted what would my hit rate, roi,
and profit be".

Two readings, both answered:
  1. PINK ONLY -- skip every non-pink row, bet only the pink ones. The natural reading.
  2. PINK + FADE THE REST -- bet the pink dogs AND back the favourite on every non-pink dog pick,
     in case "faded" meant literally betting the other side. The favourite's price comes from the
     frozen log, so it is the real paired price and not a de-vigged estimate.

Same basis as the tab throughout: deduped one row per dog, <= +300, gender-gated, no ITF men,
forward only, $25 flat. The pink rule is the one that shipped:
    +100..+150  any MC2-family cell
    +150..+200  MC2 6pt / TAKE or FADE FORM only
    +200..+250  the c75 family
"""
import math

import pandas as pd

import tennis_log

CELLS = ["mc2_dog6_all", "mc2_take_dog_all", "mc3_take_dog_all", "mc5_take_dog_all",
         "pf_c75_dis_dog", "split64_fade_dog", "mc_c75_dog", "mc2_dog_flip",
         "c75_dog_100plus", "returner_dog_w", "allround_dog_w", "cc75_nod_dog",
         "cr1_stardog", "cc75_dog", "pink_fadeb_dog_m", "pink_mc2_dog",
         "tier_avoid_dog", "dma_dog", "mc2_dog_band", "cgray_dog_late",
         "ovl_dog", "fight_mc4_dog"]
PINK_RULES = [
    (100, 150, {"pink_mc2_dog", "mc2_dog_band", "mc2_take_dog_all", "mc2_dog6_all",
                "mc2_dog_flip"}),
    (150, 200, {"mc2_dog6_all", "mc2_take_dog_all", "pf_c75_dis_dog"}),
    (200, 250, {"mc_c75_dog", "c75_dog_100plus", "cc75_dog", "cc75_nod_dog"}),
]
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


def pink_of(p, keys):
    od = p.get("odds")
    if od is None:
        return None
    for lo, hi, cs in PINK_RULES:
        if lo <= od <= hi and (keys & cs):
            return "%d-%d" % (lo, hi)
    return None


# the favourite's real price, for the fade variant
log = pd.read_parquet(tennis_log.LOG_PATH)
log["_d"] = log["date"].astype(str).str[:10]
favp = {}
for _, r in log.iterrows():
    for a, b, oa in ((r.get("player_1"), r.get("player_2"), r.get("p2_odds")),
                     (r.get("player_2"), r.get("player_1"), r.get("p1_odds"))):
        favp[(r["_d"], str(a), str(b))] = oa      # price of the OPPONENT of a

done, pend = [], 0
for (d, pick, opp), (p, keys) in rows.items():
    p["_pink"] = pink_of(p, keys)
    p["_favod"] = favp.get((d, str(pick), str(opp)))
    if p.get("won") is None:
        pend += 1
        continue
    done.append(p)

print("deduped settled dog picks: %d  (plus %d pending)" % (len(done), pend))


def rep(ps, lab, side="dog"):
    """side='dog' bets the listed dog; side='fav' backs the favourite instead."""
    n = len(ps)
    if not n:
        return "   %-30s n=0" % lab
    if side == "dog":
        w = sum(1 for p in ps if p["won"])
        prof = sum((p.get("pnl") or 0) for p in ps)
    else:
        ok = [p for p in ps if p.get("_favod") is not None and not pd.isna(p.get("_favod"))]
        n = len(ok)
        if not n:
            return "   %-30s n=0 (no paired price)" % lab
        w = sum(1 for p in ok if not p["won"])
        prof = 0.0
        for p in ok:
            fo = float(p["_favod"])
            dec = 1 + fo / 100.0 if fo > 0 else 1 + 100.0 / abs(fo)
            prof += 25.0 * (dec - 1.0) if not p["won"] else -25.0
    roi = 100 * prof / (25.0 * n)
    r = roi / 100
    t = None
    if w:
        g = (r * n + (n - w)) / w
        v = (w * g * g + (n - w)) / n - r * r
        if v > 0:
            t = r / (math.sqrt(v) / math.sqrt(n))
    return ("   %-30s n=%-4d %8s  hit %5.1f%%  ROI %+7.2f%%  profit $%+9.2f%s"
            % (lab, n, "%d-%d" % (w, n - w), 100 * w / n, roi, prof,
               "  t %5.2f" % t if t is not None else ""))


pink = [p for p in done if p["_pink"]]
nonpink = [p for p in done if not p["_pink"]]

BAR = "=" * 110
print("\n" + BAR)
print("1. PINK ONLY -- what the user asked for")
print(BAR)
print(rep(pink, "PINK ONLY"))
for lo, hi, _ in PINK_RULES:
    lab = "%d-%d" % (lo, hi)
    print(rep([p for p in pink if p["_pink"] == lab], "   band +%s" % lab))
print()
print(rep(nonpink, "the non-pink rows (skipped)"))
print(rep(done, "EVERYTHING (today's tab)"))

print("\n" + BAR)
print("2. PINK TAKEN + NON-PINK FADED -- if 'faded' meant backing the favourite")
print(BAR)
print(rep(nonpink, "fade the non-pink dogs", side="fav"))
np_ok = [p for p in nonpink if p.get("_favod") is not None and not pd.isna(p.get("_favod"))]
pk_prof = sum((p.get("pnl") or 0) for p in pink)
fd_prof = 0.0
for p in np_ok:
    fo = float(p["_favod"])
    dec = 1 + fo / 100.0 if fo > 0 else 1 + 100.0 / abs(fo)
    fd_prof += 25.0 * (dec - 1.0) if not p["won"] else -25.0
tot_n = len(pink) + len(np_ok)
print("   %-30s n=%-4d %8s  %14s  ROI %+7.2f%%  profit $%+9.2f"
      % ("COMBINED pink + faded", tot_n, "", "",
         100 * (pk_prof + fd_prof) / (25.0 * tot_n), pk_prof + fd_prof))

print("\n" + BAR)
print("3. PINK ONLY, by gender and league")
print(BAR)
for g, glab in (("m", "men"), ("w", "women")):
    print(rep([p for p in pink if gof(p) == g], glab))
for lg in sorted({str(p.get("league")) for p in pink}):
    print(rep([p for p in pink if str(p.get("league")) == lg], "   %s" % lg))

print("\n" + BAR)
print("4. PINK ONLY, by day")
print(BAR)
for d in sorted({p["date"] for p in pink}):
    print(rep([p for p in pink if p["date"] == d], d))
print("\n" + BAR)
