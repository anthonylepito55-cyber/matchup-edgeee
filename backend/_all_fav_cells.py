"""EVERY FAVOURITE CELL ON THE $25 TAB (2026-10-15)

User: "no check every single cell for favorites on the $25 bet tab".

The whole favourite side, nothing filtered out: every lane the tab scores, every price band, both
genders, every league. Printed complete rather than thresholded, so the thin cells are visible AS
thin rather than silently dropped -- with n and t beside every ROI, because on this tab a 6-bet
cell at +40% and a 60-bet cell at +4% look alike in a ROI column and are not alike at all.

Scale first, because it frames everything: the tab is a DOG board. Across all lanes there are
~3,610 dog picks and ~134 favourite picks. Only mc2_fav4_m / mc2_fav4_w / conflict_gold_fav are
favourite lanes by design; everywhere else a favourite pick is incidental -- the lane's rule
happened to land on the market favourite. So most cells below are single digits and cannot be read
as anything. That is the answer to the question as much as any ROI is.

Band assignment is FIRST MATCH, one band per pick, as the board's bandOf does it -- independent
lo<=odds<=hi tests double-count every round number and that bug flipped a cell's sign on
2026-10-14.

Prior worth holding while reading: all 13 heads measured negative on favourites in the live log
(-5.0% to -9.1%), and seven favourite cells have now failed or faded forward.

Run: ./venv/bin/python _all_fav_cells.py
"""
import json
import math
import re
import urllib.request
from collections import defaultdict

req = urllib.request.Request("http://127.0.0.1/api/tennis/track-record",
                             headers={"X-Dashboard-Password": "freezeray23"})
st = (json.load(urllib.request.urlopen(req, timeout=240)).get("ab25") or {}).get("study") or {}

BANDS = [(-150, -100, "-100..-150"), (-200, -150, "-150..-200"), (-250, -200, "-200..-250"),
         (-300, -250, "-250..-300"), (-400, -300, "-300..-400"), (-100000, -400, "-400+")]
BNAMES = [b[2] for b in BANDS]
isw = lambda lg: bool(re.search(r"wta|itf_women", str(lg or ""), re.I))


def band_of(od):
    if od is None or od >= 0:
        return None
    for lo, hi, nm in BANDS:
        if lo <= od <= hi:
            return nm
    return None


def stat(ps):
    done = [p for p in ps if p.get("won") is not None]
    if not done:
        return None
    n, w = len(done), sum(1 for p in done if p["won"])
    pl = sum(p.get("pnl") or 0 for p in done)
    r = pl / (25.0 * n)
    t = None
    if 0 < w < n:
        g = (r * n + (n - w)) / w
        v = (w * g * g + (n - w)) / n - r * r
        if v > 0:
            t = r / (math.sqrt(v) / math.sqrt(n))
    return {"n": n, "w": w, "pl": pl, "roi": 100 * r, "t": t, "pend": len(ps) - n}


def fmt(s):
    return ("%7s n=%-4d hit %5.1f%% ROI %+8.2f%% $%+7.0f t %s"
            % ("%d-%d" % (s["w"], s["n"] - s["w"]), s["n"], 100 * s["w"] / s["n"],
               s["roi"], s["pl"], ("%5.2f" % s["t"]) if s["t"] is not None else "   -"))


LANES = sorted(k for k, v in st.items() if isinstance(v, dict) and v.get("picks") is not None)
BAR = "=" * 108

# ------------------------------------------------------------------ scale
allfav = []
for k in LANES:
    for p in (st[k].get("picks") or []):
        if p.get("odds") is not None and p["odds"] < 0:
            allfav.append((k, p))
alldog = sum(1 for k in LANES for p in (st[k].get("picks") or [])
             if p.get("odds") is not None and p["odds"] > 0)
print("lanes on the tab: %d" % len(LANES))
print("picks by side:  dog %d   FAVOURITE %d   (settled favourites: %d)"
      % (alldog, len(allfav), sum(1 for _, p in allfav if p.get("won") is not None)))

# ------------------------------------------------------------------ deduped baseline
seen = {}
for k, p in allfav:
    seen[(p.get("date"), p.get("pick"), p.get("opp"))] = p
U = list(seen.values())
print("\n" + BAR)
print("BASELINE -- every favourite pick on the tab, deduped to one row per match (n=%d)" % len(U))
print(BAR)
for lab, sub in (("ALL", U), ("men", [p for p in U if not isw(p.get("league"))]),
                 ("women", [p for p in U if isw(p.get("league"))])):
    s = stat(sub)
    print("   %-8s %s" % (lab, fmt(s) if s else "no settles"))
print("\n   by band (deduped, all leagues):")
for nm in BNAMES:
    s = stat([p for p in U if band_of(p["odds"]) == nm])
    print("      %-12s %s" % (nm, fmt(s) if s else "no settles"))
print("\n   by band x gender:")
for nm in BNAMES:
    for gl, f in (("men  ", lambda p: not isw(p.get("league"))),
                  ("women", lambda p: isw(p.get("league")))):
        s = stat([p for p in U if band_of(p["odds"]) == nm and f(p)])
        if s:
            print("      %-12s %s  %s" % (nm, gl, fmt(s)))
print("\n   by league:")
for lg in sorted({str(p.get("league") or "?").lower() for p in U}):
    s = stat([p for p in U if str(p.get("league") or "?").lower() == lg])
    if s:
        print("      %-16s %s" % (lg, fmt(s)))

# ------------------------------------------------------------------ every cell
rows = []
for k in LANES:
    fav = [p for p in (st[k].get("picks") or []) if p.get("odds") is not None and p["odds"] < 0]
    if not fav:
        continue
    for gl, f in (("ALL", lambda p: True), ("M", lambda p: not isw(p.get("league"))),
                  ("W", lambda p: isw(p.get("league")))):
        g = [p for p in fav if f(p)]
        s = stat(g)
        if s:
            rows.append((k, gl, "ALL", s))
        for nm in BNAMES:
            s = stat([p for p in g if band_of(p["odds"]) == nm])
            if s:
                rows.append((k, gl, nm, s))

print("\n" + BAR)
print("EVERY LANE x GENDER x BAND ON THE FAVOURITE SIDE -- %d cells, best ROI first" % len(rows))
print(BAR)
print("   %-24s %-4s %-12s %7s %5s %9s %8s %6s" %
      ("lane", "g", "band", "W-L", "n", "ROI", "profit", "t"))
rows.sort(key=lambda r: -r[3]["roi"])
for k, gl, nm, s in rows:
    print("   %-24s %-4s %-12s %7s %5d %+8.2f%% %+8.0f %6s"
          % (k[:24], gl, nm, "%d-%d" % (s["w"], s["n"] - s["w"]), s["n"], s["roi"], s["pl"],
             ("%.2f" % s["t"]) if s["t"] is not None else "-"))

pos = [r for r in rows if r[3]["roi"] > 0]
print("\n" + BAR)
print("EVERY POSITIVE FAVOURITE CELL, AT ANY SAMPLE SIZE  (%d of %d)" % (len(pos), len(rows)))
print(BAR)
for k, gl, nm, s in pos:
    tag = ("READABLE" if s["n"] >= 25 else ("thin" if s["n"] >= 10 else "UNREADABLE"))
    print("   %-10s %-24s %-4s %-12s %s" % (tag, k[:24], gl, nm, fmt(s)))
print("\n   positive AND n>=25: %d" % sum(1 for r in pos if r[3]["n"] >= 25))
print("   positive AND n>=25 AND t>=2: %d"
      % sum(1 for r in pos if r[3]["n"] >= 25 and (r[3]["t"] or 0) >= 2))
print(BAR)
